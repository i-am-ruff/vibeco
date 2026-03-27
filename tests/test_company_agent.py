"""Tests for CompanyAgent -- event-driven Strategist container (TYPE-05)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from vcompany.container.child_spec import ChildSpec
from vcompany.container.context import ContainerContext


def _ctx(agent_id: str = "strat-1") -> ContainerContext:
    """Helper to create a ContainerContext for CompanyAgent (no project_id)."""
    return ContainerContext(
        agent_id=agent_id,
        agent_type="company",
        project_id=None,
    )


async def _make_agent(tmp_path: Path, agent_id: str = "strat-1") -> "CompanyAgent":
    """Create and start a CompanyAgent."""
    from vcompany.agent.company_agent import CompanyAgent

    agent = CompanyAgent(context=_ctx(agent_id=agent_id), data_dir=tmp_path)
    await agent.start()
    return agent


class TestCompanyAgentState:
    """Test 7: Starts in running.listening; context.project_id is None."""

    @pytest.mark.asyncio
    async def test_initial_state_and_no_project(self, tmp_path: Path) -> None:
        agent = await _make_agent(tmp_path)
        assert agent.state == "running"
        assert agent.inner_state == "listening"
        assert agent.context.project_id is None
        await agent.stop()


class TestCompanyEventProcessing:
    """Test 8: post_event + process_next_event works same as FulltimeAgent."""

    @pytest.mark.asyncio
    async def test_post_and_process_event(self, tmp_path: Path) -> None:
        agent = await _make_agent(tmp_path)
        await agent.post_event({"type": "briefing", "content": "status update"})

        result = await agent.process_next_event()
        assert result is True
        assert agent.inner_state == "listening"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_empty_queue_returns_false(self, tmp_path: Path) -> None:
        agent = await _make_agent(tmp_path)
        result = await agent.process_next_event()
        assert result is False
        await agent.stop()


class TestCrossProjectState:
    """Test 9: Cross-project state persists via memory_store KV."""

    @pytest.mark.asyncio
    async def test_set_and_get_cross_project_state(self, tmp_path: Path) -> None:
        agent = await _make_agent(tmp_path)
        await agent.set_cross_project_state("active_projects", "proj-1,proj-2")
        val = await agent.get_cross_project_state("active_projects")
        assert val == "proj-1,proj-2"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_cross_project_state_uses_xp_prefix(self, tmp_path: Path) -> None:
        agent = await _make_agent(tmp_path)
        await agent.set_cross_project_state("key1", "value1")
        # Verify it's stored with xp: prefix in memory
        raw = await agent.memory.get("xp:key1")
        assert raw == "value1"
        await agent.stop()

    @pytest.mark.asyncio
    async def test_missing_cross_project_state_returns_none(self, tmp_path: Path) -> None:
        agent = await _make_agent(tmp_path)
        val = await agent.get_cross_project_state("nonexistent")
        assert val is None
        await agent.stop()


class TestCrashRecovery:
    """Test 10: start() restores events_processed count from memory_store."""

    @pytest.mark.asyncio
    async def test_crash_recovery_restores_count(self, tmp_path: Path) -> None:
        # First agent processes some events
        agent1 = await _make_agent(tmp_path, agent_id="strat-recover")
        await agent1.post_event({"type": "e1"})
        await agent1.post_event({"type": "e2"})
        await agent1.post_event({"type": "e3"})
        await agent1.process_next_event()
        await agent1.process_next_event()
        await agent1.process_next_event()
        assert agent1._events_processed == 3
        await agent1.stop()

        # Second agent with same data_dir recovers count
        from vcompany.agent.company_agent import CompanyAgent

        agent2 = CompanyAgent(
            context=_ctx(agent_id="strat-recover"), data_dir=tmp_path
        )
        await agent2.start()
        assert agent2._events_processed == 3
        await agent2.stop()


class TestCompanyFromSpec:
    """Test 11: from_spec creates CompanyAgent with project_id=None."""

    def test_from_spec_creates_company_agent(self, tmp_path: Path) -> None:
        from vcompany.agent.company_agent import CompanyAgent

        ctx = _ctx(agent_id="strat-spec")
        spec = ChildSpec(child_id="strat-spec", agent_type="company", context=ctx)
        agent = CompanyAgent.from_spec(spec, data_dir=tmp_path)
        assert isinstance(agent, CompanyAgent)
        assert agent.context.project_id is None
