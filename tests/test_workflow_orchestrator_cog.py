"""Tests for WorkflowOrchestratorCog: message detection, gate reviews, and plan notifications."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vcompany.bot.cogs.workflow_orchestrator_cog import WorkflowOrchestratorCog
from vcompany.orchestrator.workflow_orchestrator import WorkflowStage
from vcompany.strategist.models import ConfidenceResult, PMDecision


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 12345
    bot._guild_id = 99999
    bot.get_guild.return_value = None
    return bot


@pytest.fixture
def mock_orchestrator():
    orch = MagicMock()
    orch.on_stage_complete.return_value = WorkflowStage.DISCUSSION_GATE
    orch.advance_from_gate.return_value = True
    orch.start_agent.return_value = True
    orch.get_agent_state.return_value = MagicMock(
        stage=WorkflowStage.PM_PLAN_REVIEW_GATE, current_phase=1
    )
    return orch


@pytest.fixture
def mock_pm():
    pm = AsyncMock()
    pm.evaluate_question.return_value = PMDecision(
        answer="Looks good",
        confidence=ConfidenceResult(score=0.95, level="HIGH", coverage=0.9, prior_match=1.0),
        decided_by="PM",
    )
    return pm


@pytest.fixture
def cog(mock_bot, mock_orchestrator, mock_pm):
    c = WorkflowOrchestratorCog(mock_bot)
    c.set_orchestrator(mock_orchestrator, mock_pm, Path("/tmp/test-project"))
    return c


def _make_message(content: str, channel_name: str = "agent-alpha", author_id: int = 999):
    """Create a mock Discord message."""
    msg = MagicMock()
    msg.content = content
    msg.channel = MagicMock()
    msg.channel.name = channel_name
    msg.author = MagicMock()
    msg.author.id = author_id
    return msg


# ── on_message signal detection ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_message_detects_discuss_complete(cog, mock_orchestrator):
    """on_message with vco report discuss-phase complete triggers on_stage_complete."""
    msg = _make_message("2026-03-27T00:00:00Z alpha: discuss-phase complete")
    mock_orchestrator.on_stage_complete.return_value = WorkflowStage.DISCUSSION_GATE

    await cog.on_message(msg)

    mock_orchestrator.on_stage_complete.assert_called_once_with("alpha", "discuss")


@pytest.mark.asyncio
async def test_on_message_detects_execute_complete(cog, mock_orchestrator):
    """on_message with execute-phase complete triggers on_stage_complete."""
    msg = _make_message("2026-03-27T00:00:00Z alpha: execute-phase complete")
    mock_orchestrator.on_stage_complete.return_value = WorkflowStage.VERIFY

    await cog.on_message(msg)

    mock_orchestrator.on_stage_complete.assert_called_once_with("alpha", "execute")


@pytest.mark.asyncio
async def test_on_message_ignores_non_agent_channels(cog, mock_orchestrator):
    """on_message ignores messages from non-agent channels."""
    msg = _make_message("2026-03-27T00:00:00Z alpha: discuss-phase complete", channel_name="general")

    await cog.on_message(msg)

    mock_orchestrator.on_stage_complete.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_ignores_no_signal(cog, mock_orchestrator):
    """on_message ignores messages without a stage completion signal."""
    msg = _make_message("Just some random message from an agent", channel_name="agent-alpha")

    await cog.on_message(msg)

    mock_orchestrator.on_stage_complete.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_ignores_bot_own_messages(cog, mock_orchestrator, mock_bot):
    """on_message ignores messages from the bot itself."""
    msg = _make_message(
        "2026-03-27T00:00:00Z alpha: discuss-phase complete",
        author_id=mock_bot.user.id,
    )

    await cog.on_message(msg)

    mock_orchestrator.on_stage_complete.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_ignores_mismatched_channel(cog, mock_orchestrator):
    """on_message ignores signal when agent_id doesn't match channel name."""
    msg = _make_message(
        "2026-03-27T00:00:00Z beta: discuss-phase complete",
        channel_name="agent-alpha",
    )

    await cog.on_message(msg)

    mock_orchestrator.on_stage_complete.assert_not_called()


