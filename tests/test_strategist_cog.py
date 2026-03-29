"""Tests for StrategistCog: routing framework integration, escalation, and RuntimeAPI bridge."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from vcompany.bot.cogs.strategist import StrategistCog


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
    msg.mentions = []
    msg.attachments = []

    return msg


def _make_cog_with_runtime_api(bot: MagicMock | None = None) -> tuple[StrategistCog, AsyncMock]:
    """Create a StrategistCog with mocked RuntimeAPI on daemon."""
    if bot is None:
        bot = _make_bot()
    cog = StrategistCog(bot)

    # Mock daemon with RuntimeAPI
    runtime_api = AsyncMock()
    runtime_api.relay_strategist_message = AsyncMock()
    runtime_api.handle_pm_escalation = AsyncMock(return_value="Use approach A.")
    daemon = MagicMock()
    daemon.runtime_api = runtime_api
    bot._daemon = daemon

    # Mock channel
    channel = AsyncMock(spec=discord.TextChannel)
    channel.name = "strategist"
    guild = MagicMock(spec=discord.Guild)
    guild.roles = []
    channel.guild = guild
    cog._strategist_channel = channel

    return cog, runtime_api


# --- Routing framework integration tests ---


@pytest.mark.asyncio
async def test_strategist_ignores_pm_prefixed_reply() -> None:
    """Messages that are replies to [PM]-prefixed messages are NOT routed to Strategist."""
    bot = _make_bot()
    cog, runtime_api = _make_cog_with_runtime_api(bot)

    # Message is a reply
    ref = MagicMock(spec=discord.MessageReference)
    ref.message_id = 42
    msg = _make_message(content="Thanks for that", reference=ref)
    msg.channel = cog._strategist_channel

    # When fetch_message is called, return a [PM]-prefixed message
    replied_msg = MagicMock(spec=discord.Message)
    replied_msg.content = "[PM] Here is my answer to the question"
    msg.channel.fetch_message = AsyncMock(return_value=replied_msg)

    await cog.on_message(msg)

    # RuntimeAPI should NOT have been called
    runtime_api.relay_strategist_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_strategist_processes_reply_to_own_message() -> None:
    """Messages replying to Strategist's own (no-prefix) messages ARE routed to Strategist."""
    bot = _make_bot()
    cog, runtime_api = _make_cog_with_runtime_api(bot)

    ref = MagicMock(spec=discord.MessageReference)
    ref.message_id = 42
    msg = _make_message(content="Tell me more about that", reference=ref)
    msg.channel = cog._strategist_channel

    # Replied-to message has no entity prefix (Strategist speaks without prefix per D-05)
    replied_msg = MagicMock(spec=discord.Message)
    replied_msg.content = "I think we should focus on the API layer first"
    msg.channel.fetch_message = AsyncMock(return_value=replied_msg)

    await cog.on_message(msg)

    # RuntimeAPI relay should have been called
    runtime_api.relay_strategist_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_strategist_processes_unaddressed_in_strategist_channel() -> None:
    """Unaddressed messages in #strategist route to Strategist (channel default)."""
    bot = _make_bot()
    cog, runtime_api = _make_cog_with_runtime_api(bot)

    msg = _make_message(content="What about the roadmap?")
    msg.channel = cog._strategist_channel
    msg.channel.name = "strategist"
    msg.channel.fetch_message = AsyncMock()  # Won't be called (no reference)

    await cog.on_message(msg)

    runtime_api.relay_strategist_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_message_not_found_graceful() -> None:
    """If replied-to message is deleted (NotFound), routing proceeds without crash."""
    bot = _make_bot()
    cog, runtime_api = _make_cog_with_runtime_api(bot)

    ref = MagicMock(spec=discord.MessageReference)
    ref.message_id = 42
    msg = _make_message(content="Follow up on that", reference=ref)
    msg.channel = cog._strategist_channel
    msg.channel.name = "strategist"

    # fetch_message raises NotFound
    http_response = MagicMock()
    http_response.status = 404
    msg.channel.fetch_message = AsyncMock(
        side_effect=discord.NotFound(http_response, "Unknown Message")
    )

    # Should not crash -- routes with replied_to_content=None
    # With None content and a reply, route_message defaults to STRATEGIST
    await cog.on_message(msg)

    runtime_api.relay_strategist_message.assert_awaited_once()


# --- Owner escalation with channel parameter ---


