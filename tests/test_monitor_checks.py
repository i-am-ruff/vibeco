"""Tests for monitor check functions: liveness, stuck detection, plan gate."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vcompany.models.monitor_state import CheckResult
from vcompany.monitor.checks import check_liveness, check_plan_gate, check_stuck


# ---------------------------------------------------------------------------
# Liveness checks
# ---------------------------------------------------------------------------


class TestLiveness:
    """Tests for check_liveness function."""

    def test_liveness_alive(self) -> None:
        """Pane alive AND agent PID alive -> passed=True."""
        tmux = MagicMock()
        tmux.is_alive.return_value = True
        pane = MagicMock()

        with patch("vcompany.monitor.checks.os.kill") as mock_kill:
            mock_kill.return_value = None  # os.kill succeeds
            result = check_liveness("agent-1", tmux, pane, agent_pid=1234)

        assert result.passed is True
        assert result.check_type == "liveness"
        assert result.agent_id == "agent-1"
        tmux.is_alive.assert_called_once_with(pane)
        mock_kill.assert_called_once_with(1234, 0)

    def test_liveness_dead_pane(self) -> None:
        """Pane dead -> passed=False regardless of agent_pid."""
        tmux = MagicMock()
        tmux.is_alive.return_value = False
        pane = MagicMock()

        result = check_liveness("agent-1", tmux, pane, agent_pid=1234)

        assert result.passed is False
        assert result.check_type == "liveness"

    def test_liveness_pid_missing(self) -> None:
        """Pane alive but agent PID gone -> passed=False with detail."""
        tmux = MagicMock()
        tmux.is_alive.return_value = True
        pane = MagicMock()

        with patch("vcompany.monitor.checks.os.kill") as mock_kill:
            mock_kill.side_effect = ProcessLookupError("No such process")
            result = check_liveness("agent-1", tmux, pane, agent_pid=9999)

        assert result.passed is False
        assert "pane alive" in result.detail.lower() or "agent process" in result.detail.lower()

    def test_liveness_pid_none(self) -> None:
        """Pane alive and agent_pid=None (not yet tracked) -> passed=True with note."""
        tmux = MagicMock()
        tmux.is_alive.return_value = True
        pane = MagicMock()

        result = check_liveness("agent-1", tmux, pane, agent_pid=None)

        assert result.passed is True
        assert "pid" in result.detail.lower() or "not tracked" in result.detail.lower()


# ---------------------------------------------------------------------------
# Stuck detection
# ---------------------------------------------------------------------------


class TestStuck:
    """Tests for check_stuck function."""

    def test_stuck_no_commits(self) -> None:
        """No commits in repo -> stuck=True (passed=False)."""
        with patch("vcompany.monitor.checks.git_ops") as mock_git:
            mock_git.log.return_value = MagicMock(success=True, stdout="")
            result = check_stuck("agent-1", Path("/fake/clone"))

        assert result.passed is False  # stuck means check fails
        assert result.check_type == "stuck"

    def test_stuck_old_commits(self) -> None:
        """Last commit > 30 min ago -> stuck=True."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(minutes=45)

        with patch("vcompany.monitor.checks.git_ops") as mock_git:
            mock_git.log.return_value = MagicMock(
                success=True, stdout=old_time.isoformat()
            )
            result = check_stuck("agent-1", Path("/fake/clone"), now=now)

        assert result.passed is False

    def test_stuck_recent_commits(self) -> None:
        """Last commit < 30 min ago -> not stuck."""
        now = datetime.now(timezone.utc)
        recent_time = now - timedelta(minutes=5)

        with patch("vcompany.monitor.checks.git_ops") as mock_git:
            mock_git.log.return_value = MagicMock(
                success=True, stdout=recent_time.isoformat()
            )
            result = check_stuck("agent-1", Path("/fake/clone"), now=now)

        assert result.passed is True

    def test_stuck_agent_in_planning(self) -> None:
        """Agent stuck but planning -> still flags stuck but includes suppress hint."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(minutes=45)

        with patch("vcompany.monitor.checks.git_ops") as mock_git:
            mock_git.log.return_value = MagicMock(
                success=True, stdout=old_time.isoformat()
            )
            result = check_stuck("agent-1", Path("/fake/clone"), now=now)

        # Stuck is still flagged (caller decides whether to suppress)
        assert result.passed is False


# ---------------------------------------------------------------------------
# Plan gate
# ---------------------------------------------------------------------------


class TestPlanGate:
    """Tests for check_plan_gate function."""

    def test_plan_gate_no_plans(self, tmp_path: Path) -> None:
        """Empty phases dir -> no new plans."""
        phases_dir = tmp_path / ".planning" / "phases"
        phases_dir.mkdir(parents=True)

        result, mtimes = check_plan_gate("agent-1", tmp_path, {})

        assert result.passed is True
        assert result.new_plans == []
        assert result.check_type == "plan_gate"

    def test_plan_gate_old_plans(self, tmp_path: Path) -> None:
        """Plans with mtime < last_check -> no new plans."""
        phases_dir = tmp_path / ".planning" / "phases" / "01-setup"
        phases_dir.mkdir(parents=True)
        plan_file = phases_dir / "01-01-PLAN.md"
        plan_file.write_text("# Plan")

        mtime = plan_file.stat().st_mtime
        last_mtimes = {str(plan_file): mtime}

        result, new_mtimes = check_plan_gate("agent-1", tmp_path, last_mtimes)

        assert result.passed is True
        assert result.new_plans == []

    def test_plan_gate_new_plan(self, tmp_path: Path) -> None:
        """Plan file with mtime > last_check -> reports new plan."""
        phases_dir = tmp_path / ".planning" / "phases" / "01-setup"
        phases_dir.mkdir(parents=True)
        plan_file = phases_dir / "01-01-PLAN.md"
        plan_file.write_text("# Plan")

        mtime = plan_file.stat().st_mtime
        # Set last_mtimes to older value
        last_mtimes = {str(plan_file): mtime - 100}

        result, new_mtimes = check_plan_gate("agent-1", tmp_path, last_mtimes)

        assert result.passed is True
        assert str(plan_file) in result.new_plans
        assert new_mtimes[str(plan_file)] == mtime

    def test_plan_gate_first_run(self, tmp_path: Path) -> None:
        """First run (empty last_mtimes) -> seed mtimes without triggering."""
        phases_dir = tmp_path / ".planning" / "phases" / "01-setup"
        phases_dir.mkdir(parents=True)
        plan_file = phases_dir / "01-01-PLAN.md"
        plan_file.write_text("# Plan")

        result, new_mtimes = check_plan_gate("agent-1", tmp_path, {})

        # Should NOT report as new on first run (seeding)
        assert result.new_plans == []
        # But should have seeded the mtime
        assert str(plan_file) in new_mtimes


# ---------------------------------------------------------------------------
# Error isolation
# ---------------------------------------------------------------------------


class TestErrorIsolation:
    """Each check function catches exceptions and returns error result."""

    def test_check_exception_isolated_liveness(self) -> None:
        """Liveness check catches exceptions, returns error result."""
        tmux = MagicMock()
        tmux.is_alive.side_effect = RuntimeError("tmux exploded")
        pane = MagicMock()

        result = check_liveness("agent-1", tmux, pane)

        assert result.passed is False
        assert "error" in result.detail.lower() or "tmux exploded" in result.detail.lower()

    def test_check_exception_isolated_stuck(self) -> None:
        """Stuck check catches exceptions, returns error result."""
        with patch("vcompany.monitor.checks.git_ops") as mock_git:
            mock_git.log.side_effect = RuntimeError("git broke")
            result = check_stuck("agent-1", Path("/fake/clone"))

        assert result.passed is False
        assert "error" in result.detail.lower() or "git broke" in result.detail.lower()

    def test_check_exception_isolated_plan_gate(self, tmp_path: Path) -> None:
        """Plan gate catches exceptions, returns error result."""
        # Pass a non-existent path that will cause an error in glob
        bad_path = tmp_path / "nonexistent"

        result, mtimes = check_plan_gate("agent-1", bad_path, {})

        assert result.passed is False
        assert mtimes == {}
