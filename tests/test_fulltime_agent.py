"""Tests for FulltimeAgent -- event-driven PM container (TYPE-04)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from vcompany.container.child_spec import ChildSpec
from vcompany.container.context import ContainerContext


def _ctx(agent_id: str = "pm-1", project_id: str = "proj-1") -> ContainerContext:
    """Helper to create a ContainerContext for FulltimeAgent."""
    return ContainerContext(
        agent_id=agent_id,
        agent_type="fulltime",
        project_id=project_id,
    )


async def _make_agent(tmp_path: Path, agent_id: str = "pm-1") -> "FulltimeAgent":
    """Create and start a FulltimeAgent."""
    from vcompany.agent.fulltime_agent import FulltimeAgent

    agent = FulltimeAgent(context=_ctx(agent_id=agent_id), data_dir=tmp_path)
    await agent.start()
    return agent


class TestFulltimeAgentState:
    """Test 1: Starts in running.listening; state=='running', inner_state=='listening'."""

    @pytest.mark.asyncio
    async def test_initial_state_after_start(self, tmp_path: Path) -> None:
        agent = await _make_agent(tmp_path)
        assert agent.state == "running"
        assert agent.inner_state == "listening"
        await agent.stop()


class TestEventProcessing:
    """Test 2: post_event + process_next_event transitions and processes."""

    @pytest.mark.asyncio
    async def test_post_and_process_event(self, tmp_path: Path) -> None:
        agent = await _make_agent(tmp_path)
        await agent.post_event({"type": "health_change", "agent_id": "dev-1"})

        result = await agent.process_next_event()
        assert result is True
        # After processing, should be back to listening
        assert agent.inner_state == "listening"
        await agent.stop()


class TestEventHandlerReceivesData:
    """Test 3: Event handler receives the event data."""

    @pytest.mark.asyncio
    async def test_handler_receives_event(self, tmp_path: Path) -> None:
        from vcompany.agent.fulltime_agent import FulltimeAgent

        received: list[dict] = []

        class TrackingAgent(FulltimeAgent):
            async def _handle_event(self, event: dict) -> None:
                received.append(event)

        agent = TrackingAgent(context=_ctx(agent_id="pm-track"), data_dir=tmp_path)
        await agent.start()

        event = {"type": "escalation", "from": "dev-2", "message": "blocked"}
        await agent.post_event(event)
        await agent.process_next_event()

        assert len(received) == 1
        assert received[0] == event
        await agent.stop()


class TestEmptyQueue:
    """Test 4: process_next_event() when queue empty returns False."""

    @pytest.mark.asyncio
    async def test_empty_queue_returns_false(self, tmp_path: Path) -> None:
        agent = await _make_agent(tmp_path)
        result = await agent.process_next_event()
        assert result is False
        # Should still be in listening (no transition happened)
        assert agent.inner_state == "listening"
        await agent.stop()


class TestCheckpointPersistence:
    """Test 5: Checkpoint after processing persists event count."""

    @pytest.mark.asyncio
    async def test_events_processed_persisted(self, tmp_path: Path) -> None:
        agent = await _make_agent(tmp_path)
        await agent.post_event({"type": "test1"})
        await agent.post_event({"type": "test2"})
        await agent.process_next_event()
        await agent.process_next_event()

        # Check memory store has the count
        val = await agent.memory.get("events_processed")
        assert val == "2"
        assert agent._events_processed == 2
        await agent.stop()


class TestFromSpec:
    """Test 6: from_spec creates FulltimeAgent with correct project_id."""

    def test_from_spec_creates_fulltime_agent(self, tmp_path: Path) -> None:
        from vcompany.agent.fulltime_agent import FulltimeAgent

        ctx = _ctx(agent_id="pm-spec", project_id="proj-42")
        spec = ChildSpec(child_id="pm-spec", agent_type="fulltime", context=ctx)
        agent = FulltimeAgent.from_spec(spec, data_dir=tmp_path)
        assert isinstance(agent, FulltimeAgent)
        assert agent.context.project_id == "proj-42"
