"""ChildSpec model and ChildSpecRegistry (CONT-05).

ChildSpec declares a container type with its configuration and restart policy.
ChildSpecRegistry stores specs for supervisor consumption — supervisors read
specs to instantiate and manage containers.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from vcompany.container.context import ContainerContext


class RestartPolicy(str, Enum):
    """Erlang-style restart policies for supervised containers.

    PERMANENT: Always restart, regardless of exit reason.
    TEMPORARY: Never restart, regardless of exit reason.
    TRANSIENT: Restart only on abnormal exit (error/crash).
    """

    PERMANENT = "permanent"
    TEMPORARY = "temporary"
    TRANSIENT = "transient"


class ChildSpec(BaseModel):
    """Specification for a child container in the supervision tree.

    Supervisors use ChildSpec to know how to create, configure, and manage
    the restart behavior of each child container.
    """

    child_id: str
    agent_type: str
    context: ContainerContext
    restart_policy: RestartPolicy = RestartPolicy.PERMANENT
    max_restarts: int = 3
    restart_window_seconds: int = 600
    transport: str = "local"


class ChildSpecRegistry:
    """Registry of child specifications for supervisor consumption.

    Plain class (not Pydantic) that stores ChildSpec instances keyed by
    child_id. Supervisors query this registry to get specs for spawning
    and managing containers.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ChildSpec] = {}

    def register(self, spec: ChildSpec) -> None:
        """Register a child spec (overwrites if child_id already exists)."""
        self._specs[spec.child_id] = spec

    def unregister(self, child_id: str) -> None:
        """Remove a child spec by ID. No-op if not found."""
        self._specs.pop(child_id, None)

    def get(self, child_id: str) -> ChildSpec | None:
        """Get a child spec by ID. Returns None if not found."""
        return self._specs.get(child_id)

    def all_specs(self) -> list[ChildSpec]:
        """Return all registered child specs."""
        return list(self._specs.values())
