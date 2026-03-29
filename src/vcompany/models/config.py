"""Pydantic v2 models for agents.yaml parsing and validation."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator, model_validator


class AgentConfig(BaseModel):
    """Configuration for a single agent."""

    id: str
    role: str
    owns: list[str]
    consumes: str
    gsd_mode: Literal["full", "quick"]
    system_prompt: str
    type: Literal["gsd", "continuous", "fulltime", "company"] = "gsd"
    transport: str = "local"

    @field_validator("id")
    @classmethod
    def id_must_be_alphanumeric(cls, v: str) -> str:
        """Agent ID must be alphanumeric with hyphens/underscores, non-empty."""
        if not v:
            raise ValueError("Agent ID must not be empty")
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Agent ID must be alphanumeric (with - or _): {v!r}")
        return v

    @field_validator("owns")
    @classmethod
    def owns_must_not_be_empty(cls, v: list[str]) -> list[str]:
        """Agent must own at least one directory."""
        if not v:
            raise ValueError("Agent must own at least one directory")
        return v


class ProjectConfig(BaseModel):
    """Top-level project configuration from agents.yaml."""

    project: str
    repo: str
    agents: list[AgentConfig]
    shared_readonly: list[str] = []

    @model_validator(mode="after")
    def validate_project_constraints(self) -> "ProjectConfig":
        """Validate agent IDs are unique and directory ownership does not overlap."""
        # Check for duplicate agent IDs
        seen_ids: set[str] = set()
        for agent in self.agents:
            if agent.id in seen_ids:
                raise ValueError(f"Duplicate agent ID: {agent.id!r}")
            seen_ids.add(agent.id)

        # Check for overlapping directory ownership
        all_dirs: list[tuple[str, str]] = []  # (normalized_dir, agent_id)
        for agent in self.agents:
            for d in agent.owns:
                normalized = d.rstrip("/") + "/"
                for existing_dir, existing_agent in all_dirs:
                    if normalized.startswith(existing_dir) or existing_dir.startswith(normalized):
                        raise ValueError(
                            f"Overlapping directory ownership: '{d}' (agent {agent.id}) "
                            f"conflicts with '{existing_dir.rstrip('/')}' (agent {existing_agent})"
                        )
                all_dirs.append((normalized, agent.id))

        return self


def load_config(config_path: Path) -> ProjectConfig:
    """Load and validate agents.yaml. Raises ValidationError on invalid config."""
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return ProjectConfig(**raw)
