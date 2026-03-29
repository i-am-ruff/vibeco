"""Agent type definitions and config loader.

agent-types.yaml is the single source of truth for all agent type definitions (D-05).
This module provides the Pydantic models for parsing that file, plus built-in defaults
so the system works even without an agent-types.yaml on disk.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class AgentTypeConfig(BaseModel):
    """Schema for a single agent type definition (D-08)."""

    transport: str = "local"
    docker_image: str | None = None
    container_class: str = "AgentContainer"
    capabilities: list[str] = []
    gsd_command: str | None = None
    tweakcc_profile: str | None = None
    settings_json: str | None = None
    env: dict[str, str] = {}
    volumes: dict[str, str] = {}


class AgentTypesConfig(BaseModel):
    """Top-level agent-types.yaml schema (D-05)."""

    agent_types: dict[str, AgentTypeConfig]

    def get_type(self, type_name: str) -> AgentTypeConfig:
        """Get config for a named agent type. Raises KeyError if not found."""
        if type_name not in self.agent_types:
            raise KeyError(f"Unknown agent type: {type_name!r}")
        return self.agent_types[type_name]

    def has_capability(self, type_name: str, capability: str) -> bool:
        """Check if an agent type has a specific capability."""
        return capability in self.get_type(type_name).capabilities


# Built-in defaults matching current hardcoded behavior (Pitfall 4 in RESEARCH.md).
# System works even without an agent-types.yaml file on disk.
_BUILTIN_DEFAULTS: dict[str, dict] = {
    "gsd": {
        "transport": "local",
        "container_class": "GsdAgent",
        "capabilities": ["gsd_driven", "uses_tmux"],
        "gsd_command": "/gsd:discuss-phase 1",
    },
    "continuous": {
        "transport": "local",
        "container_class": "ContinuousAgent",
        "capabilities": ["uses_tmux"],
    },
    "fulltime": {
        "transport": "local",
        "container_class": "FulltimeAgent",
        "capabilities": ["event_driven", "reviews_plans"],
    },
    "company": {
        "transport": "local",
        "container_class": "CompanyAgent",
        "capabilities": ["event_driven"],
    },
    "task": {
        "transport": "local",
        "container_class": "TaskAgent",
        "capabilities": ["uses_tmux"],
    },
}


def get_default_config() -> AgentTypesConfig:
    """Return an AgentTypesConfig built from built-in defaults."""
    return AgentTypesConfig(
        agent_types={
            name: AgentTypeConfig(**props)
            for name, props in _BUILTIN_DEFAULTS.items()
        }
    )


def load_agent_types(config_path: Path) -> AgentTypesConfig:
    """Load and validate agent-types.yaml.

    Args:
        config_path: Path to the agent-types.yaml file.

    Returns:
        Validated AgentTypesConfig instance.

    Raises:
        FileNotFoundError: If config_path does not exist.
        yaml.YAMLError: If file is not valid YAML.
        pydantic.ValidationError: If YAML content doesn't match schema.
    """
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return AgentTypesConfig(**raw)
