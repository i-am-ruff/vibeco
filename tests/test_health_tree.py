"""Tests for health tree aggregation and state-change notifications (HLTH-02, HLTH-04)."""

import asyncio

import pytest

from vcompany.container.child_spec import ChildSpec, RestartPolicy
from vcompany.container.context import ContainerContext
from vcompany.container.health import CompanyHealthTree, HealthNode, HealthReport, HealthTree
from vcompany.supervisor.company_root import CompanyRoot
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


class TestCompanyHealthTree:
    """Tests for CompanyRoot.health_tree() returning CompanyHealthTree."""

    @pytest.mark.asyncio
    async def test_company_health_tree_with_projects(self, tmp_path):
        """CompanyRoot.health_tree() returns CompanyHealthTree with project subtrees."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        await root.add_project("proj-a", [_make_spec("agent-1")])
        await root.add_project("proj-b", [_make_spec("agent-2"), _make_spec("agent-3")])

        tree = root.health_tree()

        assert isinstance(tree, CompanyHealthTree)
        assert tree.supervisor_id == "company-root"
        assert tree.state == "running"
        assert len(tree.projects) == 2

        # Each project should be a HealthTree
        for project_tree in tree.projects:
            assert isinstance(project_tree, HealthTree)

        await root.stop()

    @pytest.mark.asyncio
    async def test_company_health_tree_empty_projects(self, tmp_path):
        """CompanyRoot.health_tree() returns empty projects when none added."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        tree = root.health_tree()

        assert isinstance(tree, CompanyHealthTree)
        assert tree.projects == []

        await root.stop()


class TestStateNotifications:
    """Tests for on_health_change async callback firing on state transitions."""

    @pytest.mark.asyncio
    async def test_notification_fires_on_errored(self, tmp_path):
        """on_health_change is invoked when a child transitions to errored."""
        received: list[HealthReport] = []

        async def on_change(report: HealthReport) -> None:
            received.append(report)

        specs = [_make_spec("a")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
            on_health_change=on_change,
        )
        await sup.start()

        # Error child "a"
        await sup.children["a"].error()
        # Allow the created task to run
        await asyncio.sleep(0.05)

        assert len(received) >= 1
        assert any(r.state == "errored" for r in received)

        await sup.stop()

    @pytest.mark.asyncio
    async def test_notification_fires_on_running(self, tmp_path):
        """on_health_change is invoked when a child transitions to running."""
        received: list[HealthReport] = []

        async def on_change(report: HealthReport) -> None:
            received.append(report)

        specs = [_make_spec("a")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
            on_health_change=on_change,
        )
        await sup.start()
        # start triggers creating -> running transition
        await asyncio.sleep(0.05)

        assert len(received) >= 1
        assert any(r.state == "running" for r in received)

        await sup.stop()

    @pytest.mark.asyncio
    async def test_notification_not_fired_for_creating(self, tmp_path):
        """on_health_change is NOT invoked for 'creating' state (non-significant)."""
        received: list[HealthReport] = []

        async def on_change(report: HealthReport) -> None:
            received.append(report)

        specs = [_make_spec("a")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
            on_health_change=on_change,
        )
        await sup.start()
        await asyncio.sleep(0.05)

        # No report should have state == "creating"
        assert not any(r.state == "creating" for r in received)

        await sup.stop()


class TestNotificationSuppression:
    """Tests for notification suppression during bulk restarts."""

    @pytest.mark.asyncio
    async def test_notification_suppressed_during_restarting(self, tmp_path):
        """on_health_change is NOT invoked when _restarting is True."""
        received: list[HealthReport] = []

        async def on_change(report: HealthReport) -> None:
            received.append(report)

        specs = [_make_spec("a")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
            on_health_change=on_change,
        )
        await sup.start()
        await asyncio.sleep(0.05)

        # Clear received from start
        received.clear()

        # Set restarting flag to simulate bulk restart
        sup._restarting = True
        await sup.children["a"].error()
        await asyncio.sleep(0.05)

        # No notifications should have been delivered
        assert len(received) == 0

        sup._restarting = False
        await sup.stop()


class TestHealthTreeFiltering:
    """Tests for querying health at project level."""

    @pytest.mark.asyncio
    async def test_project_supervisor_health_tree(self, tmp_path):
        """ProjectSupervisor.health_tree() returns HealthTree for a single project."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        ps = await root.add_project("proj-a", [_make_spec("agent-1"), _make_spec("agent-2")])

        tree = ps.health_tree()

        assert isinstance(tree, HealthTree)
        assert tree.supervisor_id == "project-proj-a"
        assert len(tree.children) == 2

        await root.stop()
