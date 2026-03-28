"""Tests for WorkflowOrchestratorCog: message detection, gate reviews, and plan notifications (MIGR-01)."""

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
    bot.project_config = MagicMock()
    bot.project_config.project = "testproject"
    # v2: CompanyRoot is on bot
    mock_root = MagicMock()
    mock_root._find_container = AsyncMock(return_value=MagicMock(state="running"))
    bot.company_root = mock_root
    return bot


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
def cog(mock_bot, mock_pm):
    c = WorkflowOrchestratorCog(mock_bot)
    c.set_company_root(mock_pm, Path("/tmp/test-project"))
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
async def test_on_message_detects_discuss_complete(cog, mock_bot):
    """on_message with vco report discuss-phase complete finds container via CompanyRoot."""
    msg = _make_message("2026-03-27T00:00:00Z alpha: discuss-phase complete")

    await cog.on_message(msg)

    mock_bot.company_root._find_container.assert_called_once_with("alpha")


@pytest.mark.asyncio
async def test_on_message_detects_execute_complete(cog, mock_bot):
    """on_message with execute-phase complete finds container via CompanyRoot."""
    msg = _make_message("2026-03-27T00:00:00Z alpha: execute-phase complete")

    await cog.on_message(msg)

    mock_bot.company_root._find_container.assert_called_once_with("alpha")


@pytest.mark.asyncio
async def test_on_message_ignores_non_agent_channels(cog, mock_bot):
    """on_message ignores messages from non-agent channels."""
    msg = _make_message("2026-03-27T00:00:00Z alpha: discuss-phase complete", channel_name="general")

    await cog.on_message(msg)

    mock_bot.company_root._find_container.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_ignores_no_signal(cog, mock_bot):
    """on_message ignores messages without a stage completion signal."""
    msg = _make_message("Just some random message from an agent", channel_name="agent-alpha")

    await cog.on_message(msg)

    mock_bot.company_root._find_container.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_processes_bot_vco_report(cog, mock_bot):
    """on_message processes bot messages (vco report posts as bot via REST API)."""
    msg = _make_message(
        "2026-03-27T00:00:00Z alpha: discuss-phase complete",
        author_id=mock_bot.user.id,
    )

    await cog.on_message(msg)

    mock_bot.company_root._find_container.assert_called_once_with("alpha")


@pytest.mark.asyncio
async def test_on_message_ignores_system_messages(cog, mock_bot):
    """on_message ignores [system] event messages to avoid loops."""
    msg = _make_message(
        "[system] Stage 'discuss' complete",
        author_id=mock_bot.user.id,
    )

    await cog.on_message(msg)

    mock_bot.company_root._find_container.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_ignores_mismatched_channel(cog, mock_bot):
    """on_message ignores signal when agent_id doesn't match channel name."""
    msg = _make_message(
        "2026-03-27T00:00:00Z beta: discuss-phase complete",
        channel_name="agent-alpha",
    )

    await cog.on_message(msg)

    mock_bot.company_root._find_container.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_no_company_root(mock_bot, mock_pm):
    """on_message is a no-op when company_root is None."""
    mock_bot.company_root = None
    c = WorkflowOrchestratorCog(mock_bot)
    c.set_company_root(mock_pm, Path("/tmp/test-project"))

    msg = _make_message("2026-03-27T00:00:00Z alpha: discuss-phase complete")
    await c.on_message(msg)
    # No exception


# ── Discussion gate review ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_discussion_gate_high_confidence(cog, mock_pm):
    """PM HIGH confidence on CONTEXT.md posts approval event."""
    # Create a fake CONTEXT.md
    context_dir = Path("/tmp/test-project/clones/alpha/.planning/phases/01-test")
    context_dir.mkdir(parents=True, exist_ok=True)
    context_file = context_dir / "01-CONTEXT.md"
    context_file.write_text("# Context\nResearch findings here.")

    try:
        await cog._review_discussion_gate("alpha")
        mock_pm.evaluate_question.assert_called_once()
    finally:
        context_file.unlink(missing_ok=True)
        import shutil
        shutil.rmtree("/tmp/test-project", ignore_errors=True)


@pytest.mark.asyncio
async def test_review_discussion_gate_no_context_auto_advances(cog, mock_pm):
    """No CONTEXT.md found posts auto-advance event."""
    cog._project_dir = Path("/tmp/nonexistent-project")

    await cog._review_discussion_gate("alpha")
    mock_pm.evaluate_question.assert_not_called()


# ── Plan approval/rejection notifications ─────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_plan_approved(cog):
    """notify_plan_approved posts approval event."""
    await cog.notify_plan_approved("alpha")
    # No exception -- just posts event


@pytest.mark.asyncio
async def test_notify_plan_rejected(cog):
    """notify_plan_rejected posts rejection event."""
    await cog.notify_plan_rejected("alpha")
    # No exception -- just posts event


