"""Tests for BacklogQueue — living milestone backlog data structure."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

from vcompany.autonomy.backlog import BacklogItem, BacklogItemStatus, BacklogQueue
from vcompany.container.memory_store import MemoryStore


@pytest_asyncio.fixture
async def memory(tmp_path: Path) -> MemoryStore:
    """Create a real MemoryStore backed by a tmp_path SQLite file."""
    store = MemoryStore(tmp_path / "test_memory.db")
    await store.open()
    yield store
    await store.close()


@pytest_asyncio.fixture
async def queue(memory: MemoryStore) -> BacklogQueue:
    """Create a BacklogQueue with a fresh MemoryStore."""
    q = BacklogQueue(memory)
    await q.load()
    return q


@pytest.mark.asyncio
async def test_append(queue: BacklogQueue, memory: MemoryStore) -> None:
    """Append adds item to end of queue, persisted after reload."""
    item = BacklogItem(title="Build feature A")
    await queue.append(item)

    assert len(queue.pending_items) == 1
    assert queue.pending_items[0].title == "Build feature A"

    # Verify persistence: create new queue from same store
    q2 = BacklogQueue(memory)
    await q2.load()
    assert len(q2.pending_items) == 1
    assert q2.pending_items[0].title == "Build feature A"


@pytest.mark.asyncio
async def test_insert_urgent(queue: BacklogQueue) -> None:
    """insert_urgent places item at position 0."""
    await queue.append(BacklogItem(title="Normal task"))
    urgent = BacklogItem(title="Urgent task")
    await queue.insert_urgent(urgent)

    assert queue.pending_items[0].title == "Urgent task"
    assert queue.pending_items[1].title == "Normal task"


@pytest.mark.asyncio
async def test_insert_after(queue: BacklogQueue) -> None:
    """insert_after places item after specified ID."""
    item_a = BacklogItem(title="Task A")
    item_b = BacklogItem(title="Task B")
    await queue.append(item_a)
    await queue.append(item_b)

    item_mid = BacklogItem(title="Task Mid")
    await queue.insert_after(item_a.item_id, item_mid)

    titles = [i.title for i in queue.pending_items]
    assert titles == ["Task A", "Task Mid", "Task B"]


@pytest.mark.asyncio
async def test_insert_after_missing_id(queue: BacklogQueue) -> None:
    """insert_after raises ValueError for missing ID."""
    with pytest.raises(ValueError, match="not found"):
        await queue.insert_after("nonexistent", BacklogItem(title="X"))


@pytest.mark.asyncio
async def test_reorder(queue: BacklogQueue) -> None:
    """reorder moves item to new position."""
    items = [BacklogItem(title=f"Task {i}") for i in range(3)]
    for item in items:
        await queue.append(item)

    # Move last item to position 0
    await queue.reorder(items[2].item_id, 0)
    titles = [i.title for i in queue.pending_items]
    assert titles == ["Task 2", "Task 0", "Task 1"]


@pytest.mark.asyncio
async def test_reorder_missing_id(queue: BacklogQueue) -> None:
    """reorder raises ValueError for missing ID."""
    with pytest.raises(ValueError, match="not found"):
        await queue.reorder("nonexistent", 0)


@pytest.mark.asyncio
async def test_cancel(queue: BacklogQueue) -> None:
    """cancel sets item status to CANCELLED."""
    item = BacklogItem(title="Cancel me")
    await queue.append(item)
    await queue.cancel(item.item_id)

    assert len(queue.pending_items) == 0
    # Item still exists in internal list but is CANCELLED
    all_items = queue._items
    assert all_items[0].status == BacklogItemStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_missing_id(queue: BacklogQueue) -> None:
    """cancel raises ValueError for missing ID."""
    with pytest.raises(ValueError, match="not found"):
        await queue.cancel("nonexistent")


@pytest.mark.asyncio
async def test_claim_next(queue: BacklogQueue) -> None:
    """claim_next returns first PENDING item marked ASSIGNED with agent_id set."""
    await queue.append(BacklogItem(title="Task 1"))
    await queue.append(BacklogItem(title="Task 2"))

    claimed = await queue.claim_next("agent-alpha")
    assert claimed is not None
    assert claimed.title == "Task 1"
    assert claimed.status == BacklogItemStatus.ASSIGNED
    assert claimed.assigned_to == "agent-alpha"

    # Next claim should get Task 2
    claimed2 = await queue.claim_next("agent-beta")
    assert claimed2 is not None
    assert claimed2.title == "Task 2"


@pytest.mark.asyncio
async def test_claim_next_empty(queue: BacklogQueue) -> None:
    """claim_next returns None when no PENDING items."""
    result = await queue.claim_next("agent-alpha")
    assert result is None


@pytest.mark.asyncio
async def test_mark_completed(queue: BacklogQueue) -> None:
    """mark_completed transitions ASSIGNED item to COMPLETED."""
    item = BacklogItem(title="Complete me")
    await queue.append(item)
    await queue.claim_next("agent-alpha")
    await queue.mark_completed(item.item_id)

    found = [i for i in queue._items if i.item_id == item.item_id][0]
    assert found.status == BacklogItemStatus.COMPLETED


@pytest.mark.asyncio
async def test_mark_completed_missing_id(queue: BacklogQueue) -> None:
    """mark_completed raises ValueError for missing ID."""
    with pytest.raises(ValueError, match="not found"):
        await queue.mark_completed("nonexistent")


@pytest.mark.asyncio
async def test_mark_pending(queue: BacklogQueue) -> None:
    """mark_pending transitions item back to PENDING and clears assigned_to."""
    item = BacklogItem(title="Retry me")
    await queue.append(item)
    await queue.claim_next("agent-alpha")
    await queue.mark_pending(item.item_id)

    found = [i for i in queue._items if i.item_id == item.item_id][0]
    assert found.status == BacklogItemStatus.PENDING
    assert found.assigned_to is None


@pytest.mark.asyncio
async def test_mark_pending_missing_id(queue: BacklogQueue) -> None:
    """mark_pending raises ValueError for missing ID."""
    with pytest.raises(ValueError, match="not found"):
        await queue.mark_pending("nonexistent")


@pytest.mark.asyncio
async def test_concurrent_append_claim(memory: MemoryStore) -> None:
    """Concurrent append + claim_next do not corrupt state (asyncio.Lock)."""
    queue = BacklogQueue(memory)
    await queue.load()

    # Pre-populate with some items
    for i in range(5):
        await queue.append(BacklogItem(title=f"Task {i}"))

    async def appender() -> None:
        for i in range(5, 10):
            await queue.append(BacklogItem(title=f"Task {i}"))

    async def claimer() -> list[BacklogItem | None]:
        results = []
        for _ in range(5):
            r = await queue.claim_next("agent-concurrent")
            results.append(r)
        return results

    # Run concurrently
    _, claimed = await asyncio.gather(appender(), claimer())

    # All claimed items should be unique and non-None (at least 5 were available)
    claimed_items = [c for c in claimed if c is not None]
    claimed_ids = [c.item_id for c in claimed_items]
    assert len(claimed_ids) == len(set(claimed_ids)), "Duplicate claims detected"


@pytest.mark.asyncio
async def test_load_restores_state(memory: MemoryStore) -> None:
    """load() restores full state from MemoryStore after fresh BacklogQueue instance."""
    q1 = BacklogQueue(memory)
    await q1.load()
    await q1.append(BacklogItem(title="Persisted task"))
    await q1.claim_next("agent-1")

    # Fresh instance
    q2 = BacklogQueue(memory)
    await q2.load()
    assert len(q2._items) == 1
    assert q2._items[0].title == "Persisted task"
    assert q2._items[0].status == BacklogItemStatus.ASSIGNED
    assert q2._items[0].assigned_to == "agent-1"


@pytest.mark.asyncio
async def test_pending_items_property(queue: BacklogQueue) -> None:
    """pending_items property returns only PENDING items in order."""
    await queue.append(BacklogItem(title="Task A"))
    await queue.append(BacklogItem(title="Task B"))
    await queue.append(BacklogItem(title="Task C"))

    # Claim first one (no longer PENDING)
    await queue.claim_next("agent-1")

    pending = queue.pending_items
    assert len(pending) == 2
    assert pending[0].title == "Task B"
    assert pending[1].title == "Task C"
