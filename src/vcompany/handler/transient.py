"""PMTransientHandler -- TransientHandler implementation for PM role (D-12).

Extracts prefix-based message dispatch, stuck detector, and auto-assignment
from FulltimeAgent into a composable handler that satisfies the TransientHandler
protocol.

Handler is mostly stateless per D-02 -- all mutable state (backlog, project_state,
agent timestamps, stuck detector task) lives on the container and is accessed
via container.xxx.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.container.container import AgentContainer
    from vcompany.models.messages import MessageContext

logger = logging.getLogger("vcompany.handler.transient")


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


class PMTransientHandler:
    """TransientHandler implementation for PM role (D-12).

    Extracts prefix-based message dispatch, stuck detector, and
    auto-assignment from FulltimeAgent into a composable handler.
    """

    async def handle_message(self, container: AgentContainer, context: MessageContext) -> None:
        """Process an inbound Discord message routed to the PM.

        Dispatches by content prefix:
        - [Phase Complete] -- agent finished a phase, update tracking
        - [Task Completed] -- mark task done, auto-assign next
        - [Task Failed] -- mark task failed
        - [Request Assignment] -- assign next pending item
        - [Health Change] -- update agent state timestamps
        - Otherwise: log as informational

        Wraps in lifecycle transitions for listening/processing sub-states.

        Args:
            container: The AgentContainer this handler is attached to.
            context: Message context with sender, channel, content.
        """
        container._lifecycle.start_processing()
        try:
            content = context.content
            sender = context.sender

            if content.startswith("[Phase Complete]"):
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
                container._agent_state_timestamps[agent_id] = (
                    phase, asyncio.get_event_loop().time()
                )
                container._stuck_detected_agents.discard(agent_id)

            elif content.startswith("[Task Completed]"):
                # Format: "[Task Completed] agent={agent_id} item={item_id}"
                agent_id = _extract_field(content, "agent=", sender)
                item_id = _extract_field(content, "item=", "")
                if container._project_state is not None and item_id:
                    await container._project_state.handle_task_completed(agent_id, item_id)
                    await self._auto_assign_next(container, agent_id)

            elif content.startswith("[Task Failed]"):
                # Format: "[Task Failed] agent={agent_id} item={item_id}"
                agent_id = _extract_field(content, "agent=", sender)
                item_id = _extract_field(content, "item=", "")
                if container._project_state is not None and item_id:
                    await container._project_state.handle_task_failed(agent_id, item_id)

            elif content.startswith("[Request Assignment]"):
                # Format: "[Request Assignment] agent={agent_id}"
                agent_id = _extract_field(content, "agent=", sender)
                if container._project_state is not None:
                    await container._project_state.assign_next_task(agent_id)

            elif content.startswith("[Health Change]"):
                # Format: "[Health Change] agent={agent_id} state={state} inner={inner_state}"
                agent_id = _extract_field(content, "agent=", sender)
                inner = _extract_field(content, "inner=", "")
                if inner:
                    container._agent_state_timestamps[agent_id] = (
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
            container._lifecycle.done_processing()

    async def on_start(self, container: AgentContainer) -> None:
        """Start stuck detector background task.

        Args:
            container: The AgentContainer this handler is attached to.
        """
        container._stuck_detector_task = asyncio.create_task(
            self._run_stuck_detector(container)
        )

    async def on_stop(self, container: AgentContainer) -> None:
        """Cancel stuck detector task if running.

        Args:
            container: The AgentContainer this handler is attached to.
        """
        if container._stuck_detector_task is not None:
            container._stuck_detector_task.cancel()
            try:
                await container._stuck_detector_task
            except asyncio.CancelledError:
                pass
            container._stuck_detector_task = None

    # --- Private helpers ---

    async def _auto_assign_next(self, container: AgentContainer, agent_id: str) -> None:
        """Auto-assign the next pending backlog item to agent via Discord (VIS-06).

        Args:
            container: The AgentContainer this handler is attached to.
            agent_id: ID of the agent to assign work to.
        """
        if container._project_state is None:
            return
        item = await container._project_state.assign_next_task(agent_id)
        if item is None:
            logger.info("No pending backlog items for %s -- agent idle", agent_id)
            return
        logger.info("Auto-assigned %s to agent %s", item.item_id, agent_id)
        await container._send_discord(
            f"agent-{agent_id}",
            f"[Task Assigned] @{agent_id}: {item.title} (item: {item.item_id})",
        )

    async def _run_stuck_detector(self, container: AgentContainer) -> None:
        """Background loop detecting agents stuck in the same GSD state (PMAC-05).

        Args:
            container: The AgentContainer this handler is attached to.
        """
        while True:
            await asyncio.sleep(container._stuck_check_interval)
            now = asyncio.get_event_loop().time()
            for agent_id, (state, ts) in list(container._agent_state_timestamps.items()):
                elapsed = now - ts
                if (
                    elapsed > container._stuck_threshold_seconds
                    and agent_id not in container._stuck_detected_agents
                ):
                    container._stuck_detected_agents.add(agent_id)
                    msg = (
                        f"Agent {agent_id} stuck in state '{state}' for {int(elapsed)}s"
                        f" (threshold: {int(container._stuck_threshold_seconds)}s)"
                    )
                    logger.warning(msg)
                    await container._send_discord(
                        f"agent-{agent_id}", f"[Intervention] {msg}"
                    )