# ── Discussion gate review ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_discussion_gate_high_confidence_advances(cog, mock_orchestrator, mock_pm):
    """PM HIGH confidence on CONTEXT.md advances the discussion gate."""
    # Create a fake CONTEXT.md
    context_dir = Path("/tmp/test-project/clones/alpha/.planning/phases/01-test")
    context_dir.mkdir(parents=True, exist_ok=True)
    context_file = context_dir / "01-CONTEXT.md"
    context_file.write_text("# Context\nResearch findings here.")

    try:
        await cog._review_discussion_gate("alpha")

        mock_pm.evaluate_question.assert_called_once()
        mock_orchestrator.advance_from_gate.assert_called_once_with("alpha", True)
    finally:
        context_file.unlink(missing_ok=True)
        # Clean up dirs
        import shutil
        shutil.rmtree("/tmp/test-project", ignore_errors=True)


@pytest.mark.asyncio
async def test_review_discussion_gate_low_confidence_blocks(cog, mock_orchestrator, mock_pm):
    """PM LOW confidence on CONTEXT.md blocks the gate."""
    mock_pm.evaluate_question.return_value = PMDecision(
        answer=None,
        confidence=ConfidenceResult(score=0.3, level="LOW", coverage=0.2, prior_match=0.4),
        decided_by="PM",
        escalate_to="strategist",
    )

    # Create a fake CONTEXT.md
    context_dir = Path("/tmp/test-project/clones/alpha/.planning/phases/01-test")
    context_dir.mkdir(parents=True, exist_ok=True)
    context_file = context_dir / "01-CONTEXT.md"
    context_file.write_text("# Context\nIncomplete research.")

    try:
        await cog._review_discussion_gate("alpha")

        mock_pm.evaluate_question.assert_called_once()
        # Should NOT advance -- should block
        mock_orchestrator.advance_from_gate.assert_not_called()
        mock_orchestrator.handle_unknown_prompt.assert_called_once()
    finally:
        import shutil
        shutil.rmtree("/tmp/test-project", ignore_errors=True)


@pytest.mark.asyncio
async def test_review_discussion_gate_no_context_auto_advances(cog, mock_orchestrator, mock_pm):
    """No CONTEXT.md found auto-advances the gate."""
    # No files created -- empty project dir
    cog._project_dir = Path("/tmp/nonexistent-project")

    await cog._review_discussion_gate("alpha")

    mock_orchestrator.advance_from_gate.assert_called_once_with("alpha", True)
    mock_pm.evaluate_question.assert_not_called()


# ── Plan approval/rejection notifications ─────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_plan_approved_advances_gate(cog, mock_orchestrator):
    """notify_plan_approved advances from PM_PLAN_REVIEW_GATE."""
    await cog.notify_plan_approved("alpha")

    mock_orchestrator.advance_from_gate.assert_called_once_with("alpha", True)


@pytest.mark.asyncio
async def test_notify_plan_rejected_sends_back_to_plan(cog, mock_orchestrator):
    """notify_plan_rejected sends agent back to PLAN stage."""
    await cog.notify_plan_rejected("alpha")

    mock_orchestrator.advance_from_gate.assert_called_once_with("alpha", False)


@pytest.mark.asyncio
async def test_notify_plan_approved_noop_if_not_at_gate(cog, mock_orchestrator):
    """notify_plan_approved does nothing if agent is not at PM_PLAN_REVIEW_GATE."""
    mock_orchestrator.get_agent_state.return_value = MagicMock(
        stage=WorkflowStage.EXECUTE, current_phase=1
    )

    await cog.notify_plan_approved("alpha")

    mock_orchestrator.advance_from_gate.assert_not_called()


# ── start_workflow ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_workflow_calls_orchestrator(cog, mock_orchestrator):
    """start_workflow wraps orchestrator.start_agent."""
    result = await cog.start_workflow("alpha", 1)

    assert result is True
    mock_orchestrator.start_agent.assert_called_once_with("alpha", 1)


@pytest.mark.asyncio
async def test_start_workflow_no_orchestrator():
    """start_workflow returns False if orchestrator not initialized."""
    bot = MagicMock()
    c = WorkflowOrchestratorCog(bot)

    result = await c.start_workflow("alpha", 1)

    assert result is False
