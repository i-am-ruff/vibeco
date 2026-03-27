"""MemoryStore — per-agent async SQLite persistence (CONT-04).

Each agent gets its own SQLite file for key-value storage and labeled
checkpoints. WAL mode is enabled for concurrent read safety. All datetime
values use UTC ISO format.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite


class MemoryStore:
    """Async SQLite wrapper for per-agent persistent memory.

    Usage::

        store = MemoryStore(Path("state/containers/agent-1/memory.db"))
        await store.open()
        await store.set("phase", "planning")
        phase = await store.get("phase")  # "planning"
        await store.checkpoint("phase-start", '{"phase": "plan"}')
        await store.close()
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        """Open the SQLite database, enable WAL mode, and create tables."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))

        # Enable WAL mode for concurrent read safety
        await self._db.execute("PRAGMA journal_mode=WAL")

        # Create tables
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            "  key TEXT PRIMARY KEY,"
            "  value TEXT NOT NULL,"
            "  updated_at TEXT NOT NULL"
            ")"
        )
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS checkpoints ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  label TEXT NOT NULL,"
            "  data TEXT NOT NULL,"
            "  created_at TEXT NOT NULL"
            ")"
        )
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def get(self, key: str) -> str | None:
        """Get a value by key. Returns None if not found."""
        assert self._db is not None, "MemoryStore not opened"
        async with self._db.execute(
            "SELECT value FROM kv WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set(self, key: str, value: str) -> None:
        """Set a key-value pair (upsert)."""
        assert self._db is not None, "MemoryStore not opened"
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT OR REPLACE INTO kv (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
        await self._db.commit()

    async def delete(self, key: str) -> None:
        """Delete a key-value pair."""
        assert self._db is not None, "MemoryStore not opened"
        await self._db.execute("DELETE FROM kv WHERE key = ?", (key,))
        await self._db.commit()

    async def keys(self) -> list[str]:
        """Return sorted list of all stored keys."""
        assert self._db is not None, "MemoryStore not opened"
        async with self._db.execute("SELECT key FROM kv ORDER BY key") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def checkpoint(self, label: str, data: str) -> None:
        """Store a labeled checkpoint with timestamp."""
        assert self._db is not None, "MemoryStore not opened"
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO checkpoints (label, data, created_at) VALUES (?, ?, ?)",
            (label, data, now),
        )
        await self._db.commit()

    async def get_latest_checkpoint(self, label: str) -> str | None:
        """Get the most recent checkpoint data for a label. Returns None if not found."""
        assert self._db is not None, "MemoryStore not opened"
        async with self._db.execute(
            "SELECT data FROM checkpoints WHERE label = ? ORDER BY id DESC LIMIT 1",
            (label,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def list_checkpoints(self) -> list[dict[str, str]]:
        """List all checkpoints with label and created_at, most recent first."""
        assert self._db is not None, "MemoryStore not opened"
        async with self._db.execute(
            "SELECT label, created_at FROM checkpoints ORDER BY id DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"label": row[0], "created_at": row[1]} for row in rows]
