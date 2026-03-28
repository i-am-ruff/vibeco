"""AgentContainer — central abstraction wrapping every agent in v2.

Composes lifecycle FSM, context, memory store, health reporting, and
communication port into a single managed unit. Supervisors (Phase 2) manage
AgentContainers. Agent types (Phase 3/4) subclass them.
"""

from __future__ import annotations

import asyncio
import os
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
    from vcompany.tmux.session import TmuxManager


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
        tmux_manager: TmuxManager | None = None,
        project_dir: Path | None = None,
        project_session_name: str | None = None,
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
        # Tmux bridge attributes
        self._tmux: TmuxManager | None = tmux_manager
        self._project_dir: Path | None = project_dir
        self._project_session_name: str | None = project_session_name
        self._pane_id: str | None = None
        self._blocked_reason: str | None = None  # ARCH-03

    # --- Properties ---

    @property
    def state(self) -> str:
        """Current lifecycle state as a string."""
        return str(self._fsm_state)

    @property
    def inner_state(self) -> str | None:
        """Agent-type-specific sub-state. Overridden by subclasses."""
        return None

    @property
    def _needs_tmux_session(self) -> bool:
        """True for agent types that run in tmux (gsd, continuous)."""
        return self.context.agent_type in ("gsd", "continuous")

    # --- Tmux Bridge ---

    def _build_launch_command(self) -> str:
        """Build the chained shell command matching dispatch_cmd.py pattern."""
        clone_dir = self._project_dir / "clones" / self.context.agent_id
        prompt_path = self._project_dir / "context" / "agents" / f"{self.context.agent_id}.md"
        chained_cmd = (
            f"cd {clone_dir} "
            f"&& export DISCORD_BOT_TOKEN='{os.environ.get('DISCORD_BOT_TOKEN', '')}' "
            f"&& export DISCORD_GUILD_ID='{os.environ.get('DISCORD_GUILD_ID', '')}' "
            f"&& export PROJECT_NAME='{self.context.project_id or ''}' "
            f"&& export AGENT_ID='{self.context.agent_id}' "
            f"&& export VCO_AGENT_ID='{self.context.agent_id}' "
            f"&& export AGENT_ROLE='{self.context.agent_type}' "
            f"&& claude --dangerously-skip-permissions "
            f"--append-system-prompt-file {prompt_path}"
        )
        return chained_cmd

    async def _launch_tmux_session(self) -> None:
        """Create a tmux pane and launch Claude Code in it."""
        session = await asyncio.to_thread(
            self._tmux.get_or_create_session, self._project_session_name
        )
        pane = await asyncio.to_thread(
            self._tmux.create_pane, session, window_name=self.context.agent_id
        )
        self._pane_id = pane.pane_id
        cmd = self._build_launch_command()
        await asyncio.to_thread(self._tmux.send_command, pane, cmd)
        # Auto-accept workspace trust prompt
        await asyncio.sleep(3)
        await asyncio.to_thread(pane.send_keys, "", enter=True)

    def is_tmux_alive(self) -> bool:
        """Check if the tmux pane process is alive.

        Returns True when no tmux manager is injected (test containers).
        """
        if self._tmux is None or self._pane_id is None:
            return True
        pane = self._tmux.get_pane_by_id(self._pane_id)
        return pane is not None and self._tmux.is_alive(pane)

    # --- Health ---

    def health_report(self) -> HealthReport:
        """Generate a health snapshot for this container.

        If the FSM says 'running' but the tmux pane is dead, reports
        'errored' to reflect actual liveness.
        """
        now = datetime.now(timezone.utc)
        actual_state = self.state
        if (
            actual_state == "running"
            and self._tmux is not None
            and self._needs_tmux_session
            and not self.is_tmux_alive()
        ):
            actual_state = "errored"
        return HealthReport(
            agent_id=self.context.agent_id,
            state=actual_state,
            inner_state=self.inner_state,
            uptime=(now - self._created_at).total_seconds(),
            last_heartbeat=now,
            error_count=self._error_count,
            last_activity=self._last_activity,
            blocked_reason=self._blocked_reason,
        )

    def _on_state_change(self) -> None:
        """Called by the FSM after_transition hook."""
        self._last_activity = datetime.now(timezone.utc)
        if self._on_state_change_cb is not None:
            self._on_state_change_cb(self.health_report())

    # --- Lifecycle Methods ---

    async def start(self) -> None:
        """Transition to running, open memory store, and launch tmux if needed."""
        self._lifecycle.start()
        await self.memory.open()
        if self._tmux is not None and self._needs_tmux_session:
            await self._launch_tmux_session()

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

    def block(self, reason: str) -> None:
        """Transition to BLOCKED state with a reason (ARCH-03)."""
        self._blocked_reason = reason[:200]
        self._lifecycle.block()

    def unblock(self) -> None:
        """Transition from BLOCKED back to running (ARCH-03)."""
        self._blocked_reason = None
        self._lifecycle.unblock()

    async def stop(self) -> None:
        """Kill tmux pane (if any), transition through stopping to stopped, and close memory."""
        self._lifecycle.begin_stop()
        if self._tmux is not None and self._pane_id is not None:
            pane = await asyncio.to_thread(self._tmux.get_pane_by_id, self._pane_id)
            if pane is not None:
                await asyncio.to_thread(self._tmux.kill_pane, pane)
            self._pane_id = None
        self._lifecycle.finish_stop()
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
        tmux_manager: TmuxManager | None = None,
        project_dir: Path | None = None,
        project_session_name: str | None = None,
    ) -> AgentContainer:
        """Create an AgentContainer from a ChildSpec."""
        return cls(
            context=spec.context,
            data_dir=data_dir,
            comm_port=comm_port,
            on_state_change=on_state_change,
            tmux_manager=tmux_manager,
            project_dir=project_dir,
            project_session_name=project_session_name,
        )
