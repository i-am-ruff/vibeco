"""Pydantic v2 models for per-agent monitor state and check results.

AgentMonitorState tracks persistent state between monitor cycles.
CheckResult captures the outcome of a single check function.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CheckResult(BaseModel):
    """Result of a single monitor check."""

    check_type: Literal["liveness", "stuck", "plan_gate"]
    agent_id: str
    passed: bool
    detail: str = ""
    new_plans: list[str] = []


class AgentMonitorState(BaseModel):
    """Per-agent state tracked between monitor cycles."""

    agent_id: str
    last_commit_time: datetime | None = None
    last_plan_mtimes: dict[str, float] = {}
    current_phase: str = "unknown"
    phase_status: str = "unknown"
    # Phase 5: Plan gate tracking (D-13, D-14)
    plan_gate_status: Literal["idle", "awaiting_review", "approved", "rejected"] = "idle"
    pending_plans: list[str] = []    # plan paths awaiting review
    approved_plans: list[str] = []   # plan paths approved this phase
    # Phase 7: Integration interlock (D-01, D-02)
    integration_pending: bool = False
    # Phase 7: Checkin auto-trigger (D-09)
    checkin_sent: bool = False
