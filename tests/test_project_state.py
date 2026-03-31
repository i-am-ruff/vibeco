"""Tests for ProjectStateManager -- PM-owned project state coordination.

Tests cover:
- ProjectStateManager assign/complete/fail/reassign flows
- FulltimeAgent event routing to backlog operations
- GsdAgent assignment read/write and event generation
- Crash safety: orphaned assignments recovered by reassign_stale
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio

from vcompany.autonomy.backlog import BacklogItem, BacklogItemStatus, BacklogQueue
from vcompany.autonomy.project_state import ProjectStateManager
from vcompany.supervisor.child_spec import ContainerContext
from vcompany.shared.memory_store import MemoryStore


# --- Fixtures ---


@pytest_asyncio.fixture
async def pm_memory(tmp_path: Path) -> MemoryStore:
    """PM's MemoryStore."""
    store = MemoryStore(tmp_path / "pm_memory.db")
    await store.open()
    yield store
    await store.close()


@pytest_asyncio.fixture
async def agent_memory(tmp_path: Path) -> MemoryStore:
    """Agent's MemoryStore (separate from PM)."""
    store = MemoryStore(tmp_path / "agent_memory.db")
    await store.open()
    yield store
    await store.close()


@pytest_asyncio.fixture
async def backlog(pm_memory: MemoryStore) -> BacklogQueue:
    """BacklogQueue backed by PM's MemoryStore."""
    q = BacklogQueue(pm_memory)
    await q.load()
    return q


@pytest_asyncio.fixture
async def state_mgr(backlog: BacklogQueue, pm_memory: MemoryStore) -> ProjectStateManager:
    """ProjectStateManager with PM's backlog and memory."""
    return ProjectStateManager(backlog=backlog, memory=pm_memory)


# --- ProjectStateManager Tests ---


@pytest.mark.asyncio
async def test_assign_next_task(state_mgr: ProjectStateManager, backlog: BacklogQueue) -> None:
    """assign_next_task claims PENDING item and stores assignment in PM memory."""
    await backlog.append(BacklogItem(item_id="item-1", title="Build auth"))

    result = await state_mgr.assign_next_task("agent-1")

    assert result is not None
    assert result.item_id == "item-1"
    assert result.status == BacklogItemStatus.ASSIGNED
    assert result.assigned_to == "agent-1"

    # Assignment stored in PM memory
    assignment = await state_mgr.get_agent_assignment("agent-1")
    assert assignment is not None
    assert assignment["item_id"] == "item-1"


@pytest.mark.asyncio
async def test_assign_next_task_empty(state_mgr: ProjectStateManager) -> None:
    """assign_next_task returns None when no PENDING items."""
    result = await state_mgr.assign_next_task("agent-1")
    assert result is None


@pytest.mark.asyncio
async def test_handle_task_completed(
    state_mgr: ProjectStateManager, backlog: BacklogQueue
) -> None:
    """handle_task_completed marks item COMPLETED and clears assignment."""
    await backlog.append(BacklogItem(item_id="item-1", title="Build auth"))
    await state_mgr.assign_next_task("agent-1")

    await state_mgr.handle_task_completed("agent-1", "item-1")

    # Item is COMPLETED
    item = backlog._items[0]
    assert item.status == BacklogItemStatus.COMPLETED

    # Assignment cleared
    assignment = await state_mgr.get_agent_assignment("agent-1")
    assert assignment is None


@pytest.mark.asyncio
async def test_handle_task_failed(
    state_mgr: ProjectStateManager, backlog: BacklogQueue
) -> None:
    """handle_task_failed re-queues item as PENDING and clears assignment."""
    await backlog.append(BacklogItem(item_id="item-1", title="Build auth"))
    await state_mgr.assign_next_task("agent-1")

    await state_mgr.handle_task_failed("agent-1", "item-1")

    # Item is back to PENDING
    item = backlog._items[0]
    assert item.status == BacklogItemStatus.PENDING
    assert item.assigned_to is None

    # Assignment cleared
    assignment = await state_mgr.get_agent_assignment("agent-1")
    assert assignment is None


