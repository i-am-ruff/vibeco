"""Tests for BulkFailureDetector (RESL-02)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from vcompany.resilience.bulk_failure import BulkFailureDetector


class TestBulkFailureDetector:
    """Unit tests for BulkFailureDetector."""

    def _make_clock(self, start: datetime | None = None) -> tuple[list[datetime], callable]:
        """Create a controllable clock for testing."""
        now = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = [now]

        def clock() -> datetime:
            return state[0]

        return state, clock

    def test_bulk_detection(self) -> None:
        """Recording failures from 3 distinct children (out of 4) returns True."""
        state, clock = self._make_clock()
        detector = BulkFailureDetector(child_count=4, clock=clock)

        assert not detector.record_failure("child-1")
        # threshold = max(2, int(4*0.5)) = 2, 2nd distinct child triggers
        assert detector.record_failure("child-2")
        # 3rd distinct child also returns True (already in backoff)
        assert detector.record_failure("child-3")

    def test_no_false_positive(self) -> None:
        """Recording 1 failure from 4 children returns False."""
        state, clock = self._make_clock()
        detector = BulkFailureDetector(child_count=4, clock=clock)

        assert not detector.record_failure("child-1")
        assert not detector.is_in_backoff

    def test_window_expiry(self) -> None:
        """Failures outside the correlation window do not count toward threshold."""
        state, clock = self._make_clock()
        detector = BulkFailureDetector(
            child_count=4, correlation_window=30.0, clock=clock,
        )

        # Record first failure
        detector.record_failure("child-1")

        # Advance past window
        state[0] += timedelta(seconds=31)

        # Record second failure -- first should be purged
        assert not detector.record_failure("child-2")
        # Only child-2 should be in recent failures now
        assert len(detector._recent_failures) == 1

    def test_same_child_twice(self) -> None:
        """Same child failing twice counts as 1 unique failure, not 2."""
        state, clock = self._make_clock()
        detector = BulkFailureDetector(child_count=4, clock=clock)

        assert not detector.record_failure("child-1")
        assert not detector.record_failure("child-1")  # duplicate
        assert not detector.record_failure("child-1")  # still duplicate
        # Only 1 distinct child -- should not trigger bulk failure
        assert not detector.is_in_backoff

    def test_backoff_state(self) -> None:
        """After bulk failure detected, is_in_backoff returns True."""
        state, clock = self._make_clock()
        detector = BulkFailureDetector(child_count=4, clock=clock)

        detector.record_failure("child-1")
        detector.record_failure("child-2")
        detector.record_failure("child-3")  # triggers

        assert detector.is_in_backoff

    def test_reset_backoff(self) -> None:
        """Calling reset_backoff() clears backoff state."""
        state, clock = self._make_clock()
        detector = BulkFailureDetector(child_count=4, clock=clock)

        detector.record_failure("child-1")
        detector.record_failure("child-2")
        detector.record_failure("child-3")  # triggers

        assert detector.is_in_backoff
        detector.reset_backoff()
        assert not detector.is_in_backoff

    def test_update_child_count(self) -> None:
        """Updating child_count recalculates threshold."""
        state, clock = self._make_clock()
        detector = BulkFailureDetector(child_count=10, clock=clock)

        # threshold = max(2, int(10*0.5)) = 5
        detector.record_failure("child-1")
        detector.record_failure("child-2")
        assert not detector.is_in_backoff  # only 2 of 5 needed

        # Update to 4 children: threshold = max(2, int(4*0.5)) = 2
        detector.update_child_count(4)
        # Now 2 failures already recorded >= new threshold of 2
        # But update_child_count only recalculates threshold, doesn't re-evaluate
        # Record another to trigger evaluation
        assert detector.record_failure("child-3")

    def test_escalate_backoff(self) -> None:
        """Escalate_backoff doubles up to max."""
        state, clock = self._make_clock()
        detector = BulkFailureDetector(
            child_count=4, backoff_seconds=60.0, max_backoff=200.0, clock=clock,
        )

        assert detector.current_backoff == 60.0
        detector.escalate_backoff()
        assert detector.current_backoff == 120.0
        detector.escalate_backoff()
        assert detector.current_backoff == 200.0  # capped at max
        detector.escalate_backoff()
        assert detector.current_backoff == 200.0  # stays at max
