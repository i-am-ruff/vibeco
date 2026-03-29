"""HealthReport — self-reported health for a container (HLTH-01)."""

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
    """

    agent_id: str
    state: str
    inner_state: str | None = None
    uptime: float
    last_heartbeat: datetime
    error_count: int = 0
    last_activity: datetime
    blocked_reason: str | None = None  # ARCH-03: populated when state == "blocked"
    is_idle: bool | None = None  # True when Claude Code is waiting for input (signal-based)
    transport_type: str | None = None  # "local" or "docker"
    docker_container_id: str | None = None  # Short container ID for Docker agents
    docker_image: str | None = None  # Image name for Docker agents


class HealthNode(BaseModel):
    """A single child's health within a supervision tree.

    Wraps a HealthReport so the tree structure can be extended later
    (e.g., with restart counts, timestamps) without changing HealthReport.
    """

    report: HealthReport


class HealthTree(BaseModel):
    """Aggregated health for a Supervisor and its direct children.

    Returned by ``Supervisor.health_tree()``.
    """

    supervisor_id: str
    state: str
    children: list[HealthNode] = []


class CompanyHealthTree(BaseModel):
    """Top-level health view across all projects.

    Returned by ``CompanyRoot.health_tree()``. Each project is a HealthTree.
    """

    supervisor_id: str
    state: str
    projects: list[HealthTree] = []
    company_agents: list[HealthNode] = []  # CompanyAgent containers (Strategist etc.)
