"""CompanyAgent -- event-driven container for Strategist role (TYPE-05).

Company-scoped (no project_id), survives project restarts, holds cross-project
state in memory_store. Same event-driven pattern as FulltimeAgent but with
company-level scope and cross-project state helpers.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from statemachine.orderedset import OrderedSet

from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport
from vcompany.strategist.conversation import StrategistConversation

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
        # Strategist conversation (wired via initialize_conversation())
        self._conversation: StrategistConversation | None = None
        # Response callback: invoked with (response_text, channel_id) after
        # a strategist_message event is processed. Wired by VcoBot.on_ready.
        self._on_response: Callable[[str, int], Awaitable[None]] | None = None
        # Background drain task
        self._drain_task: asyncio.Task[None] | None = None

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

    def initialize_conversation(self, persona_path: Path | None = None) -> None:
        """Create the StrategistConversation owned by this container.

        Args:
            persona_path: Path to STRATEGIST-PERSONA.md, or None for default.
        """
        self._conversation = StrategistConversation(persona_path=persona_path)
        logger.info("StrategistConversation initialized (persona=%s)", persona_path)

    async def _handle_event(self, event: dict[str, Any]) -> None:
        """Dispatch event to Strategist conversation logic.

        Supported event types:
        - strategist_message: forward to conversation, invoke _on_response callback
        - pm_escalation: format as PM escalation, resolve _response_future if present
        Unknown types are logged as warnings.
        """
        event_type = event.get("type", "")

        if event_type == "strategist_message":
            if self._conversation is None:
                logger.warning("strategist_message received but conversation not initialized")
                future: asyncio.Future | None = event.get("_response_future")
                if future is not None and not future.done():
                    future.set_result("Strategist not initialized.")
                return
            content = event.get("content", "")
            channel_id: int = event.get("channel_id", 0)
            response = await self._conversation.send(content)
            # Resolve embedded future if present (used by StrategistCog._send_to_channel)
            resp_future: asyncio.Future | None = event.get("_response_future")
            if resp_future is not None and not resp_future.done():
                resp_future.set_result(response)
            # Also invoke _on_response callback if wired (for direct channel posting)
            if self._on_response is not None:
                await self._on_response(response, channel_id)

        elif event_type == "pm_escalation":
            if self._conversation is None:
                logger.warning("pm_escalation received but conversation not initialized")
                future: asyncio.Future | None = event.get("_response_future")
                if future is not None and not future.done():
                    future.set_result(None)
                return
            agent_id = event.get("agent_id", "")
            question = event.get("question", "")
            confidence = event.get("confidence", 0.0)
            formatted = (
                f"[PM Escalation] Agent {agent_id} asks: {question}\n"
                f"PM confidence: {confidence:.0%}. Please provide your assessment."
            )
            full_response = await self._conversation.send(formatted)

            # Check low-confidence signals -- same list as legacy StrategistCog
            low_confidence_signals = [
                "i'm not sure",
                "escalate to owner",
                "owner should decide",
                "not confident",
                "cannot determine",
            ]
            result: str | None = full_response
            if any(signal in full_response.lower() for signal in low_confidence_signals):
                result = None

            future = event.get("_response_future")
            if future is not None and not future.done():
                future.set_result(result)

        else:
            logger.warning("Unhandled event type: %s", event_type)

    async def _drain_events(self) -> None:
        """Background loop that drains the event queue continuously."""
        while True:
            processed = await self.process_next_event()
            if not processed:
                await asyncio.sleep(0.1)

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
        """Transition to running, open memory, restore event count, and start drain loop."""
        await super().start()
        count_str = await self.memory.get("events_processed")
        if count_str is not None:
            self._events_processed = int(count_str)
        self._drain_task = asyncio.create_task(self._drain_events())

    async def stop(self) -> None:
        """Cancel drain task then delegate to parent stop."""
        if self._drain_task is not None:
            self._drain_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._drain_task
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
