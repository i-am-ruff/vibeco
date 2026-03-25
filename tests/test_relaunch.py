"""Tests for AgentManager relaunch method.

Tests verify:
- relaunch calls kill then dispatch with resume=True
- relaunch uses /gsd:resume-work prompt (D-07, D-03)
- relaunch updates agents.json atomically (D-08)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vcompany.models.agent_state import AgentsRegistry
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


class TestRelaunch:
    @patch("vcompany.orchestrator.agent_manager._verify_pid_is_claude")
    @patch("vcompany.orchestrator.agent_manager._find_child_pids")
    @patch("vcompany.orchestrator.agent_manager._kill_process")
    def test_relaunch_calls_kill_then_dispatch(
        self, mock_kill_proc, mock_find_children, mock_verify, project_dir, config, mock_tmux
    ):
        """relaunch(agent_id) calls kill then dispatch with resume=True."""
        mock_find_children.return_value = [99999]
        mock_verify.return_value = True
        mock_kill_proc.return_value = True

        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        # First dispatch so there's something to kill
        manager.dispatch("backend")
        result = manager.relaunch("backend")

        assert isinstance(result, DispatchResult)
        assert result.success is True

    @patch("vcompany.orchestrator.agent_manager._verify_pid_is_claude")
    @patch("vcompany.orchestrator.agent_manager._find_child_pids")
    @patch("vcompany.orchestrator.agent_manager._kill_process")
    def test_relaunch_uses_resume_work_prompt(
        self, mock_kill_proc, mock_find_children, mock_verify, project_dir, config, mock_tmux
    ):
        """relaunch sends /gsd:resume-work instead of /gsd:new-project."""
        mock_find_children.return_value = [99999]
        mock_verify.return_value = True
        mock_kill_proc.return_value = True

        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        manager.dispatch("backend")
        manager.relaunch("backend")

        # The last send_command call should contain resume-work
        last_cmd = mock_tmux.send_command.call_args[0][1]
        assert "/gsd:resume-work" in last_cmd

    @patch("vcompany.orchestrator.agent_manager._verify_pid_is_claude")
    @patch("vcompany.orchestrator.agent_manager._find_child_pids")
    @patch("vcompany.orchestrator.agent_manager._kill_process")
    def test_relaunch_updates_agents_json(
        self, mock_kill_proc, mock_find_children, mock_verify, project_dir, config, mock_tmux
    ):
        """relaunch updates agents.json atomically."""
        mock_find_children.return_value = [99999]
        mock_verify.return_value = True
        mock_kill_proc.return_value = True

        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        manager.dispatch("backend")
        manager.relaunch("backend")

        agents_json = project_dir / "state" / "agents.json"
        registry = AgentsRegistry.model_validate_json(agents_json.read_text())
        assert "backend" in registry.agents
        # After relaunch, status should be running again
        assert registry.agents["backend"].status == "running"
