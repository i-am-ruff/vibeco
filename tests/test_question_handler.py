"""Tests for QuestionHandlerCog: agent-channel question detection and Discord reply-based answers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest


@pytest.fixture
def mock_bot():
    """Create a mock VcoBot with required attributes."""
    bot = MagicMock()
    bot.is_closed.return_value = False
    bot._ready_flag = True
    bot.is_bot_ready = True
    bot._guild_id = 123456
    bot.loop = asyncio.new_event_loop()
    # Bot user ID matches the message author for question embeds
    bot_user = MagicMock()
    bot_user.id = 999
    bot.user = bot_user
    yield bot
    bot.loop.close()


def _make_embed(
    title: str = "Question from agent-1",
    footer_text: str = "Request: abc-123",
    description: str = "What should I do?",
    fields: list[tuple[str, str]] | None = None,
) -> discord.Embed:
    """Create a mock embed mimicking ask_discord.py output."""
    embed = discord.Embed(title=title, description=description)
    embed.set_footer(text=footer_text)
    if fields is None:
        fields = [("Option A", "Do X"), ("Option B", "Do Y")]
    for name, value in fields:
        embed.add_field(name=name, value=value)
    return embed


def _make_message(
    *,
    author_id: int = 999,
    is_bot: bool = True,
    channel_name: str = "agent-1",
    embeds: list[discord.Embed] | None = None,
    webhook_id: int | None = None,
) -> MagicMock:
    """Create a mock discord.Message for on_message tests."""
    msg = MagicMock(spec=discord.Message)
    msg.webhook_id = webhook_id
    msg.author = MagicMock()
    msg.author.id = author_id
    msg.author.bot = is_bot
    msg.channel = AsyncMock(spec=discord.TextChannel)
    msg.channel.name = channel_name
    msg.channel.send = AsyncMock()
    msg.embeds = embeds if embeds is not None else [_make_embed()]
    msg.reply = AsyncMock()
    msg.reference = None
    return msg


class TestDetectsQuestionEmbed:
    """QuestionHandlerCog detects question embeds in agent channels."""

    @pytest.mark.asyncio
    async def test_detects_question_embed_in_agent_channel(self, mock_bot):
        """Bot-posted question embed in #agent-{id} triggers PM evaluation."""
        from vcompany.bot.cogs.question_handler import QuestionHandlerCog

        cog = QuestionHandlerCog(mock_bot)

        # Mock PM
        pm = AsyncMock()
        pm_decision = MagicMock()
        pm_decision.answer = "Use approach A"
        pm_decision.confidence = MagicMock()
        pm_decision.confidence.level = "HIGH"
        pm_decision.confidence.score = 0.95
        pm_decision.note = ""
        pm.evaluate_question = AsyncMock(return_value=pm_decision)
        cog.set_pm(pm)

        msg = _make_message(author_id=999)

        await cog.on_message(msg)

        pm.evaluate_question.assert_awaited_once()
        msg.reply.assert_awaited_once()
        reply_text = msg.reply.call_args[0][0]
        assert "[PM]" in reply_text
        assert "Use approach A" in reply_text

    @pytest.mark.asyncio
    async def test_ignores_non_question_bot_messages(self, mock_bot):
        """Bot messages without question embeds are ignored."""
        from vcompany.bot.cogs.question_handler import QuestionHandlerCog

        cog = QuestionHandlerCog(mock_bot)
        pm = AsyncMock()
        cog.set_pm(pm)

        # Message with no embeds
        msg = _make_message(author_id=999, embeds=[])
        await cog.on_message(msg)

        pm.evaluate_question.assert_not_awaited()
        msg.reply.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ignores_non_bot_messages(self, mock_bot):
        """Messages from non-bot users are ignored (not question embeds)."""
        from vcompany.bot.cogs.question_handler import QuestionHandlerCog

        cog = QuestionHandlerCog(mock_bot)
        pm = AsyncMock()
        cog.set_pm(pm)

        # Message from a different user (not the bot)
        msg = _make_message(author_id=12345, is_bot=False)
        await cog.on_message(msg)

        pm.evaluate_question.assert_not_awaited()
        msg.reply.assert_not_awaited()


