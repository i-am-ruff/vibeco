"""Tests for GsdAgent — state tracking, checkpointing, crash recovery."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from vcompany.agent.gsd_agent import GsdAgent
from vcompany.agent.gsd_lifecycle import GsdLifecycle
from vcompany.agent.gsd_phases import CheckpointData
from vcompany.container.child_spec import ChildSpec
from vcompany.container.context import ContainerContext


def _ctx(agent_id: str = "test-gsd-1", agent_type: str = "gsd") -> ContainerContext:
    """Helper to create a default ContainerContext."""
    return ContainerContext(agent_id=agent_id, agent_type=agent_type)


async def _make_agent(tmp_path: Path, agent_id: str = "test-gsd-1") -> GsdAgent:
    """Create and start a GsdAgent with an auto-approve review callback.

    Wires _on_review_request to immediately resolve the gate with 'approve'
    so tests don't block waiting for a PM that doesn't exist in test context.
    """
    agent = GsdAgent(context=_ctx(agent_id=agent_id), data_dir=tmp_path)

    async def _auto_approve(aid: str, stage: str) -> None:
        """Immediately resolve the gate with 'approve' for test isolation."""
        agent.resolve_review("approve")

    agent._on_review_request = _auto_approve
    await agent.start()
    return agent


# --- State Tracking (TYPE-01) ---


class TestStateTracking:
    """GsdAgent state/inner_state handle compound FSM states correctly."""

    def test_state_before_start(self, tmp_path: Path) -> None:
        """state is 'creating' before start, inner_state is None."""
        agent = GsdAgent(context=_ctx(), data_dir=tmp_path)
        assert agent.state == "creating"
        assert agent.inner_state is None

    @pytest.mark.asyncio
    async def test_state_after_start(self, tmp_path: Path) -> None:
        """state is 'running' after start, inner_state is 'idle'."""
        agent = await _make_agent(tmp_path)
        assert agent.state == "running"
        assert agent.inner_state == "idle"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_state_after_advance(self, tmp_path: Path) -> None:
        """After advance to discuss, state is running, inner_state is discuss."""
        agent = await _make_agent(tmp_path)
        await agent.advance_phase("discuss")
        assert agent.state == "running"
        assert agent.inner_state == "discuss"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_inner_state_none_when_sleeping(self, tmp_path: Path) -> None:
        """After sleep, inner_state is None, state is sleeping."""
        agent = await _make_agent(tmp_path)
        await agent.advance_phase("discuss")
        await agent.advance_phase("plan")
        await agent.sleep()
        assert agent.state == "sleeping"
        assert agent.inner_state is None
        await agent.stop()

    @pytest.mark.asyncio
    async def test_inner_state_restored_after_wake(self, tmp_path: Path) -> None:
        """After sleep then wake, inner_state is restored via HistoryState."""
        agent = await _make_agent(tmp_path)
        await agent.advance_phase("discuss")
        await agent.advance_phase("plan")
        await agent.sleep()
        await agent.wake()
        assert agent.state == "running"
        assert agent.inner_state == "plan"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_full_phase_sequence(self, tmp_path: Path) -> None:
        """Advance through all 5 transitions, verify inner_state at each."""
        agent = await _make_agent(tmp_path)
        phases = ["discuss", "plan", "execute", "uat", "ship"]
        for phase in phases:
            await agent.advance_phase(phase)
            assert agent.inner_state == phase, f"Expected {phase}, got {agent.inner_state}"
            assert agent.state == "running"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_health_report_compound_state(self, tmp_path: Path) -> None:
        """health_report shows correct state/inner_state in compound state."""
        agent = await _make_agent(tmp_path)
        await agent.advance_phase("discuss")
        await agent.advance_phase("plan")
        await agent.advance_phase("execute")
        report = agent.health_report()
        assert report.state == "running"
        assert report.inner_state == "execute"
        await agent.stop()


# --- Checkpointing (TYPE-02) ---


class TestCheckpointing:
    """Checkpoints persist on phase transitions."""

    @pytest.mark.asyncio
    async def test_checkpoint_on_advance(self, tmp_path: Path) -> None:
        """After advance to discuss, checkpoint has configuration=['running','discuss']."""
        agent = await _make_agent(tmp_path)
        await agent.advance_phase("discuss")
        raw = await agent.memory.get_latest_checkpoint("gsd_phase")
        assert raw is not None
        cp = CheckpointData.model_validate_json(raw)
        assert cp.configuration == ["running", "discuss"]
        assert cp.phase == "discuss"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_current_phase_kv_updated(self, tmp_path: Path) -> None:
        """After advance to plan, memory KV has current_phase = 'plan'."""
        agent = await _make_agent(tmp_path)
        await agent.advance_phase("discuss")
        await agent.advance_phase("plan")
        val = await agent.memory.get("current_phase")
        assert val == "plan"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_checkpoint_lock_exists(self, tmp_path: Path) -> None:
        """GsdAgent has a _checkpoint_lock attribute."""
        agent = GsdAgent(context=_ctx(), data_dir=tmp_path)
        assert hasattr(agent, "_checkpoint_lock")
        assert isinstance(agent._checkpoint_lock, asyncio.Lock)


# --- Crash Recovery (TYPE-02) ---


class TestCrashRecovery:
    """Crash recovery restores last checkpointed phase state."""

    @pytest.mark.asyncio
    async def test_recovery_from_checkpoint(self, tmp_path: Path) -> None:
        """Agent2 with same data_dir recovers agent1's phase."""
        agent1 = await _make_agent(tmp_path, agent_id="recover-1")
        await agent1.advance_phase("discuss")
        await agent1.advance_phase("plan")
        await agent1.stop()

        agent2 = GsdAgent(context=_ctx(agent_id="recover-1"), data_dir=tmp_path)
        await agent2.start()
        assert agent2.inner_state == "plan"
        await agent2.stop()

    @pytest.mark.asyncio
    async def test_recovery_full_sequence(self, tmp_path: Path) -> None:
        """Recover after advancing to execute."""
        agent1 = await _make_agent(tmp_path, agent_id="recover-2")
        await agent1.advance_phase("discuss")
        await agent1.advance_phase("plan")
        await agent1.advance_phase("execute")
        await agent1.stop()

        agent2 = GsdAgent(context=_ctx(agent_id="recover-2"), data_dir=tmp_path)
        await agent2.start()
        assert agent2.inner_state == "execute"
        await agent2.stop()

    @pytest.mark.asyncio
    async def test_invalid_checkpoint_fallback(self, tmp_path: Path) -> None:
        """Invalid state name in checkpoint falls back to idle."""
        # Manually write a checkpoint with an unknown state name
        agent = await _make_agent(tmp_path, agent_id="bad-cp-1")
        bad_cp = CheckpointData(
            configuration=["running", "nonexistent"],
            phase="nonexistent",
            timestamp="2026-01-01T00:00:00Z",
        )
        await agent.memory.checkpoint("gsd_phase", bad_cp.model_dump_json())
        await agent.stop()

        # New agent should fall back to idle
        agent2 = GsdAgent(context=_ctx(agent_id="bad-cp-1"), data_dir=tmp_path)
        await agent2.start()
        assert agent2.inner_state == "idle"
        await agent2.stop()

    @pytest.mark.asyncio
    async def test_corrupt_json_fallback(self, tmp_path: Path) -> None:
        """Corrupt JSON in checkpoint falls back to idle."""
        agent = await _make_agent(tmp_path, agent_id="bad-json-1")
        await agent.memory.checkpoint("gsd_phase", "{invalid json!!!")
        await agent.stop()

        agent2 = GsdAgent(context=_ctx(agent_id="bad-json-1"), data_dir=tmp_path)
        await agent2.start()
        assert agent2.inner_state == "idle"
        await agent2.stop()


