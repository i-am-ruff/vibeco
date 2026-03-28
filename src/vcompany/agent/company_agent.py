"""CompanyAgent -- event-driven container for Strategist role (TYPE-05).

Company-scoped (no project_id), survives project restarts, holds cross-project
state in memory_store. Same event-driven pattern as FulltimeAgent but with
company-level scope and cross-project state helpers.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from statemachine.orderedset import OrderedSet

from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport

if TYPE_CHECKING:
    from vcompany.container.communication import CommunicationPort

logger = logging.getLogger("vcompany.agent.company_agent")


class CompanyAgent(AgentContainer):
    """Event-driven agent for Strategist role (TYPE-05).

    Company-scoped (context.project_id should be None), survives project
    restarts, holds cross-project state in memory_store. Same event-driven
    pattern as FulltimeAgent but at company level.

    Args:
        context: Immutable agent metadata (project_id should be None).
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
        """Process a single event. Override in subclasses for custom behavior."""
        pass  # Base implementation is no-op; real Strategist logic added later

    # --- Cross-Project State ---

    async def get_cross_project_state(self, key: str) -> str | None:
        """Read a cross-project state value from memory_store.

        Cross-project keys are prefixed with ``xp:`` to distinguish from
        standard per-agent keys.
        """
        return await self.memory.get(f"xp:{key}")

    async def set_cross_project_state(self, key: str, value: str) -> None:
        """Write a cross-project state value to memory_store.

        Cross-project keys are prefixed with ``xp:`` to distinguish from
        standard per-agent keys.
        """
        await self.memory.set(f"xp:{key}", value)

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
