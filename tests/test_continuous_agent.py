"""Tests for ContinuousAgent — cycle transitions, checkpointing, crash recovery."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from vcompany.agent.continuous_phases import CycleCheckpointData
from vcompany.container.child_spec import ChildSpec
from vcompany.container.context import ContainerContext


def _ctx(agent_id: str = "test-cont-1", agent_type: str = "continuous") -> ContainerContext:
    """Helper to create a default ContainerContext."""
    return ContainerContext(agent_id=agent_id, agent_type=agent_type)


async def _make_agent(tmp_path: Path, agent_id: str = "test-cont-1"):
    """Create and start a ContinuousAgent."""
    from vcompany.agent.continuous_agent import ContinuousAgent

    agent = ContinuousAgent(context=_ctx(agent_id=agent_id), data_dir=tmp_path)
    await agent.start()
    return agent


# --- State Tracking ---


class TestStateTracking:
    """ContinuousAgent state/inner_state handle compound FSM states correctly."""

    @pytest.mark.asyncio
    async def test_state_after_start(self, tmp_path: Path) -> None:
        """state is 'running' after start, inner_state is 'wake'."""
        agent = await _make_agent(tmp_path)
        assert agent.state == "running"
        assert agent.inner_state == "wake"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_advance_cycle_to_gather(self, tmp_path: Path) -> None:
        """advance_cycle('gather') transitions to running.gather and checkpoints."""
        agent = await _make_agent(tmp_path)
        await agent.advance_cycle("gather")
        assert agent.state == "running"
        assert agent.inner_state == "gather"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_full_cycle_advance(self, tmp_path: Path) -> None:
        """Full cycle: wake->gather->analyze->act->report->sleep_prep."""
        agent = await _make_agent(tmp_path)
        phases = ["gather", "analyze", "act", "report", "sleep_prep"]
        for phase in phases:
            await agent.advance_cycle(phase)
            assert agent.inner_state == phase, f"Expected {phase}, got {agent.inner_state}"
            assert agent.state == "running"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_invalid_phase_raises(self, tmp_path: Path) -> None:
        """advance_cycle with unknown phase raises ValueError."""
        agent = await _make_agent(tmp_path)
        with pytest.raises(ValueError, match="Unknown cycle phase"):
            await agent.advance_cycle("nonexistent")
        await agent.stop()


# --- Checkpointing ---


class TestCheckpointing:
    """Checkpoints persist on cycle phase transitions."""

    @pytest.mark.asyncio
    async def test_checkpoint_on_advance(self, tmp_path: Path) -> None:
        """After advance to gather, checkpoint has configuration=['running','gather']."""
        agent = await _make_agent(tmp_path)
        await agent.advance_cycle("gather")
        raw = await agent.memory.get_latest_checkpoint("continuous_cycle")
        assert raw is not None
        cp = CycleCheckpointData.model_validate_json(raw)
        assert cp.configuration == ["running", "gather"]
        assert cp.cycle_phase == "gather"
        assert cp.cycle_count == 0
        await agent.stop()

    @pytest.mark.asyncio
    async def test_checkpoint_lock_exists(self, tmp_path: Path) -> None:
        """ContinuousAgent has a _checkpoint_lock attribute."""
        from vcompany.agent.continuous_agent import ContinuousAgent

        agent = ContinuousAgent(context=_ctx(), data_dir=tmp_path)
        assert hasattr(agent, "_checkpoint_lock")
        assert isinstance(agent._checkpoint_lock, asyncio.Lock)


# --- Crash Recovery ---


class TestCrashRecovery:
    """Crash recovery restores last checkpointed cycle phase."""

    @pytest.mark.asyncio
    async def test_recovery_from_checkpoint(self, tmp_path: Path) -> None:
        """Agent2 with same data_dir recovers agent1's cycle phase."""
        from vcompany.agent.continuous_agent import ContinuousAgent

        agent1 = await _make_agent(tmp_path, agent_id="recover-c1")
        await agent1.advance_cycle("gather")
        await agent1.advance_cycle("analyze")
        await agent1.stop()

        agent2 = ContinuousAgent(context=_ctx(agent_id="recover-c1"), data_dir=tmp_path)
        await agent2.start()
        assert agent2.inner_state == "analyze"
        await agent2.stop()

    @pytest.mark.asyncio
    async def test_invalid_checkpoint_fallback(self, tmp_path: Path) -> None:
        """Invalid state name in checkpoint falls back to wake."""
        from vcompany.agent.continuous_agent import ContinuousAgent

        agent = await _make_agent(tmp_path, agent_id="bad-cp-c1")
        bad_cp = CycleCheckpointData(
            configuration=["running", "nonexistent"],
            cycle_phase="nonexistent",
            cycle_count=0,
            timestamp="2026-01-01T00:00:00Z",
        )
        await agent.memory.checkpoint("continuous_cycle", bad_cp.model_dump_json())
        await agent.stop()

        agent2 = ContinuousAgent(context=_ctx(agent_id="bad-cp-c1"), data_dir=tmp_path)
        await agent2.start()
        assert agent2.inner_state == "wake"
        await agent2.stop()

    @pytest.mark.asyncio
    async def test_corrupt_json_fallback(self, tmp_path: Path) -> None:
        """Corrupt JSON in checkpoint falls back to wake."""
        from vcompany.agent.continuous_agent import ContinuousAgent

        agent = await _make_agent(tmp_path, agent_id="bad-json-c1")
        await agent.memory.checkpoint("continuous_cycle", "{invalid json!!!")
        await agent.stop()

        agent2 = ContinuousAgent(context=_ctx(agent_id="bad-json-c1"), data_dir=tmp_path)
        await agent2.start()
        assert agent2.inner_state == "wake"
        await agent2.stop()


