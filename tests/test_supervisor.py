"""Tests for Supervisor base class lifecycle (start, stop, state)."""

import pytest

from vcompany.container.child_spec import ChildSpec, RestartPolicy
from vcompany.container.context import ContainerContext
from vcompany.supervisor.strategies import RestartStrategy
from vcompany.supervisor.supervisor import Supervisor


def _make_spec(child_id: str, restart_policy: RestartPolicy = RestartPolicy.PERMANENT) -> ChildSpec:
    """Create a minimal ChildSpec for testing."""
    return ChildSpec(
        child_id=child_id,
        agent_type="test",
        context=ContainerContext(agent_id=child_id, agent_type="test"),
        restart_policy=restart_policy,
    )


class TestSupervisorLifecycle:
    @pytest.mark.asyncio
    async def test_start_starts_all_children(self, tmp_path):
        """After start(), all child containers are in 'running' state."""
        specs = [_make_spec("a"), _make_spec("b")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        assert len(sup.children) == 2
        assert sup.children["a"].state == "running"
        assert sup.children["b"].state == "running"

        await sup.stop()

    @pytest.mark.asyncio
    async def test_stop_stops_all_children(self, tmp_path):
        """After stop(), all containers are in 'stopped' state."""
        specs = [_make_spec("a"), _make_spec("b")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()
        await sup.stop()

        assert sup.children["a"].state == "stopped"
        assert sup.children["b"].state == "stopped"

    @pytest.mark.asyncio
    async def test_supervisor_state_property(self, tmp_path):
        """State is 'running' after start, 'stopped' after stop."""
        specs = [_make_spec("a")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )

        assert sup.state == "stopped"
        await sup.start()
        assert sup.state == "running"
        await sup.stop()
        assert sup.state == "stopped"
