"""Tests for Scheduler — wake sleeping ContinuousAgents on schedule (AUTO-06)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from vcompany.container.memory_store import MemoryStore
from vcompany.supervisor.scheduler import ScheduleEntry, Scheduler


@pytest.fixture
async def memory(tmp_path: Path) -> MemoryStore:
    """Open a MemoryStore in a temp directory."""
    store = MemoryStore(tmp_path / "scheduler" / "memory.db")
    await store.open()
    yield store
    await store.close()


@pytest.fixture
def find_container() -> AsyncMock:
    """Default find_container that returns None (agent not found)."""
    return AsyncMock(return_value=None)


@pytest.fixture
async def scheduler(memory: MemoryStore, find_container: AsyncMock) -> Scheduler:
    """Create a Scheduler with test memory and find_container."""
    return Scheduler(memory=memory, find_container=find_container, check_interval=60)


# --- Test 1: ScheduleEntry model validation ---

def test_schedule_entry_validates_fields():
    """ScheduleEntry validates agent_id, interval_seconds, next_wake_utc fields."""
    now = datetime.now(timezone.utc).isoformat()
    entry = ScheduleEntry(agent_id="agent-1", interval_seconds=300, next_wake_utc=now)
    assert entry.agent_id == "agent-1"
    assert entry.interval_seconds == 300
    assert entry.next_wake_utc == now


# --- Test 2: add_schedule persists to MemoryStore ---

@pytest.mark.asyncio
async def test_add_schedule_persists(scheduler: Scheduler, memory: MemoryStore):
    """Scheduler.add_schedule persists entry to MemoryStore."""
    entry = await scheduler.add_schedule("agent-1", 300)
    assert entry.agent_id == "agent-1"
    assert entry.interval_seconds == 300

    # Verify persisted in memory store
    data = await memory.get("schedules")
    assert data is not None
    entries = json.loads(data)
    assert len(entries) == 1
    assert entries[0]["agent_id"] == "agent-1"


# --- Test 3: remove_schedule removes from MemoryStore ---

@pytest.mark.asyncio
async def test_remove_schedule(scheduler: Scheduler, memory: MemoryStore):
    """Scheduler.remove_schedule removes from MemoryStore."""
    await scheduler.add_schedule("agent-1", 300)
    await scheduler.remove_schedule("agent-1")

    data = await memory.get("schedules")
    entries = json.loads(data)
    assert len(entries) == 0
    assert scheduler.get_schedule("agent-1") is None


# --- Test 4: get_schedule returns entry or None ---

@pytest.mark.asyncio
async def test_get_schedule(scheduler: Scheduler):
    """Scheduler.get_schedule returns ScheduleEntry or None."""
    assert scheduler.get_schedule("agent-1") is None
    await scheduler.add_schedule("agent-1", 300)
    entry = scheduler.get_schedule("agent-1")
    assert entry is not None
    assert entry.agent_id == "agent-1"


# --- Test 5: _check_and_wake wakes sleeping container whose time passed ---

@pytest.mark.asyncio
async def test_check_and_wake_wakes_sleeping(memory: MemoryStore):
    """_check_and_wake wakes a sleeping container whose next_wake_utc passed."""
    mock_container = AsyncMock()
    mock_container.state = "sleeping"
    mock_container.wake = AsyncMock()

    find = AsyncMock(return_value=mock_container)
    sched = Scheduler(memory=memory, find_container=find, check_interval=60)

    # Add schedule with next_wake in the past
    entry = await sched.add_schedule("agent-1", 300)
    # Force next_wake to the past
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    sched._schedules["agent-1"] = entry.model_copy(update={"next_wake_utc": past})

    await sched._check_and_wake()
    mock_container.wake.assert_awaited_once()


# --- Test 6: _check_and_wake skips non-sleeping containers ---

@pytest.mark.asyncio
async def test_check_and_wake_skips_non_sleeping(memory: MemoryStore):
    """_check_and_wake skips containers that are not sleeping."""
    mock_container = AsyncMock()
    mock_container.state = "running"
    mock_container.wake = AsyncMock()

    find = AsyncMock(return_value=mock_container)
    sched = Scheduler(memory=memory, find_container=find, check_interval=60)

    entry = await sched.add_schedule("agent-1", 300)
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    sched._schedules["agent-1"] = entry.model_copy(update={"next_wake_utc": past})

    await sched._check_and_wake()
    mock_container.wake.assert_not_awaited()


# --- Test 7: _check_and_wake updates next_wake_utc after successful wake ---

@pytest.mark.asyncio
async def test_check_and_wake_updates_next_wake(memory: MemoryStore):
    """_check_and_wake updates next_wake_utc after successful wake."""
    mock_container = AsyncMock()
    mock_container.state = "sleeping"
    mock_container.wake = AsyncMock()

    find = AsyncMock(return_value=mock_container)
    sched = Scheduler(memory=memory, find_container=find, check_interval=60)

    entry = await sched.add_schedule("agent-1", 300)
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    sched._schedules["agent-1"] = entry.model_copy(update={"next_wake_utc": past})

    before_wake = datetime.now(timezone.utc)
    await sched._check_and_wake()

    updated = sched.get_schedule("agent-1")
    assert updated is not None
    next_wake = datetime.fromisoformat(updated.next_wake_utc)
    # Next wake should be ~300s from now
    assert next_wake > before_wake
    assert next_wake < before_wake + timedelta(seconds=310)


# --- Test 8: Schedule persists across Scheduler restart ---

@pytest.mark.asyncio
async def test_schedule_persists_across_restart(memory: MemoryStore, find_container: AsyncMock):
    """Schedule persists across Scheduler restart via load from MemoryStore."""
    sched1 = Scheduler(memory=memory, find_container=find_container, check_interval=60)
    await sched1.add_schedule("agent-1", 600)

    # Create new scheduler with same memory -- simulates restart
    sched2 = Scheduler(memory=memory, find_container=find_container, check_interval=60)
    await sched2.load()
    entry = sched2.get_schedule("agent-1")
    assert entry is not None
    assert entry.agent_id == "agent-1"
    assert entry.interval_seconds == 600


# --- Test 9: Scheduler handles missing/removed agents gracefully ---

@pytest.mark.asyncio
async def test_handles_missing_agent(memory: MemoryStore):
    """Scheduler handles missing agents gracefully (no crash)."""
    find = AsyncMock(return_value=None)  # Agent not found
    sched = Scheduler(memory=memory, find_container=find, check_interval=60)

    entry = await sched.add_schedule("ghost-agent", 300)
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    sched._schedules["ghost-agent"] = entry.model_copy(update={"next_wake_utc": past})

    # Should not raise
    await sched._check_and_wake()
    # Schedule should still exist (not removed)
    assert sched.get_schedule("ghost-agent") is not None


# --- Test 10: Scheduler.run() executes check loop ---

@pytest.mark.asyncio
async def test_run_executes_loop(memory: MemoryStore):
    """Scheduler.run() executes check loop (test with short interval + cancellation)."""
    check_count = 0

    mock_container = AsyncMock()
    mock_container.state = "sleeping"
    mock_container.wake = AsyncMock()

    find = AsyncMock(return_value=mock_container)
    sched = Scheduler(memory=memory, find_container=find, check_interval=0.05)

    # Add schedule in the past so it fires each check
    entry = await sched.add_schedule("agent-1", 1)
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    sched._schedules["agent-1"] = entry.model_copy(update={"next_wake_utc": past})

    # Run for a short time then cancel
    task = asyncio.create_task(sched.run())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Wake should have been called at least once
    assert mock_container.wake.await_count >= 1
