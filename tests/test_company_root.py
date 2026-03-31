"""Tests for CompanyRoot and ProjectSupervisor classes."""

import pytest

from vcompany.supervisor.child_spec import ChildSpec
from vcompany.supervisor.child_spec import ContainerContext
from vcompany.supervisor.company_root import CompanyRoot
from vcompany.supervisor.project_supervisor import ProjectSupervisor
from vcompany.supervisor.strategies import RestartStrategy


def _make_spec(child_id: str) -> ChildSpec:
    return ChildSpec(
        child_id=child_id,
        agent_type="test",
        context=ContainerContext(agent_id=child_id, agent_type="test"),
    )


class TestProjectSupervisor:
    @pytest.mark.asyncio
    async def test_project_supervisor_creates_with_project_id(self, tmp_path):
        """ProjectSupervisor stores project_id and derives supervisor_id."""
        ps = ProjectSupervisor(
            project_id="myproj",
            child_specs=[_make_spec("a")],
            data_dir=tmp_path,
        )
        assert ps.project_id == "myproj"
        assert ps.supervisor_id == "project-myproj"

    @pytest.mark.asyncio
    async def test_project_supervisor_defaults_one_for_one(self, tmp_path):
        """ProjectSupervisor defaults to ONE_FOR_ONE strategy."""
        ps = ProjectSupervisor(
            project_id="myproj",
            child_specs=[_make_spec("a")],
            data_dir=tmp_path,
        )
        assert ps.strategy == RestartStrategy.ONE_FOR_ONE

    @pytest.mark.asyncio
    async def test_project_supervisor_starts_children(self, tmp_path):
        """ProjectSupervisor starts and runs child containers."""
        ps = ProjectSupervisor(
            project_id="myproj",
            child_specs=[_make_spec("a"), _make_spec("b")],
            data_dir=tmp_path,
        )
        await ps.start()
        assert ps.state == "running"
        assert ps.children["a"].state == "running"
        assert ps.children["b"].state == "running"
        await ps.stop()


class TestCompanyRoot:
    @pytest.mark.asyncio
    async def test_company_root_creates_with_defaults(self, tmp_path):
        """CompanyRoot has supervisor_id 'company-root' and ONE_FOR_ONE."""
        root = CompanyRoot(data_dir=tmp_path)
        assert root.supervisor_id == "company-root"
        assert root.strategy == RestartStrategy.ONE_FOR_ONE

    @pytest.mark.asyncio
    async def test_add_project_creates_and_starts_supervisor(self, tmp_path):
        """add_project creates a ProjectSupervisor, starts it, and tracks it."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        ps = await root.add_project("proj1", [_make_spec("a1")])
        assert isinstance(ps, ProjectSupervisor)
        assert ps.state == "running"
        assert "proj1" in root.projects
        assert root.projects["proj1"] is ps

        await root.stop()

    @pytest.mark.asyncio
    async def test_remove_project_stops_and_removes(self, tmp_path):
        """remove_project stops a ProjectSupervisor and removes it."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()
        await root.add_project("proj1", [_make_spec("a1")])

        await root.remove_project("proj1")
        assert "proj1" not in root.projects

        await root.stop()

    @pytest.mark.asyncio
    async def test_projects_property(self, tmp_path):
        """projects property returns dict of project_id -> ProjectSupervisor."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()
        await root.add_project("p1", [_make_spec("a1")])
        await root.add_project("p2", [_make_spec("a2")])

        assert len(root.projects) == 2
        assert "p1" in root.projects
        assert "p2" in root.projects

        await root.stop()

    @pytest.mark.asyncio
    async def test_stop_stops_all_projects(self, tmp_path):
        """Stopping CompanyRoot stops all ProjectSupervisors."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()
        ps = await root.add_project("proj1", [_make_spec("a1")])

        await root.stop()
        assert ps.state == "stopped"
        assert root.state == "stopped"

    @pytest.mark.asyncio
    async def test_on_escalation_stored(self, tmp_path):
        """CompanyRoot stores on_escalation callback."""
        messages = []

        async def handler(msg: str) -> None:
            messages.append(msg)

        root = CompanyRoot(data_dir=tmp_path, on_escalation=handler)
        assert root._on_escalation is handler

    @pytest.mark.asyncio
    async def test_add_company_agent_creates_direct_child(self, tmp_path):
        """add_company_agent creates an AgentContainer as a direct child of CompanyRoot."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        spec = _make_spec("strategist")
        container = await root.add_company_agent(spec)

        assert container is not None
        assert "strategist" in root._company_agents
        assert root._company_agents["strategist"] is container

        await root.stop()

    @pytest.mark.asyncio
    async def test_health_tree_includes_company_agents(self, tmp_path):
        """health_tree() includes company_agents nodes."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        spec = _make_spec("strategist")
        await root.add_company_agent(spec)

        tree = root.health_tree()
        assert len(tree.company_agents) == 1
        assert tree.company_agents[0].report.agent_id == "strategist"

        await root.stop()

    @pytest.mark.asyncio
    async def test_health_tree_company_agent_has_correct_agent_id(self, tmp_path):
        """health_tree() company_agents nodes have the correct agent_id."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        await root.add_company_agent(_make_spec("company-agent-1"))
        await root.add_company_agent(_make_spec("company-agent-2"))

        tree = root.health_tree()
        agent_ids = {node.report.agent_id for node in tree.company_agents}
        assert agent_ids == {"company-agent-1", "company-agent-2"}

        await root.stop()

    @pytest.mark.asyncio
    async def test_stop_stops_company_agents(self, tmp_path):
        """CompanyRoot.stop() stops all company agents."""
        root = CompanyRoot(data_dir=tmp_path)
        await root.start()

        spec = _make_spec("strategist")
        container = await root.add_company_agent(spec)

        await root.stop()

        assert container.state in ("stopped", "destroyed")
        assert root._company_agents == {}
