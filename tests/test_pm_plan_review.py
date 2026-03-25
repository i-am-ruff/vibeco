"""Tests for PlanReviewer with three-check system (D-14, D-15, D-16, D-17).

Tests scope alignment, dependency readiness, and duplicate detection checks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vcompany.models.config import AgentConfig, ProjectConfig
from vcompany.strategist.models import PMDecision


def _make_config(agents: list[dict] | None = None) -> ProjectConfig:
    """Create a minimal ProjectConfig for testing."""
    if agents is None:
        agents = [
            {
                "id": "agent-1",
                "role": "backend",
                "owns": ["src/backend/"],
                "consumes": "INTERFACES.md",
                "gsd_mode": "full",
                "system_prompt": "You are a backend agent.",
            },
            {
                "id": "agent-2",
                "role": "frontend",
                "owns": ["src/frontend/"],
                "consumes": "INTERFACES.md",
                "gsd_mode": "full",
                "system_prompt": "You are a frontend agent.",
            },
        ]
    return ProjectConfig(
        project="test-project",
        repo="https://github.com/test/repo",
        agents=[AgentConfig(**a) for a in agents],
    )


def _make_plan_content(
    files_modified: list[str] | None = None,
    depends_on: list[str] | None = None,
    objective: str = "Build the feature",
) -> str:
    """Create plan content with YAML frontmatter."""
    files = files_modified or ["src/backend/api.py"]
    deps = depends_on or []
    return f"""---
phase: 01-foundation
plan: 01
files_modified:
{chr(10).join(f'  - {f}' for f in files)}
depends_on: {json.dumps(deps)}
---

<objective>
{objective}
</objective>

Implementation details here.
"""


def _setup_project_dir(
    tmp_path: Path,
    status_content: str = "# Status\n\n## agent-1\n\n- [x] **Phase 01: Foundation** -- complete\n",
    approved_plans: list[dict] | None = None,
) -> Path:
    """Create a project directory with context and state files."""
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    (context_dir / "PROJECT-STATUS.md").write_text(status_content)

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    if approved_plans:
        lines = [json.dumps(p) for p in approved_plans]
        (state_dir / "approved_plans.jsonl").write_text("\n".join(lines) + "\n")

    return tmp_path


class TestScopeCheck:
    """Tests for _scope_check: files within agent's owned_dirs."""

    def test_passes_when_files_in_owned_dirs(self, tmp_path: Path) -> None:
        """Scope check passes when plan files are within agent's owned_dirs."""
        from vcompany.strategist.plan_reviewer import PlanReviewer

        project_dir = _setup_project_dir(tmp_path)
        config = _make_config()
        reviewer = PlanReviewer(project_dir=project_dir, config=config)

        plan = _make_plan_content(files_modified=["src/backend/api.py", "src/backend/models.py"])
        result = reviewer.review_plan(agent_id="agent-1", plan_content=plan)

        assert isinstance(result, PMDecision)
        assert result.confidence.level == "HIGH"

    def test_fails_when_files_outside_owned_dirs(self, tmp_path: Path) -> None:
        """Scope check fails when plan modifies files outside agent's owned_dirs."""
        from vcompany.strategist.plan_reviewer import PlanReviewer

        project_dir = _setup_project_dir(tmp_path)
        config = _make_config()
        reviewer = PlanReviewer(project_dir=project_dir, config=config)

        plan = _make_plan_content(files_modified=["src/frontend/app.tsx", "src/backend/api.py"])
        result = reviewer.review_plan(agent_id="agent-1", plan_content=plan)

        assert result.confidence.level == "LOW"
        assert result.escalate_to == "strategist"
        assert "scope" in (result.note or "").lower() or "outside" in (result.note or "").lower()


