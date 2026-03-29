"""BacklogQueue — living milestone backlog managed by PM, consumed by GsdAgents.

The backlog is a mutable ordered queue of BacklogItems. The PM appends,
prioritizes, reorders, and cancels items. GsdAgents claim work via
claim_next(). All mutations persist atomically to MemoryStore.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field

from vcompany.container.memory_store import MemoryStore

BACKLOG_KEY = "backlog"


class BacklogItemStatus(str, Enum):
    """Status of a backlog item through its lifecycle."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


def _short_uuid() -> str:
    return uuid4().hex[:8]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BacklogItem(BaseModel):
    """A single unit of work in the milestone backlog."""

    item_id: str = Field(default_factory=_short_uuid)
    title: str
    description: str = ""
    priority: int = 0
    status: BacklogItemStatus = BacklogItemStatus.PENDING
    assigned_to: str | None = None
    created_at: str = Field(default_factory=_utc_now)


class BacklogQueue:
    """Ordered queue of BacklogItems persisted in MemoryStore.

    Thread-safe via asyncio.Lock. All mutations persist immediately.

    Usage::

        queue = BacklogQueue(memory_store)
        await queue.load()
        await queue.append(BacklogItem(title="Build auth"))
        item = await queue.claim_next("gsd-agent-1")
        await queue.mark_completed(item.item_id)
    """

    def __init__(
        self,
        memory: MemoryStore,
        on_mutation: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._memory = memory
        self._on_mutation = on_mutation
        self._lock = asyncio.Lock()
        self._items: list[BacklogItem] = []

    async def _notify(self, message: str) -> None:
        """Fire mutation callback if registered. Never raises."""
        if self._on_mutation is not None:
            try:
                await self._on_mutation(message)
            except Exception:
                logger.warning(
                    "Backlog mutation callback failed for: %s",
                    message,
                    exc_info=True,
                )

    async def load(self) -> None:
        """Load backlog state from MemoryStore."""
        raw = await self._memory.get(BACKLOG_KEY)
        if raw is not None:
            data = json.loads(raw)
            self._items = [BacklogItem.model_validate(d) for d in data]
        else:
            self._items = []

    async def _persist(self) -> None:
        """Serialize items to JSON and write to MemoryStore.

        Caller MUST hold self._lock before calling this method.
        """
        data = [item.model_dump() for item in self._items]
        await self._memory.set(BACKLOG_KEY, json.dumps(data))

    def _find_item(self, item_id: str) -> BacklogItem:
        """Find item by ID or raise ValueError."""
        for item in self._items:
            if item.item_id == item_id:
                return item
        raise ValueError(f"Item {item_id!r} not found in backlog")

    def _find_index(self, item_id: str) -> int:
        """Find item index by ID or raise ValueError."""
        for i, item in enumerate(self._items):
            if item.item_id == item_id:
                return i
        raise ValueError(f"Item {item_id!r} not found in backlog")

    async def append(self, item: BacklogItem) -> None:
        """Add item to end of queue."""
        async with self._lock:
            self._items.append(item)
            await self._persist()
        await self._notify(f"[Backlog] Added: '{item.title}' (priority {item.priority})")

    async def insert_urgent(self, item: BacklogItem) -> None:
        """Insert item at position 0 (highest priority)."""
        async with self._lock:
            self._items.insert(0, item)
            await self._persist()
        await self._notify(f"[Backlog] Urgent: '{item.title}' inserted at position 0")

    async def insert_after(self, after_id: str, item: BacklogItem) -> None:
        """Insert item after the item with the given ID.

        Raises ValueError if after_id is not found.
        """
        async with self._lock:
            idx = self._find_index(after_id)
            self._items.insert(idx + 1, item)
            await self._persist()

    async def reorder(self, item_id: str, new_position: int) -> None:
        """Move item to a new position in the queue.

        Raises ValueError if item_id is not found.
        """
        async with self._lock:
            idx = self._find_index(item_id)
            item = self._items.pop(idx)
            pos = min(new_position, len(self._items))
            self._items.insert(pos, item)
            await self._persist()
        await self._notify(f"[Backlog] Reordered: '{item_id}' moved to position {new_position}")

    async def cancel(self, item_id: str) -> None:
        """Set item status to CANCELLED.

        Raises ValueError if item_id is not found.
        """
        async with self._lock:
            item = self._find_item(item_id)
            item.status = BacklogItemStatus.CANCELLED
            await self._persist()
        await self._notify(f"[Backlog] Cancelled: '{item_id}'")

    async def claim_next(self, agent_id: str) -> BacklogItem | None:
        """Claim the first PENDING item for the given agent.

        Sets status to ASSIGNED and assigned_to to agent_id.
        Returns the claimed item, or None if no PENDING items exist.
        """
        async with self._lock:
            for item in self._items:
                if item.status == BacklogItemStatus.PENDING:
                    item.status = BacklogItemStatus.ASSIGNED
                    item.assigned_to = agent_id
                    await self._persist()
                    await self._notify(
                        f"[Backlog] Claimed: '{item.title}' assigned to {agent_id}"
                    )
                    return item
            return None

    async def mark_completed(self, item_id: str) -> None:
        """Transition item to COMPLETED status.

        Raises ValueError if item_id is not found.
        """
        async with self._lock:
            item = self._find_item(item_id)
            item.status = BacklogItemStatus.COMPLETED
            await self._persist()
        await self._notify(f"[Backlog] Completed: '{item_id}'")

    async def mark_pending(self, item_id: str) -> None:
        """Transition item back to PENDING and clear assigned_to.

        Raises ValueError if item_id is not found.
        """
        async with self._lock:
            item = self._find_item(item_id)
            item.status = BacklogItemStatus.PENDING
            item.assigned_to = None
            await self._persist()
        await self._notify(f"[Backlog] Re-queued: '{item_id}' back to pending")

    @property
    def pending_items(self) -> list[BacklogItem]:
        """Return only PENDING items in queue order."""
        return [i for i in self._items if i.status == BacklogItemStatus.PENDING]
