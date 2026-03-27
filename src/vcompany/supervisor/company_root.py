"""CompanyRoot -- top-level supervisor managing ProjectSupervisors.

The root of the supervision tree. Manages ProjectSupervisor instances,
one per active project. When escalation bubbles to the top (no parent),
calls the on_escalation callback to alert via Discord.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Awaitable, Callable

from vcompany.container.child_spec import ChildSpec
from vcompany.supervisor.project_supervisor import ProjectSupervisor
from vcompany.supervisor.strategies import RestartStrategy
from vcompany.supervisor.supervisor import Supervisor

logger = logging.getLogger(__name__)


class CompanyRoot(Supervisor):
    """Top-level supervisor that manages ProjectSupervisors.

    CompanyRoot sits at the top of the supervision hierarchy. It creates
    and manages ProjectSupervisor instances (one per project). When
    escalation reaches CompanyRoot and cannot be handled (restart budget
    exceeded), it calls the on_escalation callback -- the Discord alert path.

    Args:
        on_escalation: Async callback invoked when escalation cannot be
            handled. Receives a descriptive message string.
        max_restarts: Maximum restarts within window.
        window_seconds: Sliding window size in seconds.
        data_dir: Root directory for child container data.
    """

    def __init__(
        self,
        on_escalation: Callable[[str], Awaitable[None]] | None = None,
        max_restarts: int = 3,
        window_seconds: int = 600,
        data_dir: Path | None = None,
    ) -> None:
        # CompanyRoot has no parent and no child_specs at init --
        # projects are added dynamically via add_project().
        super().__init__(
            supervisor_id="company-root",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=[],
            max_restarts=max_restarts,
            window_seconds=window_seconds,
            parent=None,
            on_escalation=on_escalation,
            data_dir=data_dir,
        )
        self._projects: dict[str, ProjectSupervisor] = {}

    @property
    def projects(self) -> dict[str, ProjectSupervisor]:
        """Dict of project_id -> ProjectSupervisor."""
        return dict(self._projects)

    async def add_project(
        self,
        project_id: str,
        child_specs: list[ChildSpec],
        strategy: RestartStrategy = RestartStrategy.ONE_FOR_ONE,
        max_restarts: int = 3,
        window_seconds: int = 600,
    ) -> ProjectSupervisor:
        """Create and start a ProjectSupervisor for the given project.

        Args:
            project_id: Unique project identifier.
            child_specs: Agent container specifications for the project.
            strategy: Restart strategy for the project supervisor.
            max_restarts: Maximum restarts within window.
            window_seconds: Sliding window size in seconds.

        Returns:
            The started ProjectSupervisor instance.
        """
        ps = ProjectSupervisor(
            project_id=project_id,
            child_specs=child_specs,
            strategy=strategy,
            max_restarts=max_restarts,
            window_seconds=window_seconds,
            parent=self,
            data_dir=self._data_dir,
        )
        await ps.start()
        self._projects[project_id] = ps
        logger.info("Added project %s with %d agents", project_id, len(child_specs))
        return ps

    async def remove_project(self, project_id: str) -> None:
        """Stop and remove a ProjectSupervisor.

        Args:
            project_id: The project to remove.

        Raises:
            KeyError: If project_id is not found.
        """
        ps = self._projects.pop(project_id)
        if ps.state != "stopped":
            await ps.stop()
        logger.info("Removed project %s", project_id)

    async def stop(self) -> None:
        """Stop all ProjectSupervisors and the root supervisor."""
        # Stop all dynamically added projects
        for ps in list(self._projects.values()):
            if ps.state != "stopped":
                await ps.stop()

        # Stop any static children via parent class
        await super().stop()
