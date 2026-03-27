"""Supervision tree -- Erlang-style restart strategies for agent containers."""

from vcompany.supervisor.company_root import CompanyRoot
from vcompany.supervisor.project_supervisor import ProjectSupervisor
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
