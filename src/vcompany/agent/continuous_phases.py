"""CyclePhase enum and CycleCheckpointData model for ContinuousAgent lifecycle.

CyclePhase defines the 6 cycle sub-states inside the compound running state
of ContinuousLifecycle. CycleCheckpointData is the Pydantic model serialized
to MemoryStore on each cycle transition for crash recovery.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class CyclePhase(str, Enum):
    """Continuous agent cycle sub-states inside the running compound state."""

    WAKE = "wake"
    GATHER = "gather"
    ANALYZE = "analyze"
    ACT = "act"
    REPORT = "report"
    SLEEP_PREP = "sleep_prep"


class CycleCheckpointData(BaseModel):
    """Serializable checkpoint for continuous cycle state persistence.

    Fields:
        configuration: Serialized FSM configuration_values (e.g. ["running", "gather"]).
        cycle_phase: Current inner cycle phase name (e.g. "gather").
        cycle_count: Number of completed cycles.
        timestamp: UTC ISO timestamp of checkpoint.
    """

    configuration: list[str]
    cycle_phase: str
    cycle_count: int
    timestamp: str
