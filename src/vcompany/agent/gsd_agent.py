"""GsdAgent — AgentContainer subclass with internal phase FSM (TYPE-01, TYPE-02).

GsdAgent owns its own phase state internally via GsdLifecycle's compound
running state. Phase transitions checkpoint to memory_store for crash
recovery. Absorbs WorkflowOrchestrator state-tracking responsibilities
(blocked tracking, phase number).

Extended with assignment methods: reads assignments from own MemoryStore,
produces completion/failure events for PM consumption.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from statemachine.orderedset import OrderedSet

from vcompany.agent.gsd_lifecycle import GsdLifecycle
from vcompany.agent.gsd_phases import CheckpointData
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport

if TYPE_CHECKING:
    from vcompany.container.communication import CommunicationPort

logger = logging.getLogger("vcompany.agent.gsd_agent")

# Valid FSM state names for checkpoint validation
_VALID_STATES = frozenset({
    "creating", "running", "idle", "discuss", "plan",
    "execute", "uat", "ship", "sleeping", "errored",
    "stopped", "destroyed", "blocked", "stopping",
})


class GsdAgent(AgentContainer):
    """Lifecycle-managed container for GSD agents with internal phase FSM.

    Extends AgentContainer by replacing ContainerLifecycle with GsdLifecycle
    (compound running state). Phase transitions are checkpointed to
    memory_store for crash recovery.

    Args:
        context: Immutable agent metadata.
        data_dir: Root directory for persistent data.
        comm_port: Optional communication channel.
        on_state_change: Optional callback invoked with HealthReport after
            every lifecycle transition.
    """

    def __init__(
        self,
        context: ContainerContext,
        data_dir: Path,
        comm_port: CommunicationPort | None = None,
        on_state_change: Callable[[HealthReport], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(context, data_dir, comm_port, on_state_change, **kwargs)
        # Override the parent's ContainerLifecycle with GsdLifecycle
        self._lifecycle = GsdLifecycle(model=self, state_field="_fsm_state")
        self._checkpoint_lock = asyncio.Lock()
        # Note: blocked tracking now uses FSM state (ARCH-03) via parent block()/unblock()
        # PMRT-02: Phase transition callback hook -- wired by VcoBot.on_ready()
        self._on_phase_transition: Callable[[str, str, str], "Awaitable[None]"] | None = None
        # GATE-01: Review gate Future -- blocks advance_phase() until PM decision
        self._pending_review: asyncio.Future[str] | None = None
        self._review_attempts: int = 0
        self._max_review_attempts: int = 3
        # GATE-04: Callback to post review request -- wired by VcoBot.on_ready()
        # Args: agent_id, stage -> None
        self._on_review_request: Callable[[str, str], "Awaitable[None]"] | None = None
        # AGNT-03: In-memory assignment cache -- restored on start()
        self._current_assignment: dict[str, Any] | None = None

    # --- Properties (override parent for compound state handling) ---

    @property
    def state(self) -> str:
        """Current outer lifecycle state as a plain string.

        When in compound state (running), _fsm_state is an OrderedSet like
        OrderedSet(['running', 'idle']). Return just the outer state.
        """
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            return str(list(val)[0])
        return str(val)

    @property
    def inner_state(self) -> str | None:
        """Phase sub-state when in running compound state, None otherwise."""
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            items = list(val)
            if len(items) >= 2:
                return str(items[1])
        return None

    # --- Phase Transition Methods (TYPE-01) ---

    async def advance_phase(self, phase: str) -> str:
        """Transition to the next GSD phase, checkpoint, and await PM gate decision.

        After the phase transition, creates an asyncio.Future and blocks until
        resolve_review() is called by PlanReviewCog. Loops on modify/clarify --
        only "approve" (or reaching max_review_attempts) allows the agent to
        proceed. Returns "approve" in all exit cases.

        Args:
            phase: Target phase name (discuss, plan, execute, uat, ship).

        Returns:
            Gate decision string: always "approve" (either real or auto-approved
            after max_review_attempts).

        Raises:
            ValueError: If phase name is unknown.
        """
        transitions = {
            "discuss": self._lifecycle.start_discuss,
            "plan": self._lifecycle.start_plan,
            "execute": self._lifecycle.start_execute,
            "uat": self._lifecycle.start_uat,
            "ship": self._lifecycle.start_ship,
        }
        method = transitions.get(phase)
        if method is None:
            raise ValueError(f"Unknown phase: {phase}")
        from_phase = self.inner_state or "idle"
        method()
        await self._checkpoint_phase()
        # PMRT-02: Notify PM of phase transition
        if self._on_phase_transition is not None:
            await self._on_phase_transition(self.context.agent_id, from_phase, phase)

        # GATE-01: Loop until PM approves (modify/clarify re-enter the gate)
        loop = asyncio.get_running_loop()
        self._review_attempts = 0
        while True:
            self._pending_review = loop.create_future()
            # Post review request via callback (wired by VcoBot.on_ready)
            if self._on_review_request is not None:
                await self._on_review_request(self.context.agent_id, phase)
            try:
                decision = await self._pending_review
            finally:
                self._pending_review = None

            if decision == "approve":
                return decision

            # modify/clarify: agent receives feedback via tmux (handled by
            # _handle_review_response in PlanReviewCog), then we loop back
            # and re-create the gate to wait for next PM decision.
            self._review_attempts += 1
            if self._review_attempts >= self._max_review_attempts:
                logger.warning(
                    "Agent %s hit max review attempts (%d) for phase %s, auto-approving",
                    self.context.agent_id, self._max_review_attempts, phase,
                )
                return "approve"
            logger.info(
                "Agent %s received '%s' for phase %s (attempt %d/%d), re-entering gate",
                self.context.agent_id, decision, phase,
                self._review_attempts, self._max_review_attempts,
            )

    def resolve_review(self, decision: str) -> bool:
        """Resolve the pending review gate with a PM decision.

        Called by PlanReviewCog when the PM provides approve/modify/clarify.

        Args:
            decision: The gate decision string ("approve", "modify", or "clarify").

        Returns:
            True if a pending gate was resolved, False if no gate was active.
        """
        if self._pending_review is not None and not self._pending_review.done():
            self._pending_review.set_result(decision)
            return True
        return False

    # --- Checkpoint Methods (TYPE-02) ---

    async def _checkpoint_phase(self) -> None:
        """Write current phase state to memory_store checkpoint."""
        async with self._checkpoint_lock:
            config_values = self._lifecycle.current_state_value
            if isinstance(config_values, OrderedSet):
                configuration = list(config_values)
            else:
                configuration = [str(config_values)]
            checkpoint = CheckpointData(
                configuration=configuration,
                phase=self.inner_state or "idle",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await self.memory.checkpoint("gsd_phase", checkpoint.model_dump_json())
            await self.memory.set("current_phase", self.inner_state or "idle")

    async def _restore_from_checkpoint(self) -> None:
        """Restore FSM state from the latest checkpoint if one exists.

        Invalid state names or corrupt JSON fall back to current state
        (running.idle after start()) with a warning.
        """
        try:
            data = await self.memory.get_latest_checkpoint("gsd_phase")
            if data is None:
                return

            checkpoint = CheckpointData.model_validate_json(data)

            # Validate all state names
            for state_name in checkpoint.configuration:
                if state_name not in _VALID_STATES:
                    logger.warning(
                        "Invalid state '%s' in checkpoint for %s, falling back to idle",
                        state_name,
                        self.context.agent_id,
                    )
                    return

            # Restore the FSM configuration
            self._lifecycle.current_state_value = OrderedSet(checkpoint.configuration)
            # Also update the model's _fsm_state to match
            self._fsm_state = OrderedSet(checkpoint.configuration)

            logger.info(
                "Restored %s to phase %s from checkpoint",
                self.context.agent_id,
                checkpoint.phase,
            )
            # GATE-01: Warn if restored to a non-idle phase -- a review may have been
            # pending at crash time. Auto-repost requires Discord wiring (Plan 02).
            if checkpoint.phase not in ("idle", "stopped", "errored"):
                logger.warning(
                    "Agent %s restored to phase '%s' -- a pending review request may need "
                    "to be reposted. Discord wiring required (Plan 02).",
                    self.context.agent_id,
                    checkpoint.phase,
                )
        except Exception:
            logger.warning(
                "Failed to restore checkpoint for %s, falling back to idle",
                self.context.agent_id,
                exc_info=True,
            )

    # --- Lifecycle Overrides ---

    async def start(self) -> None:
        """Transition to running, open memory, and restore from checkpoint."""
        await super().start()
        await self._restore_from_checkpoint()
        # AGNT-03: Restore assignment context from own MemoryStore
        assignment = await self.get_assignment()
        if assignment is not None:
            self._current_assignment = assignment
            logger.info(
                "Restored assignment for %s: item_id=%s",
                self.context.agent_id,
                assignment.get("item_id", "unknown"),
            )

    async def sleep(self) -> None:
        """Transition to sleeping and checkpoint current phase."""
        await self._checkpoint_phase()
        await super().sleep()

    async def error(self) -> None:
        """Transition to errored and checkpoint current phase."""
        await self._checkpoint_phase()
        await super().error()

    # --- State Tracking (absorbs WorkflowOrchestrator) ---

    @property
    def is_blocked(self) -> bool:
        """Whether the agent is currently blocked (ARCH-03: uses FSM state)."""
        return self.state == "blocked"

    def mark_blocked(self, reason: str) -> None:
        """Transition to BLOCKED FSM state with reason (ARCH-03)."""
        self.block(reason)

    def clear_blocked(self) -> None:
        """Clear BLOCKED FSM state (ARCH-03)."""
        self.unblock()

    async def get_phase_number(self) -> int | None:
        """Read phase number from memory_store KV."""
        val = await self.memory.get("phase_number")
        return int(val) if val is not None else None

    async def set_phase_number(self, phase: int) -> None:
        """Write phase number to memory_store KV."""
        await self.memory.set("phase_number", str(phase))

    # --- Assignment Methods (reads from own MemoryStore) ---

    async def get_assignment(self) -> dict[str, Any] | None:
        """Read current assignment from own MemoryStore.

        Returns:
            Parsed assignment dict, or None if no assignment stored.
        """
        raw = await self.memory.get("current_assignment")
        if raw is None:
            return None
        return json.loads(raw)

    async def set_assignment(self, assignment: dict[str, Any]) -> None:
        """Write assignment to own MemoryStore and update in-memory cache.

        Args:
            assignment: Assignment data dict to persist.
        """
        self._current_assignment = assignment
        await self.memory.set("current_assignment", json.dumps(assignment))

    def make_completion_event(self, item_id: str, result: str = "success") -> dict[str, Any]:
        """Create a task_completed event dict for PM consumption.

        Args:
            item_id: The backlog item ID that was completed.
            result: Result description (default "success").

        Returns:
            Event dict ready to post to PM's event queue.
        """
        return {
            "type": "task_completed",
            "agent_id": self.context.agent_id,
            "item_id": item_id,
            "result": result,
        }

    def make_failure_event(self, item_id: str, reason: str = "") -> dict[str, Any]:
        """Create a task_failed event dict for PM consumption.

        Args:
            item_id: The backlog item ID that failed.
            reason: Failure reason description.

        Returns:
            Event dict ready to post to PM's event queue.
        """
        return {
            "type": "task_failed",
            "agent_id": self.context.agent_id,
            "item_id": item_id,
            "reason": reason,
        }
