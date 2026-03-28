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


# --- Supervisor Integration Tests ---

from vcompany.container.child_spec import ChildSpec, RestartPolicy
from vcompany.container.context import ContainerContext
from vcompany.supervisor.strategies import RestartStrategy
from vcompany.supervisor.supervisor import Supervisor


def _make_spec(child_id: str, restart_policy: RestartPolicy = RestartPolicy.PERMANENT) -> ChildSpec:
    """Create a minimal ChildSpec for testing."""
    return ChildSpec(
        child_id=child_id,
        agent_type="test",
        context=ContainerContext(agent_id=child_id, agent_type="test"),
        restart_policy=restart_policy,
    )


class TestSupervisorDelegation:
    """Supervisor delegation request handling and cleanup."""

    @pytest.mark.asyncio
    async def test_handle_delegation_no_policy_returns_not_approved(self, tmp_path) -> None:
        """Without delegation_policy, requests are rejected."""
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=[_make_spec("a")],
            data_dir=tmp_path,
        )
        await sup.start()
        try:
            req = DelegationRequest(requester_id="a", task_description="do stuff")
            result = await sup.handle_delegation_request(req)
            assert result.approved is False
            assert "not enabled" in result.reason.lower()
        finally:
            await sup.stop()

    @pytest.mark.asyncio
    async def test_handle_delegation_spawns_temporary_child(self, tmp_path) -> None:
        """Valid delegation spawns a TEMPORARY child container."""
        policy = DelegationPolicy(max_concurrent_delegations=3, max_delegations_per_hour=10)
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=[_make_spec("a")],
            data_dir=tmp_path,
            delegation_policy=policy,
        )
        await sup.start()
        try:
            req = DelegationRequest(requester_id="a", task_description="build feature")
            result = await sup.handle_delegation_request(req)
            assert result.approved is True
            assert result.agent_id is not None
            assert result.agent_id.startswith("delegated-a-")
            # Verify spawned child exists and is running
            child = sup.children.get(result.agent_id)
            assert child is not None
            assert child.state == "running"
            # Verify the spec is TEMPORARY
            spec = sup._get_spec(result.agent_id)
            assert spec is not None
            assert spec.restart_policy == RestartPolicy.TEMPORARY
        finally:
            await sup.stop()

    @pytest.mark.asyncio
    async def test_delegated_child_stopped_triggers_completion(self, tmp_path) -> None:
        """When a delegated child stops, tracker records completion."""
        policy = DelegationPolicy(max_concurrent_delegations=1, max_delegations_per_hour=10)
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=[_make_spec("a")],
            data_dir=tmp_path,
            delegation_policy=policy,
        )
        await sup.start()
        try:
            req = DelegationRequest(requester_id="a", task_description="task")
            result = await sup.handle_delegation_request(req)
            assert result.approved is True
            agent_id = result.agent_id

            # At concurrent cap
            req2 = DelegationRequest(requester_id="a", task_description="task2")
            result2 = await sup.handle_delegation_request(req2)
            assert result2.approved is False

            # Stop the delegated child -- should release capacity
            child = sup.children[agent_id]
            await child.stop()

            # Give event loop a tick to process the callback
            import asyncio
            await asyncio.sleep(0)

            # Now should be able to delegate again
            req3 = DelegationRequest(requester_id="a", task_description="task3")
            result3 = await sup.handle_delegation_request(req3)
            assert result3.approved is True
        finally:
            await sup.stop()

    @pytest.mark.asyncio
    async def test_max_concurrent_cap_rejects(self, tmp_path) -> None:
        """Delegation rejected when max concurrent reached."""
        policy = DelegationPolicy(max_concurrent_delegations=1, max_delegations_per_hour=10)
        sup = Supervisor(
            supervisor_id="test-sup",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=[_make_spec("a")],
            data_dir=tmp_path,
            delegation_policy=policy,
        )
        await sup.start()
        try:
            req1 = DelegationRequest(requester_id="a", task_description="task1")
            result1 = await sup.handle_delegation_request(req1)
            assert result1.approved is True

            req2 = DelegationRequest(requester_id="a", task_description="task2")
            result2 = await sup.handle_delegation_request(req2)
            assert result2.approved is False
            assert "concurrent" in result2.reason.lower()
        finally:
            await sup.stop()
