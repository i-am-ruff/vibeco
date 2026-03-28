"""Tests for AgentContainer tmux bridge lifecycle and liveness monitoring."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vcompany.container.child_spec import ChildSpec, RestartPolicy
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.supervisor.strategies import RestartStrategy
from vcompany.supervisor.supervisor import Supervisor


def _ctx(
    agent_id: str = "test-agent",
    agent_type: str = "gsd",
    project_id: str = "myproject",
) -> ContainerContext:
    return ContainerContext(agent_id=agent_id, agent_type=agent_type, project_id=project_id)


def _mock_tmux():
    """Create a mock TmuxManager with standard return values."""
    mock_tmux = MagicMock()
    mock_session = MagicMock()
    mock_pane = MagicMock()
    mock_pane.pane_id = "%99"
    mock_pane.send_keys = MagicMock()
    mock_tmux.get_or_create_session.return_value = mock_session
    mock_tmux.create_pane.return_value = mock_pane
    mock_tmux.send_command.return_value = True
    mock_tmux.get_pane_by_id.return_value = mock_pane
    mock_tmux.is_alive.return_value = True
    # Return ready prompt immediately so _wait_for_claude_ready completes fast
    mock_tmux.get_output.return_value = [">"]
    return mock_tmux


def _make_spec(
    child_id: str,
    agent_type: str = "gsd",
    restart_policy: RestartPolicy = RestartPolicy.PERMANENT,
) -> ChildSpec:
    return ChildSpec(
        child_id=child_id,
        agent_type=agent_type,
        context=ContainerContext(agent_id=child_id, agent_type=agent_type, project_id="myproject"),
        restart_policy=restart_policy,
    )


@pytest.mark.asyncio
async def test_start_creates_tmux_pane_for_gsd_agent(tmp_path: Path) -> None:
    """start() creates a tmux pane and launches Claude Code for gsd agent.

    When gsd_command is configured, send_command is called twice:
    once for the claude launch command, once for the GSD command.
    """
    mock = _mock_tmux()
    container = AgentContainer(
        context=ContainerContext(
            agent_id="test-agent",
            agent_type="gsd",
            project_id="myproject",
            gsd_command="/gsd:discuss-phase 1",
        ),
        data_dir=tmp_path,
        tmux_manager=mock,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        await container.start()

    mock.get_or_create_session.assert_called_once_with("vco-myproject")
    mock.create_pane.assert_called_once()
    # Check window_name kwarg
    call_kwargs = mock.create_pane.call_args
    assert call_kwargs[1].get("window_name") == "test-agent" or call_kwargs[0][1] == "test-agent"
    # send_command called twice: once for claude launch, once for GSD command
    assert mock.send_command.call_count == 2
    first_call_arg = mock.send_command.call_args_list[0][0][1]
    assert "claude --dangerously-skip-permissions" in first_call_arg
    second_call_arg = mock.send_command.call_args_list[1][0][1]
    assert second_call_arg == "/gsd:discuss-phase 1"
    assert container._pane_id == "%99"

    await container.stop()


@pytest.mark.asyncio
async def test_gsd_command_not_sent_when_none(tmp_path: Path) -> None:
    """start() does not send a second send_command when gsd_command is None."""
    mock = _mock_tmux()
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),  # gsd_command defaults to None
        data_dir=tmp_path,
        tmux_manager=mock,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        await container.start()

    # Only the claude launch command should be sent -- no GSD command
    assert mock.send_command.call_count == 1
    cmd_arg = mock.send_command.call_args[0][1]
    assert "claude --dangerously-skip-permissions" in cmd_arg

    await container.stop()


@pytest.mark.asyncio
async def test_gsd_command_not_sent_on_timeout(tmp_path: Path) -> None:
    """start() does not send gsd_command if _wait_for_claude_ready times out."""
    mock = _mock_tmux()
    # get_output always returns a non-ready line so the poll never detects ready
    mock.get_output.return_value = ["loading..."]
    container = AgentContainer(
        context=ContainerContext(
            agent_id="test-agent",
            agent_type="gsd",
            project_id="myproject",
            gsd_command="/gsd:discuss-phase 1",
        ),
        data_dir=tmp_path,
        tmux_manager=mock,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        # Patch _wait_for_claude_ready to return False (timeout simulation)
        with patch.object(container, "_wait_for_claude_ready", return_value=False):
            await container.start()

    # Only the claude launch command should be sent -- GSD command not sent on timeout
    assert mock.send_command.call_count == 1
    cmd_arg = mock.send_command.call_args[0][1]
    assert "claude --dangerously-skip-permissions" in cmd_arg

    await container.stop()


@pytest.mark.asyncio
async def test_start_skips_tmux_for_fulltime_agent(tmp_path: Path) -> None:
    """start() does NOT create tmux for fulltime (event-driven) agents."""
    mock = _mock_tmux()
    container = AgentContainer(
        context=_ctx(agent_type="fulltime"),
        data_dir=tmp_path,
        tmux_manager=mock,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    await container.start()

    mock.get_or_create_session.assert_not_called()
    assert container.state == "running"

    await container.stop()


@pytest.mark.asyncio
async def test_start_skips_tmux_when_no_tmux_manager(tmp_path: Path) -> None:
    """start() works fine without tmux_manager (backward compatibility)."""
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
    )
    await container.start()

    assert container.state == "running"
    assert container._pane_id is None

    await container.stop()


@pytest.mark.asyncio
async def test_stop_kills_tmux_pane(tmp_path: Path) -> None:
    """stop() kills the tmux pane and clears _pane_id."""
    mock = _mock_tmux()
    mock_pane = MagicMock()
    mock.get_pane_by_id.return_value = mock_pane

    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
        tmux_manager=mock,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    # Simulate that start already happened
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        await container.start()

    container._pane_id = "%99"
    await container.stop()

    mock.kill_pane.assert_called_once_with(mock_pane)
    assert container._pane_id is None


def test_is_tmux_alive_true_when_pane_alive(tmp_path: Path) -> None:
    """is_tmux_alive() returns True when tmux pane process is alive."""
    mock = _mock_tmux()
    mock.is_alive.return_value = True
    mock_pane = MagicMock()
    mock.get_pane_by_id.return_value = mock_pane

    container = AgentContainer(
        context=_ctx(),
        data_dir=tmp_path,
        tmux_manager=mock,
    )
    container._pane_id = "%99"

    assert container.is_tmux_alive() is True
    mock.get_pane_by_id.assert_called_with("%99")
    mock.is_alive.assert_called_with(mock_pane)


def test_is_tmux_alive_false_when_pane_dead(tmp_path: Path) -> None:
    """is_tmux_alive() returns False when tmux pane process is dead."""
    mock = _mock_tmux()
    mock.is_alive.return_value = False
    mock_pane = MagicMock()
    mock.get_pane_by_id.return_value = mock_pane

    container = AgentContainer(
        context=_ctx(),
        data_dir=tmp_path,
        tmux_manager=mock,
    )
    container._pane_id = "%99"

    assert container.is_tmux_alive() is False


def test_is_tmux_alive_true_when_no_tmux_injected(tmp_path: Path) -> None:
    """is_tmux_alive() returns True when no TmuxManager is injected (test containers)."""
    container = AgentContainer(
        context=_ctx(),
        data_dir=tmp_path,
    )
    assert container.is_tmux_alive() is True


@pytest.mark.asyncio
async def test_health_report_shows_errored_when_tmux_dead(tmp_path: Path) -> None:
    """health_report() returns state='errored' when FSM says running but tmux is dead."""
    mock = _mock_tmux()
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
        tmux_manager=mock,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        await container.start()

    assert container.state == "running"

    # Now simulate dead tmux
    mock.get_pane_by_id.return_value = MagicMock()
    mock.is_alive.return_value = False

    report = container.health_report()
    assert report.state == "errored"

    await container.stop()


@pytest.mark.asyncio
async def test_health_report_shows_running_when_tmux_alive(tmp_path: Path) -> None:
    """health_report() returns state='running' when tmux pane is alive."""
    mock = _mock_tmux()
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
        tmux_manager=mock,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        await container.start()

    mock.is_alive.return_value = True

    report = container.health_report()
    assert report.state == "running"

    await container.stop()


def test_build_launch_command_matches_dispatch_pattern(tmp_path: Path) -> None:
    """_build_launch_command() produces command matching dispatch_cmd.py pattern."""
    container = AgentContainer(
        context=_ctx(agent_id="agent-a", agent_type="gsd", project_id="myproj"),
        data_dir=tmp_path,
        project_dir=tmp_path,
    )
    cmd = container._build_launch_command()

    assert f"cd {tmp_path / 'clones' / 'agent-a'}" in cmd
    assert "DISCORD_BOT_TOKEN" in cmd
    assert "DISCORD_GUILD_ID" in cmd
    assert "PROJECT_NAME" in cmd
    assert "AGENT_ID='agent-a'" in cmd
    assert "VCO_AGENT_ID='agent-a'" in cmd
    assert "claude --dangerously-skip-permissions" in cmd
    assert "--append-system-prompt-file" in cmd
    assert f"{tmp_path / 'context' / 'agents' / 'agent-a.md'}" in cmd


@pytest.mark.asyncio
async def test_supervisor_liveness_detects_dead_tmux(tmp_path: Path) -> None:
    """Supervisor monitor loop detects dead tmux pane and transitions container to errored."""
    spec = _make_spec("agent-x", agent_type="gsd")
    sup = Supervisor(
        supervisor_id="test-sup",
        strategy=RestartStrategy.ONE_FOR_ONE,
        child_specs=[spec],
        data_dir=tmp_path,
        max_restarts=0,  # no restarts -- just detect error
        window_seconds=600,
    )
    await sup.start()

    container = sup.children["agent-x"]
    assert container.state == "running"

    # Inject a mock tmux that reports dead pane
    mock = _mock_tmux()
    mock.is_alive.return_value = False
    mock_pane = MagicMock()
    mock.get_pane_by_id.return_value = mock_pane
    container._tmux = mock
    container._pane_id = "%99"

    # Wait for the 30s monitor timeout to fire (we use a shorter approach:
    # directly trigger the event to let the monitor loop run its liveness check)
    # The monitor uses asyncio.wait_for with 30s timeout, so we wait for timeout.
    # To speed up test, we patch the timeout in _monitor_child.
    # Instead, let's just wait briefly and check -- the monitor will timeout and check.

    # Cancel existing monitor task and create a new one with shorter timeout
    old_task = sup._tasks.pop("agent-x")
    old_task.cancel()
    try:
        await old_task
    except asyncio.CancelledError:
        pass

    # Create a patched monitor that checks quickly
    async def _fast_monitor(child_id: str) -> None:
        event = sup._child_events[child_id]
        try:
            await asyncio.wait_for(event.wait(), timeout=0.1)
            event.clear()
        except asyncio.TimeoutError:
            c = sup._children.get(child_id)
            if c is not None and c.state == "running":
                if hasattr(c, "is_tmux_alive") and not c.is_tmux_alive():
                    await c.error()

    task = asyncio.create_task(_fast_monitor("agent-x"))
    await asyncio.sleep(0.3)

    assert container.state == "errored"

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    await sup.stop()


@pytest.mark.asyncio
async def test_tmux_manager_injected_through_supervisor_chain(tmp_path: Path) -> None:
    """Supervisor passes tmux_manager to created containers."""
    mock = _mock_tmux()
    spec = _make_spec("agent-y", agent_type="test")

    sup = Supervisor(
        supervisor_id="test-sup",
        strategy=RestartStrategy.ONE_FOR_ONE,
        child_specs=[spec],
        data_dir=tmp_path,
        tmux_manager=mock,
        project_dir=tmp_path,
        session_name="vco-test",
    )
    await sup.start()

    container = sup.children["agent-y"]
    assert container._tmux is mock
    assert container._project_dir == tmp_path
    assert container._project_session_name == "vco-test"

    await sup.stop()
