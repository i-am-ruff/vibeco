"""Tests for MemoryStore — async SQLite persistence (CONT-04)."""

from pathlib import Path

import pytest

from vcompany.shared.memory_store import MemoryStore


@pytest.mark.asyncio
async def test_set_and_get(tmp_path: Path) -> None:
    """set() stores a value, get() retrieves it."""
    store = MemoryStore(tmp_path / "test.db")
    await store.open()
    try:
        await store.set("phase", "planning")
        assert await store.get("phase") == "planning"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_get_nonexistent_returns_none(tmp_path: Path) -> None:
    """get() returns None for keys that don't exist."""
    store = MemoryStore(tmp_path / "test.db")
    await store.open()
    try:
        assert await store.get("nonexistent") is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_set_upsert(tmp_path: Path) -> None:
    """set() with an existing key overwrites the value."""
    store = MemoryStore(tmp_path / "test.db")
    await store.open()
    try:
        await store.set("key", "v1")
        await store.set("key", "v2")
        assert await store.get("key") == "v2"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_delete(tmp_path: Path) -> None:
    """delete() removes a key; get() returns None afterward."""
    store = MemoryStore(tmp_path / "test.db")
    await store.open()
    try:
        await store.set("key", "value")
        await store.delete("key")
        assert await store.get("key") is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_keys(tmp_path: Path) -> None:
    """keys() returns sorted list of all stored keys."""
    store = MemoryStore(tmp_path / "test.db")
    await store.open()
    try:
        await store.set("beta", "2")
        await store.set("alpha", "1")
        await store.set("gamma", "3")
        result = await store.keys()
        assert result == ["alpha", "beta", "gamma"]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_checkpoint_store_and_retrieve(tmp_path: Path) -> None:
    """checkpoint() stores data; get_latest_checkpoint() retrieves it."""
    store = MemoryStore(tmp_path / "test.db")
    await store.open()
    try:
        await store.checkpoint("phase-start", '{"phase": "plan"}')
        result = await store.get_latest_checkpoint("phase-start")
        assert result == '{"phase": "plan"}'
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_get_latest_checkpoint_returns_most_recent(tmp_path: Path) -> None:
    """Multiple checkpoints with same label — get_latest returns the most recent."""
    store = MemoryStore(tmp_path / "test.db")
    await store.open()
    try:
        await store.checkpoint("phase-start", '{"phase": "plan"}')
        await store.checkpoint("phase-start", '{"phase": "execute"}')
        result = await store.get_latest_checkpoint("phase-start")
        assert result == '{"phase": "execute"}'
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_get_latest_checkpoint_nonexistent(tmp_path: Path) -> None:
    """get_latest_checkpoint() returns None for unknown labels."""
    store = MemoryStore(tmp_path / "test.db")
    await store.open()
    try:
        assert await store.get_latest_checkpoint("nonexistent") is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_list_checkpoints(tmp_path: Path) -> None:
    """list_checkpoints() returns all checkpoint labels with timestamps."""
    store = MemoryStore(tmp_path / "test.db")
    await store.open()
    try:
        await store.checkpoint("start", '{"a": 1}')
        await store.checkpoint("end", '{"b": 2}')
        result = await store.list_checkpoints()
        assert len(result) == 2
        # Most recent first (ORDER BY id DESC)
        assert result[0]["label"] == "end"
        assert result[1]["label"] == "start"
        assert "created_at" in result[0]
        assert "created_at" in result[1]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_persistence_across_reopen(tmp_path: Path) -> None:
    """Data survives close/reopen cycle."""
    db_path = tmp_path / "test.db"

    store1 = MemoryStore(db_path)
    await store1.open()
    await store1.set("key", "value")
    await store1.checkpoint("cp1", '{"data": true}')
    await store1.close()

    store2 = MemoryStore(db_path)
    await store2.open()
    try:
        assert await store2.get("key") == "value"
        assert await store2.get_latest_checkpoint("cp1") == '{"data": true}'
    finally:
        await store2.close()


@pytest.mark.asyncio
async def test_sqlite_file_created_on_open(tmp_path: Path) -> None:
    """SQLite file is created at the specified path on open()."""
    db_path = tmp_path / "subdir" / "test.db"
    assert not db_path.exists()

    store = MemoryStore(db_path)
    await store.open()
    try:
        assert db_path.exists()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_wal_mode_enabled(tmp_path: Path) -> None:
    """After open(), PRAGMA journal_mode returns 'wal'."""
    store = MemoryStore(tmp_path / "test.db")
    await store.open()
    try:
        assert store._db is not None
        async with store._db.execute("PRAGMA journal_mode") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == "wal"
    finally:
        await store.close()
