"""WorkerConfig -- config blob sent by head in StartMessage.config."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkerConfig(BaseModel):
    """Config blob sent by head in StartMessage.config.

    Validated from the dict in StartMessage.config via model_validate().
    Contains everything the worker needs to bootstrap an agent container.
    """

    handler_type: str  # "session", "conversation", "transient"
    agent_type: str = "gsd"  # For lifecycle FSM selection: "gsd", "event_driven"
    capabilities: list[str] = Field(default_factory=list)
    gsd_command: str | None = None
    persona: str | None = None
    env_vars: dict[str, str] = Field(default_factory=dict)
    data_dir: str = "/tmp/vco-worker/data"
    project_id: str | None = None
    project_dir: str | None = None
    project_session_name: str | None = None
    uses_tmux: bool = False
