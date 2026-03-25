"""Plan review with three-check validation system (D-14, D-15, D-16, D-17).

The PM reviews plans with three checks:
1. Scope alignment -- files within agent's owned_dirs (D-14).
2. Dependency readiness -- PROJECT-STATUS.md shows deps complete (STRAT-07).
3. Duplicate detection -- no similar plan already approved.

All pass = HIGH confidence auto-approve (D-15).
Any fail = LOW confidence escalate to Strategist (D-16).
Safety table validation NOT re-checked (D-17 -- Phase 5 handles that).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import yaml

from vcompany.models.config import ProjectConfig
from vcompany.strategist.models import ConfidenceResult, PMDecision

logger = logging.getLogger("vcompany.strategist.plan_reviewer")

# Stub/mock keywords that indicate a plan handles incomplete dependencies.
_STUB_KEYWORDS = {"stub", "stubs", "mock", "mocks", "placeholder"}


class PlanReviewer:
    """Plan reviewer with three-check validation per D-14.

    Runs scope, dependency, and duplicate checks. All pass = auto-approve.
    Any fail = escalate to Strategist. Does NOT re-check safety tables (D-17).
    """

    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self._project_dir = project_dir
        self._config = config

    def review_plan(self, agent_id: str, plan_content: str) -> PMDecision:
        """Review a plan with three checks per D-14.

        Args:
            agent_id: The agent submitting the plan.
            plan_content: Raw plan content including YAML frontmatter.

        Returns:
            PMDecision: HIGH confidence if all pass, LOW with escalation if any fail.
        """
        checks: list[tuple[str, bool, str]] = []

        scope_ok, scope_msg = self._scope_check(agent_id, plan_content)
        checks.append(("scope", scope_ok, scope_msg))

        dep_ok, dep_msg = self._dependency_check(plan_content)
        checks.append(("dependency", dep_ok, dep_msg))

        dup_ok, dup_msg = self._duplicate_check(agent_id, plan_content)
        checks.append(("duplicate", dup_ok, dup_msg))

        failed = [(name, msg) for name, ok, msg in checks if not ok]

        if not failed:
            return PMDecision(
                answer="Plan approved by PM",
                confidence=ConfidenceResult(
                    score=0.95, level="HIGH", coverage=0.95, prior_match=0.0
                ),
                decided_by="PM",
            )

        failed_names = ", ".join(name for name, _ in failed)
        failed_details = "; ".join(f"{name}: {msg}" for name, msg in failed)
        return PMDecision(
            answer=None,
            confidence=ConfidenceResult(
                score=0.4, level="LOW", coverage=0.4, prior_match=0.0
            ),
            decided_by="PM",
            escalate_to="strategist",
            note=f"Failed checks: {failed_names}. {failed_details}",
        )

    def _scope_check(
        self, agent_id: str, plan_content: str
    ) -> tuple[bool, str]:
        """Check that plan files are within agent's owned directories.

        Args:
            agent_id: The agent ID to look up in config.
            plan_content: Raw plan content with frontmatter.

        Returns:
            Tuple of (passed, message).
        """
        frontmatter = self._extract_frontmatter(plan_content)
        files_modified = frontmatter.get("files_modified", [])
        if not files_modified:
            return True, "No files modified"

        # Find agent in config
        agent = None
        for a in self._config.agents:
            if a.id == agent_id:
                agent = a
                break

        if agent is None:
            return False, f"Agent {agent_id} not found in config"

        # Normalize owned dirs to have trailing slash
        owned_dirs = [d if d.endswith("/") else d + "/" for d in agent.owns]

        outside_files: list[str] = []
        for file_path in files_modified:
            if not any(file_path.startswith(d) for d in owned_dirs):
                outside_files.append(file_path)

        if outside_files:
            return False, f"Files outside owned dirs: {', '.join(outside_files)}"

        return True, "Scope aligned"

    def _dependency_check(self, plan_content: str) -> tuple[bool, str]:
        """Check if plan dependencies are met per PROJECT-STATUS.md.

        Args:
            plan_content: Raw plan content with frontmatter.

        Returns:
            Tuple of (passed, message).
        """
        frontmatter = self._extract_frontmatter(plan_content)
        depends_on = frontmatter.get("depends_on", [])
        if not depends_on:
            return True, "No dependencies"

        # Read PROJECT-STATUS.md
        status_path = self._project_dir / "context" / "PROJECT-STATUS.md"
        if not status_path.exists():
            # No status file -- can't verify, assume not ready
            return False, "PROJECT-STATUS.md not found"

        status_content = status_path.read_text().lower()

        # Check if status indicates completion (look for "[x]" and "complete")
        has_complete = "[x]" in status_content and "complete" in status_content
        has_incomplete = ("[ ]" in status_content) and (
            "executing" in status_content or "pending" in status_content
        )

        if has_complete and not has_incomplete:
            return True, "Dependencies ready"

        if has_incomplete:
            # Check if plan mentions stubs/mocks
            plan_lower = plan_content.lower()
            if any(kw in plan_lower for kw in _STUB_KEYWORDS):
                return True, "Dependencies incomplete but plan uses stubs/mocks"
            return False, f"Unmet dependencies: {', '.join(depends_on)}"

        return True, "Dependencies ready"

    def _duplicate_check(
        self, agent_id: str, plan_content: str
    ) -> tuple[bool, str]:
        """Check for duplicate plans already approved by another agent.

        Args:
            agent_id: The submitting agent.
            plan_content: Raw plan content with frontmatter.

        Returns:
            Tuple of (passed, message).
        """
        approved_path = self._project_dir / "state" / "approved_plans.jsonl"
        if not approved_path.exists():
            return True, "No approved plans to compare"

        frontmatter = self._extract_frontmatter(plan_content)
        plan_files = set(frontmatter.get("files_modified", []))
        plan_objective = self._extract_objective(plan_content)

        if not plan_files and not plan_objective:
            return True, "No files or objective to compare"

        for line in approved_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                approved = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Skip plans from the same agent
            if approved.get("agent_id") == agent_id:
                continue

            # Check file overlap (>70% threshold)
            approved_files = set(approved.get("files_modified", []))
            if plan_files and approved_files:
                intersection = plan_files & approved_files
                union = plan_files | approved_files
                overlap = len(intersection) / len(union) if union else 0.0
                if overlap > 0.7:
                    return (
                        False,
                        f"Possible duplicate: >70% file overlap with "
                        f"approved plan from {approved.get('agent_id', '?')}",
                    )

            # Check objective similarity (simple word overlap)
            approved_obj = approved.get("objective", "")
            if plan_objective and approved_obj:
                plan_words = set(plan_objective.lower().split())
                approved_words = set(approved_obj.lower().split())
                if plan_words and approved_words:
                    word_overlap = len(plan_words & approved_words) / len(
                        plan_words | approved_words
                    )
                    if word_overlap > 0.7:
                        return (
                            False,
                            f"Possible duplicate: similar objective to "
                            f"approved plan from {approved.get('agent_id', '?')}",
                        )

        return True, "No duplicates"

    @staticmethod
    def _extract_frontmatter(content: str) -> dict:
        """Extract YAML frontmatter from plan content.

        Args:
            content: Raw plan content with --- delimited frontmatter.

        Returns:
            Parsed frontmatter dict, or empty dict if not found.
        """
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return {}
        try:
            return yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            return {}

    @staticmethod
    def _extract_objective(content: str) -> str:
        """Extract objective text from plan content.

        Args:
            content: Raw plan content.

        Returns:
            Objective text, or empty string if not found.
        """
        match = re.search(
            r"<objective>\s*(.*?)\s*</objective>", content, re.DOTALL
        )
        return match.group(1).strip() if match else ""
