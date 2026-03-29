"""Container factory registry for agent type dispatch.

Maps agent_type strings to AgentContainer subclasses so supervisors create
the correct container type. Unregistered types fall back to base AgentContainer.

Transport instantiation follows D-07: factory reads AgentConfig.transport
(via ChildSpec.transport), looks up the class in _TRANSPORT_REGISTRY, and
instantiates with transport_deps. New transports = add one line to registry.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from vcompany.container.child_spec import ChildSpec
from vcompany.container.container import AgentContainer
from vcompany.container.health import HealthReport
from vcompany.models.agent_types import AgentTypeConfig, AgentTypesConfig
from vcompany.transport.docker import DockerTransport
from vcompany.transport.local import LocalTransport
from vcompany.transport.protocol import AgentTransport

logger = logging.getLogger(__name__)

# Module-level registry: agent_type string -> container class
_REGISTRY: dict[str, type[AgentContainer]] = {}

# Transport registry: transport name -> transport class (D-07)
_TRANSPORT_REGISTRY: dict[str, type] = {
    "local": LocalTransport,
    "docker": DockerTransport,
}

# Module-level agent types config -- set once at daemon startup via set_agent_types_config()
_agent_types_config: AgentTypesConfig | None = None


def set_agent_types_config(config: AgentTypesConfig) -> None:
    """Set the agent types config for factory transport resolution.

    Called once at daemon startup after loading agent-types.yaml.
    """
    global _agent_types_config
    _agent_types_config = config


def get_agent_types_config() -> AgentTypesConfig | None:
    """Return the current agent types config, or None if not set."""
    return _agent_types_config


def _resolve_transport_deps(
    transport_name: str,
    global_deps: dict,
    type_config: AgentTypeConfig | None,
) -> dict:
    """Resolve per-transport constructor dependencies from global deps and agent type config.

    Args:
        transport_name: Transport name ("local", "docker", etc.).
        global_deps: Global dependency dict from daemon (tmux_manager, project_name, etc.).
        type_config: Agent type config with transport-specific fields (docker_image, etc.).

    Returns:
        Dict of kwargs for the transport constructor.
    """
    if transport_name == "local":
        return {"tmux_manager": global_deps.get("tmux_manager")}
    if transport_name == "docker":
        image = type_config.docker_image if type_config else "vco-agent:latest"
        project = global_deps.get("project_name", "")
        return {"docker_image": image, "project_name": project}
    return {}


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
    transport: AgentTransport | None = None,
    transport_deps: dict | None = None,
    project_dir: Path | None = None,
    project_session_name: str | None = None,
) -> AgentContainer:
    """Create the correct AgentContainer subclass for a ChildSpec.

    Transport resolution (per D-07):
    1. If ``transport`` is provided, use it directly (override/testing).
    2. Otherwise, read ``spec.transport`` (defaults to "local"),
       look up the class in _TRANSPORT_REGISTRY, and instantiate with
       transport_deps. New transports = add one line to _TRANSPORT_REGISTRY.

    Args:
        spec: Child specification with agent_type and context.
        data_dir: Root directory for container persistent data.
        comm_port: Optional communication port.
        on_state_change: Optional callback for state transitions.
        transport: Optional pre-built transport (overrides registry lookup).
        transport_deps: Dict of construction kwargs for transport instantiation.
                        For LocalTransport: {"tmux_manager": tmux_manager_instance}.
        project_dir: Optional project directory for clone/prompt paths.
        project_session_name: Optional tmux session name for the project.

    Returns:
        An AgentContainer instance (or subclass thereof).
    """
    if transport is None:
        # D-07 + D-01: Look up transport from spec, resolve per-transport deps via config
        transport_name = spec.transport
        transport_cls = _TRANSPORT_REGISTRY.get(transport_name)
        if transport_cls is not None:
            type_config = None
            if _agent_types_config is not None:
                try:
                    type_config = _agent_types_config.get_type(spec.agent_type)
                except KeyError:
                    pass
            deps = _resolve_transport_deps(transport_name, transport_deps or {}, type_config)
            transport = transport_cls(**deps)

    cls = _REGISTRY.get(spec.agent_type, AgentContainer)
    return cls.from_spec(
        spec,
        data_dir=data_dir,
        comm_port=comm_port,
        on_state_change=on_state_change,
        transport=transport,
        project_dir=project_dir,
        project_session_name=project_session_name,
    )


def register_defaults() -> None:
    """Register all built-in agent types. Call once at startup.

    Uses lazy imports to avoid circular dependencies. Idempotent --
    safe to call multiple times.
    """
    from vcompany.agent.company_agent import CompanyAgent
    from vcompany.agent.continuous_agent import ContinuousAgent
    from vcompany.agent.fulltime_agent import FulltimeAgent
    from vcompany.agent.gsd_agent import GsdAgent
    from vcompany.agent.task_agent import TaskAgent

    register_agent_type("gsd", GsdAgent)
    register_agent_type("continuous", ContinuousAgent)
    register_agent_type("fulltime", FulltimeAgent)
    register_agent_type("company", CompanyAgent)
    register_agent_type("task", TaskAgent)


def get_registry() -> dict[str, type[AgentContainer]]:
    """Return a copy of the current registry for inspection/testing."""
    return dict(_REGISTRY)