# --- Sleep/Wake ---


class TestSleepWake:
    """Sleep checkpoints, wake starts fresh."""

    @pytest.mark.asyncio
    async def test_sleep_checkpoints(self, tmp_path: Path) -> None:
        """sleep() checkpoints before sleeping."""
        agent = await _make_agent(tmp_path)
        await agent.advance_cycle("gather")
        await agent.advance_cycle("analyze")
        await agent.sleep()
        assert agent.state == "sleeping"

        raw = await agent.memory.get_latest_checkpoint("continuous_cycle")
        assert raw is not None
        cp = CycleCheckpointData.model_validate_json(raw)
        assert cp.cycle_phase == "analyze"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_wake_starts_fresh(self, tmp_path: Path) -> None:
        """wake() starts fresh at running.wake, not resuming mid-cycle."""
        agent = await _make_agent(tmp_path)
        await agent.advance_cycle("gather")
        await agent.advance_cycle("analyze")
        await agent.sleep()
        await agent.wake()
        assert agent.state == "running"
        assert agent.inner_state == "wake"
        await agent.stop()


# --- Error/Recover ---


class TestErrorRecover:
    """Error checkpoints, recover resumes mid-cycle."""

    @pytest.mark.asyncio
    async def test_error_checkpoints(self, tmp_path: Path) -> None:
        """error() checkpoints before transitioning to errored."""
        agent = await _make_agent(tmp_path)
        await agent.advance_cycle("gather")
        await agent.advance_cycle("analyze")
        await agent.error()
        assert agent.state == "errored"

        raw = await agent.memory.get_latest_checkpoint("continuous_cycle")
        assert raw is not None
        cp = CycleCheckpointData.model_validate_json(raw)
        assert cp.cycle_phase == "analyze"
        await agent.stop()


# --- Cycle Count ---


class TestCycleCount:
    """cycle_count increments and persists."""

    @pytest.mark.asyncio
    async def test_cycle_count_increments(self, tmp_path: Path) -> None:
        """complete_cycle() increments cycle_count."""
        agent = await _make_agent(tmp_path)
        assert agent._cycle_count == 0
        await agent.complete_cycle()
        assert agent._cycle_count == 1
        await agent.complete_cycle()
        assert agent._cycle_count == 2
        await agent.stop()

    @pytest.mark.asyncio
    async def test_cycle_count_persists(self, tmp_path: Path) -> None:
        """cycle_count persists across restarts via memory_store."""
        from vcompany.agent.continuous_agent import ContinuousAgent

        agent1 = await _make_agent(tmp_path, agent_id="count-c1")
        await agent1.complete_cycle()
        await agent1.complete_cycle()
        await agent1.complete_cycle()
        await agent1.stop()

        agent2 = ContinuousAgent(context=_ctx(agent_id="count-c1"), data_dir=tmp_path)
        await agent2.start()
        assert agent2._cycle_count == 3
        await agent2.stop()


# --- from_spec ---


class TestFromSpec:
    """ContinuousAgent.from_spec creates correct instances."""

    def test_from_spec_creates_continuous_agent(self, tmp_path: Path) -> None:
        """from_spec returns a ContinuousAgent instance."""
        from vcompany.agent.continuous_agent import ContinuousAgent
        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        ctx = _ctx(agent_id="spec-cont")
        spec = ChildSpec(child_id="spec-cont", agent_type="continuous", context=ctx)
        agent = ContinuousAgent.from_spec(spec, data_dir=tmp_path)
        assert isinstance(agent, ContinuousAgent)
        assert isinstance(agent._lifecycle, ContinuousLifecycle)