@pytest.mark.asyncio
async def test_reassign_stale(
    state_mgr: ProjectStateManager, backlog: BacklogQueue
) -> None:
    """reassign_stale recovers ASSIGNED items whose agents are no longer active."""
    await backlog.append(BacklogItem(item_id="item-1", title="Task 1"))
    await backlog.append(BacklogItem(item_id="item-2", title="Task 2"))
    await state_mgr.assign_next_task("agent-1")
    await state_mgr.assign_next_task("agent-2")

    # Only agent-2 is active -- agent-1 has crashed
    reassigned = await state_mgr.reassign_stale(active_agent_ids={"agent-2"})

    assert reassigned == ["item-1"]
    # item-1 back to PENDING
    item1 = [i for i in backlog._items if i.item_id == "item-1"][0]
    assert item1.status == BacklogItemStatus.PENDING
    assert item1.assigned_to is None

    # item-2 still ASSIGNED
    item2 = [i for i in backlog._items if i.item_id == "item-2"][0]
    assert item2.status == BacklogItemStatus.ASSIGNED


@pytest.mark.asyncio
async def test_full_lifecycle(
    state_mgr: ProjectStateManager, backlog: BacklogQueue
) -> None:
    """Full flow: add -> assign -> complete -> verify COMPLETED."""
    await backlog.append(BacklogItem(item_id="item-1", title="Build auth"))

    # Assign
    item = await state_mgr.assign_next_task("agent-1")
    assert item is not None

    # Complete
    await state_mgr.handle_task_completed("agent-1", "item-1")

    # Verify
    found = backlog._items[0]
    assert found.status == BacklogItemStatus.COMPLETED
    assert await state_mgr.get_agent_assignment("agent-1") is None


@pytest.mark.asyncio
async def test_failure_lifecycle(
    state_mgr: ProjectStateManager, backlog: BacklogQueue
) -> None:
    """Failure flow: add -> assign -> fail -> verify back to PENDING."""
    await backlog.append(BacklogItem(item_id="item-1", title="Build auth"))

    # Assign
    await state_mgr.assign_next_task("agent-1")

    # Fail
    await state_mgr.handle_task_failed("agent-1", "item-1")

    # Verify back to PENDING -- can be re-assigned
    found = backlog._items[0]
    assert found.status == BacklogItemStatus.PENDING

    # Re-assign works
    item = await state_mgr.assign_next_task("agent-2")
    assert item is not None
    assert item.assigned_to == "agent-2"


@pytest.mark.asyncio
async def test_crash_safety(
    state_mgr: ProjectStateManager, backlog: BacklogQueue
) -> None:
    """Crash simulation: assign without completion, reassign_stale recovers."""
    await backlog.append(BacklogItem(item_id="item-1", title="Build auth"))

    # Assign to agent-1
    await state_mgr.assign_next_task("agent-1")

    # Simulate crash: agent-1 never calls handle_task_completed
    # Item stays ASSIGNED -- backlog is consistent

    item = backlog._items[0]
    assert item.status == BacklogItemStatus.ASSIGNED

    # PM detects agent-1 is gone, calls reassign_stale
    reassigned = await state_mgr.reassign_stale(active_agent_ids=set())
    assert "item-1" in reassigned

    # Item is now PENDING, can be re-claimed
    item = backlog._items[0]
    assert item.status == BacklogItemStatus.PENDING
    new_item = await state_mgr.assign_next_task("agent-2")
    assert new_item is not None
    assert new_item.assigned_to == "agent-2"


@pytest.mark.asyncio
async def test_gsd_set_and_get_assignment(gsd_agent) -> None:
    """set_assignment stores, get_assignment retrieves."""
    assignment = {"item_id": "item-1", "title": "Build auth"}
    await gsd_agent.set_assignment(assignment)

    result = await gsd_agent.get_assignment()
    assert result == assignment


@pytest.mark.asyncio
async def test_gsd_make_completion_event(gsd_agent) -> None:
    """make_completion_event returns properly structured event dict."""
    event = gsd_agent.make_completion_event("item-1")

    assert event == {
        "type": "task_completed",
        "agent_id": "gsd-agent-1",
        "item_id": "item-1",
        "result": "success",
    }


@pytest.mark.asyncio
async def test_gsd_make_completion_event_custom_result(gsd_agent) -> None:
    """make_completion_event accepts custom result string."""
    event = gsd_agent.make_completion_event("item-1", result="partial")
    assert event["result"] == "partial"


@pytest.mark.asyncio
async def test_gsd_make_failure_event(gsd_agent) -> None:
    """make_failure_event returns properly structured event dict."""
    event = gsd_agent.make_failure_event("item-1", reason="timeout")

    assert event == {
        "type": "task_failed",
        "agent_id": "gsd-agent-1",
        "item_id": "item-1",
        "reason": "timeout",
    }


@pytest.mark.asyncio
async def test_gsd_make_failure_event_default_reason(gsd_agent) -> None:
    """make_failure_event default reason is empty string."""
    event = gsd_agent.make_failure_event("item-1")
    assert event["reason"] == ""
