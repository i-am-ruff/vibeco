"""Tests for QuestionHandlerCog: webhook question detection and answer delivery."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
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
    yield bot
    bot.loop.close()


@pytest.fixture
def answer_dir(tmp_path):
    """Provide a temporary answer directory and patch ANSWER_DIR."""
    d = tmp_path / "vco-answers"
    d.mkdir()
    with patch("vcompany.bot.cogs.question_handler.ANSWER_DIR", d):
        yield d


def _make_embed(
    title: str = "Question from agent-1",
    footer_text: str = "Request: abc-123",
    fields: list[tuple[str, str]] | None = None,
) -> discord.Embed:
    """Create a mock embed mimicking ask_discord.py output."""
    embed = discord.Embed(title=title, description="What should I do?")
    embed.set_footer(text=footer_text)
    if fields is None:
        fields = [("Option A", "Do X"), ("Option B", "Do Y")]
    for name, value in fields:
        embed.add_field(name=name, value=value)
    return embed


def _make_message(
    *,
    webhook_id: int | None = 999,
    channel_id: int = 100,
    embeds: list[discord.Embed] | None = None,
) -> MagicMock:
    """Create a mock discord.Message for on_message tests."""
    msg = MagicMock(spec=discord.Message)
    msg.webhook_id = webhook_id
    msg.channel = MagicMock()
    msg.channel.id = channel_id
    msg.embeds = embeds if embeds is not None else [_make_embed()]
    msg.reply = AsyncMock()
    return msg


class TestDetectsWebhookQuestion:
    """on_message detects webhook questions in #strategist."""

    @pytest.mark.asyncio
    async def test_detects_webhook_question(self, mock_bot):
        """on_message fires for webhook messages in #strategist with request_id."""
        from vcompany.bot.cogs.question_handler import QuestionHandlerCog

        cog = QuestionHandlerCog(mock_bot)

        # Set up strategist channel
        strategist = MagicMock(spec=discord.TextChannel)
        strategist.name = "strategist"
        strategist.id = 100
        cog._strategist_channel = strategist

        msg = _make_message(webhook_id=999, channel_id=100)

        await cog.on_message(msg)

        msg.reply.assert_awaited_once()
        reply_kwargs = msg.reply.call_args
        assert "abc-123" in reply_kwargs.args[0]
        assert "view" in reply_kwargs.kwargs

    @pytest.mark.asyncio
    async def test_ignores_non_webhook_messages(self, mock_bot):
        """Regular user messages in #strategist are ignored."""
        from vcompany.bot.cogs.question_handler import QuestionHandlerCog

        cog = QuestionHandlerCog(mock_bot)
        strategist = MagicMock(spec=discord.TextChannel)
        strategist.name = "strategist"
        strategist.id = 100
        cog._strategist_channel = strategist

        msg = _make_message(webhook_id=None, channel_id=100)

        await cog.on_message(msg)

        msg.reply.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ignores_messages_without_request_id(self, mock_bot):
        """Webhook messages without 'Request:' in footer are ignored."""
        from vcompany.bot.cogs.question_handler import QuestionHandlerCog

        cog = QuestionHandlerCog(mock_bot)
        strategist = MagicMock(spec=discord.TextChannel)
        strategist.name = "strategist"
        strategist.id = 100
        cog._strategist_channel = strategist

        embed = _make_embed(footer_text="No request id here")
        msg = _make_message(webhook_id=999, channel_id=100, embeds=[embed])

        await cog.on_message(msg)

        msg.reply.assert_not_awaited()


