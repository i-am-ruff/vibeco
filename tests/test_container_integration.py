"""Integration tests for AgentContainer — full lifecycle wiring (CONT-01 through CONT-06, HLTH-01)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from vcompany.container.child_spec import ChildSpec, RestartPolicy
from vcompany.container.communication import CommunicationPort, Message
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport


def _ctx(agent_id: str = "test-agent", agent_type: str = "gsd") -> ContainerContext:
    """Helper to create a default ContainerContext."""
    return ContainerContext(agent_id=agent_id, agent_type=agent_type)


class MockCommPort:
    """Mock CommunicationPort for testing."""

    async def send_message(self, target: str, content: str) -> bool:
        return True

    async def receive_message(self) -> Message | None:
        return None


# --- Creation ---


def test_creation(tmp_path: Path) -> None:
    """AgentContainer can be created with a context and data_dir."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    assert container.context.agent_id == "test-agent"


def test_initial_state_is_creating(tmp_path: Path) -> None:
    """Initial lifecycle state is 'creating'."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    assert container.state == "creating"


# --- Lifecycle Transitions (CONT-01, CONT-02) ---


@pytest.mark.asyncio
async def test_start_transitions_to_running(tmp_path: Path) -> None:
    """start() transitions state to 'running'."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    await container.start()
    assert container.state == "running"
    await container.stop()


@pytest.mark.asyncio
async def test_start_opens_memory_store(tmp_path: Path) -> None:
    """After start(), memory store is open and usable."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    await container.start()
    await container.memory.set("key", "value")
    assert await container.memory.get("key") == "value"
    await container.stop()


@pytest.mark.asyncio
async def test_stop_transitions_to_stopped(tmp_path: Path) -> None:
    """stop() transitions state to 'stopped'."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    await container.start()
    await container.stop()
    assert container.state == "stopped"


@pytest.mark.asyncio
async def test_stop_closes_memory_store(tmp_path: Path) -> None:
    """After stop(), memory store is closed."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    await container.start()
    await container.stop()
    assert container.memory._db is None


@pytest.mark.asyncio
async def test_destroy_from_stopped(tmp_path: Path) -> None:
    """destroy() from stopped transitions to 'destroyed'."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    await container.start()
    await container.stop()
    await container.destroy()
    assert container.state == "destroyed"


@pytest.mark.asyncio
async def test_error_transitions_to_errored(tmp_path: Path) -> None:
    """error() transitions to 'errored' and increments error_count."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    await container.start()
    await container.error()
    assert container.state == "errored"
    assert container._error_count == 1


@pytest.mark.asyncio
async def test_recover_from_errored(tmp_path: Path) -> None:
    """recover() from errored transitions to 'running'."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    await container.start()
    await container.error()
    await container.recover()
    assert container.state == "running"
    await container.stop()


@pytest.mark.asyncio
async def test_invalid_transition_raises(tmp_path: Path) -> None:
    """Invalid transition (stop from creating) raises TransitionNotAllowed."""
    from statemachine.exceptions import TransitionNotAllowed

    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    with pytest.raises(TransitionNotAllowed):
        await container.stop()


# --- Health Reporting (HLTH-01) ---


def test_health_report_initial(tmp_path: Path) -> None:
    """health_report() returns correct state and agent_id."""
    container = AgentContainer(context=_ctx(agent_id="a1"), data_dir=tmp_path)
    report = container.health_report()
    assert isinstance(report, HealthReport)
    assert report.state == "creating"
    assert report.agent_id == "a1"


@pytest.mark.asyncio
async def test_health_report_after_start(tmp_path: Path) -> None:
    """After start(), health_report().state is 'running'."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    await container.start()
    report = container.health_report()
    assert report.state == "running"
    await container.stop()


@pytest.mark.asyncio
async def test_health_report_uptime_positive(tmp_path: Path) -> None:
    """health_report().uptime > 0 after start()."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    await container.start()
    report = container.health_report()
    assert report.uptime > 0
    await container.stop()


