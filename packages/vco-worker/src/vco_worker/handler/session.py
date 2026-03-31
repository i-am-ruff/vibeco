"""GsdSessionHandler -- SessionHandler implementation for worker-side GSD agents.

Adapted from daemon-side src/vcompany/handler/session.py. Key changes:
- MessageContext replaced with InboundMessage (channel protocol)
- container._send_discord() replaced with container.send_report()
- All imports from vco_worker, not vcompany
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from statemachine.orderedset import OrderedSet

from vco_worker.agent.gsd_phases import CheckpointData

if TYPE_CHECKING:
    from vco_worker.channel.messages import InboundMessage
    from vco_worker.container.container import WorkerContainer

logger = logging.getLogger("vco_worker.handler.session")

# Valid FSM state names for checkpoint validation
_VALID_STATES = frozenset({
    "creating", "running", "idle", "discuss", "plan",
    "execute", "uat", "ship", "sleeping", "errored",
    "stopped", "destroyed", "blocked", "stopping",
})

# Maps restored inner phase to the GSD command that should resume work.
_PHASE_RESUME_COMMANDS: dict[str, str] = {
    "discuss": "/gsd:discuss-phase 1",
    "plan": "/gsd:plan-phase 1",
    "execute": "/gsd:execute-phase 1",
    "uat": "/gsd:verify-work",
    "ship": "/gsd:ship",
}


class GsdSessionHandler:
    """SessionHandler implementation for GSD agents in worker context.

    Handles review gates, task assignments, checkpoint/restore, and
    phase-aware GSD command resolution. All communication through
    channel protocol messages (InboundMessage in, ReportMessage out).
    """

    def __init__(self) -> None:
        self._checkpoint_lock = asyncio.Lock()

    async def handle_message(self, container: WorkerContainer, message: InboundMessage) -> None:
        """Process an inbound message routed to a GSD agent.

        Handles:
        - [Review Decision] -- resolve pending review gate with decision
        - [Task Assigned] -- store task details and persist to memory
        - Otherwise: log as informational

        Args:
            container: The WorkerContainer this handler is attached to.
            message: Inbound message from head via channel protocol.
        """
        content = message.content

        if content.startswith("[Review Decision]"):
            # Format: "[Review Decision] {decision}" (approve/reject/modify/clarify)
            decision = content.replace("[Review Decision]", "").strip().split()[0].lower()
            if container._pending_review is not None and not container._pending_review.done():
                container._pending_review.set_result(decision)
                logger.info(
                    "Agent %s received review decision: %s",
                    container.context.agent_id, decision,
                )
            else:
                logger.warning(
                    "Agent %s received review decision but no pending review: %s",
                    container.context.agent_id, decision,
                )

        elif content.startswith("[Task Assigned]"):
            # Format: "[Task Assigned] @{agent_id}: {title} (item: {item_id})"
            assignment: dict[str, object] = {
                "raw": content,
                "assigned_at": datetime.now(timezone.utc).isoformat(),
            }
            # Parse item_id if present
            if "(item: " in content:
                item_id = content.split("(item: ")[1].rstrip(")")
                assignment["item_id"] = item_id
            container._current_assignment = assignment
            await container.memory.set("current_assignment", json.dumps(assignment))
            logger.info(
                "Agent %s received task assignment: %.100s",
                container.context.agent_id, content,
            )

        else:
            # Check if this is a PM review response
            is_pm_review = message.sender == "pm" or message.channel.startswith("review-")
            if is_pm_review:
                logger.info(
                    "Agent %s received PM review message from %s: %.100s",
                    container.context.agent_id, message.sender, content,
                )
            else:
                logger.info(
                    "Agent %s received message from %s: %.100s",
                    container.context.agent_id, message.sender, content,
                )

    async def on_start(self, container: WorkerContainer) -> None:
        """Handler start hook -- restore checkpoint and resolve GSD command.

        Called AFTER memory.open() but BEFORE transport launch so that the
        correct phase-appropriate GSD command is used on restart.
        """
        # 1. Restore checkpoint to know what phase we're in
        await self._restore_from_checkpoint(container)

        # 2. Update gsd_command based on restored phase (phase-aware restart)
        container.context.gsd_command = self._resolve_gsd_command(container)

        # 3. Restore assignment context from own MemoryStore
        raw = await container.memory.get("current_assignment")
        if raw is not None:
            try:
                container._current_assignment = json.loads(raw)
                logger.info(
                    "Restored assignment for %s: item_id=%s",
                    container.context.agent_id,
                    container._current_assignment.get("item_id", "unknown"),
                )
            except (json.JSONDecodeError, AttributeError):
                logger.warning(
                    "Failed to parse stored assignment for %s",
                    container.context.agent_id,
                )

    async def on_stop(self, container: WorkerContainer) -> None:
        """Checkpoint current phase state before teardown."""
        await self._checkpoint_phase(container)

    # --- Private helpers ---

    async def _restore_from_checkpoint(self, container: WorkerContainer) -> None:
        """Restore FSM state from the latest checkpoint if one exists."""
        try:
            data = await container.memory.get_latest_checkpoint("gsd_phase")
            if data is None:
                return

            checkpoint = CheckpointData.model_validate_json(data)

            # Validate all state names
            for state_name in checkpoint.configuration:
                if state_name not in _VALID_STATES:
                    logger.warning(
                        "Invalid state '%s' in checkpoint for %s, falling back to idle",
                        state_name,
                        container.context.agent_id,
                    )
                    return

            # Restore the FSM configuration
            container._lifecycle.current_state_value = OrderedSet(checkpoint.configuration)
            # Also update the model's _fsm_state to match
            container._fsm_state = OrderedSet(checkpoint.configuration)

            logger.info(
                "Restored %s to phase %s from checkpoint",
                container.context.agent_id,
                checkpoint.phase,
            )
            if checkpoint.phase not in ("idle", "stopped", "errored"):
                logger.warning(
                    "Agent %s restored to phase '%s' -- a pending review request may need "
                    "to be reposted.",
                    container.context.agent_id,
                    checkpoint.phase,
                )
        except Exception:
            logger.warning(
                "Failed to restore checkpoint for %s, falling back to idle",
                container.context.agent_id,
                exc_info=True,
            )

    def _resolve_gsd_command(self, container: WorkerContainer) -> str | None:
        """Determine the correct GSD command based on restored phase."""
        phase = container.inner_state
        if phase and phase in _PHASE_RESUME_COMMANDS:
            cmd = _PHASE_RESUME_COMMANDS[phase]
            logger.info(
                "Resolved GSD command for %s based on restored phase '%s': %s",
                container.context.agent_id, phase, cmd,
            )
            return cmd
        # Fresh start or idle -- use the original command from context
        return container.context.gsd_command

    async def _checkpoint_phase(self, container: WorkerContainer) -> None:
        """Write current phase state to memory_store checkpoint."""
        async with self._checkpoint_lock:
            config_values = container._lifecycle.current_state_value
            if isinstance(config_values, OrderedSet):
                configuration = list(config_values)
            else:
                configuration = [str(config_values)]
            checkpoint = CheckpointData(
                configuration=configuration,
                phase=container.inner_state or "idle",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await container.memory.checkpoint("gsd_phase", checkpoint.model_dump_json())
            await container.memory.set("current_phase", container.inner_state or "idle")
