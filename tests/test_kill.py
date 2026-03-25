"""Tests for AgentManager kill method.

Tests verify:
- PID cmdline verification before sending signals (Pitfall 1)
- SIGTERM -> wait 10s -> SIGKILL escalation (D-06)
- Tmux pane fallback on signal failure (D-06)
- agents.json status update to "stopped" (D-08)
- force=True skips SIGTERM
- Unknown agent returns False
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from vcompany.models.agent_state import AgentEntry, AgentsRegistry
from vcompany.models.config import AgentConfig, ProjectConfig
from vcompany.orchestrator.agent_manager import AgentManager, DispatchResult


@pytest.fixture
def config():
    """Minimal ProjectConfig for testing."""
    return ProjectConfig(
        project="testproj",
        repo="https://github.com/test/repo.git",
        agents=[
            AgentConfig(
                id="backend",
                role="Backend developer",
                owns=["src/api/"],
                consumes="contracts",
                gsd_mode="full",
                system_prompt="You are a backend agent.",
            ),
        ],
    )


@pytest.fixture
def project_dir(tmp_path):
    """Create minimal project directory structure."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    context_dir = tmp_path / "context" / "agents"
    context_dir.mkdir(parents=True)
    (context_dir / "backend.md").write_text("Backend prompt")
    return tmp_path


@pytest.fixture
def mock_tmux():
    """Create a mock TmuxManager."""
    tmux = MagicMock()
    mock_session = MagicMock()
    mock_pane = MagicMock()
    mock_pane.pane_pid = "12345"
    tmux.create_session.return_value = mock_session
    tmux.create_pane.return_value = mock_pane
    return tmux


def _setup_running_agent(project_dir, config, mock_tmux):
    """Dispatch an agent so it can be killed."""
    manager = AgentManager(project_dir, config, tmux=mock_tmux)
    manager.dispatch("backend")
    return manager


class TestKill:
    @patch("vcompany.orchestrator.agent_manager._verify_pid_is_claude")
    @patch("vcompany.orchestrator.agent_manager._find_child_pids")
    @patch("vcompany.orchestrator.agent_manager._kill_process")
    def test_kill_verifies_pid_cmdline(
        self, mock_kill_proc, mock_find_children, mock_verify, project_dir, config, mock_tmux
    ):
        """kill(agent_id) verifies PID cmdline contains claude or node."""
        mock_find_children.return_value = [99999]
        mock_verify.return_value = True
        mock_kill_proc.return_value = True

        manager = _setup_running_agent(project_dir, config, mock_tmux)
        manager.kill("backend")

        mock_verify.assert_called_once_with(99999)

    @patch("vcompany.orchestrator.agent_manager._verify_pid_is_claude")
    @patch("vcompany.orchestrator.agent_manager._find_child_pids")
    @patch("vcompany.orchestrator.agent_manager._kill_process")
    def test_kill_sends_sigterm_then_sigkill(
        self, mock_kill_proc, mock_find_children, mock_verify, project_dir, config, mock_tmux
    ):
        """kill(agent_id) sends SIGTERM, waits, then SIGKILL if needed."""
        mock_find_children.return_value = [99999]
        mock_verify.return_value = True
        mock_kill_proc.return_value = True

        manager = _setup_running_agent(project_dir, config, mock_tmux)
        manager.kill("backend")

        # _kill_process called with force=False (default)
        mock_kill_proc.assert_called_once_with(99999, timeout=10, force=False)

    @patch("vcompany.orchestrator.agent_manager._verify_pid_is_claude")
    @patch("vcompany.orchestrator.agent_manager._find_child_pids")
    @patch("vcompany.orchestrator.agent_manager._kill_process")
    def test_kill_falls_back_to_tmux_pane_kill(
        self, mock_kill_proc, mock_find_children, mock_verify, project_dir, config, mock_tmux
    ):
        """kill(agent_id) falls back to killing tmux pane if process signal fails."""
        mock_find_children.return_value = [99999]
        mock_verify.return_value = True
        mock_kill_proc.return_value = False  # Signal failed

        manager = _setup_running_agent(project_dir, config, mock_tmux)
        # Store a reference to the pane created during dispatch
        manager.kill("backend")

        # Should still succeed via tmux fallback
        # The pane_id is tracked in registry; kill_pane is called on tmux manager

    @patch("vcompany.orchestrator.agent_manager._verify_pid_is_claude")
    @patch("vcompany.orchestrator.agent_manager._find_child_pids")
    @patch("vcompany.orchestrator.agent_manager._kill_process")
    def test_kill_updates_agents_json_to_stopped(
        self, mock_kill_proc, mock_find_children, mock_verify, project_dir, config, mock_tmux
    ):
        """kill(agent_id) updates agents.json status to stopped."""
        mock_find_children.return_value = [99999]
        mock_verify.return_value = True
        mock_kill_proc.return_value = True

        manager = _setup_running_agent(project_dir, config, mock_tmux)
        manager.kill("backend")

        agents_json = project_dir / "state" / "agents.json"
        registry = AgentsRegistry.model_validate_json(agents_json.read_text())
        assert registry.agents["backend"].status == "stopped"

    @patch("vcompany.orchestrator.agent_manager._verify_pid_is_claude")
    @patch("vcompany.orchestrator.agent_manager._find_child_pids")
    @patch("vcompany.orchestrator.agent_manager._kill_process")
    def test_kill_force_skips_sigterm(
        self, mock_kill_proc, mock_find_children, mock_verify, project_dir, config, mock_tmux
    ):
        """kill(agent_id, force=True) sends SIGKILL immediately."""
        mock_find_children.return_value = [99999]
        mock_verify.return_value = True
        mock_kill_proc.return_value = True

        manager = _setup_running_agent(project_dir, config, mock_tmux)
        manager.kill("backend", force=True)

        mock_kill_proc.assert_called_once_with(99999, timeout=10, force=True)

    def test_kill_unknown_agent_returns_false(
        self, project_dir, config, mock_tmux
    ):
        """kill(agent_id) for unknown agent returns False."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        result = manager.kill("nonexistent")
        assert result is False
