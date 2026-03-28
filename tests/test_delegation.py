"""Tests for delegation protocol — policy enforcement, tracker, and supervisor integration."""

from __future__ import annotations

import time

import pytest

from vcompany.autonomy.delegation import (
    DelegationPolicy,
    DelegationRequest,
    DelegationResult,
    DelegationTracker,
)


class TestDelegationPolicy:
    """DelegationPolicy model defaults and validation."""

    def test_default_values(self) -> None:
        policy = DelegationPolicy()
        assert policy.max_concurrent_delegations == 3
        assert policy.max_delegations_per_hour == 10
        assert policy.allowed_agent_types == ["gsd"]

    def test_custom_values(self) -> None:
        policy = DelegationPolicy(
            max_concurrent_delegations=5,
            max_delegations_per_hour=20,
            allowed_agent_types=["gsd", "continuous"],
        )
        assert policy.max_concurrent_delegations == 5
        assert policy.max_delegations_per_hour == 20
        assert policy.allowed_agent_types == ["gsd", "continuous"]


class TestDelegationRequest:
    """DelegationRequest construction and defaults."""

    def test_defaults(self) -> None:
        req = DelegationRequest(requester_id="agent-1", task_description="build feature X")
        assert req.requester_id == "agent-1"
        assert req.task_description == "build feature X"
        assert req.agent_type == "gsd"
        assert req.context_overrides == {}

    def test_custom_agent_type(self) -> None:
        req = DelegationRequest(
            requester_id="agent-1",
            task_description="analyze data",
            agent_type="continuous",
            context_overrides={"gsd_mode": "quick"},
        )
        assert req.agent_type == "continuous"
        assert req.context_overrides == {"gsd_mode": "quick"}


class TestDelegationResult:
    """DelegationResult construction."""

    def test_approved(self) -> None:
        result = DelegationResult(approved=True, agent_id="delegated-abc")
        assert result.approved is True
        assert result.agent_id == "delegated-abc"
        assert result.reason == ""

    def test_rejected(self) -> None:
        result = DelegationResult(approved=False, reason="rate limit exceeded")
        assert result.approved is False
        assert result.agent_id is None
        assert result.reason == "rate limit exceeded"


class TestDelegationTracker:
    """DelegationTracker enforces concurrent caps and hourly rate limits."""

    def _make_tracker(
        self,
        max_concurrent: int = 3,
        rate_limit: int = 10,
        allowed_types: list[str] | None = None,
        clock: float | None = None,
    ) -> DelegationTracker:
        policy = DelegationPolicy(
            max_concurrent_delegations=max_concurrent,
            max_delegations_per_hour=rate_limit,
            allowed_agent_types=allowed_types or ["gsd"],
        )
        tracker = DelegationTracker(policy)
        if clock is not None:
            tracker._clock = lambda: clock
        return tracker

    def test_can_delegate_under_limits(self) -> None:
        tracker = self._make_tracker()
        ok, reason = tracker.can_delegate("agent-1", "gsd")
        assert ok is True
        assert reason == ""

    def test_can_delegate_rejects_disallowed_agent_type(self) -> None:
        tracker = self._make_tracker(allowed_types=["gsd"])
        ok, reason = tracker.can_delegate("agent-1", "continuous")
        assert ok is False
        assert "allowed" in reason.lower() or "type" in reason.lower()

    def test_can_delegate_rejects_at_max_concurrent(self) -> None:
        tracker = self._make_tracker(max_concurrent=2)
        tracker.record_delegation("agent-1", "del-a")
        tracker.record_delegation("agent-1", "del-b")
        ok, reason = tracker.can_delegate("agent-1", "gsd")
        assert ok is False
        assert "concurrent" in reason.lower()

    def test_can_delegate_rejects_at_rate_limit(self) -> None:
        now = 1000.0
        tracker = self._make_tracker(rate_limit=3)
        tracker._clock = lambda: now
        # Record 3 delegations (all complete so not concurrent, but rate-limited)
        for i in range(3):
            tracker.record_delegation("agent-1", f"del-{i}")
            tracker.record_completion("agent-1", f"del-{i}")
        ok, reason = tracker.can_delegate("agent-1", "gsd")
        assert ok is False
        assert "rate" in reason.lower() or "hour" in reason.lower()

    def test_record_delegation_tracks_active(self) -> None:
        tracker = self._make_tracker()
        tracker.record_delegation("agent-1", "del-a")
        assert "del-a" in tracker._active["agent-1"]

    def test_record_completion_releases_capacity(self) -> None:
        tracker = self._make_tracker(max_concurrent=1)
        tracker.record_delegation("agent-1", "del-a")
        # At cap
        ok, _ = tracker.can_delegate("agent-1", "gsd")
        assert ok is False
        # Complete releases
        tracker.record_completion("agent-1", "del-a")
        ok, _ = tracker.can_delegate("agent-1", "gsd")
        assert ok is True

    def test_rate_limit_window_slides(self) -> None:
        """Old delegations expire after 1 hour."""
        now = 1000.0
        tracker = self._make_tracker(rate_limit=2)
        tracker._clock = lambda: now
        tracker.record_delegation("agent-1", "del-a")
        tracker.record_completion("agent-1", "del-a")
        tracker.record_delegation("agent-1", "del-b")
        tracker.record_completion("agent-1", "del-b")
        # At rate limit
        ok, _ = tracker.can_delegate("agent-1", "gsd")
        assert ok is False
        # Advance clock past 1 hour
        tracker._clock = lambda: now + 3601.0
        ok, _ = tracker.can_delegate("agent-1", "gsd")
        assert ok is True

    def test_concurrent_limit_per_requester(self) -> None:
        """Different requesters have independent concurrent limits."""
        tracker = self._make_tracker(max_concurrent=1)
        tracker.record_delegation("agent-1", "del-a")
        # agent-1 at cap
        ok, _ = tracker.can_delegate("agent-1", "gsd")
        assert ok is False
        # agent-2 still has capacity
        ok, _ = tracker.can_delegate("agent-2", "gsd")
        assert ok is True

    def test_record_completion_no_error_on_missing(self) -> None:
        """record_completion is a no-op for unknown agents."""
        tracker = self._make_tracker()
        # Should not raise
        tracker.record_completion("agent-1", "nonexistent")