class TestDependencyCheck:
    """Tests for _dependency_check: PROJECT-STATUS.md dependency readiness."""

    def test_passes_when_dependencies_complete(self, tmp_path: Path) -> None:
        """Dependency check passes when PROJECT-STATUS.md shows dependencies as 'complete'."""
        from vcompany.strategist.plan_reviewer import PlanReviewer

        status = "# Status\n\n## agent-1\n\n- [x] **Phase 01: Foundation** -- complete\n"
        project_dir = _setup_project_dir(tmp_path, status_content=status)
        config = _make_config()
        reviewer = PlanReviewer(project_dir=project_dir, config=config)

        plan = _make_plan_content(
            files_modified=["src/backend/api.py"],
            depends_on=["01-01"],
        )
        result = reviewer.review_plan(agent_id="agent-1", plan_content=plan)

        assert result.confidence.level == "HIGH"

    def test_fails_when_dependencies_incomplete(self, tmp_path: Path) -> None:
        """Dependency check fails when deps show as 'executing' or 'pending'."""
        from vcompany.strategist.plan_reviewer import PlanReviewer

        status = "# Status\n\n## agent-1\n\n- [ ] **Phase 01: Foundation** -- executing\n"
        project_dir = _setup_project_dir(tmp_path, status_content=status)
        config = _make_config()
        reviewer = PlanReviewer(project_dir=project_dir, config=config)

        plan = _make_plan_content(
            files_modified=["src/backend/api.py"],
            depends_on=["01-01"],
        )
        result = reviewer.review_plan(agent_id="agent-1", plan_content=plan)

        assert result.confidence.level == "LOW"
        assert result.escalate_to == "strategist"

    def test_passes_when_incomplete_but_plan_has_stubs(self, tmp_path: Path) -> None:
        """Dependency check passes when deps incomplete BUT plan mentions stubs/mocks."""
        from vcompany.strategist.plan_reviewer import PlanReviewer

        status = "# Status\n\n## agent-1\n\n- [ ] **Phase 01: Foundation** -- executing\n"
        project_dir = _setup_project_dir(tmp_path, status_content=status)
        config = _make_config()
        reviewer = PlanReviewer(project_dir=project_dir, config=config)

        plan_text = _make_plan_content(
            files_modified=["src/backend/api.py"],
            depends_on=["01-01"],
        )
        # Add stub mention to plan content
        plan_text += "\nThis plan uses stubs for the unfinished dependency.\n"
        result = reviewer.review_plan(agent_id="agent-1", plan_content=plan_text)

        assert result.confidence.level == "HIGH"


class TestDuplicateCheck:
    """Tests for _duplicate_check: no similar plan already approved."""

    def test_passes_when_no_duplicates(self, tmp_path: Path) -> None:
        """Duplicate check passes when no similar plan exists."""
        from vcompany.strategist.plan_reviewer import PlanReviewer

        project_dir = _setup_project_dir(tmp_path)
        config = _make_config()
        reviewer = PlanReviewer(project_dir=project_dir, config=config)

        plan = _make_plan_content(files_modified=["src/backend/api.py"])
        result = reviewer.review_plan(agent_id="agent-1", plan_content=plan)

        assert result.confidence.level == "HIGH"

    def test_fails_when_duplicate_exists(self, tmp_path: Path) -> None:
        """Duplicate check fails when a plan with same files already approved."""
        from vcompany.strategist.plan_reviewer import PlanReviewer

        approved = [
            {
                "agent_id": "agent-2",
                "files_modified": ["src/backend/api.py", "src/backend/models.py"],
                "objective": "Build the feature",
            }
        ]
        project_dir = _setup_project_dir(tmp_path, approved_plans=approved)
        config = _make_config()
        reviewer = PlanReviewer(project_dir=project_dir, config=config)

        plan = _make_plan_content(
            files_modified=["src/backend/api.py", "src/backend/models.py"],
            objective="Build the feature",
        )
        result = reviewer.review_plan(agent_id="agent-1", plan_content=plan)

        assert result.confidence.level == "LOW"
        assert result.escalate_to == "strategist"
        assert "duplicate" in (result.note or "").lower()


class TestReviewPlan:
    """Tests for the full review_plan method."""

    def test_all_checks_pass_returns_high_confidence(self, tmp_path: Path) -> None:
        """review_plan returns HIGH confidence when all three checks pass (D-15)."""
        from vcompany.strategist.plan_reviewer import PlanReviewer

        project_dir = _setup_project_dir(tmp_path)
        config = _make_config()
        reviewer = PlanReviewer(project_dir=project_dir, config=config)

        plan = _make_plan_content(files_modified=["src/backend/api.py"])
        result = reviewer.review_plan(agent_id="agent-1", plan_content=plan)

        assert isinstance(result, PMDecision)
        assert result.confidence.level == "HIGH"
        assert result.answer is not None
        assert "approved" in result.answer.lower()
        assert result.decided_by == "PM"
        assert result.escalate_to is None

    def test_any_check_failure_returns_low_escalation(self, tmp_path: Path) -> None:
        """review_plan returns LOW confidence and escalates on any check failure (D-16)."""
        from vcompany.strategist.plan_reviewer import PlanReviewer

        project_dir = _setup_project_dir(tmp_path)
        config = _make_config()
        reviewer = PlanReviewer(project_dir=project_dir, config=config)

        # Plan modifies files outside agent's owned dirs
        plan = _make_plan_content(files_modified=["src/frontend/app.tsx"])
        result = reviewer.review_plan(agent_id="agent-1", plan_content=plan)

        assert result.confidence.level == "LOW"
        assert result.escalate_to == "strategist"
        assert result.decided_by == "PM"
        assert result.answer is None
