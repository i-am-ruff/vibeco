"""Tests for PMTier question evaluation with escalation chain.

Tests the PM tier per D-01 (stateless), D-05 (escalation chain),
D-06/D-09 (confidence thresholds), D-08 (heuristic confidence).
Now mocks asyncio.create_subprocess_exec instead of Anthropic SDK.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vcompany.strategist.models import ConfidenceResult, DecisionLogEntry, PMDecision


def _make_confidence(level: str, score: float = 0.5) -> ConfidenceResult:
    """Create a ConfidenceResult with sensible defaults for the given level."""
    return ConfidenceResult(score=score, level=level, coverage=score, prior_match=0.0)


def _setup_project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory with context files and state dir."""
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    (context_dir / "PROJECT-BLUEPRINT.md").write_text("# Blueprint\nSome blueprint content")
    (context_dir / "INTERFACES.md").write_text("# Interfaces\nSome interface content")
    (context_dir / "MILESTONE-SCOPE.md").write_text("# Scope\nSome scope content")
    (context_dir / "PROJECT-STATUS.md").write_text("# Status\nSome status content")

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return tmp_path


def _make_mock_process(result_text: str = "The answer is 42.", returncode: int = 0):
    """Create a mock subprocess process returning Claude CLI JSON output."""
    result_json = json.dumps({
        "type": "result",
        "subtype": "success",
        "result": result_text,
    })
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(result_json.encode(), b""))
    return proc


@pytest.mark.asyncio
async def test_high_confidence_returns_direct_answer(tmp_path: Path) -> None:
    """HIGH confidence: PM answers directly with decided_by='PM'."""
    project_dir = _setup_project_dir(tmp_path)

    from vcompany.strategist.pm import PMTier

    proc = _make_mock_process("The answer is 42.")

    with patch.object(PMTier, "_get_scorer") as mock_scorer_factory, \
         patch("asyncio.create_subprocess_exec", return_value=proc):
        scorer = MagicMock()
        scorer.score.return_value = _make_confidence("HIGH", 0.95)
        mock_scorer_factory.return_value = scorer

        pm = PMTier(project_dir=project_dir)
        result = await pm.evaluate_question("What database should I use?", agent_id="agent-1")

    assert isinstance(result, PMDecision)
    assert result.answer == "The answer is 42."
    assert result.decided_by == "PM"
    assert result.confidence.level == "HIGH"
    assert result.escalate_to is None
    assert result.note == ""


@pytest.mark.asyncio
async def test_medium_confidence_returns_answer_with_note(tmp_path: Path) -> None:
    """MEDIUM confidence: PM answers with override note per STRAT-04."""
    project_dir = _setup_project_dir(tmp_path)

    from vcompany.strategist.pm import PMTier

    proc = _make_mock_process("Probably use PostgreSQL.")

    with patch.object(PMTier, "_get_scorer") as mock_scorer_factory, \
         patch("asyncio.create_subprocess_exec", return_value=proc):
        scorer = MagicMock()
        scorer.score.return_value = _make_confidence("MEDIUM", 0.75)
        mock_scorer_factory.return_value = scorer

        pm = PMTier(project_dir=project_dir)
        result = await pm.evaluate_question("Should I add caching?", agent_id="agent-2")

    assert isinstance(result, PMDecision)
    assert result.answer == "Probably use PostgreSQL."
    assert result.decided_by == "PM"
    assert result.confidence.level == "MEDIUM"
    assert "PM confidence: medium" in result.note
    assert "@Owner can override" in result.note
    assert result.escalate_to is None


@pytest.mark.asyncio
async def test_low_confidence_escalates_to_strategist(tmp_path: Path) -> None:
    """LOW confidence: PM escalates to strategist, no answer per STRAT-05/D-05."""
    project_dir = _setup_project_dir(tmp_path)

    from vcompany.strategist.pm import PMTier

    with patch.object(PMTier, "_get_scorer") as mock_scorer_factory, \
         patch("asyncio.create_subprocess_exec") as mock_exec:
        scorer = MagicMock()
        scorer.score.return_value = _make_confidence("LOW", 0.3)
        mock_scorer_factory.return_value = scorer

        pm = PMTier(project_dir=project_dir)
        result = await pm.evaluate_question("Should we pivot the product?", agent_id="agent-3")

    assert isinstance(result, PMDecision)
    assert result.answer is None
    assert result.decided_by == "PM"
    assert result.confidence.level == "LOW"
    assert result.escalate_to == "strategist"
    # Claude CLI should NOT be called for LOW confidence
    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_fresh_cli_call_per_question(tmp_path: Path) -> None:
    """PM makes a fresh Claude CLI call per question (stateless per D-01)."""
    project_dir = _setup_project_dir(tmp_path)

    from vcompany.strategist.pm import PMTier

    call_count = 0

    async def counting_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _make_mock_process("Answer.")

    with patch.object(PMTier, "_get_scorer") as mock_scorer_factory, \
         patch("asyncio.create_subprocess_exec", side_effect=counting_exec):
        scorer = MagicMock()
        scorer.score.return_value = _make_confidence("HIGH", 0.95)
        mock_scorer_factory.return_value = scorer

        pm = PMTier(project_dir=project_dir)
        await pm.evaluate_question("Question 1?", agent_id="agent-1")
        await pm.evaluate_question("Question 2?", agent_id="agent-1")

    assert call_count == 2