@pytest.mark.asyncio
async def test_notify_plan_approved_noop_if_no_company_root():
    """notify_plan_approved does nothing if company_root is None."""
    bot = MagicMock()
    bot.company_root = None
    c = WorkflowOrchestratorCog(bot)

    await c.notify_plan_approved("alpha")
    # No exception


# ── start_workflow ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_workflow_finds_container(cog, mock_bot):
    """start_workflow finds container via CompanyRoot and returns True."""
    result = await cog.start_workflow("alpha", 1)

    assert result is True
    mock_bot.company_root._find_container.assert_called_once_with("alpha")


@pytest.mark.asyncio
async def test_start_workflow_no_company_root():
    """start_workflow returns False if company_root not initialized."""
    bot = MagicMock()
    bot.company_root = None
    c = WorkflowOrchestratorCog(bot)

    result = await c.start_workflow("alpha", 1)

    assert result is False


@pytest.mark.asyncio
async def test_start_workflow_container_not_found(mock_bot, mock_pm):
    """start_workflow returns False if container not found."""
    mock_bot.company_root._find_container = AsyncMock(return_value=None)
    c = WorkflowOrchestratorCog(mock_bot)
    c.set_company_root(mock_pm, Path("/tmp/test"))

    result = await c.start_workflow("nonexistent", 1)

    assert result is False


# ── Verify gate review (D-07) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_verify_gate_all_pass(cog, mock_pm):
    """VERIFICATION.md with all PASS posts phase complete event (D-07)."""
    verify_dir = Path("/tmp/test-project/clones/alpha/.planning/phases/01-test")
    verify_dir.mkdir(parents=True, exist_ok=True)
    verify_file = verify_dir / "01-VERIFICATION.md"
    verify_file.write_text("# Verification\n- Test 1: PASS\n- Test 2: PASS\n")

    try:
        await cog._review_verify_gate("alpha")
        # PM should NOT be consulted when all pass
        mock_pm.evaluate_question.assert_not_called()
    finally:
        import shutil
        shutil.rmtree("/tmp/test-project", ignore_errors=True)


@pytest.mark.asyncio
async def test_review_verify_gate_with_failures_pm_review(cog, mock_pm):
    """VERIFICATION.md with FAIL triggers PM review."""
    mock_pm.evaluate_question.return_value = PMDecision(
        answer="Re-execute to fix failures",
        confidence=ConfidenceResult(score=0.95, level="HIGH", coverage=0.9, prior_match=1.0),
        decided_by="PM",
    )

    verify_dir = Path("/tmp/test-project/clones/alpha/.planning/phases/01-test")
    verify_dir.mkdir(parents=True, exist_ok=True)
    verify_file = verify_dir / "01-VERIFICATION.md"
    verify_file.write_text("# Verification\n- Test 1: PASS\n- Test 2: FAIL\n")

    try:
        await cog._review_verify_gate("alpha")
        mock_pm.evaluate_question.assert_called_once()
    finally:
        import shutil
        shutil.rmtree("/tmp/test-project", ignore_errors=True)


@pytest.mark.asyncio
async def test_review_verify_gate_no_verification_auto_advances(cog):
    """No VERIFICATION.md auto-advances the verify gate."""
    cog._project_dir = Path("/tmp/nonexistent-project")

    await cog._review_verify_gate("alpha")
    # No exception -- posts auto-advance event


# ── Phase complete handling ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_phase_complete(cog):
    """_handle_phase_complete logs completion."""
    await cog._handle_phase_complete("alpha")
    # No exception -- posts completion event


# ── Cog registration smoke tests ─────────────────────────────────────────────


def test_workflow_orchestrator_cog_in_extensions():
    """WorkflowOrchestratorCog is registered in _COG_EXTENSIONS."""
    from vcompany.bot.client import _COG_EXTENSIONS

    assert "vcompany.bot.cogs.workflow_orchestrator_cog" in _COG_EXTENSIONS


def test_question_handler_cog_in_extensions():
    """QuestionHandlerCog is registered in _COG_EXTENSIONS (D-09/D-10)."""
    from vcompany.bot.client import _COG_EXTENSIONS

    assert "vcompany.bot.cogs.question_handler" in _COG_EXTENSIONS


def test_plan_review_cog_has_workflow_cog_attribute():
    """PlanReviewCog has _workflow_cog attribute for notification wiring."""
    from vcompany.bot.cogs.plan_review import PlanReviewCog

    bot = MagicMock()
    cog = PlanReviewCog(bot)
    assert hasattr(cog, "_workflow_cog")
    assert cog._workflow_cog is None


def test_cog_uses_company_root():
    """WorkflowOrchestratorCog uses bot.company_root not _orchestrator."""
    bot = MagicMock()
    bot.company_root = MagicMock()
    c = WorkflowOrchestratorCog(bot)
    assert not hasattr(c, "_orchestrator")
    assert c._initialized is True
