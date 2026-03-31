"""ProjectStateManager -- PM-owned project state coordination.

The PM is the single writer to the backlog. Agents never write to PM's
MemoryStore directly. They post events to PM's queue. If an agent crashes,
the event was either posted or it was not -- PM's state remains consistent.

ProjectStateManager coordinates:
- Assigning backlog items to agents (claim_next + record assignment)
- Handling task completions (mark_completed + clear assignment)
- Handling task failures (mark_pending + clear assignment)
- Recovering orphaned assignments from crashed agents (reassign_stale)
"""

from __future__ import annotations

import json
import logging

from vcompany.autonomy.backlog import BacklogItem, BacklogItemStatus, BacklogQueue
from vcompany.shared.memory_store import MemoryStore

logger = logging.getLogger("vcompany.autonomy.project_state")


class ProjectStateManager:
    """Coordinates PM backlog and agent assignments.

    The PM owns both the backlog and the assignment records. Agents
    communicate task lifecycle events via the PM's event queue.

    Args:
        backlog: The PM's BacklogQueue instance.
        memory: The PM's MemoryStore for tracking assignments.
    """

    def __init__(self, backlog: BacklogQueue, memory: MemoryStore) -> None:
        self._backlog = backlog
        self._memory = memory

    async def assign_next_task(self, agent_id: str) -> BacklogItem | None:
        """Claim the next PENDING item for an agent and record the assignment.

        Args:
            agent_id: The agent requesting work.

        Returns:
            The claimed BacklogItem, or None if no PENDING items.
        """
        item = await self._backlog.claim_next(agent_id)
        if item is None:
            return None

        # Store assignment in PM's memory under assignment:{agent_id}
        assignment_data = json.dumps(item.model_dump())
        await self._memory.set(f"assignment:{agent_id}", assignment_data)

        logger.info("Assigned %s to agent %s", item.item_id, agent_id)
        return item

    async def handle_task_completed(self, agent_id: str, item_id: str) -> None:
        """Mark a backlog item as COMPLETED and clear the agent's assignment.

        Args:
            agent_id: The agent that completed the task.
            item_id: The backlog item ID.
        """
        await self._backlog.mark_completed(item_id)
        await self._memory.delete(f"assignment:{agent_id}")
        logger.info("Agent %s completed item %s", agent_id, item_id)

    async def handle_task_failed(self, agent_id: str, item_id: str) -> None:
        """Re-queue a failed item as PENDING and clear the agent's assignment.

        Args:
            agent_id: The agent that failed the task.
            item_id: The backlog item ID.
        """
        await self._backlog.mark_pending(item_id)
        await self._memory.delete(f"assignment:{agent_id}")
        logger.info("Agent %s failed item %s, re-queued as PENDING", agent_id, item_id)

    async def reassign_stale(self, active_agent_ids: set[str]) -> list[str]:
        """Recover ASSIGNED items whose agents are no longer active.

        Iterates all backlog items. Items with status ASSIGNED whose
        assigned_to is not in active_agent_ids are marked PENDING.

        Args:
            active_agent_ids: Set of currently active agent IDs.

        Returns:
            List of item_ids that were reassigned.
        """
        reassigned: list[str] = []
        for item in self._backlog._items:
            if (
                item.status == BacklogItemStatus.ASSIGNED
                and item.assigned_to is not None
                and item.assigned_to not in active_agent_ids
            ):
                await self._backlog.mark_pending(item.item_id)
                # Clean up stale assignment record
                await self._memory.delete(f"assignment:{item.assigned_to}")
                reassigned.append(item.item_id)
                logger.info(
                    "Reassigned stale item %s (was assigned to %s)",
                    item.item_id,
                    item.assigned_to,
                )
        return reassigned

    async def get_agent_assignment(self, agent_id: str) -> dict | None:
        """Read the current assignment for an agent from PM's memory.

        Args:
            agent_id: The agent to look up.

        Returns:
            Parsed assignment dict, or None if no assignment.
        """
        raw = await self._memory.get(f"assignment:{agent_id}")
        if raw is None:
            return None
        return json.loads(raw)