class TestCreatesAnswerButtons:
    """AnswerView creates buttons from embed fields."""

    def test_creates_answer_buttons(self):
        """For each option in embed fields, creates a button plus 'Other'."""
        from vcompany.bot.cogs.question_handler import AnswerView

        options = [
            {"name": "Option A", "value": "Do X"},
            {"name": "Option B", "value": "Do Y"},
        ]
        view = AnswerView(request_id="req-1", agent_id="agent-1", options=options)

        # 2 option buttons + 1 Other button = 3 total
        buttons = [child for child in view.children if isinstance(child, discord.ui.Button)]
        assert len(buttons) == 3

        # Last button should be "Other"
        labels = [b.label for b in buttons]
        assert "Other (type answer)" in labels

    def test_buttons_have_correct_custom_ids(self):
        """Button custom_ids include request_id for identification."""
        from vcompany.bot.cogs.question_handler import AnswerView

        options = [{"name": "A", "value": "desc"}]
        view = AnswerView(request_id="req-42", agent_id="agent-1", options=options)

        buttons = [child for child in view.children if isinstance(child, discord.ui.Button)]
        custom_ids = [b.custom_id for b in buttons]
        assert any("req-42" in cid for cid in custom_ids)


class TestAnswerFileWrite:
    """Answer file written atomically for hook polling."""

    def test_answer_button_writes_file(self, answer_dir):
        """Clicking an option writes /tmp/vco-answers/{request_id}.json with correct format."""
        from vcompany.bot.cogs.question_handler import _write_answer_file_sync

        _write_answer_file_sync("req-abc", "agent-1", "Option A - Do X", "TestUser#1234")

        answer_path = answer_dir / "req-abc.json"
        assert answer_path.exists()

        data = json.loads(answer_path.read_text())
        assert data["request_id"] == "req-abc"
        assert data["agent_id"] == "agent-1"
        assert data["answer"] == "Option A - Do X"
        assert data["answered_by"] == "TestUser#1234"
        assert "answered_at" in data

    def test_answer_file_atomic(self, answer_dir):
        """Answer file is written atomically (tmp+rename pattern)."""
        from vcompany.bot.cogs.question_handler import _write_answer_file_sync

        # Write a file
        _write_answer_file_sync("req-atomic", "agent-1", "Test answer", "User")

        answer_path = answer_dir / "req-atomic.json"
        assert answer_path.exists()

        # Verify no .tmp files remain (atomic rename cleans up)
        tmp_files = list(answer_dir.glob("*.tmp"))
        assert len(tmp_files) == 0

        # Verify file content is complete JSON (not partial)
        content = answer_path.read_text()
        data = json.loads(content)  # Should not raise
        assert data["request_id"] == "req-atomic"

    def test_answer_file_creates_directory(self, tmp_path):
        """Answer file creation creates directory if missing."""
        from vcompany.bot.cogs.question_handler import _write_answer_file_sync

        new_dir = tmp_path / "new-answers"
        with patch("vcompany.bot.cogs.question_handler.ANSWER_DIR", new_dir):
            _write_answer_file_sync("req-new", "agent-1", "answer", "User")

        assert (new_dir / "req-new.json").exists()


class TestAnswerViewCallbacks:
    """AnswerView button callbacks write answer and update UI."""

    @pytest.mark.asyncio
    async def test_option_callback_writes_answer(self, answer_dir):
        """Clicking an option button writes answer file and disables buttons."""
        from vcompany.bot.cogs.question_handler import AnswerView

        options = [{"name": "Option A", "value": "Do X"}]
        view = AnswerView(request_id="req-cb", agent_id="agent-1", options=options)

        # Get the first option button's callback
        option_button = view.children[0]

        # Mock interaction
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = AsyncMock()
        interaction.response.edit_message = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.__str__ = lambda self: "TestUser#1234"

        await option_button.callback(interaction)

        # Verify answer file written
        answer_path = answer_dir / "req-cb.json"
        assert answer_path.exists()
        data = json.loads(answer_path.read_text())
        assert data["answer"] == "Option A - Do X"
        assert view.answered is True


class TestOtherAnswerModal:
    """OtherAnswerModal provides free-text input."""

    def test_modal_has_text_input(self):
        """Modal includes a TextInput field."""
        from vcompany.bot.cogs.question_handler import OtherAnswerModal

        modal = OtherAnswerModal(request_id="req-1", agent_id="agent-1")
        assert hasattr(modal, "answer_input")
        assert modal.request_id == "req-1"
        assert modal.agent_id == "agent-1"


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
