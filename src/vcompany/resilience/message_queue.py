"""Priority message queue with rate limiting and debounce (RESL-01).

All outbound Discord messages route through MessageQueue which:
- Prioritises escalations over status updates (asyncio.PriorityQueue)
- Debounces health reports within a configurable window
- Applies exponential backoff on RateLimited errors (429)
- Resets backoff after a successful send

The queue is Discord-agnostic: callers inject a send_func that handles
the actual channel.send(). The queue catches RateLimited (a custom
exception defined here) to trigger backoff. This keeps tests simple --
no Discord mocks needed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger("vcompany.resilience.message_queue")


class RateLimited(Exception):
    """Raised by send_func when the downstream API returns 429.

    The drain loop catches this to trigger exponential backoff.
    Callers wrap discord.HTTPException (status==429) into this.
    """


class MessagePriority(IntEnum):
    """Priority levels for queued messages. Lower = higher priority.

    asyncio.PriorityQueue pops the lowest value first, so ESCALATION(0)
    always dequeues before STATUS(2).
    """

    ESCALATION = 0
    SUPERVISOR = 1
    STATUS = 2
    HEALTH_DEBOUNCED = 3


@dataclass(order=True)
class QueuedMessage:
    """A message waiting in the priority queue.

    Ordering is by (priority, timestamp) so messages with the same
    priority are FIFO. channel_id, content, and embed are excluded
    from comparison.
    """

    priority: int
    timestamp: float
    channel_id: int = field(compare=False, default=0)
    content: str | None = field(compare=False, default=None)
    embed: object | None = field(compare=False, default=None)


class MessageQueue:
    """Rate-aware priority queue for outbound Discord messages.

    Args:
        send_func: Async callable that actually sends a QueuedMessage.
            Must raise RateLimited on 429 responses.
        max_rate: Maximum messages per second (default 5.0).
        debounce_seconds: Health report coalesce window (default 5.0).
    """

    def __init__(
        self,
        send_func: Callable[[QueuedMessage], Awaitable[None]],
        max_rate: float = 5.0,
        debounce_seconds: float = 5.0,
    ) -> None:
        self._send_func = send_func
        self._max_rate = max_rate
        self._debounce_seconds = debounce_seconds

        self._queue: asyncio.PriorityQueue[QueuedMessage] = asyncio.PriorityQueue()
        self._backoff: float = 0.0
        self._health_buffer: dict[int, QueuedMessage] = {}
        self._health_flush_handle: asyncio.TimerHandle | None = None
        self._drain_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the drain loop that processes queued messages."""
        if self._drain_task is not None and not self._drain_task.done():
            return
        self._drain_task = asyncio.create_task(self._drain_loop())

    async def stop(self) -> None:
        """Stop the drain loop and flush any pending health buffer."""
        # Cancel the debounce timer
        if self._health_flush_handle is not None:
            self._health_flush_handle.cancel()
            self._health_flush_handle = None

        # Flush any buffered health messages
        await self._flush_health()

        # Cancel drain task
        if self._drain_task is not None:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass

    async def enqueue(self, msg: QueuedMessage) -> None:
        """Add a message to the priority queue."""
        await self._queue.put(msg)

    async def enqueue_health(self, channel_id: int, embed: object) -> None:
        """Enqueue a debounced health report.

        Stores in the health buffer keyed by channel_id. Resets the
        debounce timer. When the timer fires, buffered messages move
        to the priority queue.
        """
        self._health_buffer[channel_id] = QueuedMessage(
            priority=MessagePriority.HEALTH_DEBOUNCED,
            timestamp=time.monotonic(),
            channel_id=channel_id,
            embed=embed,
        )

        # Reset debounce timer
        if self._health_flush_handle is not None:
            self._health_flush_handle.cancel()

        loop = asyncio.get_running_loop()
        self._health_flush_handle = loop.call_later(
            self._debounce_seconds,
            lambda: asyncio.ensure_future(self._flush_health()),
        )

    async def _flush_health(self) -> None:
        """Move all buffered health messages into the priority queue."""
        for msg in self._health_buffer.values():
            await self._queue.put(msg)
        self._health_buffer.clear()
        self._health_flush_handle = None

    async def _drain_loop(self) -> None:
        """Infinite loop: dequeue, apply backoff, send, handle errors."""
        interval = 1.0 / self._max_rate if self._max_rate > 0 else 0.0

        while True:
            try:
                msg = await self._queue.get()
            except asyncio.CancelledError:
                return

            # Apply backoff if active
            if self._backoff > 0:
                try:
                    await asyncio.sleep(self._backoff)
                except asyncio.CancelledError:
                    # Re-enqueue message before exiting so it is not lost
                    await self._queue.put(msg)
                    return

            try:
                await self._send_func(msg)
                # Success: reset backoff
                self._backoff = 0.0
            except RateLimited:
                # Re-enqueue the message for retry
                await self._queue.put(msg)
                # Exponential backoff: start at 1.0, double, cap at 60.0
                self._backoff = min(
                    max(self._backoff * 2, 1.0),
                    60.0,
                )
                logger.warning(
                    "Rate limited, backoff now %.1fs", self._backoff
                )
            except asyncio.CancelledError:
                return
            except Exception:
                # Non-rate-limit errors: log and discard message
                logger.exception(
                    "Failed to send message to channel %d", msg.channel_id
                )

            # Rate limiting sleep
            if interval > 0:
                try:
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    return
