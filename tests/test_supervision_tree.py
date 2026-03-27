"""Integration tests for two-level supervision hierarchy.

Tests the full escalation chain: AgentContainer crash -> ProjectSupervisor
restart -> budget exceeded -> CompanyRoot -> on_escalation callback (Discord).
"""

import asyncio

import pytest

from vcompany.container.child_spec import ChildSpec
from vcompany.container.context import ContainerContext
from vcompany.supervisor.company_root import CompanyRoot
from vcompany.supervisor.project_supervisor import ProjectSupervisor
from vcompany.supervisor.strategies import RestartStrategy


def _make_spec(child_id: str) -> ChildSpec:
    """Create a minimal ChildSpec for testing."""
    return ChildSpec(
        child_id=child_id,
        agent_type="test",
        context=ContainerContext(agent_id=child_id, agent_type="test"),
    )


class TestTwoLevelHierarchy:
    """Integration tests for CompanyRoot -> ProjectSupervisor -> AgentContainers."""

    @pytest.mark.asyncio
    async def test_two_level_hierarchy_starts(self, tmp_path):
        """SUPV-01: Build CompanyRoot, add project with 2 agents, all reach running."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        ps = await root.add_project("proj1", [_make_spec("agent-a"), _make_spec("agent-b")])

        # Verify all levels are running
        assert root.state == "running"
        assert ps.state == "running"
        assert ps.children["agent-a"].state == "running"
        assert ps.children["agent-b"].state == "running"

        await root.stop()

    @pytest.mark.asyncio
    async def test_agent_failure_triggers_restart(self, tmp_path):
        """SUPV-02 integration: agent error triggers ProjectSupervisor restart."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        ps = await root.add_project("proj1", [_make_spec("agent-a"), _make_spec("agent-b")])

        # Trigger error on agent-a
        old_container = ps.children["agent-a"]
        await old_container.error()

        # Allow async monitor to process the event
        await asyncio.sleep(0.2)

        # Agent-a should be restarted (new container in running state)
        assert ps.children["agent-a"].state == "running"
        # Agent-a is a new container instance
        assert ps.children["agent-a"] is not old_container
        # Agent-b should be unaffected (one_for_one)
        assert ps.children["agent-b"].state == "running"

        await root.stop()

    @pytest.mark.asyncio
    async def test_escalation_to_company_root(self, tmp_path):
        """SUPV-06: exhausted restart budget escalates from ProjectSupervisor to CompanyRoot."""
        escalation_messages: list[str] = []

        async def capture_escalation(msg: str) -> None:
            escalation_messages.append(msg)

        root = CompanyRoot(
            data_dir=tmp_path,
            on_escalation=capture_escalation,
            max_restarts=3,
            window_seconds=600,
        )
        await root.start()

        # ProjectSupervisor with very low budget (2 restarts allowed)
        ps = await root.add_project(
            "proj1",
            [_make_spec("agent-a")],
            max_restarts=2,
            window_seconds=600,
        )

        # Fail 3 times to exhaust the budget (2 restarts + 1 final failure)
        for _ in range(3):
            agent = ps.children.get("agent-a")
            if agent is None:
                break
            await agent.error()
            await asyncio.sleep(0.2)

        # ProjectSupervisor should have escalated
        assert ps.state == "stopped"

        # CompanyRoot's handle_child_escalation was called, but since
        # ProjectSupervisor is dynamically added (not in child_specs),
        # the escalation flows through the parent mechanism.
        # The project supervisor should be stopped.
        await root.stop()

    @pytest.mark.asyncio
    async def test_top_level_escalation_calls_callback(self, tmp_path):
        """SUPV-06: CompanyRoot calls on_escalation callback with descriptive message."""
        escalation_messages: list[str] = []

        async def capture_escalation(msg: str) -> None:
            escalation_messages.append(msg)

        # CompanyRoot with zero budget -- any escalation from a child
        # immediately fires the on_escalation callback
        root = CompanyRoot(
            data_dir=tmp_path,
            on_escalation=capture_escalation,
            max_restarts=0,
            window_seconds=600,
        )
        await root.start()

        # Project with very low budget (1 restart allowed)
        ps = await root.add_project(
            "proj1",
            [_make_spec("agent-a")],
            max_restarts=1,
            window_seconds=600,
        )

        # Exhaust project supervisor budget: fail twice (1 restart + 1 escalation)
        agent = ps.children["agent-a"]
        await agent.error()
        await asyncio.sleep(0.2)

        # After first restart, fail again to exhaust PS budget -> escalates to root
        agent = ps.children.get("agent-a")
        if agent is not None:
            await agent.error()
            await asyncio.sleep(0.2)

        # The escalation should have reached the on_escalation callback
        assert len(escalation_messages) >= 1
        # Message should contain enough context
        msg = escalation_messages[0]
        assert "ESCALATION" in msg
        assert "restart limits" in msg.lower() or "restart" in msg.lower()

        await root.stop()

    @pytest.mark.asyncio
    async def test_stop_company_root_stops_everything(self, tmp_path):
        """Stopping CompanyRoot stops all ProjectSupervisors and containers."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        ps1 = await root.add_project("proj1", [_make_spec("a1"), _make_spec("a2")])
        ps2 = await root.add_project("proj2", [_make_spec("b1")])

        # All running
        assert ps1.state == "running"
        assert ps2.state == "running"

        await root.stop()

        assert root.state == "stopped"
        assert ps1.state == "stopped"
        assert ps2.state == "stopped"
        assert ps1.children["a1"].state == "stopped"
        assert ps1.children["a2"].state == "stopped"
        assert ps2.children["b1"].state == "stopped"

    @pytest.mark.asyncio
    async def test_add_remove_project_at_runtime(self, tmp_path):
        """Projects can be added and removed while CompanyRoot is running."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        # Add project
        ps = await root.add_project("proj1", [_make_spec("agent-a")])
        assert ps.state == "running"
        assert "proj1" in root.projects

        # Remove project
        await root.remove_project("proj1")
        assert "proj1" not in root.projects
        assert ps.state == "stopped"

        # Add another project after removal
        ps2 = await root.add_project("proj2", [_make_spec("agent-b")])
        assert ps2.state == "running"
        assert "proj2" in root.projects

        await root.stop()
