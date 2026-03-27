"""Agent module — agent types and supporting models."""

from vcompany.agent.company_agent import CompanyAgent
from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle
from vcompany.agent.fulltime_agent import FulltimeAgent
from vcompany.agent.gsd_agent import GsdAgent
from vcompany.agent.gsd_lifecycle import GsdLifecycle
from vcompany.agent.gsd_phases import CheckpointData, GsdPhase

__all__ = [
    "CompanyAgent",
    "EventDrivenLifecycle",
    "FulltimeAgent",
    "GsdAgent",
    "GsdLifecycle",
    "GsdPhase",
    "CheckpointData",
]
