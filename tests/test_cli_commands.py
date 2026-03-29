"""Tests for CLI commands: hire, give-task, dismiss, status, health."""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

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
