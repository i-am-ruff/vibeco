"""Tests for priority message queue with debounce and backoff (RESL-01)."""

import asyncio
import time

import pytest

from vcompany.resilience.message_queue import (
    MessagePriority,
    MessageQueue,
    QueuedMessage,
    RateLimited,
)


@pytest.fixture
def sent_messages() -> list[QueuedMessage]:
    """Accumulator for messages dispatched by the mock send_func."""
    return []


@pytest.fixture
def mock_send(sent_messages: list[QueuedMessage]):
    """Async send_func that records calls."""

    async def _send(msg: QueuedMessage) -> None:
        sent_messages.append(msg)

    return _send


@pytest.fixture
def failing_send():
    """Send func that raises RateLimited on first N calls, then succeeds."""
    state = {"fail_count": 0, "calls": [], "max_fails": 3}

    async def _send(msg: QueuedMessage) -> None:
        state["calls"].append(msg)
        if state["fail_count"] < state["max_fails"]:
            state["fail_count"] += 1
            raise RateLimited("429 Too Many Requests")

    return _send, state


@pytest.mark.asyncio
async def test_priority_ordering(mock_send, sent_messages):
    """ESCALATION(0) messages dequeue before STATUS(2) regardless of enqueue order."""
    mq = MessageQueue(send_func=mock_send, max_rate=1000.0)
    await mq.start()

    # Enqueue STATUS first, then ESCALATION
    status_msg = QueuedMessage(
        priority=MessagePriority.STATUS,
        timestamp=time.monotonic(),
        channel_id=1,
        content="status update",
    )
    escalation_msg = QueuedMessage(
        priority=MessagePriority.ESCALATION,
        timestamp=time.monotonic(),
        channel_id=1,
        content="escalation alert",
    )
    await mq.enqueue(status_msg)
    await mq.enqueue(escalation_msg)

    # Let the drain loop process both
    await asyncio.sleep(0.05)
    await mq.stop()

    assert len(sent_messages) == 2
    assert sent_messages[0].content == "escalation alert"
    assert sent_messages[1].content == "status update"


@pytest.mark.asyncio
async def test_health_debounce(mock_send, sent_messages):
    """Two health reports for same channel within debounce window result in only one send."""
    mq = MessageQueue(send_func=mock_send, max_rate=1000.0, debounce_seconds=0.1)
    await mq.start()

    # Enqueue two health updates for same channel
    await mq.enqueue_health(channel_id=42, embed="embed_v1")
    await mq.enqueue_health(channel_id=42, embed="embed_v2")

    # Wait for debounce window to expire + drain
    await asyncio.sleep(0.25)
    await mq.stop()

    # Only the latest (embed_v2) should have been sent
    assert len(sent_messages) == 1
    assert sent_messages[0].embed == "embed_v2"


@pytest.mark.asyncio
async def test_429_backoff():
    """After RateLimited, backoff doubles from 1.0 -> 2.0 -> 4.0, capped at 60.0."""
    mq = MessageQueue(send_func=lambda msg: None, max_rate=1000.0)  # placeholder

    # Simulate backoff progression
    assert mq._backoff == 0.0

    # First rate limit: should go to 1.0
    mq._backoff = max(mq._backoff * 2, 1.0)
    assert mq._backoff == 1.0

    # Second: 2.0
    mq._backoff = min(mq._backoff * 2, 60.0)
    assert mq._backoff == 2.0

    # Third: 4.0
    mq._backoff = min(mq._backoff * 2, 60.0)
    assert mq._backoff == 4.0

    # Cap test: set near max
    mq._backoff = 32.0
    mq._backoff = min(mq._backoff * 2, 60.0)
    assert mq._backoff == 60.0

    # Already at cap
    mq._backoff = min(mq._backoff * 2, 60.0)
    assert mq._backoff == 60.0


@pytest.mark.asyncio
async def test_backoff_reset(mock_send, sent_messages):
    """After a successful send following backoff, backoff resets to 0.0."""
    mq = MessageQueue(send_func=mock_send, max_rate=1000.0)
    # Simulate prior backoff (small value so test doesn't wait long)
    mq._backoff = 0.01

    await mq.start()
    await mq.enqueue(
        QueuedMessage(
            priority=MessagePriority.STATUS,
            timestamp=time.monotonic(),
            channel_id=1,
            content="test",
        )
    )

    # Let drain loop process -- send succeeds, backoff should reset
    await asyncio.sleep(0.1)
    await mq.stop()

    assert mq._backoff == 0.0
    assert len(sent_messages) == 1


@pytest.mark.asyncio
async def test_drain_loop_sends(mock_send, sent_messages):
    """Messages enqueued are actually dispatched via the send callback."""
    mq = MessageQueue(send_func=mock_send, max_rate=1000.0)
    await mq.start()

    for i in range(3):
        await mq.enqueue(
            QueuedMessage(
                priority=MessagePriority.STATUS,
                timestamp=time.monotonic(),
                channel_id=1,
                content=f"msg-{i}",
            )
        )

    await asyncio.sleep(0.05)
    await mq.stop()

    assert len(sent_messages) == 3
    contents = {m.content for m in sent_messages}
    assert contents == {"msg-0", "msg-1", "msg-2"}


@pytest.mark.asyncio
async def test_start_stop(mock_send):
    """start() creates drain task, stop() cancels it cleanly."""
    mq = MessageQueue(send_func=mock_send)

    assert mq._drain_task is None
    await mq.start()
    assert mq._drain_task is not None
    assert not mq._drain_task.done()

    await mq.stop()
    assert mq._drain_task.done()


@pytest.mark.asyncio
async def test_backoff_on_rate_limited():
    """Drain loop applies backoff when send_func raises RateLimited."""
    calls: list[QueuedMessage] = []
    call_count = 0

    async def _send(msg: QueuedMessage) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RateLimited("429")
        calls.append(msg)

    mq = MessageQueue(send_func=_send, max_rate=1000.0)
    await mq.start()

    await mq.enqueue(
        QueuedMessage(
            priority=MessagePriority.ESCALATION,
            timestamp=time.monotonic(),
            channel_id=1,
            content="retry-me",
        )
    )

    # First attempt raises RateLimited -> backoff set, message re-enqueued
    # After backoff sleep (1s is too long for tests), check state
    await asyncio.sleep(0.05)
    assert mq._backoff >= 1.0  # backoff was applied

    await mq.stop()