@pytest.mark.asyncio
async def test_uses_pm_context_as_system_prompt(tmp_path: Path) -> None:
    """PM passes --system-prompt arg to Claude CLI."""
    project_dir = _setup_project_dir(tmp_path)

    from vcompany.strategist.pm import PMTier

    captured_args = []

    async def capturing_exec(*args, **kwargs):
        captured_args.append(args)
        return _make_mock_process("Answer.")

    with patch.object(PMTier, "_get_scorer") as mock_scorer_factory, \
         patch("asyncio.create_subprocess_exec", side_effect=capturing_exec):
        scorer = MagicMock()
        scorer.score.return_value = _make_confidence("HIGH", 0.95)
        mock_scorer_factory.return_value = scorer

        pm = PMTier(project_dir=project_dir)
        await pm.evaluate_question("Test question?", agent_id="agent-1")

    # Verify --system-prompt was passed to subprocess
    assert len(captured_args) == 1
    cli_args = captured_args[0]
    assert "--system-prompt" in cli_args
    prompt_idx = cli_args.index("--system-prompt")
    system_prompt = cli_args[prompt_idx + 1]
    assert len(system_prompt) > 0


@pytest.mark.asyncio
async def test_decision_log_loaded_for_scoring(tmp_path: Path) -> None:
    """Decision log entries loaded from state/decisions.jsonl for confidence scoring."""
    project_dir = _setup_project_dir(tmp_path)

    # Write a decision log entry
    decisions_path = project_dir / "state" / "decisions.jsonl"
    entry = {
        "timestamp": "2026-03-25T10:00:00Z",
        "question_or_plan": "Which database to use?",
        "decision": "Use PostgreSQL",
        "confidence_level": "HIGH",
        "decided_by": "PM",
        "agent_id": "agent-1",
    }
    decisions_path.write_text(json.dumps(entry) + "\n")

    from vcompany.strategist.pm import PMTier

    proc = _make_mock_process("Answer.")

    with patch.object(PMTier, "_get_scorer") as mock_scorer_factory, \
         patch("asyncio.create_subprocess_exec", return_value=proc):
        scorer = MagicMock()
        scorer.score.return_value = _make_confidence("HIGH", 0.95)
        mock_scorer_factory.return_value = scorer

        pm = PMTier(project_dir=project_dir)
        await pm.evaluate_question("Which database?", agent_id="agent-1")

    # Verify scorer was called with decision log entries
    scorer.score.assert_called_once()
    call_args = scorer.score.call_args
    decision_log = call_args[0][2] if len(call_args[0]) > 2 else call_args.kwargs.get("decision_log", [])
    assert len(decision_log) == 1
    assert decision_log[0].decision == "Use PostgreSQL"


@pytest.mark.asyncio
async def test_graceful_degradation_on_cli_failure(tmp_path: Path) -> None:
    """PM returns PMDecision even when Claude CLI call fails."""
    project_dir = _setup_project_dir(tmp_path)

    from vcompany.strategist.pm import PMTier

    async def failing_exec(*args, **kwargs):
        raise OSError("CLI not found")

    with patch.object(PMTier, "_get_scorer") as mock_scorer_factory, \
         patch("asyncio.create_subprocess_exec", side_effect=failing_exec):
        scorer = MagicMock()
        scorer.score.return_value = _make_confidence("HIGH", 0.95)
        mock_scorer_factory.return_value = scorer

        pm = PMTier(project_dir=project_dir)
        result = await pm.evaluate_question("Test question?", agent_id="agent-1")

    assert isinstance(result, PMDecision)
    assert result.answer is not None
    assert "unable" in result.answer.lower() or "escalat" in result.answer.lower()
    assert result.confidence.level == "HIGH"
