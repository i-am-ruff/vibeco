"""Tests for StrategistCog: owner channel bridge, streaming, and owner escalation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest
from discord.ext import commands

from vcompany.bot.cogs.strategist import StrategistCog
from vcompany.strategist.decision_log import DecisionLogger


def _make_bot() -> MagicMock:
    """Create a mock VcoBot with loop and user."""
    bot = MagicMock(spec=commands.Bot)
    bot.loop = asyncio.get_event_loop()
    bot_user = MagicMock(spec=discord.User)
    bot_user.id = 999
    bot.user = bot_user
    return bot


def _make_message(
    *,
    content: str = "What should we prioritize?",
    author_id: int = 100,
    is_bot: bool = False,
    webhook_id: int | None = None,
    channel_name: str = "strategist",
    has_owner_role: bool = True,
    reference: discord.MessageReference | None = None,
) -> MagicMock:
    """Create a mock Discord message."""
    msg = MagicMock(spec=discord.Message)
    msg.content = content
    msg.webhook_id = webhook_id

    author = MagicMock(spec=discord.Member)
    author.id = author_id
    author.bot = is_bot

    # Role check
    if has_owner_role:
        role = MagicMock(spec=discord.Role)
        role.name = "vco-owner"
        author.roles = [role]
    else:
        author.roles = []

    msg.author = author

    channel = AsyncMock(spec=discord.TextChannel)
    channel.name = channel_name
    msg.channel = channel

    msg.reference = reference

    return msg


def _make_cog_with_conversation(bot: MagicMock | None = None) -> tuple[StrategistCog, AsyncMock]:
    """Create a StrategistCog with mocked conversation."""
    if bot is None:
        bot = _make_bot()
    cog = StrategistCog(bot)

    # Mock the conversation — send() now returns str directly
    conversation = AsyncMock()
    conversation.send = AsyncMock(return_value="Hello there friend")
    cog._conversation = conversation

    # Mock channel
    channel = AsyncMock(spec=discord.TextChannel)
    channel.name = "strategist"

    guild = MagicMock(spec=discord.Guild)
    guild.roles = []
    channel.guild = guild

    cog._strategist_channel = channel

    return cog, conversation


# --- Message filtering tests ---


@pytest.mark.asyncio
async def test_on_message_skips_webhook_messages() -> None:
    """on_message skips webhook messages."""
    cog, _ = _make_cog_with_conversation()
    msg = _make_message(webhook_id=12345)
    msg.channel = cog._strategist_channel

    await cog.on_message(msg)
    # Should not have sent any response (no channel.send call)
    cog._strategist_channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_message_skips_bot_messages() -> None:
    """on_message skips bot's own messages."""
    bot = _make_bot()
    cog, _ = _make_cog_with_conversation(bot)
    msg = _make_message(author_id=999)  # Same as bot user ID
    msg.channel = cog._strategist_channel

    await cog.on_message(msg)
    cog._strategist_channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_message_skips_wrong_channel() -> None:
    """on_message skips messages from non-strategist channels."""
    cog, _ = _make_cog_with_conversation()
    msg = _make_message(channel_name="general")

    await cog.on_message(msg)
    msg.channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_message_skips_non_owner() -> None:
    """on_message skips messages from users without vco-owner role."""
    cog, _ = _make_cog_with_conversation()
    msg = _make_message(has_owner_role=False)
    msg.channel = cog._strategist_channel

    await cog.on_message(msg)
    cog._strategist_channel.send.assert_not_awaited()


# --- Owner message forwarding tests ---


@pytest.mark.asyncio
async def test_owner_message_forwarded_to_conversation() -> None:
    """Owner message is forwarded to StrategistConversation.send()."""
    cog, conversation = _make_cog_with_conversation()
    msg = _make_message(content="What about the roadmap?")
    msg.channel = cog._strategist_channel

    # Track send calls
    sent_content = []
    original_send = conversation.send

    async def tracking_send(content: str):
        sent_content.append(content)
        return await original_send(content)

    conversation.send = tracking_send

    await cog.on_message(msg)
    assert "What about the roadmap?" in sent_content


