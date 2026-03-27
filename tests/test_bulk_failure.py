"""Tests for BulkFailureDetector (RESL-02)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from vcompany.container.child_spec import ChildSpec, RestartPolicy
from vcompany.container.context import ContainerContext
from vcompany.resilience.bulk_failure import BulkFailureDetector
from vcompany.supervisor.strategies import RestartStrategy
from vcompany.supervisor.supervisor import Supervisor


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


def _make_spec(
    child_id: str, restart_policy: RestartPolicy = RestartPolicy.PERMANENT
) -> ChildSpec:
    """Create a minimal ChildSpec for testing."""
    return ChildSpec(
        child_id=child_id,
        agent_type="test",
        context=ContainerContext(agent_id=child_id, agent_type="test"),
        restart_policy=restart_policy,
    )


class TestSupervisorBulkFailureIntegration:
    """Integration tests for BulkFailureDetector in Supervisor."""

    @pytest.mark.asyncio
    async def test_supervisor_global_backoff(self, tmp_path) -> None:
        """Supervisor enters global backoff when bulk failure detected."""
        specs = [_make_spec("a"), _make_spec("b"), _make_spec("c"), _make_spec("d")]
        escalation_msgs: list[str] = []

        async def on_escalation(msg: str) -> None:
            escalation_msgs.append(msg)

        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
            on_escalation=on_escalation,
        )
        await sup.start()

        # Verify bulk detector was created
        assert sup._bulk_detector is not None

        # Suppress event-driven monitoring so we can control failure calls
        sup._restarting = True

        # Force children into errored state (monitor suppressed by _restarting)
        for child_id in ["a", "b", "c"]:
            container = sup.children[child_id]
            container._lifecycle.error()

        sup._restarting = False

        # Clear any events that were set during the error() calls
        for child_id in ["a", "b", "c", "d"]:
            event = sup._child_events.get(child_id)
            if event is not None:
                event.clear()

        # Handle failures directly -- threshold is max(2, int(4*0.5))=2
        await sup._handle_child_failure("a")  # 1 failure, no bulk yet
        await sup._handle_child_failure("b")  # 2 failures, bulk detected!

        # Verify bulk failure was detected and backoff entered
        assert sup._bulk_detector.is_in_backoff

        # Verify escalation callback was called with outage message
        assert len(escalation_msgs) == 1
        assert "UPSTREAM OUTAGE" in escalation_msgs[0]

        # Third failure should be suppressed (in backoff)
        await sup._handle_child_failure("c")
        # No additional escalation message (still in backoff, skipped restart)
        assert len(escalation_msgs) == 1

        await sup.stop()

    @pytest.mark.asyncio
    async def test_supervisor_single_failure_no_backoff(self, tmp_path) -> None:
        """Single failure does not trigger global backoff."""
        specs = [_make_spec("a"), _make_spec("b"), _make_spec("c"), _make_spec("d")]
        escalation_msgs: list[str] = []

        async def on_escalation(msg: str) -> None:
            escalation_msgs.append(msg)

        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
            on_escalation=on_escalation,
        )
        await sup.start()

        # Force one child to error state
        container = sup.children["a"]
        container._lifecycle.error()

        # Handle single failure
        await sup._handle_child_failure("a")

        # Should NOT trigger bulk failure
        assert not sup._bulk_detector.is_in_backoff
        assert len(escalation_msgs) == 0

        await sup.stop()

    @pytest.mark.asyncio
    async def test_supervisor_no_detector_with_single_child(self, tmp_path) -> None:
        """Supervisor with 1 child does not create bulk detector."""
        specs = [_make_spec("solo")]
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=specs,
            data_dir=tmp_path,
        )
        assert sup._bulk_detector is None
