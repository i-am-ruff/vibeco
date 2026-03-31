"""RoutingState — persistence for Discord channel-to-agent routing.

Saves and loads agent routing information (channel bindings, types, config)
so the daemon can reconstruct routing after restarts without requiring
workers to re-register.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class AgentRouting(BaseModel):
    """Persisted routing info for one agent."""

    agent_id: str
    channel_id: str | None = None
    category_id: str | None = None
    agent_type: str = "task"
    handler_type: str = "session"
    config: dict = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    transport_type: str = "native"  # "native" or "docker" -- needed for reconnection


class RoutingState(BaseModel):
    """Full routing state persisted to disk.

    Maps agent_id -> AgentRouting for all known agents. Saved as JSON
    to a configurable path (default: state/supervision/routing.json).
    """

    agents: dict[str, AgentRouting] = Field(default_factory=dict)

    def add_agent(self, routing: AgentRouting) -> None:
        """Register or update an agent's routing info."""
        self.agents[routing.agent_id] = routing

    def remove_agent(self, agent_id: str) -> AgentRouting | None:
        """Remove an agent's routing info. Returns the removed entry or None."""
        return self.agents.pop(agent_id, None)

    def get_agent(self, agent_id: str) -> AgentRouting | None:
        """Look up routing info for an agent."""
        return self.agents.get(agent_id)

    def save(self, path: Path) -> None:
        """Persist routing state to disk as JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: Path) -> RoutingState:
        """Load routing state from disk. Returns empty state if file missing."""
        if not path.exists():
            return cls()
        return cls.model_validate_json(path.read_text())
