"""Tests for CompanyRoot and ProjectSupervisor classes."""

import pytest

from vcompany.container.child_spec import ChildSpec
from vcompany.container.context import ContainerContext
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
