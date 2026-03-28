"""Shared workflow stage types and signal detection utilities.

Extracted from vcompany.orchestrator.workflow_orchestrator during v1->v2 migration
(MIGR-03). These types are used by WorkflowOrchestratorCog and its tests after
the v1 module was deleted.
"""

from __future__ import annotations

import re
from enum import Enum


class WorkflowStage(str, Enum):
    """Stages in the per-agent GSD workflow state machine."""

    IDLE = "idle"
    DISCUSS = "discuss"
    DISCUSSION_GATE = "discussion_gate"
    PLAN = "plan"
    PM_PLAN_REVIEW_GATE = "pm_plan_review_gate"
    EXECUTE = "execute"
    VERIFY = "verify"
    VERIFY_GATE = "verify_gate"
    PHASE_COMPLETE = "phase_complete"


# -- Signal detection patterns --

STAGE_COMPLETE_PATTERNS: dict[str, re.Pattern[str]] = {
    "discuss": re.compile(r"discuss-phase complete", re.IGNORECASE),
    "plan": re.compile(r"plan-phase complete", re.IGNORECASE),
    "execute": re.compile(r"execute-phase complete", re.IGNORECASE),
    "research": re.compile(r"research-phase complete", re.IGNORECASE),
}

# Extracts agent_id from vco report format: "{timestamp} {agent_id}: {status_text}"
AGENT_ID_PATTERN = re.compile(r"^\S+\s+(\S+):\s+(.+)$")


def detect_stage_signal(message_content: str) -> tuple[str, str] | None:
    """Parse a vco report message and detect stage completion signals.

    Args:
        message_content: Raw message content from Discord / vco report.

    Returns:
        Tuple of (agent_id, stage_name) if a completion signal is found,
        None otherwise.
    """
    match = AGENT_ID_PATTERN.match(message_content)
    if not match:
        return None

    agent_id = match.group(1)
    status_text = match.group(2)

    for stage_name, pattern in STAGE_COMPLETE_PATTERNS.items():
        if pattern.search(status_text):
            return (agent_id, stage_name)

    return None
