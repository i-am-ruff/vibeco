"""FulltimeAgent -- event-driven container for PM role (TYPE-04).

Reacts to events (state transitions, health changes, escalations, briefings)
via asyncio.Queue. Scoped to a project (has project_id). Processes events
one at a time, transitioning between listening and processing sub-states.
Persists event processing state via memory_store for crash recovery.

Extended with backlog operations: routes task lifecycle events
(task_completed, task_failed, add_backlog_item, request_assignment) to
ProjectStateManager for PM-owned project state coordination.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from statemachine.orderedset import OrderedSet

from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle
from vcompany.autonomy.backlog import BacklogItem, BacklogQueue
from vcompany.autonomy.project_state import ProjectStateManager
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport

if TYPE_CHECKING:
    from vcompany.container.communication import CommunicationPort

logger = logging.getLogger("vcompany.agent.fulltime_agent")


class FulltimeAgent(AgentContainer):
    """Event-driven agent for PM role (TYPE-04).

    Reacts to events (state transitions, health changes, escalations,
    briefings) via asyncio.Queue. Scoped to a project.

    Args:
        context: Immutable agent metadata (must have project_id set).
        data_dir: Root directory for persistent data.
        comm_port: Optional communication channel.
        on_state_change: Optional callback invoked with HealthReport after
            every lifecycle transition.
    """

    def __init__(
        self,
        context: ContainerContext,
        data_dir: Path,
        comm_port: CommunicationPort | None = None,
        on_state_change: Callable[[HealthReport], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(context, data_dir, comm_port, on_state_change, **kwargs)
        # Override parent's ContainerLifecycle with EventDrivenLifecycle
        self._lifecycle = EventDrivenLifecycle(model=self, state_field="_fsm_state")
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._events_processed: int = 0
        self._checkpoint_lock = asyncio.Lock()
        # Backlog and project state (wired after construction, not in __init__ args)
        self.backlog: BacklogQueue | None = None
        self._project_state: ProjectStateManager | None = None
        # GATE-02: Callback invoked when gsd_transition event received.
        # Wired by VcoBot.on_ready to call PlanReviewCog.dispatch_pm_review().
        self._on_gsd_review: Callable[[str, str], Awaitable[None]] | None = None

    # --- Properties (override parent for compound state handling) ---

    @property
    def state(self) -> str:
        """Current outer lifecycle state as a plain string."""
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            return str(list(val)[0])
        return str(val)

    @property
    def inner_state(self) -> str | None:
        """Sub-state when in running compound state (listening/processing)."""
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            items = list(val)
            if len(items) >= 2:
                return str(items[1])
        return None

    # --- Event Processing ---

    async def post_event(self, event: dict[str, Any]) -> None:
        """Add an event to the queue for processing."""
        await self._event_queue.put(event)

    async def process_next_event(self) -> bool:
        """Process one event from queue. Returns False if queue empty."""
        try:
            event = self._event_queue.get_nowait()
        except asyncio.QueueEmpty:
            return False

        self._lifecycle.start_processing()
        try:
            await self._handle_event(event)
            self._events_processed += 1
            await self.memory.set("events_processed", str(self._events_processed))
        finally:
            self._lifecycle.done_processing()
        return True

    async def _handle_event(self, event: dict[str, Any]) -> None:
        """Process a single event, routing to appropriate backlog operation.

        Supported event types:
        - task_completed: marks item COMPLETED via ProjectStateManager
        - task_failed: re-queues item as PENDING via ProjectStateManager
        - add_backlog_item: appends new item to backlog
        - request_assignment: assigns next PENDING item to requesting agent

        Unknown event types are logged as warnings (no-op, no raise).
        """
        event_type = event.get("type", "")

        if event_type == "task_completed" and self._project_state is not None:
            await self._project_state.handle_task_completed(
                event["agent_id"], event["item_id"]
            )
        elif event_type == "task_failed" and self._project_state is not None:
            await self._project_state.handle_task_failed(
                event["agent_id"], event["item_id"]
            )
        elif event_type == "add_backlog_item" and self.backlog is not None:
            await self.backlog.append(BacklogItem(**event["item"]))
        elif event_type == "request_assignment" and self._project_state is not None:
            await self._project_state.assign_next_task(event["agent_id"])
        elif event_type == "health_change":
            logger.info(
                "PM received health_change: agent=%s state=%s inner=%s",
                event.get("agent_id"), event.get("state"), event.get("inner_state"),
            )
        elif event_type == "gsd_transition":
            logger.info(
                "PM received gsd_transition: agent=%s %s->%s",
                event.get("agent_id"), event.get("from_phase"), event.get("to_phase"),
            )
            if self._on_gsd_review is not None:
                await self._on_gsd_review(event.get("agent_id", ""), event.get("to_phase", ""))
        elif event_type == "briefing":
            logger.info(
                "PM received briefing from %s (content_len=%d)",
                event.get("agent_id"), len(event.get("content", "")),
            )
        elif event_type == "escalation":
            logger.info(
                "PM received escalation: agent=%s reason=%s",
                event.get("agent_id"), event.get("reason"),
            )
        else:
            logger.warning("Unhandled event type: %s", event_type)

    # --- Lifecycle Overrides ---

    async def start(self) -> None:
        """Transition to running, open memory, and restore event count."""
        await super().start()
        count_str = await self.memory.get("events_processed")
        if count_str is not None:
            self._events_processed = int(count_str)

    async def sleep(self) -> None:
        """Checkpoint event count then transition to sleeping."""
        async with self._checkpoint_lock:
            await self.memory.set("events_processed", str(self._events_processed))
        await super().sleep()

    async def error(self) -> None:
        """Checkpoint event count then transition to errored."""
        async with self._checkpoint_lock:
            await self.memory.set("events_processed", str(self._events_processed))
        await super().error()
