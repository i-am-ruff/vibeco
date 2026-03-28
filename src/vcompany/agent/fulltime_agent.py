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
    from vcompany.container.child_spec import ChildSpec
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
        # WORK-03: Sends assignment + GSD command to agent.
        self._on_assign_task: Callable[[str, BacklogItem], Awaitable[None]] | None = None
        # PMAC-01: Triggers integration review.
        self._on_trigger_integration_review: Callable[[], Awaitable[None]] | None = None
        # PMAC-03: Agent recruitment/removal callbacks.
        self._on_recruit_agent: Callable[[ChildSpec], Awaitable[None]] | None = None
        self._on_remove_agent: Callable[[str], Awaitable[None]] | None = None
        # PMAC-04: Escalate question to Strategist, returns answer or None.
        self._on_escalate_to_strategist: Callable[[str, str, float], Awaitable[str | None]] | None = None
        # PMAC-05: Sends intervention message to an agent channel.
        self._on_send_intervention: Callable[[str, str], Awaitable[None]] | None = None

        # Stuck detector state (PMAC-05)
        self._agent_state_timestamps: dict[str, tuple[str, float]] = {}
        self._stuck_threshold_seconds: float = 1800.0  # 30 min default
        self._stuck_check_interval: float = 60.0  # poll every 60s
        self._stuck_detected_agents: set[str] = set()
        self._stuck_detector_task: asyncio.Task[None] | None = None

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
            await self._auto_assign_next(event["agent_id"])
        elif event_type == "task_failed" and self._project_state is not None:
            await self._project_state.handle_task_failed(
                event["agent_id"], event["item_id"]
            )
        elif event_type == "add_backlog_item" and self.backlog is not None:
            await self.backlog.append(BacklogItem(**event["item"]))
        elif event_type == "request_assignment" and self._project_state is not None:
            await self._project_state.assign_next_task(event["agent_id"])
        elif event_type == "health_change":
            agent_id = event.get("agent_id", "")
            inner = event.get("inner_state", "")
            logger.info(
                "PM received health_change: agent=%s state=%s inner=%s",
                agent_id, event.get("state"), inner,
            )
            if inner:
                self._agent_state_timestamps[agent_id] = (inner, asyncio.get_event_loop().time())
        elif event_type == "gsd_transition":
            agent_id = event.get("agent_id", "")
            to_phase = event.get("to_phase", "")
            logger.info(
                "PM received gsd_transition: agent=%s %s->%s",
                agent_id, event.get("from_phase"), to_phase,
            )
            self._agent_state_timestamps[agent_id] = (to_phase, asyncio.get_event_loop().time())
            self._stuck_detected_agents.discard(agent_id)
            if self._on_gsd_review is not None:
                await self._on_gsd_review(agent_id, to_phase)
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
            await self.escalate_to_strategist(
                event.get("agent_id", ""), event.get("reason", "unknown")
            )
        else:
            logger.warning("Unhandled event type: %s", event_type)

    # --- Lifecycle Overrides ---

    # --- PM Action Methods ---

    async def _auto_assign_next(self, agent_id: str) -> None:
        """Auto-assign the next pending backlog item to agent (WORK-03)."""
        if self._project_state is None:
            return
        item = await self._project_state.assign_next_task(agent_id)
        if item is None:
            logger.info("No pending backlog items for %s -- agent idle", agent_id)
            return
        logger.info("Auto-assigned %s to agent %s", item.item_id, agent_id)
        if self._on_assign_task is not None:
            await self._on_assign_task(agent_id, item)

    async def trigger_integration_review(self) -> None:
        """Trigger integration review via callback (PMAC-01)."""
        logger.info("PM triggering integration review")
        if self._on_trigger_integration_review is not None:
            await self._on_trigger_integration_review()
        else:
            logger.warning("Integration review requested but no handler wired")

    async def inject_backlog_item(self, item: BacklogItem, urgent: bool = False) -> None:
        """Inject an item into the backlog (PMAC-02)."""
        if self.backlog is None:
            logger.warning("Cannot inject backlog item -- backlog not wired")
            return
        if urgent:
            await self.backlog.insert_urgent(item)
            logger.info("Injected urgent backlog item: %s", item.item_id)
        else:
            await self.backlog.append(item)
            logger.info("Appended backlog item: %s", item.item_id)

    async def request_recruit_agent(self, spec: ChildSpec) -> None:
        """Request agent recruitment through supervisor (PMAC-03)."""
        logger.info("PM requesting agent recruitment: %s", spec.child_id)
        if self._on_recruit_agent is not None:
            await self._on_recruit_agent(spec)
        else:
            logger.warning("Agent recruitment requested but no handler wired")

    async def request_remove_agent(self, agent_id: str) -> None:
        """Request agent removal through supervisor (PMAC-03)."""
        logger.info("PM requesting agent removal: %s", agent_id)
        if self._on_remove_agent is not None:
            await self._on_remove_agent(agent_id)
        else:
            logger.warning("Agent removal requested but no handler wired")

    async def escalate_to_strategist(
        self, agent_id: str, question: str, confidence: float = 0.0
    ) -> str | None:
        """Escalate a decision to the Strategist, returning the answer (PMAC-04)."""
        logger.info("PM escalating to Strategist for %s: %s", agent_id, question[:80])
        if self._on_escalate_to_strategist is not None:
            return await self._on_escalate_to_strategist(agent_id, question, confidence)
        logger.warning("Strategist escalation requested but no handler wired")
        return None

    # --- Stuck Detector ---

    async def _run_stuck_detector(self) -> None:
        """Background loop detecting agents stuck in the same GSD state (PMAC-05)."""
        while True:
            await asyncio.sleep(self._stuck_check_interval)
            now = asyncio.get_event_loop().time()
            for agent_id, (state, ts) in list(self._agent_state_timestamps.items()):
                elapsed = now - ts
                if (
                    elapsed > self._stuck_threshold_seconds
                    and agent_id not in self._stuck_detected_agents
                ):
                    self._stuck_detected_agents.add(agent_id)
                    msg = (
                        f"Agent {agent_id} stuck in state '{state}' for {int(elapsed)}s"
                        f" (threshold: {int(self._stuck_threshold_seconds)}s)"
                    )
                    logger.warning(msg)
                    if self._on_send_intervention is not None:
                        await self._on_send_intervention(agent_id, msg)

    # --- Lifecycle Overrides ---

    async def start(self) -> None:
        """Transition to running, open memory, restore event count, start stuck detector."""
        await super().start()
        count_str = await self.memory.get("events_processed")
        if count_str is not None:
            self._events_processed = int(count_str)
        self._stuck_detector_task = asyncio.create_task(self._run_stuck_detector())

    async def stop(self) -> None:
        """Cancel stuck detector task then delegate to parent stop."""
        if self._stuck_detector_task is not None:
            self._stuck_detector_task.cancel()
            try:
                await self._stuck_detector_task
            except asyncio.CancelledError:
                pass
        await super().stop()

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