# --- Response posting tests ---


@pytest.mark.asyncio
async def test_streaming_response_posted_to_channel() -> None:
    """Response is posted to channel after full reply received."""
    cog, _ = _make_cog_with_conversation()

    channel = AsyncMock(spec=discord.TextChannel)
    placeholder_msg = AsyncMock(spec=discord.Message)
    channel.send.return_value = placeholder_msg

    result = await cog._send_to_channel(channel, "test input")

    # Should have sent "Thinking..." placeholder
    channel.send.assert_awaited()
    first_send = channel.send.call_args_list[0]
    assert "Thinking" in str(first_send)

    # Should have edited with response
    assert placeholder_msg.edit.await_count >= 1
    assert result == "Hello there friend"


@pytest.mark.asyncio
async def test_long_response_handled() -> None:
    """Long responses (>2000 chars) are truncated with continuation."""
    cog, conversation = _make_cog_with_conversation()

    # Make conversation return a long response
    long_text = "A" * 2500
    conversation.send = AsyncMock(return_value=long_text)
    cog._conversation = conversation

    channel = AsyncMock(spec=discord.TextChannel)
    placeholder_msg = AsyncMock(spec=discord.Message)
    channel.send.return_value = placeholder_msg

    result = await cog._send_to_channel(channel, "test")

    # Full text returned
    assert len(result) == 2500
    # Placeholder message should have been edited with truncated text
    last_edit_call = placeholder_msg.edit.call_args
    edited_content = last_edit_call.kwargs.get("content", last_edit_call[1].get("content", ""))
    assert len(edited_content) <= 2000


# --- PM escalation tests ---


@pytest.mark.asyncio
async def test_handle_pm_escalation_formats_message() -> None:
    """PM escalation adds formatted message to conversation."""
    cog, conversation = _make_cog_with_conversation()

    sent_content = []

    async def tracking_send(content: str):
        sent_content.append(content)
        return "Use approach A."

    conversation.send = tracking_send

    result = await cog.handle_pm_escalation("agent-alpha", "Which framework?", 0.55)
    assert "[PM Escalation]" in sent_content[0]
    assert "agent-alpha" in sent_content[0]
    assert "Which framework?" in sent_content[0]
    assert result is not None


@pytest.mark.asyncio
async def test_handle_pm_escalation_returns_response() -> None:
    """Strategist response to escalation is returned for relay to agent."""
    cog, conversation = _make_cog_with_conversation()

    conversation.send = AsyncMock(return_value="Use REST for simplicity.")

    result = await cog.handle_pm_escalation("agent-alpha", "REST or GraphQL?", 0.75)
    assert result == "Use REST for simplicity."


# --- Sync callback tests ---


@pytest.mark.asyncio
async def test_make_sync_callbacks_returns_dict() -> None:
    """StrategistCog provides make_sync_callbacks() for PM escalation from sync context."""
    bot = _make_bot()
    cog, _ = _make_cog_with_conversation(bot)

    callbacks = cog.make_sync_callbacks()
    assert "on_pm_escalation" in callbacks
    assert "on_owner_escalation" in callbacks
    assert callable(callbacks["on_pm_escalation"])
    assert callable(callbacks["on_owner_escalation"])


# --- Owner escalation tests (D-07) ---


