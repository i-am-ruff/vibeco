"""GsdAgent — AgentContainer subclass with internal phase FSM (TYPE-01, TYPE-02).

GsdAgent owns its own phase state internally via GsdLifecycle's compound
running state. Phase transitions checkpoint to memory_store for crash
recovery. Absorbs WorkflowOrchestrator state-tracking responsibilities
(blocked tracking, phase number).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable

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
    "stopped", "destroyed",
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
    ) -> None:
        super().__init__(context, data_dir, comm_port, on_state_change)
        # Override the parent's ContainerLifecycle with GsdLifecycle
        self._lifecycle = GsdLifecycle(model=self, state_field="_fsm_state")
        self._checkpoint_lock = asyncio.Lock()
        # Blocked tracking (absorbs WorkflowOrchestrator.handle_unknown_prompt)
        self._blocked_since: float | None = None
        self._blocked_reason: str = ""

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

    async def advance_phase(self, phase: str) -> None:
        """Transition to the next GSD phase and checkpoint.

        Args:
            phase: Target phase name (discuss, plan, execute, uat, ship).

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
        method()
        await self._checkpoint_phase()

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
        """Whether the agent is currently blocked."""
        return self._blocked_since is not None

    def mark_blocked(self, reason: str) -> None:
        """Mark agent as blocked with a reason (truncated to 200 chars)."""
        self._blocked_since = time.monotonic()
        self._blocked_reason = reason[:200]

    def clear_blocked(self) -> None:
        """Clear blocked state."""
        self._blocked_since = None
        self._blocked_reason = ""

    async def get_phase_number(self) -> int | None:
        """Read phase number from memory_store KV."""
        val = await self.memory.get("phase_number")
        return int(val) if val is not None else None

    async def set_phase_number(self, phase: int) -> None:
        """Write phase number to memory_store KV."""
        await self.memory.set("phase_number", str(phase))
