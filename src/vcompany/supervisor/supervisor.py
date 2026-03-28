"""Supervisor base class with Erlang-style restart strategies (SUPV-02..06).

Manages child AgentContainers via asyncio Tasks. Implements one_for_one,
all_for_one, and rest_for_one restart strategies with restart intensity
tracking and escalation to parent or callback.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from vcompany.autonomy.delegation import (
    DelegationPolicy,
    DelegationRequest,
    DelegationResult,
    DelegationTracker,
)
from vcompany.container.child_spec import ChildSpec, RestartPolicy
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.factory import create_container
from vcompany.container.health import HealthNode, HealthReport, HealthTree
from vcompany.resilience.bulk_failure import BulkFailureDetector
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
        on_health_change: Callable[[HealthReport], Awaitable[None]] | None = None,
        delegation_policy: DelegationPolicy | None = None,
        tmux_manager: object | None = None,
        project_dir: Path | None = None,
        session_name: str | None = None,
        comm_port: object | None = None,
    ) -> None:
        self.supervisor_id = supervisor_id
        self.strategy = strategy
        self._child_specs = list(child_specs)  # preserve order
        self._parent = parent
        self._on_escalation = on_escalation
        self._on_health_change = on_health_change
        self._data_dir = data_dir or Path("/tmp/vcompany-supervisor")
        # Tmux bridge params -- injected into child containers
        self._tmux_manager = tmux_manager
        self._project_dir = project_dir
        self._session_name = session_name
        # Communication port passed to all child containers
        self._comm_port = comm_port

        self._children: dict[str, AgentContainer] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._child_events: dict[str, asyncio.Event] = {}
        # AUTO-03/04: Delegation tracking
        self._delegation_tracker: DelegationTracker | None = (
            DelegationTracker(delegation_policy) if delegation_policy is not None else None
        )
        self._delegated_children: dict[str, str] = {}  # agent_id -> requester_id
        self._restart_tracker = RestartTracker(
            max_restarts=max_restarts,
            window_seconds=window_seconds,
        )
        # RESL-02: Bulk failure detection (upstream outage)
        self._bulk_detector: BulkFailureDetector | None = None
        if len(child_specs) >= 2:
            self._bulk_detector = BulkFailureDetector(
                child_count=len(child_specs),
            )
        self._restarting: bool = False
        self._state: str = "stopped"
        self._health_reports: dict[str, HealthReport] = {}

    # --- Properties ---

    @property
    def state(self) -> str:
        """Current supervisor state: 'running' or 'stopped'."""
        return self._state

    @property
    def children(self) -> dict[str, AgentContainer]:
        """Dict of child_id -> AgentContainer."""
        return self._children

    # --- Health Aggregation ---

    def health_tree(self) -> HealthTree:
        """Build a health tree from cached reports and live containers.

        Iterates ``_child_specs`` (not ``_health_reports``) to preserve
        child ordering. Uses cached reports when available, falling back
        to ``container.health_report()`` for children without a cached report.
        """
        nodes: list[HealthNode] = []
        for spec in self._child_specs:
            report = self._health_reports.get(spec.child_id)
            if report is None:
                container = self._children.get(spec.child_id)
                if container is not None:
                    report = container.health_report()
            if report is not None:
                nodes.append(HealthNode(report=report))
        return HealthTree(
            supervisor_id=self.supervisor_id,
            state=self._state,
            children=nodes,
        )

    # --- Delegation (AUTO-03/04) ---

    async def handle_delegation_request(self, request: DelegationRequest) -> DelegationResult:
        """Validate and execute a delegation request.

        Checks the request against delegation policy (concurrent caps, rate
        limits, allowed agent types). If approved, spawns a TEMPORARY agent
        and tracks it for cleanup on termination.

        Args:
            request: The delegation request from an agent.

        Returns:
            DelegationResult with approval status and spawned agent_id.
        """
        if self._delegation_tracker is None:
            return DelegationResult(approved=False, reason="Delegation not enabled")

        ok, reason = self._delegation_tracker.can_delegate(request.requester_id, request.agent_type)
        if not ok:
            return DelegationResult(approved=False, reason=reason)

        agent_id = f"delegated-{request.requester_id}-{uuid.uuid4().hex[:6]}"

        # Derive project_id from first child spec if available
        project_id = None
        if self._child_specs:
            project_id = self._child_specs[0].context.project_id

        context = ContainerContext(
            agent_id=agent_id,
            agent_type=request.agent_type,
            parent_id=self.supervisor_id,
            project_id=project_id,
        )
        # Apply context overrides
        for key, value in request.context_overrides.items():
            if hasattr(context, key):
                object.__setattr__(context, key, value)

        spec = ChildSpec(
            child_id=agent_id,
            agent_type=request.agent_type,
            context=context,
            restart_policy=RestartPolicy.TEMPORARY,
        )

        self._child_specs.append(spec)
        await self._start_child(spec)
        self._delegation_tracker.record_delegation(request.requester_id, agent_id)
        self._delegated_children[agent_id] = request.requester_id

        return DelegationResult(approved=True, agent_id=agent_id)

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
            if child is not None and child.state not in ("stopped", "destroyed", "stopping"):
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
            self._health_reports[child_id] = report

            # AUTO-04: Clean up delegation tracking for terminated delegated children
            if child_id in self._delegated_children and report.state in ("stopped", "destroyed"):
                requester_id = self._delegated_children.pop(child_id)
                if self._delegation_tracker is not None:
                    self._delegation_tracker.record_completion(requester_id, child_id)

            if self._restarting:
                return  # Suppress during supervisor-initiated restarts
            if report.state in ("errored", "stopped", "stopping"):
                event = self._child_events.get(child_id)
                if event is not None:
                    event.set()

            # Notify on significant transitions (not during restarts)
            if self._on_health_change is not None and report.state in (
                "errored",
                "running",
                "stopped",
                "blocked",
                "stopping",
            ):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._on_health_change(report))
                except RuntimeError:
                    pass  # No running event loop

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

        # Clear stale health report before creating new container
        self._health_reports.pop(spec.child_id, None)

        # Create event for this child
        event = asyncio.Event()
        self._child_events[spec.child_id] = event

        # Create and start container
        container = create_container(
            spec,
            data_dir=self._data_dir,
            comm_port=self._comm_port,
            on_state_change=self._make_state_change_callback(spec.child_id),
            tmux_manager=self._tmux_manager,
            project_dir=self._project_dir,
            project_session_name=self._session_name,
        )
        await container.start()
        self._children[spec.child_id] = container

        # Create monitor task
        self._tasks[spec.child_id] = asyncio.create_task(
            self._monitor_child(spec.child_id)
        )

    async def _monitor_child(self, child_id: str) -> None:
        """Wait for child events and handle failures.

        Uses a 30s timeout on event.wait() to periodically check tmux
        liveness. If the tmux pane is dead but the FSM still says
        'running', transitions the container to errored.
        """
        event = self._child_events[child_id]
        while True:
            try:
                await asyncio.wait_for(event.wait(), timeout=30.0)
                event.clear()
            except asyncio.TimeoutError:
                # Periodic liveness check
                container = self._children.get(child_id)
                if container is not None and container.state == "running":
                    if hasattr(container, "is_tmux_alive") and not container.is_tmux_alive():
                        logger.warning("Tmux pane dead for %s, transitioning to errored", child_id)
                        await container.error()
                continue

            container = self._children.get(child_id)
            if container is None:
                break

            if container.state == "errored":
                await self._handle_child_failure(child_id)
            elif container.state == "stopping":
                pass  # Transient -- will reach stopped soon; do not restart
            elif container.state == "blocked":
                pass  # Blocked -- do not restart, wait for external unblock
            elif container.state in ("stopped", "destroyed"):
                # Check if transient that stopped normally -- no restart
                break

    # --- Failure Handling ---

    async def _handle_child_failure(self, failed_id: str) -> None:
        """Apply restart policy and strategy for a failed child."""
        # RESL-02: Check for bulk failure (upstream outage detection)
        if self._bulk_detector is not None:
            if self._bulk_detector.is_in_backoff:
                logger.info(
                    "Supervisor %s in global backoff, skipping restart for %s",
                    self.supervisor_id,
                    failed_id,
                )
                return
            is_outage = self._bulk_detector.record_failure(failed_id)
            if is_outage:
                logger.warning(
                    "Supervisor %s detected upstream outage (bulk failure from %s)",
                    self.supervisor_id,
                    failed_id,
                )
                await self._enter_global_backoff()
                return

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

    async def _enter_global_backoff(self) -> None:
        """Enter global backoff due to bulk failure (RESL-02).

        Suppresses per-agent restarts. Notifies owner via escalation callback.
        After backoff period, resets detector to allow restarts.
        """
        if self._bulk_detector is None:
            return

        backoff = self._bulk_detector.current_backoff
        msg = (
            f"UPSTREAM OUTAGE: Supervisor {self.supervisor_id} detected bulk failure. "
            f"Global backoff for {backoff:.0f}s. Per-agent restarts suppressed."
        )

        if self._on_escalation is not None:
            await self._on_escalation(msg)
        elif self._parent is not None:
            # Notify parent but don't escalate (we're handling it)
            pass

        # Schedule backoff reset
        async def _reset_after_backoff() -> None:
            await asyncio.sleep(backoff)
            if self._bulk_detector is not None:
                self._bulk_detector.escalate_backoff()
                self._bulk_detector.reset_backoff()
                logger.info(
                    "Supervisor %s global backoff expired, resuming restarts",
                    self.supervisor_id,
                )

        asyncio.create_task(_reset_after_backoff())

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
        if old is not None and old.state not in ("stopped", "destroyed", "stopping"):
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
                if child is not None and child.state not in ("stopped", "destroyed", "stopping"):
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
                if child is not None and child.state not in ("stopped", "destroyed", "stopping"):
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
            if child is not None and child.state not in ("stopped", "destroyed", "stopping"):
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
