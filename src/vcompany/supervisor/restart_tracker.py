"""Sliding window restart intensity tracker (SUPV-05).

Tracks restart timestamps in a deque. Before each restart, purges timestamps
older than the window, then checks whether the count exceeds the max.
Accepts an injectable clock callable for deterministic testing.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Callable


class RestartTracker:
    """Track restart intensity using a sliding time window.

    Args:
        max_restarts: Maximum restarts allowed within the window.
        window_seconds: Size of the sliding window in seconds.
        clock: Optional callable returning current UTC datetime.
            Defaults to ``datetime.now(timezone.utc)``.
    """

    def __init__(
        self,
        max_restarts: int = 3,
        window_seconds: int = 600,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.max_restarts = max_restarts
        self.window_seconds = window_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._timestamps: deque[datetime] = deque()

    def _purge(self) -> None:
        """Remove timestamps older than the sliding window."""
        now = self._clock()
        cutoff = now.timestamp() - self.window_seconds
        while self._timestamps and self._timestamps[0].timestamp() < cutoff:
            self._timestamps.popleft()

    def allow_restart(self) -> bool:
        """Check if a restart is allowed, recording the timestamp if so.

        Returns True and records the current time if under the limit.
        Returns False if at or over the limit within the window.
        """
        self._purge()
        if len(self._timestamps) >= self.max_restarts:
            return False
        self._timestamps.append(self._clock())
        return True

    def reset(self) -> None:
        """Clear all recorded timestamps, restoring full budget."""
        self._timestamps.clear()

    @property
    def restart_count(self) -> int:
        """Current number of restarts within the active window."""
        self._purge()
        return len(self._timestamps)
