"""Tests for AgentContainer transport bridge lifecycle and liveness monitoring."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vcompany.container.child_spec import ChildSpec, RestartPolicy
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.supervisor.strategies import RestartStrategy
from vcompany.supervisor.supervisor import Supervisor
from vcompany.transport.protocol import NoopTransport


def _ctx(
    agent_id: str = "test-agent",
    agent_type: str = "gsd",
    project_id: str = "myproject",
    uses_tmux: bool = True,
) -> ContainerContext:
    return ContainerContext(
        agent_id=agent_id, agent_type=agent_type, project_id=project_id, uses_tmux=uses_tmux,
    )


class MockTransport:
    """Mock transport implementing AgentTransport for testing."""

    def __init__(self) -> None:
        self.setup_calls: list[tuple] = []
        self.exec_calls: list[tuple] = []
        self.teardown_calls: list[str] = []
        self.send_keys_calls: list[tuple] = []
        self._alive: dict[str, bool] = {}

    async def setup(self, agent_id: str, working_dir: Path, **kwargs) -> None:
        self.setup_calls.append((agent_id, working_dir, kwargs))
        self._alive[agent_id] = True

    async def teardown(self, agent_id: str) -> None:
        self.teardown_calls.append(agent_id)
        self._alive.pop(agent_id, None)

    async def exec(self, agent_id: str, command, *, stdin=None, timeout=None) -> str:
        self.exec_calls.append((agent_id, command, stdin, timeout))
        return ""

    async def exec_streaming(self, agent_id, command, *, stdin=None):
        return
        yield  # async generator

    def is_alive(self, agent_id: str) -> bool:
        return self._alive.get(agent_id, False)

    async def send_keys(self, agent_id: str, keys: str, *, enter: bool = False) -> None:
        self.send_keys_calls.append((agent_id, keys, enter))

    async def read_file(self, agent_id: str, path: Path) -> str:
        return ""

    async def write_file(self, agent_id: str, path: Path, content: str) -> None:
        pass


def _make_spec(
    child_id: str,
    agent_type: str = "gsd",
    restart_policy: RestartPolicy = RestartPolicy.PERMANENT,
) -> ChildSpec:
    return ChildSpec(
        child_id=child_id,
        agent_type=agent_type,
        context=ContainerContext(
            agent_id=child_id, agent_type=agent_type, project_id="myproject",
            uses_tmux=agent_type in ("gsd", "continuous", "task"),
        ),
        restart_policy=restart_policy,
    )


@pytest.mark.asyncio
async def test_start_sets_up_transport_for_gsd_agent(tmp_path: Path) -> None:
    """start() calls transport.setup() and transport.exec() for gsd agents."""
    transport = MockTransport()
    container = AgentContainer(
        context=ContainerContext(
            agent_id="test-agent",
            agent_type="gsd",
            project_id="myproject",
            gsd_command="/gsd:discuss-phase 1",
            uses_tmux=True,
        ),
        data_dir=tmp_path,
        transport=transport,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        await container.start()

    assert len(transport.setup_calls) == 1
    agent_id, working_dir, kwargs = transport.setup_calls[0]
    assert agent_id == "test-agent"
    assert kwargs.get("interactive") is True
    assert kwargs.get("session_name") == "vco-myproject"

    # exec called with launch command
    assert len(transport.exec_calls) == 1
    cmd = transport.exec_calls[0][1]
    assert "claude --dangerously-skip-permissions" in cmd
    assert "/gsd:discuss-phase 1" in cmd

    # send_keys called for workspace trust
    assert len(transport.send_keys_calls) == 1
    assert transport.send_keys_calls[0][2] is True  # enter=True

    await container.stop()


@pytest.mark.asyncio
async def test_gsd_command_not_sent_when_none(tmp_path: Path) -> None:
    """start() launches claude without prompt arg when gsd_command is None."""
    transport = MockTransport()
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
        transport=transport,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        await container.start()

    cmd = transport.exec_calls[0][1]
    assert "claude --dangerously-skip-permissions" in cmd
    assert "/gsd:" not in cmd

    await container.stop()


@pytest.mark.asyncio
async def test_start_skips_transport_for_fulltime_agent(tmp_path: Path) -> None:
    """start() does NOT set up transport for fulltime (event-driven) agents."""
    transport = MockTransport()
    container = AgentContainer(
        context=_ctx(agent_type="fulltime", uses_tmux=False),
        data_dir=tmp_path,
        transport=transport,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    await container.start()

    assert len(transport.setup_calls) == 0
    assert container.state == "running"

    await container.stop()


@pytest.mark.asyncio
async def test_start_skips_transport_when_no_transport(tmp_path: Path) -> None:
    """start() works fine without transport (backward compatibility)."""
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
    )
    await container.start()

    assert container.state == "running"

    await container.stop()


@pytest.mark.asyncio
async def test_stop_teardowns_transport(tmp_path: Path) -> None:
    """stop() calls transport.teardown()."""
    transport = MockTransport()
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
        transport=transport,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        await container.start()

    await container.stop()

    assert "test-agent" in transport.teardown_calls


def test_is_alive_true_when_transport_alive(tmp_path: Path) -> None:
    """is_alive() returns True when transport reports alive."""
    transport = MockTransport()
    transport._alive["test-agent"] = True
    container = AgentContainer(
        context=_ctx(),
        data_dir=tmp_path,
        transport=transport,
    )
    assert container.is_alive() is True


def test_is_alive_false_when_transport_dead(tmp_path: Path) -> None:
    """is_alive() returns False when transport reports dead."""
    transport = MockTransport()
    transport._alive["test-agent"] = False
    container = AgentContainer(
        context=_ctx(),
        data_dir=tmp_path,
        transport=transport,
    )
    assert container.is_alive() is False


def test_is_alive_true_when_no_transport(tmp_path: Path) -> None:
    """is_alive() returns True when no transport is injected (test containers)."""
    container = AgentContainer(
        context=_ctx(),
        data_dir=tmp_path,
    )
    assert container.is_alive() is True


def test_is_tmux_alive_backward_compat(tmp_path: Path) -> None:
    """is_tmux_alive() still works as backward-compat alias."""
    container = AgentContainer(
        context=_ctx(),
        data_dir=tmp_path,
    )
    assert container.is_tmux_alive() is True


@pytest.mark.asyncio
async def test_health_report_shows_errored_when_transport_dead(tmp_path: Path) -> None:
    """health_report() returns state='errored' when FSM says running but transport is dead."""
    transport = MockTransport()
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
        transport=transport,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        await container.start()

    assert container.state == "running"

    # Simulate dead transport
    transport._alive["test-agent"] = False

    report = container.health_report()
    assert report.state == "errored"

    await container.stop()


@pytest.mark.asyncio
async def test_health_report_shows_running_when_transport_alive(tmp_path: Path) -> None:
    """health_report() returns state='running' when transport is alive."""
    transport = MockTransport()
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
        transport=transport,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        await container.start()

    report = container.health_report()
    assert report.state == "running"

    await container.stop()


@pytest.mark.asyncio
async def test_health_report_includes_idle_state(tmp_path: Path) -> None:
    """health_report() includes is_idle field for transport agents."""
    transport = MockTransport()
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
        transport=transport,
        project_dir=tmp_path,
        project_session_name="vco-myproject",
    )
    with patch("vcompany.container.container.asyncio.sleep", return_value=None):
        await container.start()

    # Push-based signal: set idle via _handle_signal
    await container._handle_signal("idle")
    report = container.health_report()
    assert report.is_idle is True

    # Push-based signal: set ready (not idle)
    await container._handle_signal("ready")
    report = container.health_report()
    assert report.is_idle is False

    await container.stop()


def test_build_launch_command_includes_gsd_prompt(tmp_path: Path) -> None:
    """_build_launch_command() embeds gsd_command as positional prompt arg."""
    container = AgentContainer(
        context=ContainerContext(
            agent_id="agent-a",
            agent_type="gsd",
            project_id="myproj",
            gsd_command="/gsd:discuss-phase 1",
            uses_tmux=True,
        ),
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
    assert "'/gsd:discuss-phase 1'" in cmd


def test_build_launch_command_no_prompt_without_gsd_command(tmp_path: Path) -> None:
    """_build_launch_command() omits prompt arg when gsd_command is None."""
    container = AgentContainer(
        context=_ctx(agent_id="agent-a", agent_type="gsd", project_id="myproj"),
        data_dir=tmp_path,
        project_dir=tmp_path,
    )
    cmd = container._build_launch_command()

    assert "claude --dangerously-skip-permissions" in cmd
    assert cmd.rstrip().endswith(f"{tmp_path / 'context' / 'agents' / 'agent-a.md'}")


@pytest.mark.asyncio
async def test_handle_signal_sets_idle(tmp_path: Path) -> None:
    """_handle_signal('idle') sets _is_idle to True."""
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
    )
    await container._handle_signal("idle")
    assert container._is_idle is True
    assert container.is_idle is True


@pytest.mark.asyncio
async def test_handle_signal_ready_clears_idle(tmp_path: Path) -> None:
    """_handle_signal('ready') sets _is_idle to False."""
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
    )
    container._is_idle = True
    await container._handle_signal("ready")
    assert container._is_idle is False


@pytest.mark.asyncio
async def test_handle_signal_drains_queue(tmp_path: Path) -> None:
    """_handle_signal('idle') drains the task queue."""
    transport = MockTransport()
    container = AgentContainer(
        context=_ctx(agent_type="gsd"),
        data_dir=tmp_path,
        transport=transport,
    )
    await container._task_queue.put("do something")
    await container._handle_signal("idle")

    assert len(transport.exec_calls) == 1
    assert transport.exec_calls[0][1] == "do something"
    assert container._is_idle is False  # was cleared by drain


@pytest.mark.asyncio
async def test_supervisor_liveness_detects_dead_transport(tmp_path: Path) -> None:
    """Supervisor monitor loop detects dead transport and transitions container to errored."""
    # Use a non-tmux agent type so start() doesn't try to launch
    spec = _make_spec("agent-x", agent_type="test")
    sup = Supervisor(
        supervisor_id="test-sup",
        strategy=RestartStrategy.ONE_FOR_ONE,
        child_specs=[spec],
        data_dir=tmp_path,
        max_restarts=0,
        window_seconds=600,
    )
    await sup.start()

    container = sup.children["agent-x"]
    assert container.state == "running"

    # Inject a mock transport that reports dead
    transport = MockTransport()
    transport._alive["agent-x"] = False
    container._transport = transport

    # Cancel existing monitor task and create a new one with shorter timeout
    old_task = sup._tasks.pop("agent-x")
    old_task.cancel()
    try:
        await old_task
    except asyncio.CancelledError:
        pass

    async def _fast_monitor(child_id: str) -> None:
        event = sup._child_events[child_id]
        try:
            await asyncio.wait_for(event.wait(), timeout=0.1)
            event.clear()
        except asyncio.TimeoutError:
            c = sup._children.get(child_id)
            if c is not None and c.state == "running":
                if hasattr(c, "is_alive") and not c.is_alive():
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
async def test_transport_deps_injected_through_supervisor_chain(tmp_path: Path) -> None:
    """Supervisor passes transport_deps to created containers via factory."""
    spec = _make_spec("agent-y", agent_type="test")

    sup = Supervisor(
        supervisor_id="test-sup",
        strategy=RestartStrategy.ONE_FOR_ONE,
        child_specs=[spec],
        data_dir=tmp_path,
        transport_deps={},
        project_dir=tmp_path,
        session_name="vco-test",
    )
    await sup.start()

    container = sup.children["agent-y"]
    # Container should have a transport (created by factory from transport_deps)
    assert container._transport is not None
    assert container._project_dir == tmp_path
    assert container._project_session_name == "vco-test"

    await sup.stop()
