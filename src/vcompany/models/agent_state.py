"""Pydantic v2 models for agent runtime state and crash logs.

AgentEntry and AgentsRegistry define the schema for agents.json -- the runtime
state of all dispatched agents. CrashRecord and CrashLog define the schema for
crash_log.json -- persistent crash history used by the circuit breaker.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AgentEntry(BaseModel):
    """Runtime state for a single dispatched agent."""

    agent_id: str
    pane_id: str
    pid: int | None = None
    session_name: str
    status: Literal["starting", "running", "stopped", "crashed", "circuit_open"]
    launched_at: datetime
    last_crash: datetime | None = None


class AgentsRegistry(BaseModel):
    """Registry of all dispatched agents (serialized to agents.json)."""

    project: str
    agents: dict[str, AgentEntry] = {}


class CrashRecord(BaseModel):
    """Single crash event record."""

    agent_id: str
    timestamp: datetime
    exit_code: int
    classification: str
    pane_output: list[str] = []


class CrashLog(BaseModel):
    """Persistent crash history (serialized to crash_log.json)."""

    project: str
    records: list[CrashRecord] = []
