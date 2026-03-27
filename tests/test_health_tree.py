"""Tests for health tree aggregation and state-change notifications (HLTH-02, HLTH-04)."""

import pytest

from vcompany.container.child_spec import ChildSpec, RestartPolicy
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthNode, HealthReport, HealthTree
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


class TestHealthAggregation:
    """Tests for Supervisor._health_reports storage and health_tree() method."""

    @pytest.mark.asyncio
    async def test_health_reports_stored_on_state_change(self, tmp_path):
        """Supervisor stores HealthReport per child when state_change_callback fires."""
        specs = [_make_spec("a"), _make_spec("b")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        # Trigger a state change on child "a" (error it)
        await sup.children["a"].error()

        assert "a" in sup._health_reports
        assert sup._health_reports["a"].agent_id == "a"
        assert sup._health_reports["a"].state == "errored"

        await sup.stop()

    @pytest.mark.asyncio
    async def test_health_tree_returns_correct_structure(self, tmp_path):
        """health_tree() returns HealthTree with supervisor_id, state, and child nodes."""
        specs = [_make_spec("a"), _make_spec("b")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        tree = sup.health_tree()

        assert isinstance(tree, HealthTree)
        assert tree.supervisor_id == "test-sup"
        assert tree.state == "running"
        assert len(tree.children) == 2
        # Children should be HealthNode instances wrapping HealthReport
        for node in tree.children:
            assert isinstance(node, HealthNode)
            assert isinstance(node.report, HealthReport)

        await sup.stop()

    @pytest.mark.asyncio
    async def test_health_tree_uses_cached_report_when_available(self, tmp_path):
        """health_tree() uses cached report from _health_reports if available."""
        specs = [_make_spec("a")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        # Error child "a" to cache a report
        await sup.children["a"].error()

        tree = sup.health_tree()
        # The cached report should show "errored" state
        assert tree.children[0].report.state == "errored"

        await sup.stop()

    @pytest.mark.asyncio
    async def test_health_tree_falls_back_to_container_health_report(self, tmp_path):
        """health_tree() calls container.health_report() when no cached report exists."""
        specs = [_make_spec("a")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        # No state change triggered beyond start -- no cached report for fresh container
        # Clear any cached reports to force fallback
        sup._health_reports.clear()

        tree = sup.health_tree()
        assert len(tree.children) == 1
        assert tree.children[0].report.agent_id == "a"
        assert tree.children[0].report.state == "running"

        await sup.stop()

    @pytest.mark.asyncio
    async def test_health_tree_empty_children(self, tmp_path):
        """health_tree() returns empty children list when no children exist."""
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=[],
            data_dir=tmp_path,
        )
        await sup.start()

        tree = sup.health_tree()
        assert tree.children == []

        await sup.stop()

    @pytest.mark.asyncio
    async def test_stale_report_cleared_on_restart(self, tmp_path):
        """_health_reports entry is cleared when _start_child() creates a new container."""
        specs = [_make_spec("a")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        await sup.start()

        # Trigger state change to cache a report
        await sup.children["a"].error()
        assert "a" in sup._health_reports

        # Restart the child (simulates _start_child clearing stale report)
        await sup._start_child(specs[0])

        # The stale errored report should be cleared
        # Either no entry or a fresh one from the new container's start
        if "a" in sup._health_reports:
            # If present, it should be from the new container (running state)
            assert sup._health_reports["a"].state == "running"

        await sup.stop()
