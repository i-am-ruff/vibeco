"""Tests for GSD workflow patcher tool (D-12, D-13)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

# We import after setting up the mock directory via monkeypatch
import tools.patch_gsd_workflows as patcher


# --- Fixtures ---


MOCK_DISCUSS_PHASE = """\
<purpose>Discussion workflow</purpose>

<step name="check_existing">
Check if CONTEXT.md already exists.
</step>

<step name="auto_advance">
Check for auto-advance trigger.
</step>
"""

MOCK_DISCUSS_ASSUMPTIONS = """\
<purpose>Assumptions mode discussion</purpose>

<step name="check_existing">
Check if CONTEXT.md already exists.
</step>

<step name="auto_advance">
Check for auto-advance trigger.
</step>
"""

MOCK_PLAN_PHASE = """\
## Planning workflow

Otherwise use AskUserQuestion:
- header: "No context"
- question: "No CONTEXT.md found"

Otherwise use AskUserQuestion:
- header: "UI Design Contract"
- question: "Generate a design contract?"
"""

MOCK_EXECUTE_PHASE = """\
<step name="regression_gate">
Run prior phases' test suites.

Use AskUserQuestion to present the options.
</step>
"""

MOCK_EXECUTE_PLAN = """\
<step name="previous_phase_check">
If previous SUMMARY has unresolved issues: AskUserQuestion(header="Previous Issues", options: "Proceed anyway" | "Address first" | "Review previous").
</step>
"""


@pytest.fixture()
def workflow_dir(tmp_path: Path) -> Path:
    """Create a mock GSD workflows directory with representative content."""
    (tmp_path / "discuss-phase.md").write_text(MOCK_DISCUSS_PHASE)
    (tmp_path / "discuss-phase-assumptions.md").write_text(MOCK_DISCUSS_ASSUMPTIONS)
    (tmp_path / "plan-phase.md").write_text(MOCK_PLAN_PHASE)
    (tmp_path / "execute-phase.md").write_text(MOCK_EXECUTE_PHASE)
    (tmp_path / "execute-plan.md").write_text(MOCK_EXECUTE_PLAN)
    return tmp_path


@pytest.fixture(autouse=True)
def _mock_workflows_dir(workflow_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the patcher at our tmp directory."""
    monkeypatch.setattr(patcher, "GSD_WORKFLOWS_DIR", workflow_dir)


# --- discuss-phase.md tests ---


