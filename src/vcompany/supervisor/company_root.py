"""CompanyRoot -- top-level supervisor managing ProjectSupervisors.

The root of the supervision tree. Manages ProjectSupervisor instances,
one per active project. When escalation bubbles to the top (no parent),
calls the on_escalation callback to alert via Discord.

Owns the Scheduler (AUTO-06) which wakes sleeping ContinuousAgents on
schedule. Registers all built-in agent types in the factory at startup.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

from vcompany.container.child_spec import ChildSpec
from vcompany.container.container import AgentContainer
from vcompany.container.factory import register_defaults
from vcompany.container.health import CompanyHealthTree, HealthReport, HealthTree
from vcompany.container.memory_store import MemoryStore
from vcompany.resilience.degraded_mode import DegradedModeManager
from vcompany.supervisor.project_supervisor import ProjectSupervisor
from vcompany.supervisor.scheduler import Scheduler
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
        on_health_change: Callable[[HealthReport], Awaitable[None]] | None = None,
        health_check: Callable[[], Awaitable[bool]] | None = None,
        on_degraded: Callable[[], Awaitable[None]] | None = None,
        on_recovered: Callable[[], Awaitable[None]] | None = None,
        tmux_manager: object | None = None,
        project_dir: Path | None = None,
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
            on_health_change=on_health_change,
        )
        self._projects: dict[str, ProjectSupervisor] = {}
        self._tmux_manager = tmux_manager
        self._project_dir = project_dir
        # Degraded mode manager (RESL-03)
        self._degraded_mode: DegradedModeManager | None = None
        if health_check is not None:
            self._degraded_mode = DegradedModeManager(
                health_check=health_check,
                on_degraded=on_degraded,
                on_recovered=on_recovered,
            )
        # Scheduler for waking sleeping ContinuousAgents (AUTO-06)
        self._scheduler: Scheduler | None = None
        self._scheduler_task: asyncio.Task | None = None
        self._scheduler_memory: MemoryStore | None = None
        if data_dir is not None:
            self._scheduler_memory = MemoryStore(data_dir / "scheduler" / "memory.db")

    @property
    def is_degraded(self) -> bool:
        """True when the system is in degraded mode (Claude unreachable)."""
        if self._degraded_mode is not None:
            return self._degraded_mode.is_degraded
        return False

    @property
    def projects(self) -> dict[str, ProjectSupervisor]:
        """Dict of project_id -> ProjectSupervisor."""
        return dict(self._projects)

    def health_tree(self) -> CompanyHealthTree:
        """Build a company-wide health tree from all project supervisors.

        Returns a CompanyHealthTree containing a HealthTree per project.
        """
        project_trees: list[HealthTree] = []
        for _project_id, ps in self._projects.items():
            project_trees.append(ps.health_tree())
        return CompanyHealthTree(
            supervisor_id=self.supervisor_id,
            state=self._state,
            projects=project_trees,
        )

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

        Raises:
            RuntimeError: If system is in degraded mode (Claude unreachable).
        """
        if self._degraded_mode is not None and self._degraded_mode.is_degraded:
            raise RuntimeError(
                f"System in degraded mode (Claude unreachable). "
                f"Cannot add project {project_id}. Will auto-recover."
            )
        ps = ProjectSupervisor(
            project_id=project_id,
            child_specs=child_specs,
            strategy=strategy,
            max_restarts=max_restarts,
            window_seconds=window_seconds,
            parent=self,
            data_dir=self._data_dir,
            tmux_manager=self._tmux_manager,
            project_dir=self._project_dir,
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

    async def _find_container(self, agent_id: str) -> AgentContainer | None:
        """Search all ProjectSupervisors for a container by agent_id."""
        for ps in self._projects.values():
            container = ps.children.get(agent_id)
            if container is not None:
                return container
        return None

    async def start(self) -> None:
        """Register agent types, open scheduler memory, and start scheduler loop."""
        register_defaults()
        await super().start()

        if self._degraded_mode is not None:
            await self._degraded_mode.start()
            logger.info("DegradedModeManager started")

        if self._scheduler_memory is not None:
            await self._scheduler_memory.open()
            self._scheduler = Scheduler(
                memory=self._scheduler_memory,
                find_container=self._find_container,
            )
            await self._scheduler.load()
            self._scheduler_task = asyncio.create_task(self._scheduler.run())
            logger.info("Scheduler started")

    async def add_schedule(self, agent_id: str, interval_seconds: int) -> None:
        """Add a wake schedule for an agent (pass-through to Scheduler)."""
        if self._scheduler is not None:
            await self._scheduler.add_schedule(agent_id, interval_seconds)

    async def remove_schedule(self, agent_id: str) -> None:
        """Remove a wake schedule for an agent (pass-through to Scheduler)."""
        if self._scheduler is not None:
            await self._scheduler.remove_schedule(agent_id)

    async def handle_child_escalation(self, child_supervisor_id: str) -> None:
        """Handle escalation from a child ProjectSupervisor.

        Since ProjectSupervisors are managed dynamically (not via child_specs),
        the base Supervisor._handle_child_failure path cannot find them.
        CompanyRoot handles this directly: check its own restart budget,
        and if exceeded, call on_escalation (the Discord alert path).
        """
        logger.warning(
            "CompanyRoot received escalation from child %s",
            child_supervisor_id,
        )

        if not self._restart_tracker.allow_restart():
            # CompanyRoot itself has exceeded its budget -- fire the callback
            msg = (
                f"ESCALATION: Supervisor {self.supervisor_id} exceeded restart limits "
                f"for child {child_supervisor_id}. Manual intervention required."
            )
            if self._on_escalation is not None:
                await self._on_escalation(msg)
            return

        # Otherwise, try to restart the project supervisor
        # Find the project by supervisor_id
        project_id: str | None = None
        for pid, ps in self._projects.items():
            if ps.supervisor_id == child_supervisor_id:
                project_id = pid
                break

        if project_id is not None:
            old_ps = self._projects[project_id]
            # Rebuild with same specs
            new_ps = ProjectSupervisor(
                project_id=project_id,
                child_specs=old_ps._child_specs,
                strategy=old_ps.strategy,
                max_restarts=old_ps._restart_tracker.max_restarts,
                window_seconds=old_ps._restart_tracker.window_seconds,
                parent=self,
                data_dir=self._data_dir,
                tmux_manager=self._tmux_manager,
                project_dir=self._project_dir,
            )
            await new_ps.start()
            self._projects[project_id] = new_ps
            logger.info("Restarted project supervisor for %s", project_id)
        else:
            # Unknown child -- fire escalation callback
            msg = (
                f"ESCALATION: Supervisor {self.supervisor_id} received escalation "
                f"from unknown child {child_supervisor_id}. Manual intervention required."
            )
            if self._on_escalation is not None:
                await self._on_escalation(msg)

    async def stop(self) -> None:
        """Cancel scheduler, stop all ProjectSupervisors, and stop the root."""
        # Stop degraded mode manager first
        if self._degraded_mode is not None:
            await self._degraded_mode.stop()
            logger.info("DegradedModeManager stopped")

        # Cancel the scheduler task first
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None
            logger.info("Scheduler stopped")

        # Close scheduler memory store
        if self._scheduler_memory is not None:
            await self._scheduler_memory.close()

        # Stop all dynamically added projects
        for ps in list(self._projects.values()):
            if ps.state != "stopped":
                await ps.stop()

        # Stop any static children via parent class
        await super().stop()
