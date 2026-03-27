"""ContinuousAgent — AgentContainer subclass with cycle FSM (TYPE-03).

ContinuousAgent runs repeating cycles of WAKE->GATHER->ANALYZE->ACT->REPORT->
SLEEP_PREP. Each cycle phase transition is checkpointed to memory_store for
crash recovery. Wake always starts a fresh cycle; crash recovery resumes
mid-cycle via HistoryState.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from statemachine.orderedset import OrderedSet

from vcompany.agent.continuous_lifecycle import ContinuousLifecycle
from vcompany.agent.continuous_phases import CycleCheckpointData
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport

if TYPE_CHECKING:
    from vcompany.container.communication import CommunicationPort

logger = logging.getLogger("vcompany.agent.continuous_agent")

# Valid FSM state names for checkpoint validation
_VALID_STATES = frozenset({
    "creating", "running", "wake", "gather", "analyze",
    "act", "report", "sleep_prep", "sleeping", "errored",
    "stopped", "destroyed",
})


class ContinuousAgent(AgentContainer):
    """Lifecycle-managed container for continuous agents with cycle FSM.

    Extends AgentContainer by replacing ContainerLifecycle with
    ContinuousLifecycle (compound running state with cycle phases).
    Cycle transitions are checkpointed to memory_store for crash recovery.

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
        # Override the parent's ContainerLifecycle with ContinuousLifecycle
        self._lifecycle = ContinuousLifecycle(model=self, state_field="_fsm_state")
        self._checkpoint_lock = asyncio.Lock()
        self._cycle_count: int = 0

    # --- Properties (override parent for compound state handling) ---

    @property
    def state(self) -> str:
        """Current outer lifecycle state as a plain string.

        When in compound state (running), _fsm_state is an OrderedSet like
        OrderedSet(['running', 'wake']). Return just the outer state.
        """
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            return str(list(val)[0])
        return str(val)

    @property
    def inner_state(self) -> str | None:
        """Cycle sub-state when in running compound state, None otherwise."""
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            items = list(val)
            if len(items) >= 2:
                return str(items[1])
        return None

    # --- Cycle Transition Methods (TYPE-03) ---

    async def advance_cycle(self, phase: str) -> None:
        """Transition to the next cycle phase and checkpoint.

        Args:
            phase: Target phase name (gather, analyze, act, report, sleep_prep).

        Raises:
            ValueError: If phase name is unknown.
        """
        transitions = {
            "gather": self._lifecycle.start_gather,
            "analyze": self._lifecycle.start_analyze,
            "act": self._lifecycle.start_act,
            "report": self._lifecycle.start_report,
            "sleep_prep": self._lifecycle.start_sleep_prep,
        }
        method = transitions.get(phase)
        if method is None:
            raise ValueError(f"Unknown cycle phase: {phase}")
        method()
        await self._checkpoint_cycle()

    async def complete_cycle(self) -> None:
        """Increment cycle_count and persist it after a full cycle."""
        self._cycle_count += 1
        await self.memory.set("cycle_count", str(self._cycle_count))

    # --- Checkpoint Methods (TYPE-03) ---

    async def _checkpoint_cycle(self) -> None:
        """Write current cycle phase state to memory_store checkpoint."""
        async with self._checkpoint_lock:
            config_values = self._lifecycle.current_state_value
            if isinstance(config_values, OrderedSet):
                configuration = list(config_values)
            else:
                configuration = [str(config_values)]
            checkpoint = CycleCheckpointData(
                configuration=configuration,
                cycle_phase=self.inner_state or "wake",
                cycle_count=self._cycle_count,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await self.memory.checkpoint("continuous_cycle", checkpoint.model_dump_json())

    async def _restore_from_checkpoint(self) -> None:
        """Restore FSM state from the latest checkpoint if one exists.

        Invalid state names or corrupt JSON fall back to current state
        (running.wake after start()) with a warning.
        """
        try:
            data = await self.memory.get_latest_checkpoint("continuous_cycle")
            if data is None:
                return

            checkpoint = CycleCheckpointData.model_validate_json(data)

            # Validate all state names
            for state_name in checkpoint.configuration:
                if state_name not in _VALID_STATES:
                    logger.warning(
                        "Invalid state '%s' in checkpoint for %s, falling back to wake",
                        state_name,
                        self.context.agent_id,
                    )
                    return

            # Restore the FSM configuration
            self._lifecycle.current_state_value = OrderedSet(checkpoint.configuration)
            # Also update the model's _fsm_state to match
            self._fsm_state = OrderedSet(checkpoint.configuration)

            logger.info(
                "Restored %s to cycle phase %s from checkpoint",
                self.context.agent_id,
                checkpoint.cycle_phase,
            )
        except Exception:
            logger.warning(
                "Failed to restore checkpoint for %s, falling back to wake",
                self.context.agent_id,
                exc_info=True,
            )

    # --- Lifecycle Overrides ---

    async def start(self) -> None:
        """Transition to running, open memory, and restore from checkpoint."""
        await super().start()
        # Restore cycle_count from KV
        count_str = await self.memory.get("cycle_count")
        if count_str is not None:
            self._cycle_count = int(count_str)
        await self._restore_from_checkpoint()

    async def sleep(self) -> None:
        """Checkpoint current phase and transition to sleeping."""
        await self._checkpoint_cycle()
        await super().sleep()

    async def error(self) -> None:
        """Checkpoint current phase and transition to errored."""
        await self._checkpoint_cycle()
        await super().error()
