"""Supervision tree -- Erlang-style restart strategies for agent containers."""

from vcompany.supervisor.restart_tracker import RestartTracker
from vcompany.supervisor.strategies import RestartStrategy
from vcompany.supervisor.supervisor import Supervisor

__all__ = [
    "CompanyRoot",
    "ProjectSupervisor",
    "RestartStrategy",
    "RestartTracker",
    "Supervisor",
]


def __getattr__(name: str):  # noqa: N807
    """Lazy imports to avoid circular dependency with daemon.agent_handle."""
    if name == "CompanyRoot":
        from vcompany.supervisor.company_root import CompanyRoot
        return CompanyRoot
    if name == "ProjectSupervisor":
        from vcompany.supervisor.project_supervisor import ProjectSupervisor
        return ProjectSupervisor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
