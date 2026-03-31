"""HealthReport -- self-reported health for a worker container."""

from datetime import datetime

from pydantic import BaseModel


class HealthReport(BaseModel):
    """Health snapshot emitted by a container on every state transition.

    Fields:
        agent_id: Which agent this report belongs to.
        state: Current lifecycle state (creating, running, sleeping, etc.).
        inner_state: Agent-type-specific sub-state (e.g., IDLE, PLAN for GsdAgent).
        uptime: Seconds since container creation.
        last_heartbeat: When this report was generated.
        error_count: Cumulative error transitions since creation.
        last_activity: When the container last did meaningful work.
        blocked_reason: Populated when state == "blocked".
        is_idle: True when Claude Code is waiting for input (signal-based).
    """

    agent_id: str
    state: str
    inner_state: str | None = None
    uptime: float
    last_heartbeat: datetime
    error_count: int = 0
    last_activity: datetime
    blocked_reason: str | None = None
    is_idle: bool | None = None
