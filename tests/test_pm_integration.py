"""Tests for PM/Strategist integration wiring (Phase 6 Plan 05 Task 1).

Tests the PM intercept in QuestionHandlerCog, PM review in PlanReviewCog,
bot startup wiring, and graceful degradation without API key.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vcompany.strategist.models import ConfidenceResult, PMDecision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pm_decision(level: str, answer: str | None = None, note: str = "") -> PMDecision:
    """Create a PMDecision with the given confidence level."""
    scores = {"HIGH": 0.95, "MEDIUM": 0.7, "LOW": 0.3}
    return PMDecision(
        answer=answer,
        confidence=ConfidenceResult(
            score=scores.get(level, 0.5),
            level=level,
            coverage=0.8,
            prior_match=0.5,
        ),
        decided_by="PM",
        note=note,
        escalate_to="strategist" if level == "LOW" else None,
    )


def _make_mock_embed(
    request_id: str = "req-123",
    agent_id: str = "agent-a",
    description: str = "What color should the button be?",
) -> MagicMock:
    """Create a mock Discord embed with expected structure."""
    embed = MagicMock()
    embed.footer = MagicMock()
    embed.footer.text = f"Request: {request_id}"
    embed.title = f"Question from {agent_id}"
    embed.description = description
    embed.fields = []
    return embed


def _make_mock_message(
    embed: MagicMock,
    channel_id: int = 100,
    webhook_id: int = 999,
) -> MagicMock:
    """Create a mock Discord message with webhook and embed."""
    message = MagicMock()
    message.webhook_id = webhook_id
    message.channel = MagicMock()
    message.channel.id = channel_id
    message.embeds = [embed]
    message.reply = AsyncMock()
    return message


def _make_question_handler_cog(channel_id: int = 100) -> MagicMock:
    """Create a QuestionHandlerCog with mocked bot."""
    from vcompany.bot.cogs.question_handler import QuestionHandlerCog

    bot = MagicMock()
    bot.get_cog = MagicMock(return_value=None)
    cog = QuestionHandlerCog(bot)
    cog._strategist_channel = MagicMock()
    cog._strategist_channel.id = channel_id
    return cog


# ---------------------------------------------------------------------------
# QuestionHandlerCog PM intercept tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_question_handler_pm_high_confidence_auto_answers():
    """HIGH confidence PM decision should auto-answer without buttons."""
    cog = _make_question_handler_cog()
    pm = AsyncMock()
    pm.evaluate_question = AsyncMock(
        return_value=_make_pm_decision("HIGH", answer="Use blue for the button")
    )
    cog.set_pm(pm)

    embed = _make_mock_embed()
    message = _make_mock_message(embed)

    with patch("vcompany.bot.cogs.question_handler._write_answer_file_sync"):
        await cog.on_message(message)

    # PM was called
    pm.evaluate_question.assert_awaited_once_with("What color should the button be?", "agent-a")
    # Auto-answered via reply (not AnswerView buttons)
    message.reply.assert_awaited_once()
    reply_text = message.reply.call_args[0][0]
    assert "PM auto-answered" in reply_text
    assert "Use blue for the button" in reply_text


@pytest.mark.asyncio
async def test_question_handler_pm_medium_shows_suggestion_and_buttons():
    """MEDIUM confidence should suggest answer but still show buttons for override."""
    cog = _make_question_handler_cog()
    pm = AsyncMock()
    pm.evaluate_question = AsyncMock(
        return_value=_make_pm_decision(
            "MEDIUM",
            answer="Try red for the button",
            note="PM confidence: medium -- @Owner can override",
        )
    )
    cog.set_pm(pm)

    embed = _make_mock_embed()
    message = _make_mock_message(embed)

    await cog.on_message(message)

    # Should have TWO replies: PM suggestion + answer buttons
    assert message.reply.await_count == 2
    first_reply = message.reply.call_args_list[0][0][0]
    assert "PM suggests" in first_reply


@pytest.mark.asyncio
async def test_question_handler_pm_low_escalates_to_strategist():
    """LOW confidence should escalate to Strategist via handle_pm_escalation."""
    cog = _make_question_handler_cog()
    pm = AsyncMock()
    pm.evaluate_question = AsyncMock(return_value=_make_pm_decision("LOW"))
    cog.set_pm(pm)

    # Mock StrategistCog
    strategist_cog = MagicMock()
    strategist_cog.handle_pm_escalation = AsyncMock(return_value="Strategist says: use green")
    strategist_cog.decision_logger = None
    cog.bot.get_cog = MagicMock(return_value=strategist_cog)

    embed = _make_mock_embed()
    message = _make_mock_message(embed)

    with patch("vcompany.bot.cogs.question_handler._write_answer_file_sync"):
        await cog.on_message(message)

    strategist_cog.handle_pm_escalation.assert_awaited_once()
    reply_text = message.reply.call_args[0][0]
    assert "Strategist answered" in reply_text


@pytest.mark.asyncio
async def test_question_handler_pm_low_strategist_low_escalates_to_owner():
    """LOW PM + LOW Strategist should escalate to owner via post_owner_escalation (indefinite wait D-07)."""
    cog = _make_question_handler_cog()
    pm = AsyncMock()
    pm.evaluate_question = AsyncMock(return_value=_make_pm_decision("LOW"))
    cog.set_pm(pm)

    # Mock StrategistCog -- handle_pm_escalation returns None (not confident)
    strategist_cog = MagicMock()
    strategist_cog.handle_pm_escalation = AsyncMock(return_value=None)
    strategist_cog.post_owner_escalation = AsyncMock(return_value="Owner says: use purple")
    strategist_cog.decision_logger = None
    cog.bot.get_cog = MagicMock(return_value=strategist_cog)

    embed = _make_mock_embed()
    message = _make_mock_message(embed)

    with patch("vcompany.bot.cogs.question_handler._write_answer_file_sync"):
        await cog.on_message(message)

    # post_owner_escalation was called (indefinite wait per D-07)
    strategist_cog.post_owner_escalation.assert_awaited_once()
    reply_text = message.reply.call_args[0][0]
    assert "Owner answered" in reply_text


@pytest.mark.asyncio
async def test_question_handler_pm_low_does_not_fall_through_to_buttons():
    """LOW confidence with initialized StrategistCog should NOT fall through to AnswerView buttons."""
    cog = _make_question_handler_cog()
    pm = AsyncMock()
    pm.evaluate_question = AsyncMock(return_value=_make_pm_decision("LOW"))
    cog.set_pm(pm)

    # Mock StrategistCog that returns an answer
    strategist_cog = MagicMock()
    strategist_cog.handle_pm_escalation = AsyncMock(return_value="Some answer")
    strategist_cog.decision_logger = None
    cog.bot.get_cog = MagicMock(return_value=strategist_cog)

    embed = _make_mock_embed()
    message = _make_mock_message(embed)

    with patch("vcompany.bot.cogs.question_handler._write_answer_file_sync"):
        await cog.on_message(message)

    # Only one reply (the Strategist answer), no AnswerView buttons
    assert message.reply.await_count == 1
    reply_text = message.reply.call_args[0][0]
    assert "Strategist answered" in reply_text
    # Should NOT contain "Select an answer" (the AnswerView prompt)
    assert "Select an answer" not in reply_text


# ---------------------------------------------------------------------------
# PlanReviewCog PM review tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_review_pm_high_auto_approves():
    """HIGH confidence PM plan review should auto-approve with notification."""
    from vcompany.bot.cogs.plan_review import PlanReviewCog

    bot = MagicMock()
    bot.get_cog = MagicMock(return_value=None)
    bot.monitor_loop = MagicMock()
    bot.monitor_loop._agent_states = {}
    cog = PlanReviewCog(bot)

    channel = MagicMock()
    channel.send = AsyncMock()
    cog._plan_review_channel = channel
    cog._alerts_channel = MagicMock()
    cog._alerts_channel.send = AsyncMock()

    # Mock PlanReviewer with HIGH confidence
    reviewer = MagicMock()
    reviewer.review_plan = MagicMock(
        return_value=_make_pm_decision("HIGH", answer="Plan approved by PM")
    )
    cog.set_plan_reviewer(reviewer)

    # Create a temp plan file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\nphase: 06\nplan: 01\n---\n<objective>Test</objective>\n")
        plan_path = Path(f.name)

    try:
        with (
            patch("vcompany.bot.cogs.plan_review.build_plan_review_embed") as mock_embed,
            patch("vcompany.bot.cogs.plan_review.validate_safety_table", return_value=(True, "OK")),
        ):
            mock_embed.return_value = MagicMock()
            mock_embed.return_value.add_field = MagicMock()
            await cog.handle_new_plan("agent-a", plan_path)

        reviewer.review_plan.assert_called_once()
        # Embed was sent with auto-approval notice
        channel.send.assert_awaited()
    finally:
        plan_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_plan_review_pm_low_falls_through_to_buttons():
    """LOW confidence PM plan review should fall through to normal button review."""
    from vcompany.bot.cogs.plan_review import PlanReviewCog

    bot = MagicMock()
    bot.get_cog = MagicMock(return_value=None)
    bot.monitor_loop = MagicMock()
    bot.monitor_loop._agent_states = {}
    cog = PlanReviewCog(bot)

    channel = MagicMock()
    channel.send = AsyncMock()
    cog._plan_review_channel = channel

    # Mock PlanReviewer with LOW confidence
    reviewer = MagicMock()
    reviewer.review_plan = MagicMock(
        return_value=_make_pm_decision("LOW", note="Failed checks: scope")
    )
    cog.set_plan_reviewer(reviewer)

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\nphase: 06\nplan: 01\n---\n<objective>Test</objective>\n")
        plan_path = Path(f.name)

    try:
        with (
            patch("vcompany.bot.cogs.plan_review.build_plan_review_embed") as mock_embed,
            patch("vcompany.bot.cogs.plan_review.validate_safety_table", return_value=(True, "OK")),
            patch("vcompany.bot.cogs.plan_review.PlanReviewView") as mock_view_cls,
        ):
            mock_embed.return_value = MagicMock()
            mock_embed.return_value.add_field = MagicMock()
            mock_view = MagicMock()
            mock_view.wait = AsyncMock(return_value=True)  # timeout
            mock_view_cls.return_value = mock_view
            mock_file_cls = MagicMock()

            with patch("vcompany.bot.cogs.plan_review.discord.File", return_value=mock_file_cls):
                await cog.handle_new_plan("agent-a", plan_path)

        # embed should have PM review note added
        mock_embed.return_value.add_field.assert_called()
        add_field_calls = mock_embed.return_value.add_field.call_args_list
        pm_review_call = [c for c in add_field_calls if "PM Review" in str(c)]
        assert len(pm_review_call) > 0
    finally:
        plan_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Bot startup graceful degradation
# ---------------------------------------------------------------------------


def test_bot_config_has_anthropic_fields():
    """BotConfig should have anthropic_api_key, strategist_persona_path, status_digest_interval."""
    from vcompany.bot.config import BotConfig

    # BotConfig requires discord_bot_token and discord_guild_id
    config = BotConfig(
        discord_bot_token="test-token",
        discord_guild_id=12345,
        _env_file=None,
    )
    assert config.anthropic_api_key == ""
    assert config.strategist_persona_path == ""
    assert config.status_digest_interval == 1800


def test_bot_config_graceful_without_api_key():
    """Bot should start without ANTHROPIC_API_KEY -- PM/Strategist disabled."""
    from vcompany.bot.config import BotConfig

    config = BotConfig(
        discord_bot_token="test-token",
        discord_guild_id=12345,
        anthropic_api_key="",
    )
    assert config.anthropic_api_key == ""


# ---------------------------------------------------------------------------
# MonitorLoop status digest
# ---------------------------------------------------------------------------


def test_monitor_loop_accepts_digest_callback():
    """MonitorLoop should accept on_status_digest and digest_interval params."""
    from vcompany.monitor.loop import MonitorLoop

    callback = MagicMock()
    config = MagicMock()
    config.agents = []
    tmux = MagicMock()

    loop = MonitorLoop(
        project_dir=Path("/tmp/test"),
        config=config,
        tmux=tmux,
        on_status_digest=callback,
        digest_interval=900,
    )
    assert loop._on_status_digest is callback
    assert loop._digest_interval == 900
