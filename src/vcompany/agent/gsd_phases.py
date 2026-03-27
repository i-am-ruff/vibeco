"""GsdPhase enum and CheckpointData model for the GSD agent lifecycle.

GsdPhase defines the 6 phase sub-states that exist inside the compound
running state of GsdLifecycle. CheckpointData is the Pydantic model
serialized to MemoryStore on each phase transition for crash recovery.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class GsdPhase(str, Enum):
    """GSD workflow phase sub-states inside the running compound state."""

    IDLE = "idle"
    DISCUSS = "discuss"
    PLAN = "plan"
    EXECUTE = "execute"
    UAT = "uat"
    SHIP = "ship"


class CheckpointData(BaseModel):
    """Serializable checkpoint for GSD phase state persistence.

    Fields:
        configuration: Serialized FSM configuration_values (e.g. ["running", "plan"]).
        phase: Current inner phase name (e.g. "plan").
        timestamp: UTC ISO timestamp of checkpoint.
    """

    configuration: list[str]
    phase: str
    timestamp: str
