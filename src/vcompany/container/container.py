"""AgentContainer — central abstraction wrapping every agent in v2.

Composes lifecycle FSM, context, memory store, health reporting, and
communication port into a single managed unit. Supervisors (Phase 2) manage
AgentContainers. Agent types (Phase 3/4) subclass them.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
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
    from vcompany.tmux.session import TmuxManager


# Sentinel file directory for Claude Code hook signals.
_SIGNAL_DIR = Path("/tmp")
_SIGNAL_PREFIX = "vco-agent-"


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
        # Signal-based idle tracking (driven by Claude Code hooks)
        self._is_idle: bool = False
        # Task queue: idle-gated command delivery to tmux pane
        self._task_queue: asyncio.Queue[str] = asyncio.Queue()
        self._idle_watcher_task: asyncio.Task | None = None

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
        """True when this container should launch a tmux session."""
        return self.context.uses_tmux

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

    @property
    def _signal_path(self) -> Path:
        """Path to this agent's sentinel file written by Claude Code hooks."""
        return _SIGNAL_DIR / f"{_SIGNAL_PREFIX}{self.context.agent_id}.state"

    # --- Signal-Based Readiness ---

    def _read_signal(self) -> str | None:
        """Read the current signal from the sentinel file, or None if absent."""
        try:
            return self._signal_path.read_text().strip()
        except FileNotFoundError:
            return None

    def _clear_signal(self) -> None:
        """Remove the sentinel file (cleanup on start/stop)."""
        try:
            self._signal_path.unlink()
        except FileNotFoundError:
            pass

    async def _wait_for_signal(
        self,
        expected: str | tuple[str, ...],
        timeout: float = 120.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Wait until the sentinel file contains one of the expected values.

        Returns True when signal detected, False on timeout.
        """
        if isinstance(expected, str):
            expected = (expected,)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = await asyncio.to_thread(self._read_signal)
            if value in expected:
                self._is_idle = value == "idle"
                return True
            await asyncio.sleep(poll_interval)
        return False

    # --- Task Queue (idle-gated command delivery) ---

    async def give_task(self, task: str) -> None:
        """Queue a task for delivery to the tmux pane when agent is idle.

        If the agent is currently idle, sends immediately. Otherwise queues
        for delivery when the next ``Stop`` hook signal arrives.
        """
        await self._task_queue.put(task)
        logger.info("Queued task for %s: %s", self.context.agent_id, task[:80])
        if self._is_idle:
            await self._drain_task_queue()

    async def _drain_task_queue(self) -> None:
        """Send the next queued task to the tmux pane."""
        if self._pane_id is None or self._tmux is None:
            return
        try:
            task = self._task_queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        self._is_idle = False
        self._clear_signal()  # prevent re-reading stale "idle"
        await asyncio.to_thread(self._tmux.send_command, self._pane_id, task)
        logger.info("Sent queued task to %s: %s", self.context.agent_id, task[:80])

    async def _watch_idle_signals(self) -> None:
        """Background task: watch signal file and drain queue when idle."""
        while True:
            try:
                signal = await asyncio.to_thread(self._read_signal)
                if signal in ("idle", "started"):
                    self._is_idle = True
                    self._last_activity = datetime.now(timezone.utc)
                    if not self._task_queue.empty():
                        await self._drain_task_queue()
            except Exception:
                pass  # resilient — don't crash on signal read errors
            await asyncio.sleep(1.0)

    # --- Tmux Bridge ---

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

    async def _launch_tmux_session(self) -> None:
        """Create a tmux pane and launch Claude Code in it.

        The GSD command (if any) is passed as the positional prompt argument
        to the ``claude`` CLI, so Claude processes it on startup. Readiness
        is detected via the ``SessionStart`` hook signal (sentinel file)
        rather than polling tmux pane output.
        """
        # Clean up any stale signal from a previous run
        self._clear_signal()

        session = await asyncio.to_thread(
            self._tmux.get_or_create_session, self._project_session_name
        )
        pane = await asyncio.to_thread(
            self._tmux.create_pane, session, window_name=self.context.agent_id
        )
        self._pane_id = pane.pane_id
        cmd = self._build_launch_command()
        await asyncio.to_thread(self._tmux.send_command, pane, cmd)

        # Wait for the workspace trust prompt and auto-accept it.
        # With --dangerously-skip-permissions the permissions are bypassed but
        # the trust dialog still appears. We send Enter to accept it.
        # The SessionStart hook fires AFTER trust is accepted, so we use
        # the signal to know when Claude is truly ready rather than a blind sleep.
        await asyncio.sleep(3)
        await asyncio.to_thread(pane.send_keys, "", enter=True)

        # Wait for Claude Code to signal it has started (SessionStart hook).
        # This replaces the old _wait_for_claude_ready() pane-output polling.
        started = await self._wait_for_signal(("started", "idle"), timeout=120.0)
        if started:
            logger.info(
                "Claude Code session started for %s (signal-based)",
                self.context.agent_id,
            )
            if self.context.gsd_command:
                logger.info(
                    "GSD command passed as initial prompt to %s: %s",
                    self.context.agent_id,
                    self.context.gsd_command,
                )
        else:
            logger.warning(
                "Claude Code did not signal startup within timeout for %s"
                " -- agent may not be running",
                self.context.agent_id,
            )

        # Start background idle watcher for queue-based task delivery
        self._idle_watcher_task = asyncio.create_task(self._watch_idle_signals())

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

        # Refresh idle state from signal file for tmux agents
        if self._tmux is not None and self._needs_tmux_session:
            signal = self._read_signal()
            self._is_idle = signal == "idle"

        return HealthReport(
            agent_id=self.context.agent_id,
            state=actual_state,
            inner_state=self.inner_state,
            uptime=(now - self._created_at).total_seconds(),
            last_heartbeat=now,
            error_count=self._error_count,
            last_activity=self._last_activity,
            blocked_reason=self._blocked_reason,
            is_idle=self._is_idle if self._needs_tmux_session else None,
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
        """Kill tmux pane (if any), cancel watcher, transition to stopped, and close memory."""
        # Cancel idle watcher before killing pane
        if self._idle_watcher_task is not None:
            self._idle_watcher_task.cancel()
            try:
                await self._idle_watcher_task
            except asyncio.CancelledError:
                pass
            self._idle_watcher_task = None
        self._lifecycle.begin_stop()
        if self._tmux is not None and self._pane_id is not None:
            pane = await asyncio.to_thread(self._tmux.get_pane_by_id, self._pane_id)
            if pane is not None:
                await asyncio.to_thread(self._tmux.kill_pane, pane)
            self._pane_id = None
        self._clear_signal()
        self._lifecycle.finish_stop()
        await self.memory.close()

    async def destroy(self) -> None:
        """Transition to destroyed and close memory store."""
        self._lifecycle.destroy()
        self._clear_signal()
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
