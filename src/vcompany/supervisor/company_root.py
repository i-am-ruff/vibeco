"""CompanyRoot -- top-level supervisor managing ProjectSupervisors.

The root of the supervision tree. Manages ProjectSupervisor instances,
one per active project. When escalation bubbles to the top (no parent),
calls the on_escalation callback to alert via Discord.

All agents use AgentHandle + transport channel protocol.
Owns the Scheduler (AUTO-06) which wakes sleeping agents on schedule.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

from vcompany.daemon.comm import NoopCommunicationPort
from vcompany.shared.memory_store import MemoryStore
from vcompany.supervisor.child_spec import ChildSpec
from vcompany.supervisor.health import CompanyHealthTree, HealthNode, HealthReport, HealthTree
from vcompany.daemon.agent_handle import AgentHandle
from vcompany.daemon.routing_state import AgentRouting, RoutingState
from vcompany.resilience.degraded_mode import DegradedModeManager
from vcompany.supervisor.project_supervisor import ProjectSupervisor
from vcompany.supervisor.scheduler import Scheduler
from vcompany.supervisor.strategies import RestartStrategy
from vcompany.supervisor.supervisor import Supervisor
from vcompany.transport.channel.framing import decode_worker
from vcompany.transport.channel_transport import ChannelTransport
from vcompany.transport.docker_channel import DockerChannelTransport
from vcompany.transport.native import NativeTransport
from vcompany.transport.channel.messages import (
    AskMessage,
    HealthCheckMessage,
    HealthReportMessage,
    ReconnectMessage,
    ReportMessage,
    SendFileMessage,
    SignalMessage,
    StartMessage,
    StopMessage,
)

logger = logging.getLogger(__name__)


class CompanyRoot(Supervisor):
    """Top-level supervisor that manages ProjectSupervisors.

    CompanyRoot sits at the top of the supervision hierarchy. It creates
    and manages ProjectSupervisor instances (one per project). When
    escalation reaches CompanyRoot and cannot be handled (restart budget
    exceeded), it calls the on_escalation callback -- the Discord alert path.

    All agents use AgentHandle (transport channel protocol).

    Args:
        on_escalation: Async callback invoked when escalation cannot be
            handled. Receives a descriptive message string.
        max_restarts: Maximum restarts within window.
        window_seconds: Sliding window size in seconds.
        data_dir: Root directory for child data.
    """

    def __init__(
        self,
        on_escalation: Callable[[str], Awaitable[None]] | None = None,
        max_restarts: int = 3,
        window_seconds: int = 600,
        data_dir: Path | None = None,
        on_health_change: Callable[[HealthReport], Awaitable[None]] | None = None,
        health_check: Callable[[], Awaitable[bool]] | None = None,
        on_degraded: Callable[[], Awaitable[None]] | None = None,
        on_recovered: Callable[[], Awaitable[None]] | None = None,
        transport_deps: dict | None = None,
        project_dir: Path | None = None,
        signal_router: object | None = None,
        comm_port: object | None = None,
    ) -> None:
        # CompanyRoot has no parent and no child_specs at init --
        # projects are added dynamically via add_project().
        super().__init__(
            supervisor_id="company-root",
            strategy=RestartStrategy.ONE_FOR_ONE,
            child_specs=[],
            max_restarts=max_restarts,
            window_seconds=window_seconds,
            parent=None,
            on_escalation=on_escalation,
            data_dir=data_dir,
            on_health_change=on_health_change,
            signal_router=signal_router,
        )
        self._projects: dict[str, ProjectSupervisor] = {}
        self._company_agents: dict[str, AgentHandle] = {}
        self._comm_port = comm_port or NoopCommunicationPort()
        self._transport_deps = transport_deps
        self._project_dir = project_dir
        # Routing state persistence (HEAD-05)
        self._routing_path: Path | None = None
        if data_dir is not None:
            self._routing_path = data_dir / "routing.json"
        self._routing_state = RoutingState.load(self._routing_path) if self._routing_path else RoutingState()
        # Degraded mode manager (RESL-03)
        self._degraded_mode: DegradedModeManager | None = None
        if health_check is not None:
            self._degraded_mode = DegradedModeManager(
                health_check=health_check,
                on_degraded=on_degraded,
                on_recovered=on_recovered,
            )
        # Health polling (sends HealthCheckMessage to each agent periodically)
        self._health_poll_task: asyncio.Task | None = None
        self._health_poll_interval: int = 60  # seconds
        # Scheduler for waking sleeping ContinuousAgents (AUTO-06)
        self._scheduler: Scheduler | None = None
        self._scheduler_task: asyncio.Task | None = None
        self._scheduler_memory: MemoryStore | None = None
        if data_dir is not None:
            self._scheduler_memory = MemoryStore(data_dir / "scheduler" / "memory.db")

    @property
    def is_degraded(self) -> bool:
        """True when the system is in degraded mode (Claude unreachable)."""
        if self._degraded_mode is not None:
            return self._degraded_mode.is_degraded
        return False

    @property
    def projects(self) -> dict[str, ProjectSupervisor]:
        """Dict of project_id -> ProjectSupervisor."""
        return dict(self._projects)

    def health_tree(self) -> CompanyHealthTree:
        """Build a company-wide health tree from all project supervisors.

        Returns a CompanyHealthTree containing a HealthTree per project and
        HealthNodes for company-level agents (e.g. Strategist).
        """
        company_nodes = [
            HealthNode(report=handle.health_report())
            for handle in self._company_agents.values()
        ]
        project_trees: list[HealthTree] = []
        for _project_id, ps in self._projects.items():
            project_trees.append(ps.health_tree())
        return CompanyHealthTree(
            supervisor_id=self.supervisor_id,
            state=self._state,
            company_agents=company_nodes,
            projects=project_trees,
        )

    def _get_transport(self, transport_name: str) -> ChannelTransport:
        """Get or create a transport by name.

        Transports are lazily instantiated and cached for reuse across
        multiple hire() calls with the same transport type.

        Args:
            transport_name: Transport identifier ('native' or 'docker').

        Returns:
            A ChannelTransport implementation.

        Raises:
            ValueError: If transport_name is not recognized.
        """
        if not hasattr(self, '_transports'):
            self._transports: dict[str, ChannelTransport] = {}
        if transport_name not in self._transports:
            if transport_name == "native":
                self._transports[transport_name] = NativeTransport()
            elif transport_name == "docker":
                self._transports[transport_name] = DockerChannelTransport()
            elif transport_name == "network":
                from vcompany.transport.network import NetworkTransport
                self._transports[transport_name] = NetworkTransport()
            else:
                raise ValueError(f"Unknown transport: {transport_name}. Use 'native', 'docker', or 'network'.")
        return self._transports[transport_name]

    # Available agent templates. Maps template name to Jinja2 template file.
    AGENT_TEMPLATES: dict[str, dict] = {
        "generic": {"claude_md": "task_claude_md.md.j2", "extras": []},
        "researcher": {"claude_md": "research_claude_md.md.j2", "extras": ["scripts", "reference"]},
    }

    async def hire(
        self,
        agent_id: str,
        template: str = "generic",
        agent_type: str | None = None,
        channel_id: str | None = None,
        transport_name: str = "native",
    ) -> AgentHandle:
        """Hire a company-level agent. Creates scratch dir, deploys artifacts,
        spawns vco-worker subprocess, sends StartMessage via channel protocol.
        Agent starts idle -- use ``give_task()`` to assign work.

        CRITICAL: channel_id must be passed in so AgentHandle is created with
        it populated BEFORE _save_routing() persists routing state.

        Args:
            agent_id: Unique identifier for the agent.
            template: Agent template key (see AGENT_TEMPLATES).
            agent_type: If provided, look up from agent-types config for
                capabilities, gsd_command, etc.
            channel_id: Discord channel ID for this agent (passed by RuntimeAPI).

        Returns:
            The AgentHandle for the spawned worker.
        """
        from vcompany.shared.file_ops import write_atomic
        from vcompany.shared.templates import render_template
        import shutil

        # Look up agent type config
        agent_types = None
        try:
            from vcompany.models.agent_types import get_agent_types_config
            agent_types = get_agent_types_config()
        except Exception:
            pass

        effective_type = agent_type or "task"
        type_config = None
        if agent_types:
            try:
                type_config = agent_types.get_type(effective_type)
            except KeyError:
                logger.warning("Unknown agent type %s, using defaults", effective_type)

        tmpl = self.AGENT_TEMPLATES.get(template, self.AGENT_TEMPLATES["generic"])
        repo_root = Path(__file__).parent.parent.parent.parent

        # 1. Create scratch working directory
        tasks_dir = Path.home() / "vco-tasks"
        working_dir = tasks_dir / agent_id
        working_dir.mkdir(parents=True, exist_ok=True)

        # 2. Deploy artifacts
        claude_dir = working_dir / ".claude"
        claude_dir.mkdir(exist_ok=True)

        # settings.json (hooks: ask_discord, idle signals)
        write_atomic(claude_dir / "settings.json", render_template("settings.json.j2"))

        # CLAUDE.md (identity + workflow -- template-specific)
        claude_md = render_template(
            tmpl["claude_md"],
            task_id=agent_id,
            task_prompt="Awaiting task assignment from the Strategist.",
        )
        write_atomic(working_dir / "CLAUDE.md", claude_md)

        # Slash commands (/vco:send, /vco:finish)
        commands_dir = claude_dir / "commands" / "vco"
        commands_dir.mkdir(parents=True, exist_ok=True)
        commands_source = repo_root / "commands" / "vco"
        for cmd_file in ("send.md", "finish.md"):
            src = commands_source / cmd_file
            if src.exists():
                shutil.copy2(src, commands_dir / cmd_file)

        # Template-specific extras (scripts, reference docs)
        for extra in tmpl.get("extras", []):
            source_dir = repo_root / "tools" / f"research_{extra}"
            if source_dir.is_dir():
                dest_dir = working_dir / extra
                dest_dir.mkdir(exist_ok=True)
                for f in source_dir.iterdir():
                    if f.is_file():
                        shutil.copy2(f, dest_dir / f.name)
                logger.info("Deployed %s to %s", extra, dest_dir)

        # 3. Build worker config dict
        config_dict = {
            "handler_type": type_config.handler_type if type_config and hasattr(type_config, "handler_type") else "session",
            "agent_type": effective_type,
            "capabilities": list(type_config.capabilities) if type_config else [],
            "gsd_command": type_config.gsd_command if type_config else None,
            "uses_tmux": "uses_tmux" in type_config.capabilities if type_config else True,
        }

        # 4. Create handle -- channel_id is passed in so it's populated BEFORE _save_routing
        handle = AgentHandle(
            agent_id=agent_id,
            agent_type=effective_type,
            handler_type=config_dict["handler_type"],
            config=config_dict,
            capabilities=config_dict.get("capabilities", []),
            channel_id=channel_id,
        )

        # 5. Spawn worker via transport (native subprocess or Docker container)
        import os
        transport = self._get_transport(transport_name)
        reader, writer = await transport.spawn(
            agent_id,
            config=config_dict,
            env={"ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "")},
            working_dir=str(working_dir),
        )
        handle.attach_socket(reader, writer)

        # 6. Send StartMessage
        await handle.send(StartMessage(agent_id=agent_id, config=config_dict))

        # 7. Start channel reader task
        handle._reader_task = asyncio.create_task(
            self._channel_reader(handle),
            name=f"channel-reader-{agent_id}",
        )

        self._company_agents[agent_id] = handle
        # Persist routing state -- channel_id is already set on handle
        self._save_routing(handle, transport_name=transport_name)
        logger.info("Hired agent %s (template=%s, type=%s)", agent_id, template, effective_type)
        return handle

    async def _channel_reader(self, handle: AgentHandle) -> None:
        """Read WorkerMessages from transport channel, dispatch to handlers."""
        reader = handle.reader
        if reader is None:
            return
        try:
            async for line in reader:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    msg = decode_worker(stripped)
                except Exception:
                    logger.warning("Failed to decode worker message: %s", stripped[:200])
                    continue
                if isinstance(msg, HealthReportMessage):
                    handle.update_health(msg)
                elif isinstance(msg, SignalMessage):
                    logger.info("Agent %s signal: %s %s", handle.agent_id, msg.signal, msg.detail)
                elif isinstance(msg, ReportMessage):
                    await self._route_report(handle, msg)
                elif isinstance(msg, AskMessage):
                    await self._route_ask(handle, msg)
                elif isinstance(msg, SendFileMessage):
                    logger.info("Agent %s sent file: %s", handle.agent_id, msg.filename)
        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, BrokenPipeError):
            logger.warning("Channel reader lost connection to %s", handle.agent_id)
        except Exception:
            logger.exception("Channel reader error for %s", handle.agent_id)

    async def _health_poll_loop(self) -> None:
        """Periodically send HealthCheckMessage to all agents to keep health data fresh."""
        try:
            while True:
                await asyncio.sleep(self._health_poll_interval)
                for handle in list(self._company_agents.values()):
                    if handle.is_alive:
                        try:
                            await handle.send(HealthCheckMessage())
                        except (RuntimeError, OSError, ConnectionResetError):
                            logger.debug("Health check failed for %s", handle.agent_id)
        except asyncio.CancelledError:
            pass

    async def _route_report(self, handle: AgentHandle, msg: ReportMessage) -> None:
        """Route a worker report to the appropriate Discord channel via comm_port."""
        from vcompany.daemon.comm import SendMessagePayload
        if handle.channel_id:
            await self._comm_port.send_message(
                SendMessagePayload(channel_id=handle.channel_id, content=msg.content)
            )

    async def _route_ask(self, handle: AgentHandle, msg: AskMessage) -> None:
        """Route a worker question to the appropriate Discord channel via comm_port."""
        from vcompany.daemon.comm import SendMessagePayload
        if handle.channel_id:
            await self._comm_port.send_message(
                SendMessagePayload(channel_id=handle.channel_id, content=f"**Question:** {msg.question}")
            )

    async def dismiss(self, agent_id: str) -> None:
        """Dismiss (stop) a company-level agent.

        Sends StopMessage through transport, stops process, cleans up reader task.

        Args:
            agent_id: The agent to dismiss.

        Raises:
            KeyError: If agent_id not found in company agents.
        """
        handle = self._company_agents.pop(agent_id)
        await handle.stop_process()
        if handle._reader_task is not None:
            handle._reader_task.cancel()
        self._remove_routing(agent_id)
        logger.info("Dismissed agent %s", agent_id)

    async def dispatch_task_agent(
        self,
        task_id: str,
        task_prompt: str,
        template: str = "generic",
    ) -> AgentHandle:
        """Convenience: hire an agent and immediately give it a task.

        Equivalent to ``hire()`` followed by sending a GiveTaskMessage.
        """
        from vcompany.transport.channel.messages import GiveTaskMessage
        handle = await self.hire(task_id, template=template)
        await handle.send(GiveTaskMessage(task_id=task_id, description=task_prompt))
        return handle

    async def add_project(
        self,
        project_id: str,
        child_specs: list[ChildSpec],
        strategy: RestartStrategy = RestartStrategy.ONE_FOR_ONE,
        max_restarts: int = 3,
        window_seconds: int = 600,
    ) -> ProjectSupervisor:
        """Create and start a ProjectSupervisor for the given project.

        Args:
            project_id: Unique project identifier.
            child_specs: Agent container specifications for the project.
            strategy: Restart strategy for the project supervisor.
            max_restarts: Maximum restarts within window.
            window_seconds: Sliding window size in seconds.

        Returns:
            The started ProjectSupervisor instance.

        Raises:
            RuntimeError: If system is in degraded mode (Claude unreachable).
        """
        if self._degraded_mode is not None and self._degraded_mode.is_degraded:
            raise RuntimeError(
                f"System in degraded mode (Claude unreachable). "
                f"Cannot add project {project_id}. Will auto-recover."
            )
        ps = ProjectSupervisor(
            project_id=project_id,
            child_specs=child_specs,
            strategy=strategy,
            max_restarts=max_restarts,
            window_seconds=window_seconds,
            parent=self,
            data_dir=self._data_dir,
            transport_deps=self._transport_deps,
            project_dir=self._project_dir,
            comm_port=self._comm_port,
            signal_router=self._signal_router,
        )
        await ps.start()
        self._projects[project_id] = ps
        logger.info("Added project %s with %d agents", project_id, len(child_specs))
        return ps

    async def remove_project(self, project_id: str) -> None:
        """Stop and remove a ProjectSupervisor.

        Args:
            project_id: The project to remove.

        Raises:
            KeyError: If project_id is not found.
        """
        ps = self._projects.pop(project_id)
        if ps.state != "stopped":
            await ps.stop()
        logger.info("Removed project %s", project_id)

    async def _find_handle(self, agent_id: str) -> AgentHandle | None:
        """Search company agents for a handle by agent_id."""
        return self._company_agents.get(agent_id)

    # ── Routing state persistence (HEAD-05) ──────────────────────────

    def _save_routing(self, handle: AgentHandle, transport_name: str = "native") -> None:
        """Persist routing state after adding an agent."""
        if self._routing_path is None:
            return
        routing = AgentRouting(
            agent_id=handle.agent_id,
            channel_id=handle.channel_id,
            agent_type=handle.agent_type,
            handler_type=handle.handler_type,
            config=handle.config,
            capabilities=handle.capabilities,
            transport_type=transport_name,
        )
        self._routing_state.add_agent(routing)
        self._routing_state.save(self._routing_path)

    def _remove_routing(self, agent_id: str) -> None:
        """Remove routing state after dismissing an agent."""
        if self._routing_path is None:
            return
        self._routing_state.remove_agent(agent_id)
        self._routing_state.save(self._routing_path)

    # ── Reconnection (AUTO-03) ─────────────────────────────────────

    async def reconnect_agents(self) -> None:
        """Reconnect to surviving workers after daemon restart.

        Iterates RoutingState, gets the appropriate transport for each agent,
        attempts to connect to its socket. On success: creates AgentHandle,
        sends ReconnectMessage, starts channel reader. On failure: removes
        stale routing entry.
        """
        if not self._routing_state.agents:
            return

        logger.info("Reconnecting to %d persisted agents", len(self._routing_state.agents))
        stale_agents: list[str] = []

        for agent_id, routing in list(self._routing_state.agents.items()):
            try:
                transport = self._get_transport(routing.transport_type)
                reader, writer = await transport.connect(agent_id)

                handle = AgentHandle(
                    agent_id=routing.agent_id,
                    agent_type=routing.agent_type,
                    channel_id=routing.channel_id,
                    handler_type=routing.handler_type,
                    config=routing.config,
                    capabilities=routing.capabilities,
                )
                handle.attach_socket(reader, writer)

                # Send reconnect message -- worker responds with HealthReport
                await handle.send(ReconnectMessage(agent_id=agent_id))

                # Start channel reader
                handle._reader_task = asyncio.create_task(
                    self._channel_reader(handle),
                    name=f"channel-reader-{agent_id}",
                )

                self._company_agents[agent_id] = handle
                logger.info("Reconnected to worker %s (transport=%s)", agent_id, routing.transport_type)

            except (ConnectionError, ConnectionRefusedError, FileNotFoundError, TimeoutError) as e:
                logger.warning("Failed to reconnect to worker %s: %s", agent_id, e)
                stale_agents.append(agent_id)
            except Exception:
                logger.exception("Unexpected error reconnecting to %s", agent_id)
                stale_agents.append(agent_id)

        # Clean up stale routing entries
        for agent_id in stale_agents:
            self._routing_state.remove_agent(agent_id)
        if stale_agents and self._routing_path:
            self._routing_state.save(self._routing_path)
            logger.info("Removed %d stale agent entries from routing state", len(stale_agents))

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        """Load routing state, open scheduler memory, and start scheduler loop."""
        await super().start()

        # Load routing state from disk
        if self._routing_path is not None:
            self._routing_state = RoutingState.load(self._routing_path)

        # Reconnect to surviving workers (AUTO-03)
        await self.reconnect_agents()

        if self._degraded_mode is not None:
            await self._degraded_mode.start()
            logger.info("DegradedModeManager started")

        # Start health polling loop
        self._health_poll_task = asyncio.create_task(
            self._health_poll_loop(), name="health-poll"
        )
        logger.info("Health poll started (interval=%ds)", self._health_poll_interval)

        if self._scheduler_memory is not None:
            await self._scheduler_memory.open()
            self._scheduler = Scheduler(
                memory=self._scheduler_memory,
                find_container=self._find_handle,
            )
            await self._scheduler.load()
            self._scheduler_task = asyncio.create_task(self._scheduler.run())
            logger.info("Scheduler started")

    async def add_schedule(self, agent_id: str, interval_seconds: int) -> None:
        """Add a wake schedule for an agent (pass-through to Scheduler)."""
        if self._scheduler is not None:
            await self._scheduler.add_schedule(agent_id, interval_seconds)

    async def remove_schedule(self, agent_id: str) -> None:
        """Remove a wake schedule for an agent (pass-through to Scheduler)."""
        if self._scheduler is not None:
            await self._scheduler.remove_schedule(agent_id)

    async def handle_child_escalation(self, child_supervisor_id: str) -> None:
        """Handle escalation from a child ProjectSupervisor.

        Since ProjectSupervisors are managed dynamically (not via child_specs),
        the base Supervisor._handle_child_failure path cannot find them.
        CompanyRoot handles this directly: check its own restart budget,
        and if exceeded, call on_escalation (the Discord alert path).
        """
        logger.warning(
            "CompanyRoot received escalation from child %s",
            child_supervisor_id,
        )

        if not self._restart_tracker.allow_restart():
            # CompanyRoot itself has exceeded its budget -- fire the callback
            msg = (
                f"ESCALATION: Supervisor {self.supervisor_id} exceeded restart limits "
                f"for child {child_supervisor_id}. Manual intervention required."
            )
            if self._on_escalation is not None:
                await self._on_escalation(msg)
            return

        # Otherwise, try to restart the project supervisor
        # Find the project by supervisor_id
        project_id: str | None = None
        for pid, ps in self._projects.items():
            if ps.supervisor_id == child_supervisor_id:
                project_id = pid
                break

        if project_id is not None:
            old_ps = self._projects[project_id]
            # Rebuild with same specs
            new_ps = ProjectSupervisor(
                project_id=project_id,
                child_specs=old_ps._child_specs,
                strategy=old_ps.strategy,
                max_restarts=old_ps._restart_tracker.max_restarts,
                window_seconds=old_ps._restart_tracker.window_seconds,
                parent=self,
                data_dir=self._data_dir,
                transport_deps=self._transport_deps,
                project_dir=self._project_dir,
                comm_port=self._comm_port,
                signal_router=self._signal_router,
            )
            await new_ps.start()
            self._projects[project_id] = new_ps
            logger.info("Restarted project supervisor for %s", project_id)
        else:
            # Unknown child -- fire escalation callback
            msg = (
                f"ESCALATION: Supervisor {self.supervisor_id} received escalation "
                f"from unknown child {child_supervisor_id}. Manual intervention required."
            )
            if self._on_escalation is not None:
                await self._on_escalation(msg)

    async def stop(self) -> None:
        """Cancel scheduler, stop all agents and ProjectSupervisors, and stop the root."""
        # Stop degraded mode manager first
        if self._degraded_mode is not None:
            await self._degraded_mode.stop()
            logger.info("DegradedModeManager stopped")

        # Cancel the scheduler task first
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None
            logger.info("Scheduler stopped")

        # Close scheduler memory store
        if self._scheduler_memory is not None:
            await self._scheduler_memory.close()

        # Stop company-level agents
        for agent in list(self._company_agents.values()):
            try:
                await agent.stop_process()
                if agent._reader_task is not None:
                    agent._reader_task.cancel()
            except Exception:
                logger.warning("Error stopping company agent", exc_info=True)
        self._company_agents.clear()

        # Stop all dynamically added projects
        for ps in list(self._projects.values()):
            if ps.state != "stopped":
                await ps.stop()

        # Stop any static children via parent class
        await super().stop()
