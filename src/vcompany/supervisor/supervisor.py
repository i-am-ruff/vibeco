"""Supervisor base class with Erlang-style restart strategies (SUPV-02..06).

Manages child AgentContainers via asyncio Tasks. Implements one_for_one,
all_for_one, and rest_for_one restart strategies with restart intensity
tracking and escalation to parent or callback.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from vcompany.container.child_spec import ChildSpec, RestartPolicy
from vcompany.container.container import AgentContainer
from vcompany.container.health import HealthReport
from vcompany.supervisor.restart_tracker import RestartTracker
from vcompany.supervisor.strategies import RestartStrategy

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class Supervisor:
    """Manages child AgentContainers with Erlang-style restart semantics.

    Args:
        supervisor_id: Unique identifier for this supervisor.
        strategy: Restart strategy (one_for_one, all_for_one, rest_for_one).
        child_specs: Ordered list of child specifications.
        max_restarts: Maximum restarts allowed within window (supervisor-level).
        window_seconds: Sliding window size in seconds.
        parent: Parent supervisor for escalation (None for top-level).
        on_escalation: Callback invoked on escalation if no parent.
        data_dir: Root directory for child container data.
    """

    def __init__(
        self,
        supervisor_id: str,
        strategy: RestartStrategy,
        child_specs: list[ChildSpec],
        max_restarts: int = 3,
        window_seconds: int = 600,
        parent: Any | None = None,
        on_escalation: Callable[[str], Awaitable[None]] | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.supervisor_id = supervisor_id
        self.strategy = strategy
        self._child_specs = list(child_specs)  # preserve order
        self._parent = parent
        self._on_escalation = on_escalation
        self._data_dir = data_dir or Path("/tmp/vcompany-supervisor")

        self._children: dict[str, AgentContainer] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._child_events: dict[str, asyncio.Event] = {}
        self._restart_tracker = RestartTracker(
            max_restarts=max_restarts,
            window_seconds=window_seconds,
        )
        self._restarting: bool = False
        self._state: str = "stopped"

    # --- Properties ---

    @property
    def state(self) -> str:
        """Current supervisor state: 'running' or 'stopped'."""
        return self._state

    @property
    def children(self) -> dict[str, AgentContainer]:
        """Dict of child_id -> AgentContainer."""
        return self._children

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start all children in spec order."""
        for spec in self._child_specs:
            await self._start_child(spec)
        self._state = "running"

    async def stop(self) -> None:
        """Stop all children in reverse spec order and cancel monitor tasks."""
        self._restarting = True  # suppress callbacks during shutdown
        # Cancel all monitor tasks
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

        # Stop children in reverse spec order
        for spec in reversed(self._child_specs):
            child = self._children.get(spec.child_id)
            if child is not None and child.state not in ("stopped", "destroyed"):
                try:
                    await child.stop()
                except Exception:
                    logger.warning("Error stopping child %s", spec.child_id, exc_info=True)

        self._restarting = False
        self._state = "stopped"

    # --- Child Management ---

    def _make_state_change_callback(self, child_id: str) -> Callable[[HealthReport], None]:
        """Create a state-change callback that signals the monitor for a child."""

        def callback(report: HealthReport) -> None:
            if self._restarting:
                return  # Suppress during supervisor-initiated restarts
            if report.state in ("errored", "stopped"):
                event = self._child_events.get(child_id)
                if event is not None:
                    event.set()

        return callback

    async def _start_child(self, spec: ChildSpec) -> None:
        """Create a container from spec, start it, and set up monitoring."""
        # Cancel existing monitor task if any
        old_task = self._tasks.pop(spec.child_id, None)
        if old_task is not None:
            old_task.cancel()
            try:
                await old_task
            except asyncio.CancelledError:
                pass

        # Create event for this child
        event = asyncio.Event()
        self._child_events[spec.child_id] = event

        # Create and start container
        container = AgentContainer.from_spec(
            spec,
            data_dir=self._data_dir,
            on_state_change=self._make_state_change_callback(spec.child_id),
        )
        await container.start()
        self._children[spec.child_id] = container

        # Create monitor task
        self._tasks[spec.child_id] = asyncio.create_task(
            self._monitor_child(spec.child_id)
        )

    async def _monitor_child(self, child_id: str) -> None:
        """Wait for child events and handle failures."""
        event = self._child_events[child_id]
        while True:
            await event.wait()
            event.clear()

            container = self._children.get(child_id)
            if container is None:
                break

            if container.state == "errored":
                await self._handle_child_failure(child_id)
            elif container.state in ("stopped", "destroyed"):
                # Check if transient that stopped normally -- no restart
                break

    # --- Failure Handling ---

    async def _handle_child_failure(self, failed_id: str) -> None:
        """Apply restart policy and strategy for a failed child."""
        spec = self._get_spec(failed_id)
        if spec is None:
            return

        container = self._children.get(failed_id)
        if container is None:
            return

        # Check restart policy (per-child)
        if spec.restart_policy == RestartPolicy.TEMPORARY:
            return  # Never restart
        if spec.restart_policy == RestartPolicy.TRANSIENT:
            if container.state != "errored":
                return  # Only restart on abnormal exit

        # Check restart intensity (per-supervisor)
        if not self._restart_tracker.allow_restart():
            await self._escalate()
            return

        # Dispatch to strategy
        if self.strategy == RestartStrategy.ONE_FOR_ONE:
            await self._restart_one(failed_id)
        elif self.strategy == RestartStrategy.ALL_FOR_ONE:
            await self._restart_all(failed_id)
        elif self.strategy == RestartStrategy.REST_FOR_ONE:
            await self._restart_rest(failed_id)

    def _get_spec(self, child_id: str) -> ChildSpec | None:
        """Look up a child spec by ID."""
        for spec in self._child_specs:
            if spec.child_id == child_id:
                return spec
        return None

    # --- Restart Strategies ---

    async def _restart_one(self, failed_id: str) -> None:
        """one_for_one: restart only the failed child."""
        spec = self._get_spec(failed_id)
        if spec is None:
            return

        # Stop old container
        old = self._children.get(failed_id)
        if old is not None and old.state not in ("stopped", "destroyed"):
            await old.stop()

        # Start new container from spec
        await self._start_child(spec)

    async def _restart_all(self, _failed_id: str) -> None:
        """all_for_one: stop all children reverse order, restart all forward order."""
        self._restarting = True
        try:
            # Stop all children in reverse spec order
            for spec in reversed(self._child_specs):
                child = self._children.get(spec.child_id)
                if child is not None and child.state not in ("stopped", "destroyed"):
                    await child.stop()
                # Cancel monitor task
                task = self._tasks.pop(spec.child_id, None)
                if task is not None:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            # Restart all children in forward spec order
            for spec in self._child_specs:
                await self._start_child(spec)
        finally:
            self._restarting = False

    async def _restart_rest(self, failed_id: str) -> None:
        """rest_for_one: stop failed + later children reverse, restart forward."""
        failed_idx = None
        for i, spec in enumerate(self._child_specs):
            if spec.child_id == failed_id:
                failed_idx = i
                break
        if failed_idx is None:
            return

        specs_to_restart = self._child_specs[failed_idx:]

        self._restarting = True
        try:
            # Stop affected children in reverse order
            for spec in reversed(specs_to_restart):
                child = self._children.get(spec.child_id)
                if child is not None and child.state not in ("stopped", "destroyed"):
                    await child.stop()
                # Cancel monitor task
                task = self._tasks.pop(spec.child_id, None)
                if task is not None:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            # Restart in forward order
            for spec in specs_to_restart:
                await self._start_child(spec)
        finally:
            self._restarting = False

    # --- Escalation ---

    async def _escalate(self) -> None:
        """Escalate when restart intensity is exceeded."""
        logger.warning(
            "Supervisor %s exceeded restart intensity -- escalating",
            self.supervisor_id,
        )

        # Stop all children
        self._restarting = True
        for spec in reversed(self._child_specs):
            child = self._children.get(spec.child_id)
            if child is not None and child.state not in ("stopped", "destroyed"):
                try:
                    await child.stop()
                except Exception:
                    logger.warning("Error stopping child %s during escalation", spec.child_id)
        # Cancel monitor tasks
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        self._restarting = False
        self._state = "stopped"

        if self._parent is not None:
            await self._parent.handle_child_escalation(self.supervisor_id)
        elif self._on_escalation is not None:
            msg = (
                f"ESCALATION: Supervisor {self.supervisor_id} exceeded restart limits. "
                f"Manual intervention required."
            )
            await self._on_escalation(msg)

    async def handle_child_escalation(self, child_supervisor_id: str) -> None:
        """Handle escalation from a child supervisor.

        Treats the escalating child supervisor as a failed child and applies
        this supervisor's own restart strategy.
        """
        logger.warning(
            "Supervisor %s received escalation from child %s",
            self.supervisor_id,
            child_supervisor_id,
        )
        await self._handle_child_failure(child_supervisor_id)
