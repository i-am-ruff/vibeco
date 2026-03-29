"""AgentContainer — central abstraction wrapping every agent in v2.

Composes lifecycle FSM, context, memory store, health reporting, and
communication port into a single managed unit. Supervisors (Phase 2) manage
AgentContainers. Agent types (Phase 3/4) subclass them.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable

logger = logging.getLogger(__name__)

from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport
from vcompany.container.memory_store import MemoryStore
from vcompany.container.state_machine import ContainerLifecycle

if TYPE_CHECKING:
    from vcompany.container.child_spec import ChildSpec
    from vcompany.container.communication import CommunicationPort
    from vcompany.models.messages import MessageContext
    from vcompany.transport.protocol import AgentTransport


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
        transport: Optional AgentTransport for execution environment abstraction.
        project_dir: Optional project directory for clone/prompt paths.
        project_session_name: Optional tmux session name for the project.
    """

    def __init__(
        self,
        context: ContainerContext,
        data_dir: Path,
        comm_port: CommunicationPort | None = None,
        on_state_change: Callable[[HealthReport], None] | None = None,
        transport: AgentTransport | None = None,
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
        # Transport abstraction (replaces direct TmuxManager usage)
        self._transport: AgentTransport | None = transport
        self._project_dir: Path | None = project_dir
        self._project_session_name: str | None = project_session_name
        self._blocked_reason: str | None = None  # ARCH-03
        # Signal-based idle tracking (driven by push-based signals from daemon)
        self._is_idle: bool = False
        # Task queue: idle-gated command delivery via transport
        self._task_queue: asyncio.Queue[str] = asyncio.Queue()
        self._idle_watcher_task: asyncio.Task | None = None
        # Transport setup kwargs from agent type config (D-06: tweakcc_profile, settings_json)
        self._transport_setup_kwargs: dict = {}

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
    def _needs_transport(self) -> bool:
        """True when this container should set up a transport environment."""
        return self.context.uses_tmux

    @property
    def _needs_tmux_session(self) -> bool:
        """Deprecated: use _needs_transport. Kept for backward compat."""
        return self._needs_transport

    @property
    def working_dir(self) -> Path:
        """Working directory where Claude Code runs.

        Default assumes GSD clone layout: ``project_dir/clones/{agent_id}``.
        Subclasses override for different layouts (e.g., TaskAgent uses
        the project_dir directly as the working dir).
        """
        return self._project_dir / "clones" / self.context.agent_id

    @property
    def system_prompt_path(self) -> Path | None:
        """Path to system prompt file appended via --append-system-prompt-file.

        Returns None to skip (agent uses CLAUDE.md auto-discovery instead).
        Default assumes GSD layout: ``project_dir/context/agents/{agent_id}.md``.
        """
        return self._project_dir / "context" / "agents" / f"{self.context.agent_id}.md"

    @property
    def is_idle(self) -> bool:
        """Whether Claude Code is idle and ready for input (signal-based)."""
        return self._is_idle

    # --- Push-Based Signal Handling (replaces polling) ---

    async def _handle_signal(self, signal_type: str) -> None:
        """Handle push-based signal from daemon (replaces polling idle watcher).

        Called by the daemon's SignalRouter when a 'vco signal' HTTP request arrives.
        """
        if signal_type in ("ready", "idle"):
            self._is_idle = signal_type == "idle"
            self._last_activity = datetime.now(timezone.utc)
            logger.info("Signal received for %s: %s", self.context.agent_id, signal_type)
            if self._is_idle and not self._task_queue.empty():
                await self._drain_task_queue()

    # --- Task Queue (idle-gated command delivery) ---

    async def give_task(self, task: str) -> None:
        """Queue a task for delivery to the agent's execution environment when idle.

        If the agent is currently idle, sends immediately. Otherwise queues
        for delivery when the next signal arrives.
        """
        await self._task_queue.put(task)
        logger.info("Queued task for %s: %s", self.context.agent_id, task[:80])
        if self._is_idle:
            await self._drain_task_queue()

    async def _drain_task_queue(self) -> None:
        """Send the next queued task to the agent's execution environment."""
        if self._transport is None:
            return
        try:
            task = self._task_queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        self._is_idle = False
        await self._transport.exec(self.context.agent_id, task)
        logger.info("Sent queued task to %s: %s", self.context.agent_id, task[:80])

    # --- Transport Bridge ---

    def _build_launch_command(self) -> str:
        """Build the chained shell command to launch Claude Code.

        Uses ``self.working_dir`` and ``self.system_prompt_path`` properties
        so subclasses can override path layout without rewriting the whole
        command. If ``context.gsd_command`` is set, it is passed as the
        positional ``prompt`` argument.
        """
        wd = self.working_dir
        chained_cmd = (
            f"cd {wd} "
            f"&& export DISCORD_BOT_TOKEN='{os.environ.get('DISCORD_BOT_TOKEN', '')}' "
            f"&& export DISCORD_GUILD_ID='{os.environ.get('DISCORD_GUILD_ID', '')}' "
            f"&& export PROJECT_NAME='{self.context.project_id or ''}' "
            f"&& export AGENT_ID='{self.context.agent_id}' "
            f"&& export VCO_AGENT_ID='{self.context.agent_id}' "
            f"&& export AGENT_ROLE='{self.context.agent_type}' "
            f"&& claude --dangerously-skip-permissions"
        )
        # Append system prompt file if one is configured
        prompt_path = self.system_prompt_path
        if prompt_path is not None:
            chained_cmd += f" --append-system-prompt-file {prompt_path}"
        # Append initial command/prompt as positional arg
        if self.context.gsd_command:
            escaped = self.context.gsd_command.replace("'", "'\\''")
            chained_cmd += f" '{escaped}'"
        return chained_cmd

    async def _launch_agent(self) -> None:
        """Set up transport environment and launch Claude Code.

        Delegates environment creation to transport.setup(), sends the launch
        command via transport.exec(), and handles workspace trust acceptance
        via transport.send_keys() -- no TmuxManager import needed.
        """
        await self._transport.setup(
            self.context.agent_id,
            working_dir=self.working_dir,
            interactive=True,
            session_name=self._project_session_name,
            window_name=self.context.agent_id,
            **self._transport_setup_kwargs,
        )

        cmd = self._build_launch_command()
        await self._transport.exec(self.context.agent_id, cmd)

        # Wait for workspace trust prompt and auto-accept via transport
        await asyncio.sleep(3)
        await self._transport.send_keys(self.context.agent_id, "", enter=True)

        # Signal-based readiness is now push-based -- no polling here.
        # The daemon's SignalRouter will call _handle_signal("ready") when
        # the SessionStart hook fires. We just log that we launched.
        logger.info(
            "Claude Code launched for %s via transport (awaiting ready signal)",
            self.context.agent_id,
        )

    def is_alive(self) -> bool:
        """Check if the agent's execution environment is alive.

        Returns True when no transport is injected (test containers).
        """
        if self._transport is None:
            return True
        return self._transport.is_alive(self.context.agent_id)

    def is_tmux_alive(self) -> bool:
        """Deprecated: use is_alive(). Kept for backward compat with supervisor monitor."""
        return self.is_alive()

    # --- Health ---

    def health_report(self) -> HealthReport:
        """Generate a health snapshot for this container.

        If the FSM says 'running' but the transport is dead, reports
        'errored' to reflect actual liveness.
        """
        now = datetime.now(timezone.utc)
        actual_state = self.state
        if (
            actual_state == "running"
            and self._transport is not None
            and self._needs_transport
            and not self.is_alive()
        ):
            actual_state = "errored"

        # _is_idle is now set by push-based _handle_signal(), no polling needed

        return HealthReport(
            agent_id=self.context.agent_id,
            state=actual_state,
            inner_state=self.inner_state,
            uptime=(now - self._created_at).total_seconds(),
            last_heartbeat=now,
            error_count=self._error_count,
            last_activity=self._last_activity,
            blocked_reason=self._blocked_reason,
            is_idle=self._is_idle if self._needs_transport else None,
        )

    def _on_state_change(self) -> None:
        """Called by the FSM after_transition hook."""
        self._last_activity = datetime.now(timezone.utc)
        if self._on_state_change_cb is not None:
            self._on_state_change_cb(self.health_report())

    # --- Lifecycle Methods ---

    async def start(self) -> None:
        """Transition to running, open memory store, and launch via transport if needed."""
        self._lifecycle.start()
        await self.memory.open()
        if self._transport is not None and self._needs_transport:
            await self._launch_agent()

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
        """Teardown transport, transition to stopped, and close memory."""
        # Cancel idle watcher if any (shouldn't exist in new code but defensive)
        if self._idle_watcher_task is not None:
            self._idle_watcher_task.cancel()
            try:
                await self._idle_watcher_task
            except asyncio.CancelledError:
                pass
            self._idle_watcher_task = None
        self._lifecycle.begin_stop()
        if self._transport is not None:
            await self._transport.teardown(self.context.agent_id)
        self._lifecycle.finish_stop()
        await self.memory.close()

    async def destroy(self) -> None:
        """Transition to destroyed and close memory store."""
        self._lifecycle.destroy()
        await self.memory.close()

    async def send_event(self, name: str) -> None:
        """String-based event dispatch for supervisor use."""
        self._lifecycle.send(name)

    # --- Discord Message Delivery ---

    async def receive_discord_message(self, context: MessageContext) -> None:
        """Receive an inbound Discord message routed to this agent.

        Base implementation is a no-op log. Subclasses (FulltimeAgent,
        CompanyAgent, GsdAgent) override to process messages.

        Args:
            context: Message context with sender, channel, content, and
                optional parent_message for reply context.
        """
        logger.info(
            "Agent %s received Discord message from %s in #%s",
            self.context.agent_id,
            context.sender,
            context.channel,
        )

    # --- Factory ---

    @classmethod
    def from_spec(
        cls,
        spec: ChildSpec,
        data_dir: Path,
        comm_port: CommunicationPort | None = None,
        on_state_change: Callable[[HealthReport], None] | None = None,
        transport: AgentTransport | None = None,
        project_dir: Path | None = None,
        project_session_name: str | None = None,
    ) -> AgentContainer:
        """Create an AgentContainer from a ChildSpec."""
        return cls(
            context=spec.context,
            data_dir=data_dir,
            comm_port=comm_port,
            on_state_change=on_state_change,
            transport=transport,
            project_dir=project_dir,
            project_session_name=project_session_name,
        )
