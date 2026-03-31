"""Tests for RoutingState — agent-to-channel routing persistence."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vcompany.daemon.routing_state import AgentRouting, RoutingState


class TestRoutingStateRoundTrip:
    """Test save/load round-trip with tmp_path."""

    def test_save_load_round_trip(self, tmp_path):
        state = RoutingState()
        state.add_agent(
            AgentRouting(
                agent_id="agent-1",
                channel_id="ch-123",
                category_id="cat-456",
                agent_type="task",
                handler_type="session",
                capabilities=["code"],
                config={"persona": "coder"},
            )
        )
        state.add_agent(
            AgentRouting(agent_id="agent-2", agent_type="continuous")
        )

        path = tmp_path / "routing.json"
        state.save(path)

        loaded = RoutingState.load(path)
        assert len(loaded.agents) == 2
        assert loaded.agents["agent-1"].channel_id == "ch-123"
        assert loaded.agents["agent-1"].capabilities == ["code"]
        assert loaded.agents["agent-2"].agent_type == "continuous"

    def test_save_creates_parent_dirs(self, tmp_path):
        state = RoutingState()
        path = tmp_path / "deep" / "nested" / "routing.json"
        state.save(path)
        assert path.exists()


class TestRoutingStateOperations:
    """Test add_agent/remove_agent operations."""

    def test_add_agent(self):
        state = RoutingState()
        routing = AgentRouting(agent_id="a1", channel_id="ch1")
        state.add_agent(routing)
        assert "a1" in state.agents
        assert state.agents["a1"].channel_id == "ch1"

    def test_add_agent_overwrites_existing(self):
        state = RoutingState()
        state.add_agent(AgentRouting(agent_id="a1", channel_id="ch1"))
        state.add_agent(AgentRouting(agent_id="a1", channel_id="ch2"))
        assert state.agents["a1"].channel_id == "ch2"

    def test_remove_agent_returns_removed(self):
        state = RoutingState()
        state.add_agent(AgentRouting(agent_id="a1", channel_id="ch1"))
        removed = state.remove_agent("a1")
        assert removed is not None
        assert removed.agent_id == "a1"
        assert "a1" not in state.agents

    def test_remove_nonexistent_returns_none(self):
        state = RoutingState()
        assert state.remove_agent("nope") is None

    def test_get_agent(self):
        state = RoutingState()
        state.add_agent(AgentRouting(agent_id="a1", channel_id="ch1"))
        assert state.get_agent("a1") is not None
        assert state.get_agent("nope") is None


class TestRoutingStateEdgeCases:
    """Test load with missing/corrupted files."""

    def test_load_returns_empty_when_file_missing(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        state = RoutingState.load(path)
        assert state.agents == {}

    def test_load_corrupted_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not valid json {{{")
        with pytest.raises(ValidationError):
            RoutingState.load(path)
