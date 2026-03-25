"""Heartbeat file writing and watchdog checking.

The monitor writes a heartbeat file at the START of each cycle (per Pitfall 6)
to prevent false watchdog triggers during long cycles. The watchdog checks
heartbeat staleness to detect if the monitor itself has died.

Implements D-18, D-19.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from vcompany.shared.file_ops import write_atomic

logger = logging.getLogger("vcompany.monitor.heartbeat")

_HEARTBEAT_FILENAME = "monitor_heartbeat"
_DEFAULT_MAX_AGE_SECONDS = 180  # 3 missed 60s cycles per D-19


def write_heartbeat(project_dir: Path, *, now: datetime | None = None) -> None:
    """Write ISO timestamp to heartbeat file.

    Per Pitfall 6 from Research: this should be called at the START of each
    monitor cycle, not the end, to prevent false watchdog triggers during
    long cycles.

    Args:
        project_dir: Root project directory.
        now: Current timestamp (injectable for testing). Defaults to UTC now.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    heartbeat_path = project_dir / "state" / _HEARTBEAT_FILENAME
    write_atomic(heartbeat_path, now.isoformat())


def check_heartbeat(
    project_dir: Path,
    max_age_seconds: int = _DEFAULT_MAX_AGE_SECONDS,
    *,
    now: datetime | None = None,
) -> bool:
    """Check if the monitor heartbeat is fresh.

    Args:
        project_dir: Root project directory.
        max_age_seconds: Maximum acceptable heartbeat age in seconds.
            Default 180 (3 missed 60s cycles per D-19).
        now: Current timestamp (injectable for testing). Defaults to UTC now.

    Returns:
        True if heartbeat is fresh (<= max_age_seconds old).
        False if heartbeat is stale, missing, or corrupt.
    """
    heartbeat_path = project_dir / "state" / _HEARTBEAT_FILENAME

    if not heartbeat_path.exists():
        return False

    try:
        content = heartbeat_path.read_text().strip()
        ts = datetime.fromisoformat(content)
    except (ValueError, OSError):
        return False

    if now is None:
        now = datetime.now(timezone.utc)

    # Ensure timezone-aware comparison
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    age = (now - ts).total_seconds()
    return age <= max_age_seconds