@pytest.mark.asyncio
async def test_health_report_error_count(tmp_path: Path) -> None:
    """error_count is 0 initially, 1 after one error()."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    assert container.health_report().error_count == 0
    await container.start()
    await container.error()
    assert container.health_report().error_count == 1


def test_health_report_last_heartbeat_recent(tmp_path: Path) -> None:
    """last_heartbeat is within 1 second of now."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    now = datetime.now(timezone.utc)
    report = container.health_report()
    assert abs((report.last_heartbeat - now).total_seconds()) < 1.0


# --- Health Emission on State Change ---


@pytest.mark.asyncio
async def test_on_state_change_callback(tmp_path: Path) -> None:
    """on_state_change callback fires with HealthReport on transition."""
    reports: list[HealthReport] = []
    container = AgentContainer(
        context=_ctx(), data_dir=tmp_path, on_state_change=reports.append
    )
    await container.start()
    assert len(reports) == 1
    assert reports[0].state == "running"
    await container.stop()


@pytest.mark.asyncio
async def test_on_state_change_callback_state(tmp_path: Path) -> None:
    """Callback receives HealthReport with state='running' after start()."""
    reports: list[HealthReport] = []
    container = AgentContainer(
        context=_ctx(), data_dir=tmp_path, on_state_change=reports.append
    )
    await container.start()
    assert reports[0].state == "running"
    assert isinstance(reports[0], HealthReport)
    await container.stop()


# --- Communication Port (CONT-06) ---


def test_comm_port_none_by_default(tmp_path: Path) -> None:
    """comm_port is None by default."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    assert container.comm_port is None


def test_comm_port_set_when_provided(tmp_path: Path) -> None:
    """Providing a CommunicationPort sets container.comm_port."""
    port = MockCommPort()
    container = AgentContainer(context=_ctx(), data_dir=tmp_path, comm_port=port)
    assert container.comm_port is port
    assert isinstance(container.comm_port, CommunicationPort)


# --- Factory from ChildSpec (CONT-05) ---


def test_from_spec_creates_container(tmp_path: Path) -> None:
    """from_spec() creates a container with the spec's context."""
    ctx = _ctx(agent_id="spec-agent")
    spec = ChildSpec(child_id="spec-agent", agent_type="gsd", context=ctx)
    container = AgentContainer.from_spec(spec, data_dir=tmp_path)
    assert container.context.agent_id == "spec-agent"


def test_from_spec_correct_agent_id(tmp_path: Path) -> None:
    """from_spec container has correct agent_id."""
    ctx = _ctx(agent_id="id-from-spec")
    spec = ChildSpec(child_id="id-from-spec", agent_type="gsd", context=ctx)
    container = AgentContainer.from_spec(spec, data_dir=tmp_path)
    assert container.context.agent_id == "id-from-spec"


# --- Memory Persistence (CONT-04) ---


@pytest.mark.asyncio
async def test_memory_set_get(tmp_path: Path) -> None:
    """After start(), memory store set/get works."""
    container = AgentContainer(context=_ctx(), data_dir=tmp_path)
    await container.start()
    await container.memory.set("key", "val")
    assert await container.memory.get("key") == "val"
    await container.stop()


@pytest.mark.asyncio
async def test_memory_persists_across_restart(tmp_path: Path) -> None:
    """Memory persists across stop/start with same data_dir."""
    ctx = _ctx(agent_id="persist-agent")

    # First container: write data
    c1 = AgentContainer(context=ctx, data_dir=tmp_path)
    await c1.start()
    await c1.memory.set("key", "val")
    await c1.stop()

    # Second container: same data_dir, read data
    c2 = AgentContainer(context=ctx, data_dir=tmp_path)
    await c2.start()
    assert await c2.memory.get("key") == "val"
    await c2.stop()
