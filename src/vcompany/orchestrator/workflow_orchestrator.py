"""Per-agent workflow state machine driving GSD stages with gate transitions.

The WorkflowOrchestrator owns all stage transitions for each agent independently.
GSD runs each stage and stops; the orchestrator decides what to send next based
on gate reviews and completion signals from vco report messages.

Stage flow per agent:
  IDLE -> DISCUSS -> DISCUSSION_GATE -> PLAN -> PM_PLAN_REVIEW_GATE
       -> EXECUTE -> VERIFY -> VERIFY_GATE -> PHASE_COMPLETE

D-07: Execute transitions to VERIFY (not PHASE_COMPLETE). VERIFY_GATE
requires PM approval before advancing to PHASE_COMPLETE.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger("vcompany.orchestrator.workflow")


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


@dataclass
class AgentWorkflowState:
    """Tracks the current workflow state for a single agent."""

    agent_id: str
    current_phase: int = 0
    stage: WorkflowStage = WorkflowStage.IDLE
    stage_started_at: float = 0.0
    blocked_since: float | None = None
    blocked_reason: str = ""


# ── Signal detection patterns ──────────────────────────────────────────────

STAGE_COMPLETE_PATTERNS: dict[str, re.Pattern] = {
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


# ── Stage transition maps ──────────────────────────────────────────────────

# on_stage_complete: which gate to transition to after a stage finishes
_STAGE_TO_GATE: dict[str, WorkflowStage] = {
    "discuss": WorkflowStage.DISCUSSION_GATE,
    "plan": WorkflowStage.PM_PLAN_REVIEW_GATE,
    "execute": WorkflowStage.VERIFY,  # D-07: NOT PHASE_COMPLETE
    "research": WorkflowStage.DISCUSSION_GATE,  # research flows back to discuss gate
}

# advance_from_gate when approved: (next_stage, command_template or None)
_GATE_APPROVED: dict[WorkflowStage, tuple[WorkflowStage, str | None]] = {
    WorkflowStage.DISCUSSION_GATE: (WorkflowStage.PLAN, "/gsd:plan-phase {phase}"),
    WorkflowStage.PM_PLAN_REVIEW_GATE: (WorkflowStage.EXECUTE, "/gsd:execute-phase {phase}"),
    WorkflowStage.VERIFY_GATE: (WorkflowStage.PHASE_COMPLETE, None),
}

# advance_from_gate when rejected: (next_stage, command_template)
_GATE_REJECTED: dict[WorkflowStage, tuple[WorkflowStage, str]] = {
    WorkflowStage.DISCUSSION_GATE: (WorkflowStage.DISCUSS, "/gsd:discuss-phase {phase}"),
    WorkflowStage.PM_PLAN_REVIEW_GATE: (WorkflowStage.PLAN, "/gsd:plan-phase {phase}"),
    WorkflowStage.VERIFY_GATE: (WorkflowStage.EXECUTE, "/gsd:execute-phase {phase}"),
}


class WorkflowOrchestrator:
    """Drives per-agent state machines through GSD stages with gate transitions.

    Separate from MonitorLoop (D-01). Monitor handles liveness/alerts,
    orchestrator handles the state machine and gate transitions.
    """

    def __init__(
        self,
        project_dir: Path,
        config: object,
        agent_manager: object,
    ) -> None:
        self._project_dir = Path(project_dir)
        self._config = config
        self._agent_manager = agent_manager
        self._agent_states: dict[str, AgentWorkflowState] = {}

    def start_agent(self, agent_id: str, phase: int) -> bool:
        """Initialize an agent's workflow and send the first discuss command.

        Args:
            agent_id: Agent identifier.
            phase: Phase number to start.

        Returns:
            True if the command was sent successfully.
        """
        state = AgentWorkflowState(
            agent_id=agent_id,
            current_phase=phase,
            stage=WorkflowStage.DISCUSS,
            stage_started_at=time.monotonic(),
        )
        self._agent_states[agent_id] = state

        command = f"/gsd:discuss-phase {phase}"
        result = self._agent_manager.send_work_command(
            agent_id, command, wait_for_ready=True
        )
        logger.info(
            "Started agent %s on phase %d (sent=%s)", agent_id, phase, result
        )
        return result

    def on_stage_complete(self, agent_id: str, stage: str) -> WorkflowStage:
        """Handle a stage completion signal for an agent.

        Transitions the agent to the appropriate gate or next stage.

        Args:
            agent_id: Agent that completed the stage.
            stage: Name of the completed stage (discuss, plan, execute).

        Returns:
            The new WorkflowStage after transition.
        """
        state = self._agent_states.get(agent_id)
        if state is None:
            logger.warning(
                "on_stage_complete for unknown agent %s, creating state", agent_id
            )
            state = AgentWorkflowState(agent_id=agent_id)
            self._agent_states[agent_id] = state

        new_stage = _STAGE_TO_GATE.get(stage, WorkflowStage.IDLE)
        state.stage = new_stage
        state.stage_started_at = time.monotonic()
        state.blocked_since = None
        state.blocked_reason = ""

        logger.info(
            "Agent %s completed '%s' -> %s", agent_id, stage, new_stage.value
        )
        return new_stage

    def advance_from_gate(self, agent_id: str, approved: bool) -> bool:
        """Advance an agent past a gate checkpoint.

        If approved, sends the next GSD command and transitions forward.
        If rejected, re-sends the previous stage command.

        Args:
            agent_id: Agent at the gate.
            approved: True to advance, False to reject and redo.

        Returns:
            True if the transition succeeded (command sent or no command needed).
        """
        state = self._agent_states.get(agent_id)
        if state is None:
            logger.error("advance_from_gate for unknown agent %s", agent_id)
            return False

        current_gate = state.stage
        phase = state.current_phase

        if approved:
            transition = _GATE_APPROVED.get(current_gate)
            if transition is None:
                logger.error(
                    "Agent %s at %s is not at a gate", agent_id, current_gate.value
                )
                return False

            next_stage, cmd_template = transition
            state.stage = next_stage
            state.stage_started_at = time.monotonic()

            if cmd_template is not None:
                command = cmd_template.format(phase=phase)
                result = self._agent_manager.send_work_command(
                    agent_id, command, wait_for_ready=True
                )
                logger.info(
                    "Agent %s approved at %s -> %s (cmd=%s, sent=%s)",
                    agent_id, current_gate.value, next_stage.value, command, result,
                )
                return result
            else:
                # No command needed (e.g., VERIFY_GATE -> PHASE_COMPLETE)
                logger.info(
                    "Agent %s approved at %s -> %s (no command)",
                    agent_id, current_gate.value, next_stage.value,
                )
                return True
        else:
            transition = _GATE_REJECTED.get(current_gate)
            if transition is None:
                logger.error(
                    "Agent %s at %s is not at a rejectable gate",
                    agent_id, current_gate.value,
                )
                return False

            next_stage, cmd_template = transition
            state.stage = next_stage
            state.stage_started_at = time.monotonic()

            command = cmd_template.format(phase=phase)
            result = self._agent_manager.send_work_command(
                agent_id, command, wait_for_ready=True
            )
            logger.info(
                "Agent %s rejected at %s -> %s (cmd=%s, sent=%s)",
                agent_id, current_gate.value, next_stage.value, command, result,
            )
            return result

    def get_agent_state(self, agent_id: str) -> AgentWorkflowState | None:
        """Return the current workflow state for an agent, or None if unknown."""
        return self._agent_states.get(agent_id)

    def get_all_states(self) -> dict[str, AgentWorkflowState]:
        """Return all agent workflow states."""
        return dict(self._agent_states)

    def recover_from_state(self, agent_id: str, clone_dir: Path) -> WorkflowStage:
        """Recover an agent's workflow stage by reading its clone's STATE.md.

        Parses the stopped_at and status fields from the agent's GSD state
        to determine where to resume.

        Args:
            agent_id: Agent to recover.
            clone_dir: Path to the agent's clone directory.

        Returns:
            The recovered WorkflowStage.
        """
        state_path = clone_dir / ".planning" / "STATE.md"
        state = self._agent_states.get(agent_id)
        if state is None:
            state = AgentWorkflowState(agent_id=agent_id)
            self._agent_states[agent_id] = state

        if not state_path.exists():
            logger.warning(
                "No STATE.md found for %s at %s, defaulting to IDLE",
                agent_id, state_path,
            )
            state.stage = WorkflowStage.IDLE
            return WorkflowStage.IDLE

        content = state_path.read_text().lower()

        # Map keywords in STATE.md to workflow stages
        if "verified" in content:
            recovered = WorkflowStage.VERIFY_GATE
        elif "executing" in content:
            recovered = WorkflowStage.EXECUTE
        elif "planned" in content:
            recovered = WorkflowStage.PM_PLAN_REVIEW_GATE
        elif "context gathered" in content:
            recovered = WorkflowStage.DISCUSSION_GATE
        else:
            recovered = WorkflowStage.IDLE

        state.stage = recovered
        state.stage_started_at = time.monotonic()
        logger.info(
            "Recovered agent %s from STATE.md -> %s", agent_id, recovered.value
        )
        return recovered

    def handle_unknown_prompt(self, agent_id: str, prompt_text: str) -> str:
        """Mark an agent as blocked on an unknown prompt.

        Sets blocked_since and blocked_reason on the agent state, and
        returns an alert message for Discord.

        Args:
            agent_id: Agent encountering the unknown prompt.
            prompt_text: The prompt text that was unrecognized.

        Returns:
            Alert message string.
        """
        state = self._agent_states.get(agent_id)
        if state is None:
            state = AgentWorkflowState(agent_id=agent_id)
            self._agent_states[agent_id] = state

        state.blocked_since = time.monotonic()
        state.blocked_reason = prompt_text[:200]

        msg = f"Agent {agent_id} blocked on unknown prompt: {prompt_text[:100]}"
        logger.warning(msg)
        return msg

    def check_blocked_agents(self, timeout: float = 600.0) -> list[AgentWorkflowState]:
        """Return agents that have been blocked longer than the timeout.

        Args:
            timeout: Seconds after which a blocked agent is considered timed out.
                     Default 600s (10 minutes) per D-16.

        Returns:
            List of AgentWorkflowState for agents blocked beyond timeout.
        """
        now = time.monotonic()
        blocked = []
        for state in self._agent_states.values():
            if state.blocked_since is not None:
                if (now - state.blocked_since) > timeout:
                    blocked.append(state)
        return blocked
