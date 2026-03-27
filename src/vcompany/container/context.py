"""ContainerContext — immutable metadata for an agent container (CONT-03)."""

from pydantic import BaseModel


class ContainerContext(BaseModel):
    """Immutable context set at container creation time.

    Fields:
        agent_id: Unique identifier for the agent.
        agent_type: One of "gsd", "continuous", "fulltime", "company".
        parent_id: ID of the parent supervisor (None for root).
        project_id: ID of the project this agent belongs to.
        owned_dirs: Directories this agent is allowed to modify.
        gsd_mode: GSD pipeline mode ("full" or "quick").
        system_prompt: System prompt injected into the agent's session.
    """

    agent_id: str
    agent_type: str
    parent_id: str | None = None
    project_id: str | None = None
    owned_dirs: list[str] = []
    gsd_mode: str = "full"
    system_prompt: str = ""