class TestPMReplyBehavior:
    """PM answers via Discord reply based on confidence level."""

    @pytest.mark.asyncio
    async def test_pm_high_confidence_replies_to_question(self, mock_bot):
        """HIGH confidence: PM replies directly to the question message."""
        from vcompany.bot.cogs.question_handler import QuestionHandlerCog

        cog = QuestionHandlerCog(mock_bot)

        pm = AsyncMock()
        pm_decision = MagicMock()
        pm_decision.answer = "Do X"
        pm_decision.confidence = MagicMock()
        pm_decision.confidence.level = "HIGH"
        pm_decision.confidence.score = 0.95
        pm.evaluate_question = AsyncMock(return_value=pm_decision)
        cog.set_pm(pm)

        msg = _make_message()
        await cog.on_message(msg)

        msg.reply.assert_awaited_once()
        reply_text = msg.reply.call_args[0][0]
        assert "[PM] Do X" == reply_text

    @pytest.mark.asyncio
    async def test_pm_medium_confidence_replies_with_note(self, mock_bot):
        """MEDIUM confidence: PM replies with answer and note."""
        from vcompany.bot.cogs.question_handler import QuestionHandlerCog

        cog = QuestionHandlerCog(mock_bot)

        pm = AsyncMock()
        pm_decision = MagicMock()
        pm_decision.answer = "Probably Y"
        pm_decision.confidence = MagicMock()
        pm_decision.confidence.level = "MEDIUM"
        pm_decision.confidence.score = 0.7
        pm_decision.note = "PM confidence: medium -- @Owner can override"
        pm.evaluate_question = AsyncMock(return_value=pm_decision)
        cog.set_pm(pm)

        # Mock decision logging
        mock_bot.get_cog = MagicMock(return_value=None)

        msg = _make_message()
        await cog.on_message(msg)

        msg.reply.assert_awaited_once()
        reply_text = msg.reply.call_args[0][0]
        assert "[PM] Probably Y" in reply_text
        assert "medium" in reply_text

    @pytest.mark.asyncio
    async def test_pm_low_confidence_escalates_non_reply(self, mock_bot):
        """LOW confidence: posts non-reply escalation (Pattern B), then escalates."""
        from vcompany.bot.cogs.question_handler import QuestionHandlerCog

        cog = QuestionHandlerCog(mock_bot)

        pm = AsyncMock()
        pm_decision = MagicMock()
        pm_decision.answer = None
        pm_decision.confidence = MagicMock()
        pm_decision.confidence.level = "LOW"
        pm_decision.confidence.score = 0.3
        pm_decision.escalate_to = "strategist"
        pm.evaluate_question = AsyncMock(return_value=pm_decision)
        cog.set_pm(pm)

        # Mock StrategistCog with successful answer
        strat_cog = AsyncMock()
        strat_cog.handle_pm_escalation = AsyncMock(return_value="Use Z approach")
        strat_cog.decision_logger = None
        mock_bot.get_cog = MagicMock(return_value=strat_cog)

        msg = _make_message()
        await cog.on_message(msg)

        # Non-reply escalation message sent to channel (Pattern B)
        msg.channel.send.assert_awaited()
        escalation_text = msg.channel.send.call_args[0][0]
        assert "[PM] Escalating to @Strategist" in escalation_text

        # Strategist answer replied to original question
        msg.reply.assert_awaited_once()
        reply_text = msg.reply.call_args[0][0]
        assert "Use Z approach" in reply_text


class TestGracefulDegradation:
    """Cog handles edge cases without crashing."""

    @pytest.mark.asyncio
    async def test_pm_not_injected_no_action(self, mock_bot):
        """When PM is not injected, question sits for manual reply."""
        from vcompany.bot.cogs.question_handler import QuestionHandlerCog

        cog = QuestionHandlerCog(mock_bot)
        # PM not set -- should be None

        msg = _make_message()
        await cog.on_message(msg)

        msg.reply.assert_not_awaited()
        msg.channel.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_in_pm_does_not_crash(self, mock_bot):
        """PM evaluation error is caught; question sits for manual reply."""
        from vcompany.bot.cogs.question_handler import QuestionHandlerCog

        cog = QuestionHandlerCog(mock_bot)

        pm = AsyncMock()
        pm.evaluate_question = AsyncMock(side_effect=RuntimeError("API down"))
        cog.set_pm(pm)

        msg = _make_message()
        # Should not raise
        await cog.on_message(msg)

        msg.reply.assert_not_awaited()

    def test_no_file_writes(self):
        """question_handler.py does not reference ANSWER_DIR or file-based IPC."""
        import inspect
        from vcompany.bot.cogs import question_handler

        source = inspect.getsource(question_handler)
        assert "ANSWER_DIR" not in source
        assert "vco-answers" not in source
        assert "AnswerView" not in source
        assert "OtherAnswerModal" not in source
        assert "_write_answer_file_sync" not in source
        assert "tempfile" not in source


class TestSetupFunction:
    """setup() loads QuestionHandlerCog into bot."""

    @pytest.mark.asyncio
    async def test_setup_adds_cog(self):
        """setup() calls bot.add_cog with QuestionHandlerCog."""
        from vcompany.bot.cogs.question_handler import setup

        bot = MagicMock()
        bot.add_cog = AsyncMock()

        await setup(bot)

        bot.add_cog.assert_awaited_once()