class TestPatchDiscussPhase:
    def test_adds_vco_report_start(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase()
        content = (workflow_dir / "discuss-phase.md").read_text()
        assert 'vco report "starting discuss-phase $PHASE"' in content

    def test_adds_vco_report_end(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase()
        content = (workflow_dir / "discuss-phase.md").read_text()
        assert 'vco report "discuss-phase complete"' in content

    def test_start_report_before_check_existing(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase()
        content = (workflow_dir / "discuss-phase.md").read_text()
        start_idx = content.index("starting discuss-phase")
        check_idx = content.index('<step name="check_existing">')
        assert start_idx < check_idx

    def test_end_report_before_auto_advance(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase()
        content = (workflow_dir / "discuss-phase.md").read_text()
        end_idx = content.index("discuss-phase complete")
        advance_idx = content.index('<step name="auto_advance">')
        assert end_idx < advance_idx

    def test_adds_patch_marker(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase()
        content = (workflow_dir / "discuss-phase.md").read_text()
        assert patcher.PATCH_MARKER in content

    def test_returns_true_on_success(self, workflow_dir: Path) -> None:
        assert patcher.patch_discuss_phase() is True

    def test_returns_false_if_missing(self, workflow_dir: Path) -> None:
        (workflow_dir / "discuss-phase.md").unlink()
        assert patcher.patch_discuss_phase() is False


# --- discuss-phase-assumptions.md tests ---


class TestPatchDiscussPhaseAssumptions:
    def test_adds_vco_report_start(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase_assumptions()
        content = (workflow_dir / "discuss-phase-assumptions.md").read_text()
        assert 'vco report "starting discuss-phase-assumptions $PHASE"' in content

    def test_adds_vco_report_end(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase_assumptions()
        content = (workflow_dir / "discuss-phase-assumptions.md").read_text()
        assert 'vco report "discuss-phase-assumptions complete"' in content

    def test_start_report_before_check_existing(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase_assumptions()
        content = (workflow_dir / "discuss-phase-assumptions.md").read_text()
        start_idx = content.index("starting discuss-phase-assumptions")
        check_idx = content.index('<step name="check_existing">')
        assert start_idx < check_idx

    def test_end_report_before_auto_advance(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase_assumptions()
        content = (workflow_dir / "discuss-phase-assumptions.md").read_text()
        end_idx = content.index("discuss-phase-assumptions complete")
        advance_idx = content.index('<step name="auto_advance">')
        assert end_idx < advance_idx

    def test_adds_patch_marker(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase_assumptions()
        content = (workflow_dir / "discuss-phase-assumptions.md").read_text()
        assert patcher.PATCH_MARKER in content

    def test_returns_true_on_success(self, workflow_dir: Path) -> None:
        assert patcher.patch_discuss_phase_assumptions() is True

    def test_returns_false_if_missing(self, workflow_dir: Path) -> None:
        (workflow_dir / "discuss-phase-assumptions.md").unlink()
        assert patcher.patch_discuss_phase_assumptions() is False


# --- plan-phase.md tests ---


class TestPatchPlanPhase:
    def test_adds_context_gate_autonomous_mode(self, workflow_dir: Path) -> None:
        patcher.patch_plan_phase()
        content = (workflow_dir / "plan-phase.md").read_text()
        assert "AUTONOMOUS MODE" in content
        assert "Continue without context" in content

    def test_adds_ui_gate_autonomous_mode(self, workflow_dir: Path) -> None:
        patcher.patch_plan_phase()
        content = (workflow_dir / "plan-phase.md").read_text()
        assert "Continue without UI-SPEC" in content

    def test_adds_patch_marker(self, workflow_dir: Path) -> None:
        patcher.patch_plan_phase()
        content = (workflow_dir / "plan-phase.md").read_text()
        assert patcher.PATCH_MARKER in content


# --- execute-phase.md tests ---


class TestPatchExecutePhase:
    def test_adds_regression_gate_autonomous_mode(self, workflow_dir: Path) -> None:
        patcher.patch_execute_phase()
        content = (workflow_dir / "execute-phase.md").read_text()
        assert "AUTONOMOUS MODE" in content
        assert "Fix regressions" in content

    def test_adds_patch_marker(self, workflow_dir: Path) -> None:
        patcher.patch_execute_phase()
        content = (workflow_dir / "execute-phase.md").read_text()
        assert patcher.PATCH_MARKER in content


# --- execute-plan.md tests ---


class TestPatchExecutePlan:
    def test_adds_previous_phase_check_autonomous_mode(
        self, workflow_dir: Path
    ) -> None:
        patcher.patch_execute_plan()
        content = (workflow_dir / "execute-plan.md").read_text()
        assert "AUTONOMOUS MODE" in content
        assert "Proceed anyway" in content

    def test_adds_patch_marker(self, workflow_dir: Path) -> None:
        patcher.patch_execute_plan()
        content = (workflow_dir / "execute-plan.md").read_text()
        assert patcher.PATCH_MARKER in content


# --- Idempotency tests ---


class TestIdempotency:
    def test_discuss_phase_idempotent(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase()
        first = (workflow_dir / "discuss-phase.md").read_text()
        patcher.patch_discuss_phase()
        second = (workflow_dir / "discuss-phase.md").read_text()
        assert first == second

    def test_discuss_assumptions_idempotent(self, workflow_dir: Path) -> None:
        patcher.patch_discuss_phase_assumptions()
        first = (workflow_dir / "discuss-phase-assumptions.md").read_text()
        patcher.patch_discuss_phase_assumptions()
        second = (workflow_dir / "discuss-phase-assumptions.md").read_text()
        assert first == second

    def test_plan_phase_idempotent(self, workflow_dir: Path) -> None:
        patcher.patch_plan_phase()
        first = (workflow_dir / "plan-phase.md").read_text()
        patcher.patch_plan_phase()
        second = (workflow_dir / "plan-phase.md").read_text()
        assert first == second

    def test_execute_phase_idempotent(self, workflow_dir: Path) -> None:
        patcher.patch_execute_phase()
        first = (workflow_dir / "execute-phase.md").read_text()
        patcher.patch_execute_phase()
        second = (workflow_dir / "execute-phase.md").read_text()
        assert first == second

    def test_execute_plan_idempotent(self, workflow_dir: Path) -> None:
        patcher.patch_execute_plan()
        first = (workflow_dir / "execute-plan.md").read_text()
        patcher.patch_execute_plan()
        second = (workflow_dir / "execute-plan.md").read_text()
        assert first == second


# --- verify_patches tests ---


class TestVerifyPatches:
    def test_returns_false_for_unpatched(self, workflow_dir: Path) -> None:
        results = patcher.verify_patches()
        assert results["discuss-phase.md"] is False
        assert results["discuss-phase-assumptions.md"] is False
        assert results["plan-phase.md"] is False

    def test_returns_true_after_patching(self, workflow_dir: Path) -> None:
        patcher.patch_all()
        results = patcher.verify_patches()
        assert all(results.values()), f"Some patches not verified: {results}"

    def test_includes_discuss_phase_assumptions(self, workflow_dir: Path) -> None:
        results = patcher.verify_patches()
        assert "discuss-phase-assumptions.md" in results

    def test_includes_all_five_workflows(self, workflow_dir: Path) -> None:
        results = patcher.verify_patches()
        expected = {
            "discuss-phase.md",
            "discuss-phase-assumptions.md",
            "plan-phase.md",
            "execute-phase.md",
            "execute-plan.md",
        }
        assert set(results.keys()) == expected


# --- patch_all tests ---


class TestPatchAll:
    def test_returns_dict_with_all_workflows(self, workflow_dir: Path) -> None:
        results = patcher.patch_all()
        assert "discuss-phase.md" in results
        assert "discuss-phase-assumptions.md" in results
        assert "plan-phase.md" in results
        assert "execute-phase.md" in results
        assert "execute-plan.md" in results

    def test_all_succeed(self, workflow_dir: Path) -> None:
        results = patcher.patch_all()
        assert all(results.values()), f"Some patches failed: {results}"

    def test_includes_discuss_phase_assumptions_key(
        self, workflow_dir: Path
    ) -> None:
        results = patcher.patch_all()
        assert "discuss-phase-assumptions.md" in results
        assert results["discuss-phase-assumptions.md"] is True
