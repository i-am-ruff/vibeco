"""Tests for RestartTracker sliding window restart intensity limiter."""

from datetime import datetime, timedelta, timezone

from vcompany.supervisor.restart_tracker import RestartTracker


def _make_clock(start: datetime | None = None):
    """Create a controllable clock for testing."""
    current = [start or datetime(2026, 1, 1, tzinfo=timezone.utc)]

    def clock() -> datetime:
        return current[0]

    def advance(seconds: float) -> None:
        current[0] += timedelta(seconds=seconds)

    return clock, advance


class TestRestartTracker:
    def test_allows_restarts_under_limit(self):
        """3 restarts allowed with default max_restarts=3, 4th blocked."""
        clock, _advance = _make_clock()
        tracker = RestartTracker(max_restarts=3, window_seconds=600, clock=clock)

        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is False

    def test_window_expiry_resets_count(self):
        """After window expires, old timestamps are purged and restarts allowed again."""
        clock, advance = _make_clock()
        tracker = RestartTracker(max_restarts=3, window_seconds=600, clock=clock)

        # Exhaust the budget
        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is False

        # Advance past the window
        advance(601)

        # Budget is restored
        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is False

    def test_reset_clears_timestamps(self):
        """After reset(), full restart budget is available."""
        clock, _advance = _make_clock()
        tracker = RestartTracker(max_restarts=3, window_seconds=600, clock=clock)

        # Use some budget
        tracker.allow_restart()
        tracker.allow_restart()

        # Reset
        tracker.reset()

        # Full budget available
        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is False

    def test_custom_limits(self):
        """Custom max_restarts=1, window=60 -- 1 allowed, 2nd blocked."""
        clock, _advance = _make_clock()
        tracker = RestartTracker(max_restarts=1, window_seconds=60, clock=clock)

        assert tracker.allow_restart() is True
        assert tracker.allow_restart() is False

    def test_restart_count_property(self):
        """restart_count reflects current timestamps within window."""
        clock, advance = _make_clock()
        tracker = RestartTracker(max_restarts=5, window_seconds=60, clock=clock)

        assert tracker.restart_count == 0
        tracker.allow_restart()
        assert tracker.restart_count == 1
        tracker.allow_restart()
        assert tracker.restart_count == 2

        # Advance past window -- count should drop
        advance(61)
        assert tracker.restart_count == 0

    def test_partial_window_expiry(self):
        """Only timestamps older than window are purged, recent ones remain."""
        clock, advance = _make_clock()
        tracker = RestartTracker(max_restarts=3, window_seconds=100, clock=clock)

        tracker.allow_restart()  # t=0
        advance(50)
        tracker.allow_restart()  # t=50
        advance(51)
        # Now t=101; first timestamp (t=0) is >100s ago, but second (t=50) is only 51s ago
        # After purge: 1 timestamp remains, so 2 more allowed
        assert tracker.allow_restart() is True  # count was 1, now 2
        assert tracker.allow_restart() is True  # count now 3
        assert tracker.allow_restart() is False  # at limit
