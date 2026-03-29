"""FulltimeAgent -- Discord-message-driven container for PM role (TYPE-04).

Reacts to inbound Discord messages via receive_discord_message(). Scoped to
a project (has project_id). Processes messages one at a time, transitioning
between listening and processing sub-states. Persists state via memory_store
for crash recovery.

Extended with backlog operations: routes task lifecycle events
(task_completed, task_failed, request_assignment) through Discord messages
to ProjectStateManager for PM-owned project state coordination.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from statemachine.orderedset import OrderedSet

from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle
from vcompany.autonomy.backlog import BacklogItem, BacklogQueue
from vcompany.autonomy.project_state import ProjectStateManager
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport
from vcompany.models.messages import MessageContext

if TYPE_CHECKING:
    from vcompany.container.communication import CommunicationPort, SendMessagePayload

logger = logging.getLogger("vcompany.agent.fulltime_agent")


class FulltimeAgent(AgentContainer):
    """Discord-message-driven agent for PM role (TYPE-04).

    Reacts to inbound Discord messages (phase transitions, task completions,
    health changes, assignments) via receive_discord_message(). Scoped to a
    project.

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
        # Backlog and project state (wired after construction, not in __init__ args)
        self.backlog: BacklogQueue | None = None
        self._project_state: ProjectStateManager | None = None

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

    # --- Discord Message Handling ---

    async def receive_discord_message(self, context: MessageContext) -> None:
        """Process an inbound Discord message routed to the PM.

        Parses message content for prefixed message types and dispatches
        to the appropriate PM action. Uses lifecycle transitions to track
        listening vs processing sub-states.

        Message type dispatch based on content prefix:
        - [Phase Complete] -- agent finished a phase, update tracking
        - [Task Completed] -- mark task done, auto-assign next
        - [Task Failed] -- mark task failed
        - [Request Assignment] -- assign next pending item
        - [Health Change] -- update agent state timestamps
        - Otherwise: log as informational
        """
        self._lifecycle.start_processing()
        try:
            content = context.content
            sender = context.sender

            if content.startswith("[Phase Complete]"):
                # Extract agent_id and phase from message
                # Format: "[Phase Complete] {agent_id} finished '{from_phase}', entering '{phase}'. @PM"
                parts = content.split()
                agent_id = parts[2] if len(parts) > 2 else sender
                # Extract phase from 'entering' clause
                phase = ""
                if "entering '" in content:
                    phase = content.split("entering '")[1].split("'")[0]
                logger.info(
                    "PM received phase transition: agent=%s phase=%s",
                    agent_id, phase,
                )
                self._agent_state_timestamps[agent_id] = (
                    phase, asyncio.get_event_loop().time()
                )
                self._stuck_detected_agents.discard(agent_id)

            elif content.startswith("[Task Completed]"):
                # Format: "[Task Completed] agent={agent_id} item={item_id}"
                agent_id = _extract_field(content, "agent=", sender)
                item_id = _extract_field(content, "item=", "")
                if self._project_state is not None and item_id:
                    await self._project_state.handle_task_completed(agent_id, item_id)
                    await self._auto_assign_next(agent_id)

            elif content.startswith("[Task Failed]"):
                # Format: "[Task Failed] agent={agent_id} item={item_id}"
                agent_id = _extract_field(content, "agent=", sender)
                item_id = _extract_field(content, "item=", "")
                if self._project_state is not None and item_id:
                    await self._project_state.handle_task_failed(agent_id, item_id)

            elif content.startswith("[Request Assignment]"):
                # Format: "[Request Assignment] agent={agent_id}"
                agent_id = _extract_field(content, "agent=", sender)
                if self._project_state is not None:
                    await self._project_state.assign_next_task(agent_id)

            elif content.startswith("[Health Change]"):
                # Format: "[Health Change] agent={agent_id} state={state} inner={inner_state}"
                agent_id = _extract_field(content, "agent=", sender)
                inner = _extract_field(content, "inner=", "")
                if inner:
                    self._agent_state_timestamps[agent_id] = (
                        inner, asyncio.get_event_loop().time()
                    )
                logger.info(
                    "PM received health_change: agent=%s inner=%s",
                    agent_id, inner,
                )

            else:
                logger.info(
                    "PM received unhandled message from %s: %.100s",
                    sender, content,
                )
        finally:
            self._lifecycle.done_processing()

    # --- Discord Output ---

    async def _send_discord(self, channel_name: str, content: str) -> None:
        """Send a message to a Discord channel via the CommunicationPort.

        Uses self.comm_port (from parent AgentContainer) if available.
        Channel name is used as a logical identifier; the CommunicationPort
        adapter handles name-to-id resolution.

        Args:
            channel_name: Logical channel name (e.g. "agent-alpha", "pm").
            content: Message text to send.
        """
        if self.comm_port is None:
            logger.warning("Cannot send Discord message -- no comm_port wired")
            return
        from vcompany.container.communication import SendMessagePayload

        payload = SendMessagePayload(channel_id=channel_name, content=content)
        await self.comm_port.send_message(payload)

    # --- PM Action Methods ---

    async def _auto_assign_next(self, agent_id: str) -> None:
        """Auto-assign the next pending backlog item to agent via Discord (VIS-06)."""
        if self._project_state is None:
            return
        item = await self._project_state.assign_next_task(agent_id)
        if item is None:
            logger.info("No pending backlog items for %s -- agent idle", agent_id)
            return
        logger.info("Auto-assigned %s to agent %s", item.item_id, agent_id)
        await self._send_discord(
            f"agent-{agent_id}",
            f"[Task Assigned] @{agent_id}: {item.title} (item: {item.item_id})",
        )

    async def trigger_integration_review(self) -> None:
        """Trigger integration review via Discord message (PMAC-01)."""
        logger.info("PM triggering integration review")
        await self._send_discord(
            "integration",
            "[Integration Review] PM requests integration review",
        )

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

    async def escalate_to_strategist(
        self, agent_id: str, question: str, confidence: float = 0.0
    ) -> None:
        """Escalate a decision to the Strategist via Discord (PMAC-04)."""
        logger.info("PM escalating to Strategist for %s: %s", agent_id, question[:80])
        await self._send_discord(
            "strategist",
            f"[PM Escalation] Agent {agent_id} asks: {question}\n"
            f"PM confidence: {confidence:.0%}. Please provide your assessment.",
        )

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
                    await self._send_discord(f"agent-{agent_id}", f"[Intervention] {msg}")

    # --- Lifecycle Overrides ---

    async def start(self) -> None:
        """Transition to running, open memory, start stuck detector."""
        await super().start()
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
        """Transition to sleeping."""
        await super().sleep()

    async def error(self) -> None:
        """Transition to errored."""
        await super().error()


def _extract_field(content: str, field: str, default: str) -> str:
    """Extract a named field value from a message string.

    Parses patterns like 'agent=alpha' or 'item=backlog-001' from
    space-delimited message content.

    Args:
        content: Full message content string.
        field: Field prefix to search for (e.g. "agent=").
        default: Default value if field not found.

    Returns:
        Extracted value, or default.
    """
    for part in content.split():
        if part.startswith(field):
            return part[len(field):]
    return default