# --- Blocked Tracking ---


class TestBlockedTracking:
    """Blocked tracking replaces WorkflowOrchestrator.handle_unknown_prompt."""

    @pytest.mark.asyncio
    async def test_mark_blocked(self, tmp_path: Path) -> None:
        """mark_blocked sets is_blocked True."""
        agent = await _make_agent(tmp_path)
        agent.mark_blocked("stuck on prompt")
        assert agent.is_blocked is True
        await agent.stop()

    @pytest.mark.asyncio
    async def test_clear_blocked(self, tmp_path: Path) -> None:
        """clear_blocked resets is_blocked."""
        agent = await _make_agent(tmp_path)
        agent.mark_blocked("stuck")
        agent.clear_blocked()
        assert agent.is_blocked is False
        await agent.stop()

    @pytest.mark.asyncio
    async def test_blocked_reason_truncated(self, tmp_path: Path) -> None:
        """Blocked reason is truncated to 200 chars."""
        agent = await _make_agent(tmp_path)
        agent.mark_blocked("x" * 300)
        assert len(agent._blocked_reason) == 200
        await agent.stop()


# --- Review Gate Loop (GATE-01) ---


class TestReviewGateLoop:
    """advance_phase re-enters gate on modify/clarify until approve."""

    @pytest.mark.asyncio
    async def test_modify_then_approve(self, tmp_path: Path) -> None:
        """Gate blocks after modify, only continues after approve."""
        agent = GsdAgent(context=_ctx(), data_dir=tmp_path)
        decisions = iter(["modify", "approve"])

        async def _staged_review(aid: str, stage: str) -> None:
            agent.resolve_review(next(decisions))

        agent._on_review_request = _staged_review
        await agent.start()
        result = await agent.advance_phase("discuss")
        assert result == "approve"
        assert agent._review_attempts == 1  # one modify before approve
        await agent.stop()

    @pytest.mark.asyncio
    async def test_clarify_then_modify_then_approve(self, tmp_path: Path) -> None:
        """Multiple non-approve decisions loop until approve."""
        agent = GsdAgent(context=_ctx(), data_dir=tmp_path)
        decisions = iter(["clarify", "modify", "approve"])

        async def _staged_review(aid: str, stage: str) -> None:
            agent.resolve_review(next(decisions))

        agent._on_review_request = _staged_review
        await agent.start()
        # advance_phase("discuss") is valid from idle; tests the looping behavior
        result = await agent.advance_phase("discuss")
        assert result == "approve"
        assert agent._review_attempts == 2
        await agent.stop()

    @pytest.mark.asyncio
    async def test_max_attempts_auto_approves(self, tmp_path: Path) -> None:
        """After max_review_attempts non-approvals, auto-approves."""
        agent = GsdAgent(context=_ctx(), data_dir=tmp_path)
        agent._max_review_attempts = 2

        async def _always_modify(aid: str, stage: str) -> None:
            agent.resolve_review("modify")

        agent._on_review_request = _always_modify
        await agent.start()
        # advance_phase("discuss") is valid from idle; tests the max-attempts safety valve
        result = await agent.advance_phase("discuss")
        assert result == "approve"
        assert agent._review_attempts == 2
        await agent.stop()


# --- from_spec ---


class TestFromSpec:
    """GsdAgent.from_spec creates GsdAgent instances."""

    def test_from_spec_creates_gsd_agent(self, tmp_path: Path) -> None:
        """from_spec returns a GsdAgent instance."""
        ctx = _ctx(agent_id="spec-agent")
        spec = ChildSpec(child_id="spec-agent", agent_type="gsd", context=ctx)
        agent = GsdAgent.from_spec(spec, data_dir=tmp_path)
        assert isinstance(agent, GsdAgent)

    def test_from_spec_uses_gsd_lifecycle(self, tmp_path: Path) -> None:
        """from_spec result uses GsdLifecycle as its _lifecycle."""
        ctx = _ctx(agent_id="spec-agent-2")
        spec = ChildSpec(child_id="spec-agent-2", agent_type="gsd", context=ctx)
        agent = GsdAgent.from_spec(spec, data_dir=tmp_path)
        assert isinstance(agent._lifecycle, GsdLifecycle)
