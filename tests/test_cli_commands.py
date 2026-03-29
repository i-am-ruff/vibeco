"""Tests for CLI commands: hire, give-task, dismiss, status, health, new-project."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner


# ── Helpers ─────────────────────────────────────────────────────────

def _make_daemon_ctx(mock_client: MagicMock):
    """Create a fake daemon_client context manager yielding mock_client."""

    @contextlib.contextmanager
    def _fake():
        yield mock_client

    return _fake


# ── CRUD command tests ──────────────────────────────────────────────

def test_hire_calls_daemon():
    from vcompany.cli.hire_cmd import hire

    mock_client = MagicMock()
    mock_client.call.return_value = {"agent_id": "my-agent"}

    with patch("vcompany.cli.hire_cmd.daemon_client", _make_daemon_ctx(mock_client)):
        result = CliRunner().invoke(hire, ["gsd", "my-agent"])

    assert result.exit_code == 0, result.output + (result.stderr or "")
    mock_client.call.assert_called_once_with("hire", {"agent_id": "my-agent", "template": "gsd"})
    assert "my-agent" in result.output


def test_give_task_calls_daemon():
    from vcompany.cli.give_task_cmd import give_task

    mock_client = MagicMock()
    mock_client.call.return_value = {"status": "ok"}

    with patch("vcompany.cli.give_task_cmd.daemon_client", _make_daemon_ctx(mock_client)):
        result = CliRunner().invoke(give_task, ["my-agent", "build feature"])

    assert result.exit_code == 0, result.output + (result.stderr or "")
    mock_client.call.assert_called_once_with("give_task", {"agent_id": "my-agent", "task": "build feature"})
    assert "my-agent" in result.output


def test_dismiss_calls_daemon():
    from vcompany.cli.dismiss_cmd import dismiss

    mock_client = MagicMock()
    mock_client.call.return_value = {"status": "ok"}

    with patch("vcompany.cli.dismiss_cmd.daemon_client", _make_daemon_ctx(mock_client)):
        result = CliRunner().invoke(dismiss, ["my-agent"])

    assert result.exit_code == 0, result.output + (result.stderr or "")
    mock_client.call.assert_called_once_with("dismiss", {"agent_id": "my-agent"})
    assert "my-agent" in result.output


def test_daemon_not_running_hire():
    from vcompany.cli.hire_cmd import hire

    with patch("vcompany.cli.helpers.DaemonClient") as MockDC:
        MockDC.return_value.connect.side_effect = ConnectionRefusedError
        result = CliRunner().invoke(hire, ["gsd", "my-agent"])

    assert result.exit_code != 0
    assert "Daemon not running" in result.stderr


def test_daemon_not_running_give_task():
    from vcompany.cli.give_task_cmd import give_task

    with patch("vcompany.cli.helpers.DaemonClient") as MockDC:
        MockDC.return_value.connect.side_effect = FileNotFoundError
        result = CliRunner().invoke(give_task, ["my-agent", "build"])

    assert result.exit_code != 0
    assert "Daemon not running" in result.stderr


def test_daemon_not_running_dismiss():
    from vcompany.cli.dismiss_cmd import dismiss

    with patch("vcompany.cli.helpers.DaemonClient") as MockDC:
        MockDC.return_value.connect.side_effect = ConnectionRefusedError
        result = CliRunner().invoke(dismiss, ["my-agent"])

    assert result.exit_code != 0
    assert "Daemon not running" in result.stderr


def test_rpc_error_hire():
    from vcompany.cli.hire_cmd import hire

    with patch("vcompany.cli.helpers.DaemonClient") as MockDC:
        mock_instance = MockDC.return_value
        mock_instance.call.side_effect = RuntimeError("Agent already exists")
        result = CliRunner().invoke(hire, ["gsd", "my-agent"])

    assert result.exit_code != 0
    assert "Agent already exists" in result.stderr


# ── Status command tests ────────────────────────────────────────────

def test_status_renders():
    from vcompany.cli.status_cmd import status

    mock_client = MagicMock()
    mock_client.call.return_value = {
        "projects": {"my-project": {"agents": 3}},
        "company_agents": ["strategist"],
    }

    with patch("vcompany.cli.status_cmd.daemon_client", _make_daemon_ctx(mock_client)):
        result = CliRunner().invoke(status, [])

    assert result.exit_code == 0, result.output + (result.stderr or "")
    mock_client.call.assert_called_once_with("status")
    assert "my-project" in result.output
    assert "strategist" in result.output


def test_status_empty():
    from vcompany.cli.status_cmd import status

    mock_client = MagicMock()
    mock_client.call.return_value = {"projects": {}, "company_agents": []}

    with patch("vcompany.cli.status_cmd.daemon_client", _make_daemon_ctx(mock_client)):
        result = CliRunner().invoke(status, [])

    assert result.exit_code == 0
    assert "No active projects or agents" in result.output


# ── Health command tests ────────────────────────────────────────────

def test_health_renders():
    from vcompany.cli.health_cmd import health

    mock_client = MagicMock()
    mock_client.call.return_value = {
        "supervisor_id": "company-root",
        "state": "running",
        "projects": [],
        "company_agents": [],
    }

    with patch("vcompany.cli.health_cmd.daemon_client", _make_daemon_ctx(mock_client)):
        result = CliRunner().invoke(health, [])

    assert result.exit_code == 0, result.output + (result.stderr or "")
    mock_client.call.assert_called_once_with("health_tree")
    assert "company-root" in result.output


def test_health_shows_agent_states():
    from vcompany.cli.health_cmd import health

    mock_client = MagicMock()
    mock_client.call.return_value = {
        "supervisor_id": "company-root",
        "state": "running",
        "projects": [
            {
                "supervisor_id": "proj-1",
                "state": "running",
                "children": [
                    {
                        "report": {
                            "agent_id": "agent-a",
                            "state": "running",
                            "inner_state": "working",
                            "uptime": 120.5,
                            "error_count": 0,
                            "blocked_reason": None,
                            "is_idle": False,
                        }
                    }
                ],
            }
        ],
        "company_agents": [
            {
                "report": {
                    "agent_id": "strategist",
                    "state": "idle",
                    "inner_state": "waiting",
                    "uptime": 300.0,
                    "error_count": 0,
                    "blocked_reason": None,
                    "is_idle": True,
                }
            }
        ],
    }

    with patch("vcompany.cli.health_cmd.daemon_client", _make_daemon_ctx(mock_client)):
        result = CliRunner().invoke(health, [])

    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "agent-a" in result.output
    assert "strategist" in result.output


# ── Daemon new_project handler tests ─────────────────────────────

def test_handle_new_project_calls_runtime_api(tmp_path):
    """Handler loads config from project_dir/agents.yaml, calls RuntimeAPI.new_project, wires strategist cog."""
    from vcompany.daemon.daemon import Daemon

    # Create agents.yaml in tmp project dir
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        "project: test-proj\n"
        "repo: https://github.com/test/test\n"
        "agents:\n"
        "  - id: dev1\n"
        "    role: developer\n"
        "    owns: [src/]\n"
        "    consumes: all\n"
        "    gsd_mode: full\n"
        "    system_prompt: Build stuff\n"
        "    type: gsd\n"
    )

    mock_bot = MagicMock()
    mock_runtime_api = AsyncMock()
    mock_runtime_api.new_project = AsyncMock()
    mock_runtime_api._strategist_container = MagicMock()

    mock_strategist_cog = MagicMock()
    mock_bot.get_cog.return_value = mock_strategist_cog

    daemon = Daemon(bot=mock_bot, bot_token="fake")
    daemon._runtime_api = mock_runtime_api

    result = asyncio.get_event_loop().run_until_complete(
        daemon._handle_new_project({"project_dir": str(tmp_path)})
    )

    assert result["status"] == "ok"
    assert result["project"] == "test-proj"
    mock_runtime_api.new_project.assert_awaited_once()
    # Verify strategist cog wiring
    mock_bot.get_cog.assert_called_with("StrategistCog")
    mock_strategist_cog.set_company_agent.assert_called_once_with(
        mock_runtime_api._strategist_container
    )


def test_handle_new_project_no_runtime_api():
    """Handler raises RuntimeError if RuntimeAPI not initialized."""
    from vcompany.daemon.daemon import Daemon

    mock_bot = MagicMock()
    daemon = Daemon(bot=mock_bot, bot_token="fake")
    daemon._runtime_api = None

    with __import__("pytest").raises(RuntimeError, match="RuntimeAPI not initialized"):
        asyncio.get_event_loop().run_until_complete(
            daemon._handle_new_project({"project_dir": "/some/path"})
        )


def test_handle_new_project_no_config(tmp_path):
    """Handler raises FileNotFoundError if agents.yaml not found at project_dir."""
    from vcompany.daemon.daemon import Daemon

    mock_bot = MagicMock()
    mock_runtime_api = AsyncMock()
    daemon = Daemon(bot=mock_bot, bot_token="fake")
    daemon._runtime_api = mock_runtime_api

    with __import__("pytest").raises(FileNotFoundError):
        asyncio.get_event_loop().run_until_complete(
            daemon._handle_new_project({"project_dir": str(tmp_path)})
        )


# ── new-project CLI command tests ────────────────────────────────

def test_new_project_registered():
    """new-project command is registered in CLI group."""
    from vcompany.cli.main import cli
    assert "new-project" in [c.name for c in cli.commands.values()]


def test_new_project_composite(tmp_path, monkeypatch):
    """vco new-project runs init logic, clone logic, then calls daemon new_project."""
    from vcompany.cli.new_project_cmd import new_project

    # Create a config file
    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        "project: test-proj\n"
        "repo: https://github.com/test/repo\n"
        "agents:\n"
        "  - id: dev1\n"
        "    role: developer\n"
        "    owns: [src/]\n"
        "    consumes: all\n"
        "    gsd_mode: full\n"
        "    system_prompt: Build\n"
        "    type: gsd\n"
    )

    project_base = tmp_path / "projects"
    project_base.mkdir()
    monkeypatch.setattr("vcompany.cli.new_project_cmd.PROJECTS_BASE", project_base)

    # Mock git clone to create the dir and return success
    def fake_clone(repo, dest):
        dest.mkdir(parents=True, exist_ok=True)
        return MagicMock(success=True)

    monkeypatch.setattr("vcompany.cli.new_project_cmd.git.clone", fake_clone)

    mock_git_branch = MagicMock()
    mock_git_branch.return_value = MagicMock(success=True)
    monkeypatch.setattr("vcompany.cli.new_project_cmd.git.checkout_new_branch", mock_git_branch)

    # Mock _deploy_artifacts since it needs real git repo structure
    monkeypatch.setattr("vcompany.cli.new_project_cmd._deploy_artifacts", lambda *a, **kw: None)

    # Mock daemon client
    mock_client = MagicMock()
    mock_client.call.return_value = {"status": "ok", "project": "test-proj"}

    with patch("vcompany.cli.new_project_cmd.daemon_client", _make_daemon_ctx(mock_client)):
        result = CliRunner().invoke(new_project, ["test-proj", "--config", str(config_file)])

    assert result.exit_code == 0, result.output + (result.stderr or "")
    # Verify daemon was called with new_project
    mock_client.call.assert_called_once()
    call_args = mock_client.call.call_args
    assert call_args[0][0] == "new_project"
    assert "project_dir" in call_args[0][1]


def test_new_project_existing_project(tmp_path, monkeypatch):
    """Command exits 1 if project directory already exists."""
    from vcompany.cli.new_project_cmd import new_project

    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        "project: test-proj\nrepo: https://github.com/t/t\nagents:\n"
        "  - id: d\n    role: dev\n    owns: [s/]\n    consumes: all\n"
        "    gsd_mode: full\n    system_prompt: x\n    type: gsd\n"
    )

    project_base = tmp_path / "projects"
    project_base.mkdir()
    # Pre-create project dir
    (project_base / "existing").mkdir()
    monkeypatch.setattr("vcompany.cli.new_project_cmd.PROJECTS_BASE", project_base)

    result = CliRunner().invoke(new_project, ["existing", "--config", str(config_file)])
    assert result.exit_code != 0


def test_new_project_daemon_not_running(tmp_path, monkeypatch):
    """Command runs init and clone, fails at daemon call with warning."""
    from vcompany.cli.new_project_cmd import new_project

    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        "project: test-proj\nrepo: https://github.com/t/t\nagents:\n"
        "  - id: d\n    role: dev\n    owns: [s/]\n    consumes: all\n"
        "    gsd_mode: full\n    system_prompt: x\n    type: gsd\n"
    )

    project_base = tmp_path / "projects"
    project_base.mkdir()
    monkeypatch.setattr("vcompany.cli.new_project_cmd.PROJECTS_BASE", project_base)

    def fake_clone(repo, dest):
        dest.mkdir(parents=True, exist_ok=True)
        return MagicMock(success=True)

    monkeypatch.setattr("vcompany.cli.new_project_cmd.git.clone", fake_clone)

    mock_git_branch = MagicMock()
    mock_git_branch.return_value = MagicMock(success=True)
    monkeypatch.setattr("vcompany.cli.new_project_cmd.git.checkout_new_branch", mock_git_branch)

    monkeypatch.setattr("vcompany.cli.new_project_cmd._deploy_artifacts", lambda *a, **kw: None)

    # Daemon client raises SystemExit(1) like the real daemon_client helper does
    @contextlib.contextmanager
    def _fail_client():
        raise SystemExit(1)
        yield  # noqa: unreachable

    with patch("vcompany.cli.new_project_cmd.daemon_client", _fail_client):
        result = CliRunner().invoke(new_project, ["test-proj", "--config", str(config_file)])

    # Should succeed (init+clone done) but warn about daemon
    assert result.exit_code == 0
    assert "daemon" in result.output.lower() or "vco up" in result.output.lower()