@pytest.mark.asyncio
async def test_post_owner_escalation_posts_mention() -> None:
    """post_owner_escalation posts @Owner mention in #strategist."""
    cog, _ = _make_cog_with_conversation()

    # Set up channel to return a sent message
    sent_msg = MagicMock(spec=discord.Message)
    sent_msg.id = 42
    cog._strategist_channel.send.return_value = sent_msg

    # Set up guild with owner role
    owner_role = MagicMock(spec=discord.Role)
    owner_role.name = "vco-owner"
    owner_role.mention = "<@&111>"
    cog._strategist_channel.guild.roles = [owner_role]

    # Run escalation in background and resolve immediately
    async def resolve_future():
        await asyncio.sleep(0.05)
        # Simulate owner reply
        if 42 in cog._pending_escalations:
            future = cog._pending_escalations[42]
            if not future.done():
                future.set_result("Do approach B.")

    task = asyncio.create_task(resolve_future())
    result = await cog.post_owner_escalation("agent-beta", "Big architecture question?", 0.3)
    await task

    # Check message was posted
    cog._strategist_channel.send.assert_awaited()
    call_content = cog._strategist_channel.send.call_args.kwargs.get(
        "content", cog._strategist_channel.send.call_args[0][0] if cog._strategist_channel.send.call_args[0] else ""
    )
    assert "<@&111>" in call_content
    assert "Strategic decision needed" in call_content
    assert result == "Do approach B."


@pytest.mark.asyncio
async def test_post_owner_escalation_waits_indefinitely() -> None:
    """post_owner_escalation waits indefinitely (no timeout) per D-07."""
    cog, _ = _make_cog_with_conversation()

    sent_msg = MagicMock(spec=discord.Message)
    sent_msg.id = 99
    cog._strategist_channel.send.return_value = sent_msg
    cog._strategist_channel.guild.roles = []

    # Resolve after a delay to prove it waits
    async def delayed_resolve():
        await asyncio.sleep(0.2)
        if 99 in cog._pending_escalations:
            cog._pending_escalations[99].set_result("Finally answered.")

    task = asyncio.create_task(delayed_resolve())
    result = await cog.post_owner_escalation("agent-gamma", "Hard question", 0.2)
    await task

    assert result == "Finally answered."


@pytest.mark.asyncio
async def test_owner_reply_resolves_pending_escalation() -> None:
    """Owner reply in #strategist after escalation resolves the pending future with reply content."""
    bot = _make_bot()
    cog, _ = _make_cog_with_conversation(bot)

    # Set up pending escalation
    future = bot.loop.create_future()
    cog._pending_escalations[42] = future

    # Simulate owner reply referencing escalation message
    ref = MagicMock(spec=discord.MessageReference)
    ref.message_id = 42
    msg = _make_message(content="Go with plan B.", reference=ref)
    msg.channel = cog._strategist_channel

    await cog.on_message(msg)

    assert future.done()
    assert future.result() == "Go with plan B."


@pytest.mark.asyncio
async def test_escalation_cleanup_on_reply() -> None:
    """Owner reply pops the entry from pending_escalations dict."""
    bot = _make_bot()
    cog, _ = _make_cog_with_conversation(bot)

    future = bot.loop.create_future()
    cog._pending_escalations[42] = future

    ref = MagicMock(spec=discord.MessageReference)
    ref.message_id = 42
    msg = _make_message(content="Answer here.", reference=ref)
    msg.channel = cog._strategist_channel

    await cog.on_message(msg)

    assert 42 not in cog._pending_escalations


@pytest.mark.asyncio
async def test_not_initialized_reply() -> None:
    """If conversation not initialized, reply with error message."""
    bot = _make_bot()
    cog = StrategistCog(bot)
    cog._strategist_channel = AsyncMock(spec=discord.TextChannel)
    cog._strategist_channel.name = "strategist"
    cog._conversation = None

    msg = _make_message()
    msg.channel = cog._strategist_channel
    msg.reply = AsyncMock()

    await cog.on_message(msg)
    msg.reply.assert_awaited_once()
    reply_text = msg.reply.call_args[0][0]
    assert "not initialized" in reply_text.lower()


@pytest.mark.asyncio
async def test_decision_logger_property() -> None:
    """StrategistCog exposes decision_logger property."""
    cog, _ = _make_cog_with_conversation()
    assert cog.decision_logger is None

    mock_logger = MagicMock(spec=DecisionLogger)
    cog._decision_logger = mock_logger
    assert cog.decision_logger is mock_logger
