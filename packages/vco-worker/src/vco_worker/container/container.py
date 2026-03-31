"""WorkerContainer -- agent container runtime inside the worker process.

Composes lifecycle FSM, memory store, health reporting, task queue,
idle tracking, and handler into a self-managed container that communicates
exclusively through channel protocol messages.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from statemachine.orderedset import OrderedSet

from vco_worker.channel.framing import encode
from vco_worker.channel.messages import (
    InboundMessage, ReportMessage, SignalMessage,
)
from vco_worker.config import WorkerConfig
from vco_worker.container.context import ContainerContext
from vco_worker.container.health import HealthReport
from vco_worker.container.memory_store import MemoryStore
from vco_worker.container.state_machine import ContainerLifecycle

logger = logging.getLogger(__name__)


class WorkerContainer:
    """Lifecycle-managed container running inside a worker process.

    All outbound communication goes through self._writer as NDJSON
    channel messages. No Discord, no CommunicationPort, no transport.
    """

    def __init__(
        self,
        config: WorkerConfig,
        agent_id: str,
        writer: asyncio.StreamWriter | None = None,
    ) -> None:
        self.config = config
        self.context = ContainerContext(
            agent_id=agent_id,
            agent_type=config.agent_type,
            project_id=config.project_id,
            gsd_command=config.gsd_command,
            uses_tmux=config.uses_tmux,
        )
        self._fsm_state: str | None = None
        self._lifecycle = self._create_lifecycle()
        data_dir = Path.cwd() / ".vco-state" / agent_id
        self.memory = MemoryStore(data_dir / "memory.db")
        self._writer = writer
        self._created_at = datetime.now(timezone.utc)
        self._error_count: int = 0
        self._last_activity = self._created_at
        self._is_idle: bool = False
        self._task_queue: asyncio.Queue[str] = asyncio.Queue()
        self._handler: Any = None
        self._blocked_reason: str | None = None
        # GSD-specific state (used by session handler)
        self._pending_review: asyncio.Future | None = None
        self._current_assignment: dict | None = None
        # PM-specific state (used by transient handler)
        self._agent_state_timestamps: dict[str, tuple[str, float]] = {}
        self._stuck_detected_agents: set[str] = set()
        self._stuck_check_interval: float = 60.0
        self._stuck_threshold_seconds: float = 600.0
        self._project_state: Any = None  # ProjectState if needed
        self._stuck_detector_task: asyncio.Task | None = None
        # Conversation-specific (used by conversation handler)
        self._conversation: Any = None

    def _create_lifecycle(self) -> ContainerLifecycle:
        """Create the appropriate lifecycle FSM based on agent_type."""
        if self.config.agent_type == "gsd":
            from vco_worker.agent.gsd_lifecycle import GsdLifecycle
            return GsdLifecycle(model=self, state_field="_fsm_state")
        elif self.config.agent_type in ("fulltime", "company"):
            from vco_worker.agent.event_driven_lifecycle import EventDrivenLifecycle
            return EventDrivenLifecycle(model=self, state_field="_fsm_state")
        else:
            return ContainerLifecycle(model=self, state_field="_fsm_state")

    # --- Properties ---

    @property
    def state(self) -> str:
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            return str(list(val)[0])
        return str(val)

    @property
    def inner_state(self) -> str | None:
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            items = list(val)
            if len(items) >= 2:
                return str(items[1])
        return None

    @property
    def is_idle(self) -> bool:
        return self._is_idle

    # --- Channel Communication ---

    async def _write_message(self, msg: Any) -> None:
        """Write a channel message to the output stream."""
        if self._writer is None:
            logger.warning("No writer -- cannot send message: %s", type(msg).__name__)
            return
        self._writer.write(encode(msg))
        await self._writer.drain()

    async def send_report(self, channel: str, content: str) -> None:
        """Send a report via channel protocol (replaces _send_discord)."""
        await self._write_message(ReportMessage(channel=channel, content=content))

    async def send_signal(self, signal: str, detail: str = "") -> None:
        """Send a signal via channel protocol."""
        await self._write_message(SignalMessage(signal=signal, detail=detail))

    # --- Signal + Task Queue ---

    async def handle_signal(self, signal_type: str) -> None:
        """Handle a signal (ready/idle) -- drives task queue draining."""
        if signal_type in ("ready", "idle"):
            self._is_idle = signal_type == "idle"
            self._last_activity = datetime.now(timezone.utc)
            logger.info("Signal: %s for %s", signal_type, self.context.agent_id)
            if self._is_idle and not self._task_queue.empty():
                await self._drain_task_queue()

    async def give_task(self, task: str) -> None:
        """Queue a task. Send immediately if idle, else queue."""
        await self._task_queue.put(task)
        logger.info("Queued task for %s: %s", self.context.agent_id, task[:80])
        if self._is_idle:
            await self._drain_task_queue()

    async def _drain_task_queue(self) -> None:
        """Send next queued task via signal (worker manages its own process)."""
        try:
            task = self._task_queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        self._is_idle = False
        # In worker context, task delivery goes through the handler or process manager
        # For now, log it. The main loop will integrate with process management.
        logger.info("Draining task for %s: %s", self.context.agent_id, task[:80])

    # --- Inbound Message Handling ---

    async def handle_inbound(self, message: InboundMessage) -> None:
        """Handle an inbound message from head (replaces receive_discord_message)."""
        if self._handler is not None:
            await self._handler.handle_message(self, message)
            return
        logger.info(
            "Agent %s received message from %s (no handler)",
            self.context.agent_id, message.sender,
        )

    # --- Health ---

    def health_report(self) -> HealthReport:
        now = datetime.now(timezone.utc)
        return HealthReport(
            agent_id=self.context.agent_id,
            state=self.state,
            inner_state=self.inner_state,
            uptime=(now - self._created_at).total_seconds(),
            last_heartbeat=now,
            error_count=self._error_count,
            last_activity=self._last_activity,
            blocked_reason=self._blocked_reason,
            is_idle=self._is_idle if self.config.uses_tmux else None,
        )

    def _on_state_change(self) -> None:
        self._last_activity = datetime.now(timezone.utc)

    # --- Lifecycle ---

    async def start(self) -> None:
        self._lifecycle.start()
        await self.memory.open()
        if self._handler is not None:
            await self._handler.on_start(self)

    async def stop(self) -> None:
        if self._handler is not None:
            await self._handler.on_stop(self)
        self._lifecycle.begin_stop()
        self._lifecycle.finish_stop()
        await self.memory.close()

    async def error(self) -> None:
        self._error_count += 1
        self._lifecycle.error()

    async def recover(self) -> None:
        self._lifecycle.recover()

    def block(self, reason: str) -> None:
        self._blocked_reason = reason[:200]
        self._lifecycle.block()

    def unblock(self) -> None:
        self._blocked_reason = None
        self._lifecycle.unblock()

    def set_handler(self, handler: Any) -> None:
        """Inject a handler for message processing."""
        self._handler = handler