@pytest.mark.asyncio
async def test_post_owner_escalation_uses_channel_param() -> None:
    """post_owner_escalation with channel= sends to that channel, not #strategist."""
    bot = _make_bot()
    cog, _ = _make_cog_with_runtime_api(bot)

    # Create a separate agent channel
    agent_channel = AsyncMock(spec=discord.TextChannel)
    agent_channel.name = "agent-alpha"
    agent_guild = MagicMock(spec=discord.Guild)
    agent_guild.roles = []
    agent_channel.guild = agent_guild

    sent_msg = MagicMock(spec=discord.Message)
    sent_msg.id = 77
    agent_channel.send.return_value = sent_msg

    # Resolve the future immediately
    async def resolve_future():
        await asyncio.sleep(0.05)
        if 77 in cog._pending_escalations:
            future = cog._pending_escalations[77]
            if not future.done():
                future.set_result("Use approach C.")

    task = asyncio.create_task(resolve_future())
    result = await cog.post_owner_escalation(
        "agent-alpha", "Architecture question?", 0.3, channel=agent_channel
    )
    await task

    # Message sent to agent_channel, not _strategist_channel
    agent_channel.send.assert_awaited_once()
    cog._strategist_channel.send.assert_not_awaited()
    assert result == "Use approach C."


@pytest.mark.asyncio
async def test_pending_escalation_resolved_on_reply() -> None:
    """Owner reply to escalation message resolves the pending future."""
    bot = _make_bot()
    cog, _ = _make_cog_with_runtime_api(bot)

    # Set up pending escalation
    future = bot.loop.create_future()
    cog._pending_escalations[42] = future

    # Simulate owner reply referencing escalation message
    ref = MagicMock(spec=discord.MessageReference)
    ref.message_id = 42
    msg = _make_message(content="Go with plan B.", reference=ref)
    msg.channel = cog._strategist_channel

    # fetch_message returns the escalation message (non-PM prefix)
    replied_msg = MagicMock(spec=discord.Message)
    replied_msg.content = "@Owner -- Strategic decision needed..."
    msg.channel.fetch_message = AsyncMock(return_value=replied_msg)

    await cog.on_message(msg)

    assert future.done()
    assert future.result() == "Go with plan B."
    assert 42 not in cog._pending_escalations


# --- Preserved existing behavior tests ---


@pytest.mark.asyncio
async def test_on_message_skips_webhook_messages() -> None:
    """on_message skips webhook messages (via routing IGNORE)."""
    cog, runtime_api = _make_cog_with_runtime_api()
    msg = _make_message(webhook_id=12345)
    msg.channel = cog._strategist_channel

    await cog.on_message(msg)
    runtime_api.relay_strategist_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_message_skips_bot_messages() -> None:
    """on_message skips bot's own messages (via routing IGNORE)."""
    bot = _make_bot()
    cog, runtime_api = _make_cog_with_runtime_api(bot)
    msg = _make_message(author_id=999, is_bot=True)
    msg.channel = cog._strategist_channel
    msg.channel.name = "strategist"

    await cog.on_message(msg)
    runtime_api.relay_strategist_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_message_skips_non_owner() -> None:
    """on_message skips messages from users without vco-owner role."""
    cog, runtime_api = _make_cog_with_runtime_api()
    msg = _make_message(has_owner_role=False)
    msg.channel = cog._strategist_channel
    msg.channel.name = "strategist"

    await cog.on_message(msg)
    runtime_api.relay_strategist_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_not_initialized_reply() -> None:
    """If RuntimeAPI not available, reply with error message."""
    bot = _make_bot()
    bot._daemon = None  # No daemon = no RuntimeAPI
    cog = StrategistCog(bot)
    cog._strategist_channel = AsyncMock(spec=discord.TextChannel)
    cog._strategist_channel.name = "strategist"

    msg = _make_message()
    msg.channel = cog._strategist_channel
    msg.channel.name = "strategist"
    msg.reply = AsyncMock()
    msg.channel.fetch_message = AsyncMock()

    await cog.on_message(msg)
    msg.reply.assert_awaited_once()
    reply_text = msg.reply.call_args[0][0]
    assert "not initialized" in reply_text.lower()


# --- PM escalation tests ---


@pytest.mark.asyncio
async def test_handle_pm_escalation_delegates_to_runtime_api() -> None:
    """PM escalation delegates to RuntimeAPI."""
    cog, runtime_api = _make_cog_with_runtime_api()
    runtime_api.handle_pm_escalation = AsyncMock(return_value="Use approach A.")

    result = await cog.handle_pm_escalation("agent-alpha", "Which framework?", 0.55)
    runtime_api.handle_pm_escalation.assert_awaited_once_with(
        "agent-alpha", "Which framework?", 0.55
    )
    assert result == "Use approach A."


@pytest.mark.asyncio
async def test_make_sync_callbacks_returns_dict() -> None:
    """StrategistCog provides make_sync_callbacks()."""
    bot = _make_bot()
    cog, _ = _make_cog_with_runtime_api(bot)

    callbacks = cog.make_sync_callbacks()
    assert "on_pm_escalation" in callbacks
    assert "on_owner_escalation" in callbacks
    assert callable(callbacks["on_pm_escalation"])
    assert callable(callbacks["on_owner_escalation"])


# --- Dead code removal verification ---


def test_no_cmd_tags_in_cog() -> None:
    """Verify [CMD:...] action tag code is fully removed from strategist cog."""
    import inspect
    source = inspect.getsource(StrategistCog)
    assert "[CMD:" not in source
    assert "_execute_actions" not in source
    assert "_CMD_PATTERN" not in source
