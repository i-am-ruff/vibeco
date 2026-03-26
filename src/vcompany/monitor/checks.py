"""Individual monitor check functions: liveness, stuck detection, plan gate.

Each check function is independent and wrapped in try/except so that one
failure does not affect others. All return CheckResult instances.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vcompany.git import ops as git_ops
from vcompany.models.monitor_state import CheckResult
from vcompany.monitor.status_generator import parse_roadmap
from vcompany.tmux.session import TmuxManager

logger = logging.getLogger("vcompany.monitor.checks")


def check_liveness(
    agent_id: str,
    tmux: TmuxManager,
    pane: object,
    agent_pid: int | None = None,
) -> CheckResult:
    """Check if an agent is alive (tmux pane + agent process PID).

    Per D-02, liveness verifies BOTH:
    1. tmux pane shell is alive (via TmuxManager.is_alive which checks pane PID)
    2. Claude Code agent process PID is alive (via os.kill signal 0)

    Args:
        agent_id: Agent identifier.
        tmux: TmuxManager instance.
        pane: libtmux Pane object.
        agent_pid: Claude Code process PID (distinct from tmux pane PID).
                   None if not yet recorded.

    Returns:
        CheckResult with passed=True if agent is alive.
    """
    try:
        # Step 1: Check tmux pane is alive
        if not tmux.is_alive(pane):
            return CheckResult(
                check_type="liveness",
                agent_id=agent_id,
                passed=False,
                detail="Tmux pane is dead",
            )

        # Step 2: If agent_pid provided, verify the agent process is alive
        if agent_pid is not None:
            try:
                os.kill(agent_pid, 0)
            except ProcessLookupError:
                return CheckResult(
                    check_type="liveness",
                    agent_id=agent_id,
                    passed=False,
                    detail=f"Pane alive but agent process (PID {agent_pid}) is dead",
                )
            except OSError as exc:
                return CheckResult(
                    check_type="liveness",
                    agent_id=agent_id,
                    passed=False,
                    detail=f"Pane alive but agent process PID check failed: {exc}",
                )

            return CheckResult(
                check_type="liveness",
                agent_id=agent_id,
                passed=True,
                detail="Pane and agent process alive",
            )

        # Step 3: agent_pid is None (not yet tracked)
        return CheckResult(
            check_type="liveness",
            agent_id=agent_id,
            passed=True,
            detail="Pane alive; agent PID not tracked yet",
        )

    except Exception as exc:
        logger.exception("Liveness check error for %s", agent_id)
        return CheckResult(
            check_type="liveness",
            agent_id=agent_id,
            passed=False,
            detail=f"Liveness check error: {exc}",
        )


def check_stuck(
    agent_id: str,
    clone_dir: Path,
    *,
    threshold_minutes: int = 30,
    now: datetime | None = None,
) -> CheckResult:
    """Check if an agent is stuck (no git commits for threshold_minutes).

    Uses git log to get the latest commit timestamp. If the commit is older
    than threshold_minutes, the agent is considered stuck.

    Args:
        agent_id: Agent identifier.
        clone_dir: Path to agent's git clone.
        threshold_minutes: Minutes without commits before flagging stuck.
        now: Current time (injectable for testing).

    Returns:
        CheckResult with passed=False if agent is stuck.
    """
    try:
        if now is None:
            now = datetime.now(timezone.utc)

        result = git_ops.log(clone_dir, args=["--format=%aI", "-1"])

        if not result.success or not result.stdout.strip():
            # No commits yet (fresh clone or empty repo) — cannot determine
            # stuck-ness without a baseline commit, so treat as not-stuck.
            return CheckResult(
                check_type="stuck",
                agent_id=agent_id,
                passed=True,
                detail="No commits found yet — skipping stuck check",
            )

        # Parse ISO timestamp from git log
        commit_time_str = result.stdout.strip()
        commit_time = datetime.fromisoformat(commit_time_str)

        # Ensure timezone-aware comparison
        if commit_time.tzinfo is None:
            commit_time = commit_time.replace(tzinfo=timezone.utc)

        elapsed = now - commit_time
        threshold = timedelta(minutes=threshold_minutes)

        if elapsed > threshold:
            minutes_ago = int(elapsed.total_seconds() / 60)
            return CheckResult(
                check_type="stuck",
                agent_id=agent_id,
                passed=False,
                detail=f"Last commit {minutes_ago} minutes ago (threshold: {threshold_minutes}m)",
            )

        return CheckResult(
            check_type="stuck",
            agent_id=agent_id,
            passed=True,
            detail=f"Last commit {int(elapsed.total_seconds() / 60)} minutes ago",
        )

    except Exception as exc:
        logger.exception("Stuck check error for %s", agent_id)
        return CheckResult(
            check_type="stuck",
            agent_id=agent_id,
            passed=False,
            detail=f"Stuck check error: {exc}",
        )


def check_plan_gate(
    agent_id: str,
    clone_dir: Path,
    last_plan_mtimes: dict[str, float],
) -> tuple[CheckResult, dict[str, float]]:
    """Check for new or modified PLAN.md files in the agent's clone.

    Scans .planning/phases/ for *-PLAN.md files and compares their mtime
    against the last known mtimes. On first run (empty last_plan_mtimes),
    seeds all current mtimes without reporting as new.

    Args:
        agent_id: Agent identifier.
        clone_dir: Path to agent's git clone.
        last_plan_mtimes: Previous mtime mapping (path -> mtime).

    Returns:
        Tuple of (CheckResult, updated_mtimes_dict).
    """
    try:
        phases_dir = clone_dir / ".planning" / "phases"

        if not phases_dir.exists():
            return (
                CheckResult(
                    check_type="plan_gate",
                    agent_id=agent_id,
                    passed=True,
                    detail="No phases directory found",
                ),
                {},
            )

        # Scan for all PLAN.md files
        current_mtimes: dict[str, float] = {}
        for plan_file in sorted(phases_dir.rglob("*-PLAN.md")):
            current_mtimes[str(plan_file)] = plan_file.stat().st_mtime

        # First run: seed mtimes without triggering
        is_first_run = len(last_plan_mtimes) == 0
        if is_first_run:
            return (
                CheckResult(
                    check_type="plan_gate",
                    agent_id=agent_id,
                    passed=True,
                    detail=f"First run: seeded {len(current_mtimes)} plan mtimes",
                    new_plans=[],
                ),
                current_mtimes,
            )

        # Compare mtimes to find new or modified plans
        new_plans: list[str] = []
        for path, mtime in current_mtimes.items():
            if path not in last_plan_mtimes or mtime > last_plan_mtimes[path]:
                new_plans.append(path)

        detail = f"Found {len(new_plans)} new/modified plan(s)" if new_plans else "No new plans"

        return (
            CheckResult(
                check_type="plan_gate",
                agent_id=agent_id,
                passed=True,
                detail=detail,
                new_plans=new_plans,
            ),
            current_mtimes,
        )

    except Exception as exc:
        logger.exception("Plan gate check error for %s", agent_id)
        return (
            CheckResult(
                check_type="plan_gate",
                agent_id=agent_id,
                passed=False,
                detail=f"Plan gate check error: {exc}",
            ),
            {},
        )


def check_phase_completion(
    agent_id: str,
    clone_dir: Path,
    previous_phase_status: str,
) -> tuple[str, str]:
    """Check if the agent's current phase has been completed.

    Parses ROADMAP.md to determine the current executing phase and its status.
    Returns the current phase identifier and status so the monitor can detect
    transitions to "completed" and trigger auto-checkin.

    Args:
        agent_id: Agent identifier.
        clone_dir: Path to agent's git clone.
        previous_phase_status: The phase_status from the previous cycle.

    Returns:
        Tuple of (current_phase, phase_status) where phase_status is one of:
        "executing", "completed", "unknown".
    """
    try:
        roadmap_path = clone_dir / ".planning" / "ROADMAP.md"
        if not roadmap_path.exists():
            return ("unknown", "unknown")

        phases = parse_roadmap(roadmap_path)
        if not phases or phases[0]["status"] == "unknown":
            return ("unknown", "unknown")

        # Find the currently executing phase
        executing = [p for p in phases if p["status"] == "executing"]
        completed = [p for p in phases if p["status"] == "complete"]

        if executing:
            phase_id = f"Phase {executing[0]['number']}"
            return (phase_id, "executing")

        # No executing phase — all phases either complete or pending.
        # If we were previously executing, that means the phase just completed.
        if completed and previous_phase_status == "executing":
            last_done = completed[-1]
            phase_id = f"Phase {last_done['number']}"
            return (phase_id, "completed")

        # All done or nothing started
        if completed and not executing:
            last_done = completed[-1]
            return (f"Phase {last_done['number']}", "completed")

        return ("unknown", "unknown")

    except Exception:
        logger.exception("Phase completion check error for %s", agent_id)
        return ("unknown", "unknown")
