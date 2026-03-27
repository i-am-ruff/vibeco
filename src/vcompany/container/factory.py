"""Container factory registry for agent type dispatch.

Maps agent_type strings to AgentContainer subclasses so supervisors create
the correct container type. Unregistered types fall back to base AgentContainer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from vcompany.container.child_spec import ChildSpec
from vcompany.container.container import AgentContainer
from vcompany.container.health import HealthReport

# Module-level registry: agent_type string -> container class
_REGISTRY: dict[str, type[AgentContainer]] = {}


def register_agent_type(agent_type: str, cls: type[AgentContainer]) -> None:
    """Register a container class for an agent type string.

    Args:
        agent_type: The agent_type value from ChildSpec/ContainerContext.
        cls: AgentContainer subclass to instantiate for this type.
    """
    _REGISTRY[agent_type] = cls


def create_container(
    spec: ChildSpec,
    data_dir: Path,
    comm_port: object | None = None,
    on_state_change: Callable[[HealthReport], None] | None = None,
) -> AgentContainer:
    """Create the correct AgentContainer subclass for a ChildSpec.

    Looks up spec.agent_type in the registry. Falls back to base
    AgentContainer if the type is not registered.

    Args:
        spec: Child specification with agent_type and context.
        data_dir: Root directory for container persistent data.
        comm_port: Optional communication port.
        on_state_change: Optional callback for state transitions.

    Returns:
        An AgentContainer instance (or subclass thereof).
    """
    cls = _REGISTRY.get(spec.agent_type, AgentContainer)
    return cls.from_spec(spec, data_dir=data_dir, comm_port=comm_port, on_state_change=on_state_change)


def get_registry() -> dict[str, type[AgentContainer]]:
    """Return a copy of the current registry for inspection/testing."""
    return dict(_REGISTRY)
