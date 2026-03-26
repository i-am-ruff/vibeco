"""Tests for AgentManager dispatch and dispatch_all methods.

All tmux operations are mocked via constructor injection. Tests verify:
- Correct Claude command construction with flags and env vars
- State persistence to agents.json via write_atomic
- DispatchResult success/failure paths
- dispatch_all creates session with all agents + monitor pane
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

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
            AgentConfig(
                id="frontend",
                role="Frontend developer",
                owns=["src/ui/"],
                consumes="contracts",
                gsd_mode="full",
                system_prompt="You are a frontend agent.",
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
    # Create agent prompt files
    (context_dir / "backend.md").write_text("Backend prompt")
    (context_dir / "frontend.md").write_text("Frontend prompt")
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


class TestDispatch:
    def test_dispatch_creates_pane_and_sends_claude_command(
        self, project_dir, config, mock_tmux
    ):
        """dispatch(agent_id) creates a tmux pane and sends claude command."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        result = manager.dispatch("backend")

        assert result.success is True
        assert result.agent_id == "backend"

        # Verify send_command was called with correct flags
        send_call = mock_tmux.send_command.call_args
        cmd = send_call[0][1]
        assert "--dangerously-skip-permissions" in cmd
        assert "--append-system-prompt-file" in cmd

    def test_dispatch_sets_env_vars_before_claude(
        self, project_dir, config, mock_tmux
    ):
        """dispatch(agent_id) sets env vars chained with && in single call."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        manager.dispatch("backend")

        cmd = mock_tmux.send_command.call_args[0][1]
        assert "DISCORD_AGENT_WEBHOOK_URL" in cmd
        assert "PROJECT_NAME" in cmd
        assert "AGENT_ID" in cmd
        assert "AGENT_ROLE" in cmd
        # All chained with && (Pitfall 2)
        assert "&&" in cmd

    def test_dispatch_records_state_in_agents_json(
        self, project_dir, config, mock_tmux
    ):
        """dispatch(agent_id) records pane_id, pid, session_name, status=running."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        manager.dispatch("backend")

        # Read agents.json
        agents_json = project_dir / "state" / "agents.json"
        assert agents_json.exists()
        registry = AgentsRegistry.model_validate_json(agents_json.read_text())
        assert "backend" in registry.agents
        entry = registry.agents["backend"]
        assert entry.status == "running"
        assert entry.agent_id == "backend"

    def test_dispatch_returns_dispatch_result(
        self, project_dir, config, mock_tmux
    ):
        """dispatch(agent_id) returns DispatchResult with success=True."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        result = manager.dispatch("backend")

        assert isinstance(result, DispatchResult)
        assert result.success is True
        assert result.agent_id == "backend"
        assert result.pane_id != ""
        assert result.error == ""

    def test_dispatch_unknown_agent_returns_error(
        self, project_dir, config, mock_tmux
    ):
        """dispatch(agent_id) for unknown agent returns DispatchResult with success=False."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        result = manager.dispatch("nonexistent")

        assert result.success is False
        assert "nonexistent" in result.error

    def test_dispatch_launches_interactive_claude(
        self, project_dir, config, mock_tmux
    ):
        """dispatch(agent_id) launches Claude in interactive mode (no -p flag)."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        manager.dispatch("backend")

        cmd = mock_tmux.send_command.call_args[0][1]
        assert "claude --dangerously-skip-permissions" in cmd
        assert "-p " not in cmd  # No single-prompt mode

    def test_dispatch_does_not_embed_gsd_command(
        self, project_dir, config, mock_tmux
    ):
        """dispatch no longer embeds GSD commands — work commands sent separately."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        manager.dispatch("backend")

        cmd = mock_tmux.send_command.call_args[0][1]
        assert "/gsd:" not in cmd

    def test_dispatch_uses_append_system_prompt_file_flag(
        self, project_dir, config, mock_tmux
    ):
        """Uses --append-system-prompt-file (not --append-system-prompt) per Pitfall 4."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        manager.dispatch("backend")

        cmd = mock_tmux.send_command.call_args[0][1]
        assert "--append-system-prompt-file" in cmd


class TestDispatchAll:
    def test_dispatch_all_creates_session_and_dispatches_all_agents(
        self, project_dir, config, mock_tmux
    ):
        """dispatch_all() creates tmux session with one pane per agent."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        results = manager.dispatch_all()

        assert len(results) == 2  # Two agents in config
        assert all(r.success for r in results)
        mock_tmux.create_session.assert_called_once()

    def test_dispatch_all_returns_list_of_dispatch_results(
        self, project_dir, config, mock_tmux
    ):
        """dispatch_all() returns one DispatchResult per agent."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        results = manager.dispatch_all()

        assert isinstance(results, list)
        assert all(isinstance(r, DispatchResult) for r in results)
        agent_ids = {r.agent_id for r in results}
        assert agent_ids == {"backend", "frontend"}


class TestWaitForClaudeReady:
    """Tests for _wait_for_claude_ready with Claude-specific markers."""

    def test_detects_bypass_permissions_marker(self, project_dir, config, mock_tmux):
        """_wait_for_claude_ready returns True when 'bypass permissions' is in output."""
        mock_tmux.get_output.return_value = ["some init output", "bypass permissions mode"]
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        mock_pane = MagicMock()
        result = manager._wait_for_claude_ready(mock_pane, "backend", timeout=5)
        assert result is True

    def test_detects_tips_marker(self, project_dir, config, mock_tmux):
        """_wait_for_claude_ready returns True when 'tips:' is in output."""
        mock_tmux.get_output.return_value = ["Welcome to Claude", "Tips: press Ctrl+C"]
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        mock_pane = MagicMock()
        result = manager._wait_for_claude_ready(mock_pane, "backend", timeout=5)
        assert result is True

    def test_returns_false_on_timeout(self, project_dir, config, mock_tmux):
        """_wait_for_claude_ready returns False when no markers found."""
        mock_tmux.get_output.return_value = ["loading...", "initializing..."]
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        mock_pane = MagicMock()
        result = manager._wait_for_claude_ready(mock_pane, "backend", timeout=1)
        assert result is False

    def test_bare_angle_bracket_does_not_trigger_ready(self, project_dir, config, mock_tmux):
        """_wait_for_claude_ready does NOT match bare '>' as a ready marker."""
        mock_tmux.get_output.return_value = ["$ >", "some > output"]
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        mock_pane = MagicMock()
        result = manager._wait_for_claude_ready(mock_pane, "backend", timeout=1)
        assert result is False


class TestSendWorkCommand:
    """Tests for send_work_command with registry fallback."""

    def test_send_from_panes_dict(self, project_dir, config, mock_tmux):
        """send_work_command succeeds when agent is in _panes dict."""
        mock_tmux.send_command.return_value = True
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        mock_pane = MagicMock()
        manager._panes["backend"] = mock_pane
        result = manager.send_work_command("backend", "/gsd:plan-phase 1")
        assert result is True

    def test_falls_back_to_registry_pane_id(self, project_dir, config, mock_tmux):
        """send_work_command falls back to registry pane_id when _panes is empty."""
        mock_resolved_pane = MagicMock()
        mock_tmux.get_pane_by_id.return_value = mock_resolved_pane
        mock_tmux.send_command.return_value = True
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        # Put agent in registry with pane_id but NOT in _panes
        manager._registry.agents["backend"] = AgentEntry(
            agent_id="backend", pane_id="%5", status="running",
            session_name="vco-test", launched_at=datetime.now(timezone.utc),
        )
        result = manager.send_work_command("backend", "/gsd:plan-phase 1")
        assert result is True
        mock_tmux.get_pane_by_id.assert_called_once_with("%5")

    def test_returns_false_when_not_in_panes_or_registry(self, project_dir, config, mock_tmux):
        """send_work_command returns False when agent has no pane anywhere."""
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        result = manager.send_work_command("nonexistent", "/gsd:plan-phase 1")
        assert result is False


class TestSendWorkCommandAll:
    """Tests for send_work_command_all iterating registry agents."""

    def test_iterates_registry_agents(self, project_dir, config, mock_tmux):
        """send_work_command_all includes agents from registry, not just _panes."""
        mock_tmux.get_pane_by_id.return_value = MagicMock()
        mock_tmux.send_command.return_value = True
        manager = AgentManager(project_dir, config, tmux=mock_tmux)
        # Agent only in registry, not in _panes
        manager._registry.agents["backend"] = AgentEntry(
            agent_id="backend", pane_id="%5", status="running",
            session_name="vco-test", launched_at=datetime.now(timezone.utc),
        )
        results = manager.send_work_command_all("/gsd:execute-phase 1")
        assert "backend" in results
        assert results["backend"] is True
