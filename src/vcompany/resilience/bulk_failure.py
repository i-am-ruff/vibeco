"""Bulk failure detection for upstream outage correlation (RESL-02).

Tracks per-child failure timestamps in a sliding window. When 50%+ of
distinct children fail within the correlation window, triggers global
backoff to prevent wasteful per-agent restart loops.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable


class BulkFailureDetector:
    """Detect correlated bulk failures indicating upstream outage.

    Uses a ``dict[str, datetime]`` (not a deque) to track per-child
    failure timestamps. This prevents false positives from the same child
    failing repeatedly -- the threshold requires N distinct children
    failing, not N total failures.

    Args:
        child_count: Total number of children managed by the supervisor.
        correlation_window: Seconds within which failures are correlated.
        threshold_ratio: Fraction of children that must fail to trigger.
        backoff_seconds: Initial global backoff duration in seconds.
        max_backoff: Maximum backoff duration cap in seconds.
        clock: Injectable clock for testing. Defaults to UTC now.
    """

    def __init__(
        self,
        child_count: int,
        correlation_window: float = 30.0,
        threshold_ratio: float = 0.5,
        backoff_seconds: float = 120.0,
        max_backoff: float = 600.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._child_count = child_count
        self._correlation_window = correlation_window
        self._threshold_ratio = threshold_ratio
        self._threshold: int = max(2, int(child_count * threshold_ratio))
        self._backoff_seconds = backoff_seconds
        self._max_backoff = max_backoff
        self._clock = clock or (lambda: datetime.now(timezone.utc))

        self._recent_failures: dict[str, datetime] = {}
        self._in_backoff: bool = False
        self._current_backoff: float = backoff_seconds

    def record_failure(self, child_id: str) -> bool:
        """Record a failure for the given child.

        Purges entries older than the correlation window, then stores or
        updates the child's timestamp. Returns True if the number of
        distinct recently-failed children meets or exceeds the threshold
        (bulk failure detected).
        """
        self._purge_old()
        self._recent_failures[child_id] = self._clock()

        if len(self._recent_failures) >= self._threshold:
            self._in_backoff = True
            return True
        return False

    def _purge_old(self) -> None:
        """Remove entries older than the correlation window."""
        now = self._clock()
        cutoff = now.timestamp() - self._correlation_window
        expired = [
            cid
            for cid, ts in self._recent_failures.items()
            if ts.timestamp() < cutoff
        ]
        for cid in expired:
            del self._recent_failures[cid]

    @property
    def is_in_backoff(self) -> bool:
        """Whether the detector is currently in global backoff."""
        return self._in_backoff

    @property
    def current_backoff(self) -> float:
        """Current backoff duration in seconds."""
        return self._current_backoff

    def reset_backoff(self) -> None:
        """Clear backoff state and reset duration to initial value."""
        self._in_backoff = False
        self._current_backoff = self._backoff_seconds

    def escalate_backoff(self) -> None:
        """Double the current backoff duration, capped at max_backoff."""
        self._current_backoff = min(
            self._current_backoff * 2,
            self._max_backoff,
        )

    def update_child_count(self, count: int) -> None:
        """Update child count and recalculate threshold."""
        self._child_count = count
        self._threshold = max(2, int(count * self._threshold_ratio))
