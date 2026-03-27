"""AgentContainer — central abstraction wrapping every agent in v2.

Composes lifecycle FSM, context, memory store, health reporting, and
communication port into a single managed unit. Supervisors (Phase 2) manage
AgentContainers. Agent types (Phase 3/4) subclass them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport
from vcompany.container.memory_store import MemoryStore
from vcompany.container.state_machine import ContainerLifecycle

if TYPE_CHECKING:
    from vcompany.container.child_spec import ChildSpec
    from vcompany.container.communication import CommunicationPort


class AgentContainer:
    """Lifecycle-managed container for a single agent.

    Wraps the FSM, context, memory store, health reporting, and communication
    port. Created directly or via ``from_spec()`` factory.

    Args:
        context: Immutable agent metadata.
        data_dir: Root directory for persistent data (memory DB lives under
            ``data_dir / agent_id / memory.db``).
        comm_port: Optional communication channel to other containers.
        on_state_change: Optional callback invoked with a HealthReport after
            every lifecycle transition.
    """

    def __init__(
        self,
        context: ContainerContext,
        data_dir: Path,
        comm_port: CommunicationPort | None = None,
        on_state_change: Callable[[HealthReport], None] | None = None,
    ) -> None:
        self.context = context
        # _fsm_state is written by python-statemachine via state_field param
        self._fsm_state: str | None = None
        self._lifecycle = ContainerLifecycle(model=self, state_field="_fsm_state")
        self.memory = MemoryStore(data_dir / context.agent_id / "memory.db")
        self.comm_port = comm_port
        self._on_state_change_cb = on_state_change
        self._created_at = datetime.now(timezone.utc)
        self._error_count: int = 0
        self._last_activity = self._created_at

    # --- Properties ---

    @property
    def state(self) -> str:
        """Current lifecycle state as a string."""
        return str(self._fsm_state)

    @property
    def inner_state(self) -> str | None:
        """Agent-type-specific sub-state. Overridden by subclasses."""
        return None

    # --- Health ---

    def health_report(self) -> HealthReport:
        """Generate a health snapshot for this container."""
        now = datetime.now(timezone.utc)
        return HealthReport(
            agent_id=self.context.agent_id,
            state=self.state,
            inner_state=self.inner_state,
            uptime=(now - self._created_at).total_seconds(),
            last_heartbeat=now,
            error_count=self._error_count,
            last_activity=self._last_activity,
        )

    def _on_state_change(self) -> None:
        """Called by the FSM after_transition hook."""
        self._last_activity = datetime.now(timezone.utc)
        if self._on_state_change_cb is not None:
            self._on_state_change_cb(self.health_report())

    # --- Lifecycle Methods ---

    async def start(self) -> None:
        """Transition to running and open memory store."""
        self._lifecycle.start()
        await self.memory.open()

    async def sleep(self) -> None:
        """Transition to sleeping."""
        self._lifecycle.sleep()

    async def wake(self) -> None:
        """Transition from sleeping to running."""
        self._lifecycle.wake()

    async def error(self) -> None:
        """Transition to errored, incrementing the error count."""
        self._error_count += 1
        self._lifecycle.error()

    async def recover(self) -> None:
        """Transition from errored to running."""
        self._lifecycle.recover()

    async def stop(self) -> None:
        """Transition to stopped and close memory store."""
        self._lifecycle.stop()
        await self.memory.close()

    async def destroy(self) -> None:
        """Transition to destroyed and close memory store."""
        self._lifecycle.destroy()
        await self.memory.close()

    async def send_event(self, name: str) -> None:
        """String-based event dispatch for supervisor use."""
        self._lifecycle.send(name)

    # --- Factory ---

    @classmethod
    def from_spec(
        cls,
        spec: ChildSpec,
        data_dir: Path,
        comm_port: CommunicationPort | None = None,
        on_state_change: Callable[[HealthReport], None] | None = None,
    ) -> AgentContainer:
        """Create an AgentContainer from a ChildSpec."""
        return cls(
            context=spec.context,
            data_dir=data_dir,
            comm_port=comm_port,
            on_state_change=on_state_change,
        )
