"""Scheduler — wakes sleeping ContinuousAgents on schedule (AUTO-06).

Runs a configurable check loop as an asyncio task. Schedule entries are
persisted to a MemoryStore (SQLite) so they survive bot restarts.

Usage::

    scheduler = Scheduler(memory_store, find_container_callback)
    await scheduler.load()  # restore schedules from previous run
    task = asyncio.create_task(scheduler.run())
    # ... later ...
    task.cancel()
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Awaitable, Callable

from pydantic import BaseModel

from vcompany.shared.memory_store import MemoryStore

if TYPE_CHECKING:
    from vcompany.container.container import AgentContainer

logger = logging.getLogger(__name__)


class ScheduleEntry(BaseModel):
    """Persistent record of an agent's wake schedule."""

    agent_id: str
    interval_seconds: int
    next_wake_utc: str  # ISO format UTC timestamp


class Scheduler:
    """Wakes sleeping ContinuousAgents on schedule (AUTO-06).

    Runs a check loop as an asyncio task. Schedule entries are
    persisted to a MemoryStore (SQLite) so they survive bot restarts.

    Args:
        memory: MemoryStore for persistent schedule storage.
        find_container: Callback that resolves agent_id to an AgentContainer
            (or None if not found). Used to locate containers in the supervision tree.
        check_interval: Seconds between schedule checks (default 60).
    """

    def __init__(
        self,
        memory: MemoryStore,
        find_container: Callable[[str], Awaitable[AgentContainer | None]],
        check_interval: float = 60,
    ) -> None:
        self._memory = memory
        self._find_container = find_container
        self._check_interval = check_interval
        self._schedules: dict[str, ScheduleEntry] = {}
        self._task: asyncio.Task | None = None

    async def load(self) -> None:
        """Load persisted schedules from MemoryStore."""
        data = await self._memory.get("schedules")
        if data is not None:
            entries = json.loads(data)
            for entry_dict in entries:
                entry = ScheduleEntry.model_validate(entry_dict)
                self._schedules[entry.agent_id] = entry

    async def _persist(self) -> None:
        """Write all schedules to MemoryStore."""
        entries = [e.model_dump() for e in self._schedules.values()]
        await self._memory.set("schedules", json.dumps(entries))

    async def add_schedule(self, agent_id: str, interval_seconds: int) -> ScheduleEntry:
        """Add or update a wake schedule for an agent."""
        next_wake = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
        entry = ScheduleEntry(
            agent_id=agent_id,
            interval_seconds=interval_seconds,
            next_wake_utc=next_wake.isoformat(),
        )
        self._schedules[agent_id] = entry
        await self._persist()
        return entry

    async def remove_schedule(self, agent_id: str) -> None:
        """Remove a wake schedule."""
        self._schedules.pop(agent_id, None)
        await self._persist()

    def get_schedule(self, agent_id: str) -> ScheduleEntry | None:
        """Return the schedule for an agent, or None if not scheduled."""
        return self._schedules.get(agent_id)

    async def _check_and_wake(self) -> None:
        """Check all schedules and wake agents whose time has come."""
        now = datetime.now(timezone.utc)
        for agent_id, entry in list(self._schedules.items()):
            next_wake = datetime.fromisoformat(entry.next_wake_utc)
            if now >= next_wake:
                container = await self._find_container(agent_id)
                if container is None:
                    logger.warning("Scheduled agent %s not found", agent_id)
                    continue
                if container.state != "sleeping":
                    # Already awake or in another state -- reschedule
                    new_wake = now + timedelta(seconds=entry.interval_seconds)
                    entry_copy = entry.model_copy(update={"next_wake_utc": new_wake.isoformat()})
                    self._schedules[agent_id] = entry_copy
                    await self._persist()
                    continue
                try:
                    await container.wake()
                    # Schedule next wake
                    new_wake = now + timedelta(seconds=entry.interval_seconds)
                    entry_copy = entry.model_copy(update={"next_wake_utc": new_wake.isoformat()})
                    self._schedules[agent_id] = entry_copy
                    await self._persist()
                    logger.info("Woke agent %s, next wake at %s", agent_id, new_wake.isoformat())
                except Exception:
                    logger.exception("Failed to wake agent %s", agent_id)

    async def run(self) -> None:
        """Main scheduler loop. Run as asyncio.create_task(scheduler.run())."""
        while True:
            try:
                await self._check_and_wake()
            except Exception:
                logger.exception("Scheduler loop error")
            await asyncio.sleep(self._check_interval)
