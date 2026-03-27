"""Tests for Scheduler — wake sleeping ContinuousAgents on schedule (AUTO-06)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from vcompany.container.memory_store import MemoryStore
from vcompany.supervisor.scheduler import ScheduleEntry, Scheduler


async def _open_memory(tmp_path: Path) -> MemoryStore:
    store = MemoryStore(tmp_path / "scheduler" / "memory.db")
    await store.open()
    return store


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
async def test_add_schedule_persists(tmp_path: Path):
    """Scheduler.add_schedule persists entry to MemoryStore."""
    memory = await _open_memory(tmp_path)
    find = AsyncMock(return_value=None)
    sched = Scheduler(memory=memory, find_container=find, check_interval=60)

    entry = await sched.add_schedule("agent-1", 300)
    assert entry.agent_id == "agent-1"
    assert entry.interval_seconds == 300

    data = await memory.get("schedules")
    assert data is not None
    entries = json.loads(data)
    assert len(entries) == 1
    assert entries[0]["agent_id"] == "agent-1"
    await memory.close()


# --- Test 3: remove_schedule removes from MemoryStore ---


@pytest.mark.asyncio
async def test_remove_schedule(tmp_path: Path):
    """Scheduler.remove_schedule removes from MemoryStore."""
    memory = await _open_memory(tmp_path)
    find = AsyncMock(return_value=None)
    sched = Scheduler(memory=memory, find_container=find, check_interval=60)

    await sched.add_schedule("agent-1", 300)
    await sched.remove_schedule("agent-1")

    data = await memory.get("schedules")
    entries = json.loads(data)
    assert len(entries) == 0
    assert sched.get_schedule("agent-1") is None
    await memory.close()


# --- Test 4: get_schedule returns entry or None ---


@pytest.mark.asyncio
async def test_get_schedule(tmp_path: Path):
    """Scheduler.get_schedule returns ScheduleEntry or None."""
    memory = await _open_memory(tmp_path)
    find = AsyncMock(return_value=None)
    sched = Scheduler(memory=memory, find_container=find, check_interval=60)

    assert sched.get_schedule("agent-1") is None
    await sched.add_schedule("agent-1", 300)
    entry = sched.get_schedule("agent-1")
    assert entry is not None
    assert entry.agent_id == "agent-1"
    await memory.close()


# --- Test 5: _check_and_wake wakes sleeping container whose time passed ---


@pytest.mark.asyncio
async def test_check_and_wake_wakes_sleeping(tmp_path: Path):
    """_check_and_wake wakes a sleeping container whose next_wake_utc passed."""
    memory = await _open_memory(tmp_path)
    mock_container = AsyncMock()
    mock_container.state = "sleeping"
    mock_container.wake = AsyncMock()

    find = AsyncMock(return_value=mock_container)
    sched = Scheduler(memory=memory, find_container=find, check_interval=60)

    entry = await sched.add_schedule("agent-1", 300)
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    sched._schedules["agent-1"] = entry.model_copy(update={"next_wake_utc": past})

    await sched._check_and_wake()
    mock_container.wake.assert_awaited_once()
    await memory.close()


# --- Test 6: _check_and_wake skips non-sleeping containers ---


@pytest.mark.asyncio
async def test_check_and_wake_skips_non_sleeping(tmp_path: Path):
    """_check_and_wake skips containers that are not sleeping."""
    memory = await _open_memory(tmp_path)
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
    await memory.close()


# --- Test 7: _check_and_wake updates next_wake_utc after successful wake ---


@pytest.mark.asyncio
async def test_check_and_wake_updates_next_wake(tmp_path: Path):
    """_check_and_wake updates next_wake_utc after successful wake."""
    memory = await _open_memory(tmp_path)
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
    assert next_wake > before_wake
    assert next_wake < before_wake + timedelta(seconds=310)
    await memory.close()


# --- Test 8: Schedule persists across Scheduler restart ---


@pytest.mark.asyncio
async def test_schedule_persists_across_restart(tmp_path: Path):
    """Schedule persists across Scheduler restart via load from MemoryStore."""
    memory = await _open_memory(tmp_path)
    find = AsyncMock(return_value=None)

    sched1 = Scheduler(memory=memory, find_container=find, check_interval=60)
    await sched1.add_schedule("agent-1", 600)

    sched2 = Scheduler(memory=memory, find_container=find, check_interval=60)
    await sched2.load()
    entry = sched2.get_schedule("agent-1")
    assert entry is not None
    assert entry.agent_id == "agent-1"
    assert entry.interval_seconds == 600
    await memory.close()


# --- Test 9: Scheduler handles missing/removed agents gracefully ---


@pytest.mark.asyncio
async def test_handles_missing_agent(tmp_path: Path):
    """Scheduler handles missing agents gracefully (no crash)."""
    memory = await _open_memory(tmp_path)
    find = AsyncMock(return_value=None)
    sched = Scheduler(memory=memory, find_container=find, check_interval=60)

    entry = await sched.add_schedule("ghost-agent", 300)
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    sched._schedules["ghost-agent"] = entry.model_copy(update={"next_wake_utc": past})

    await sched._check_and_wake()
    assert sched.get_schedule("ghost-agent") is not None
    await memory.close()


# --- Test 10: Scheduler.run() executes check loop ---


@pytest.mark.asyncio
async def test_run_executes_loop(tmp_path: Path):
    """Scheduler.run() executes check loop (test with short interval + cancellation)."""
    memory = await _open_memory(tmp_path)
    mock_container = AsyncMock()
    mock_container.state = "sleeping"
    mock_container.wake = AsyncMock()

    find = AsyncMock(return_value=mock_container)
    sched = Scheduler(memory=memory, find_container=find, check_interval=0.05)

    entry = await sched.add_schedule("agent-1", 1)
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    sched._schedules["agent-1"] = entry.model_copy(update={"next_wake_utc": past})

    task = asyncio.create_task(sched.run())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert mock_container.wake.await_count >= 1
    await memory.close()
