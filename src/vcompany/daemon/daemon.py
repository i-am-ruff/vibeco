"""Runtime daemon managing bot, socket API, and RuntimeAPI gateway.

Owns: PID file, signal handlers, SocketServer, bot lifecycle, RuntimeAPI,
CompanyRoot initialization and shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

from vcompany.daemon.comm import CommunicationPort, NoopCommunicationPort, SendMessagePayload
from vcompany.daemon.runtime_api import RuntimeAPI
from vcompany.daemon.server import SocketServer
from vcompany.shared.paths import VCO_PID_PATH, VCO_SOCKET_PATH

logger = logging.getLogger("vcompany.daemon")


class Daemon:
    """Runtime daemon managing bot, socket API, and RuntimeAPI gateway.

    Owns: PID file, signal handlers, SocketServer, bot lifecycle, RuntimeAPI,
    CompanyRoot initialization and shutdown.
    """

    def __init__(
        self,
        bot: object,
        bot_token: str,
        socket_path: Path | None = None,
        pid_path: Path | None = None,
        project_dir: Path | None = None,
        project_config: object | None = None,
    ) -> None:
        self._bot = bot
        self._bot_token = bot_token
        self._socket_path = socket_path or VCO_SOCKET_PATH
        self._pid_path = pid_path or VCO_PID_PATH
        self._server: SocketServer | None = None
        self._shutdown_event = asyncio.Event()
        self._bot_task: asyncio.Task | None = None
        self._comm_port: CommunicationPort | None = None
        self._runtime_api: RuntimeAPI | None = None
        self._project_dir = project_dir
        self._project_config = project_config
        self._bot_ready_event = asyncio.Event()
        self._company_root: object | None = None  # CompanyRoot, typed as object to avoid import at module level

    def set_comm_port(self, port: CommunicationPort) -> None:
        """Register a CommunicationPort adapter (called by bot on_ready)."""
        if not isinstance(port, CommunicationPort):
            raise TypeError(
                f"{type(port).__name__} does not satisfy CommunicationPort protocol"
            )
        self._comm_port = port
        logger.info("CommunicationPort registered: %s", type(port).__name__)

    @property
    def comm_port(self) -> CommunicationPort:
        """Get registered CommunicationPort. Raises if not registered."""
        if self._comm_port is None:
            raise RuntimeError(
                "CommunicationPort not registered -- is the bot connected?"
            )
        return self._comm_port

    @property
    def runtime_api(self) -> RuntimeAPI | None:
        """RuntimeAPI gateway. Available after CompanyRoot initialization."""
        return self._runtime_api

    def set_runtime_api(self, api: RuntimeAPI) -> None:
        """Register the RuntimeAPI (called during CompanyRoot setup)."""
        self._runtime_api = api
        logger.info("RuntimeAPI registered")

    def run(self) -> None:
        """Blocking entry point. Calls asyncio.run(self._run())."""
        asyncio.run(self._run())

    async def _run(self) -> None:
        """Main async lifecycle: PID -> signals -> socket -> bot -> CompanyRoot -> wait -> shutdown."""
        self._check_already_running()
        self._write_pid_file()
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, self._signal_shutdown)
            loop.add_signal_handler(signal.SIGINT, self._signal_shutdown)

            # Start socket server
            self._server = SocketServer(self._socket_path)
            self._server.register_method("shutdown", self._handle_shutdown)
            await self._server.start()
            logger.info("Socket server listening on %s", self._socket_path)

            # Inject daemon reference into bot so on_ready can register CommunicationPort
            self._bot._daemon = self

            # Start Discord bot (DAEMON-06: bot.start() not bot.run())
            self._bot_task = asyncio.create_task(self._bot.start(self._bot_token))
            logger.info("Bot starting...")

            # Wait for bot to signal readiness (on_ready fires and registers CommunicationPort)
            logger.info("Waiting for bot to connect...")
            bot_ready_task = asyncio.create_task(self._bot_ready_event.wait())
            done, _ = await asyncio.wait(
                [bot_ready_task, self._bot_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self._bot_task in done:
                # Bot crashed before ready
                logger.error("Bot crashed before on_ready")
            else:
                logger.info("Bot connected, initializing CompanyRoot...")
                await self._init_company_root()

            # Wait for shutdown signal
            await self._shutdown_event.wait()
            logger.info("Shutdown signal received, cleaning up...")

            # Graceful shutdown sequence
            await self._shutdown()
        finally:
            self._cleanup_pid_file()
            self._cleanup_socket()

    # ── CompanyRoot initialization ────────────────────────────────────

    async def _init_company_root(self) -> None:
        """Initialize CompanyRoot and RuntimeAPI after bot is connected.

        Uses CommunicationPort (registered by bot on_ready) for all outbound messaging.
        Detects active project from bot and initializes supervision tree.
        """
        runtime_api = await self._create_runtime_api()
        self._register_socket_endpoints()
        await self._init_project(runtime_api)
        await self._send_boot_notifications()

    async def _create_runtime_api(self) -> RuntimeAPI:
        """Create CompanyRoot and wrap in RuntimeAPI."""
        from vcompany.supervisor.company_root import CompanyRoot
        from vcompany.tmux.session import TmuxManager

        # Claude health check for degraded mode
        async def claude_health_check() -> bool:
            try:
                import anthropic
                client = anthropic.AsyncAnthropic()
                await client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1,
                    messages=[{"role": "user", "content": "ping"}],
                )
                return True
            except Exception:
                return False

        # Create TmuxManager
        tmux_manager = TmuxManager()

        # Determine project_dir and project_config
        project_dir = self._project_dir or getattr(self._bot, 'project_dir', None)
        project_config = self._project_config or getattr(self._bot, 'project_config', None)

        # Auto-detect active project if not provided
        if project_dir is None and project_config is None:
            detected = getattr(self._bot, '_detect_active_project', lambda: None)()
            if detected:
                project_dir, project_config = detected
                self._bot.project_dir = project_dir
                self._bot.project_config = project_config
                logger.info("Auto-detected active project: %s", project_config.project)

        self._project_dir = project_dir
        self._project_config = project_config
        data_dir = project_dir / "state" / "supervision" if project_dir else None

        # Create comm_port getter (lazy -- uses Noop until Discord adapter is set)
        def comm_port_getter() -> CommunicationPort:
            if self._comm_port is not None:
                return self._comm_port
            return NoopCommunicationPort()

        # Forward reference for callbacks that need RuntimeAPI before it exists
        api_ref: list[RuntimeAPI | None] = [None]

        async def _noop_async() -> None:
            pass

        company_root = CompanyRoot(
            on_escalation=lambda msg: api_ref[0]._on_escalation(msg) if api_ref[0] else _noop_async(),
            max_restarts=3,
            window_seconds=600,
            data_dir=data_dir,
            on_health_change=None,  # Health cog wiring deferred to Phase 22
            health_check=claude_health_check,
            on_degraded=lambda: api_ref[0]._on_degraded() if api_ref[0] else _noop_async(),
            on_recovered=lambda: api_ref[0]._on_recovered() if api_ref[0] else _noop_async(),
            tmux_manager=tmux_manager,
            project_dir=project_dir,
        )
        await company_root.start()
        self._company_root = company_root

        # Create RuntimeAPI
        runtime_api = RuntimeAPI(company_root, comm_port_getter)
        api_ref[0] = runtime_api
        self._runtime_api = runtime_api
        logger.info("RuntimeAPI initialized")

        # Register channel IDs from bot's system channels (if available)
        if hasattr(self._bot, '_system_channels'):
            channel_map = {
                name: str(ch.id)
                for name, ch in self._bot._system_channels.items()
            }
            runtime_api.register_channels(channel_map)

        return runtime_api

    def _register_socket_endpoints(self) -> None:
        """Register RuntimeAPI methods as socket API endpoints."""
        if self._server and self._runtime_api:
            self._server.register_method("hire", self._handle_hire)
            self._server.register_method("give_task", self._handle_give_task)
            self._server.register_method("dismiss", self._handle_dismiss)
            self._server.register_method("status", self._handle_status)
            self._server.register_method("health_tree", self._handle_health_tree)
            self._server.register_method("new_project", self._handle_new_project)

    async def _init_project(self, runtime_api: RuntimeAPI) -> None:
        """Initialize project if config available. Wire cogs through RuntimeAPI only.

        IMPORTANT (EXTRACT-04): Bot cogs do NOT receive direct PlanReviewer or PMTier
        references. All business logic flows through RuntimeAPI. PlanReviewCog and
        WorkflowOrchestratorCog will be fully rewired in Phase 22 (BOT-01..05).
        For now, cogs that need PlanReviewer/PMTier functionality call
        RuntimeAPI.handle_plan_approval() / handle_plan_rejection() instead.
        """
        project_config = self._project_config
        project_dir = self._project_dir

        if project_config is None or project_dir is None:
            logger.info("No project loaded -- running in Strategist-only mode")
            return

        persona_path = getattr(self._bot, '_strategist_persona_path', None)

        # Wire StrategistCog to CompanyAgent via RuntimeAPI
        await runtime_api.new_project(project_config, project_dir, persona_path)

        # NOTE: StrategistCog and PlanReviewCog access RuntimeAPI exclusively.
        # No direct container injection needed — cogs use _get_runtime_api(self.bot).
        #   daemon.runtime_api.handle_plan_approval(agent_id, plan_path)
        #   daemon.runtime_api.handle_plan_rejection(agent_id, plan_path, feedback)
        # This is wired in Plan 20-04 when cogs are updated.

        logger.info("Project %s initialized in daemon", project_config.project)

    # ── Socket API handlers ───────────────────────────────────────────

    async def _handle_hire(self, params: dict) -> dict:
        if not self._runtime_api:
            raise RuntimeError("RuntimeAPI not initialized")
        agent_id = await self._runtime_api.hire(params["agent_id"], params.get("template", "generic"))
        return {"agent_id": agent_id}

    async def _handle_give_task(self, params: dict) -> dict:
        if not self._runtime_api:
            raise RuntimeError("RuntimeAPI not initialized")
        await self._runtime_api.give_task(params["agent_id"], params["task"])
        return {"status": "ok"}

    async def _handle_dismiss(self, params: dict) -> dict:
        if not self._runtime_api:
            raise RuntimeError("RuntimeAPI not initialized")
        await self._runtime_api.dismiss(params["agent_id"])
        return {"status": "ok"}

    async def _handle_status(self, params: dict) -> dict:
        if not self._runtime_api:
            raise RuntimeError("RuntimeAPI not initialized")
        return await self._runtime_api.status()

    async def _handle_health_tree(self, params: dict) -> dict:
        if not self._runtime_api:
            raise RuntimeError("RuntimeAPI not initialized")
        return await self._runtime_api.health_tree()

    async def _handle_new_project(self, params: dict) -> dict:
        """Socket handler for new_project: loads config server-side, calls RuntimeAPI."""
        if not self._runtime_api:
            raise RuntimeError("RuntimeAPI not initialized")

        project_dir = Path(params["project_dir"])
        config_path = project_dir / "agents.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"agents.yaml not found at {config_path}")

        from vcompany.models.config import load_config

        config = load_config(config_path)
        persona_path_str = params.get("persona_path")
        persona_path = Path(persona_path_str) if persona_path_str else None

        self._project_dir = project_dir
        self._project_config = config

        await self._runtime_api.new_project(config, project_dir, persona_path)

        return {"status": "ok", "project": config.project}

    # ── Boot notifications ────────────────────────────────────────────

    async def _send_boot_notifications(self) -> None:
        """Send boot notifications via CommunicationPort."""
        if not self._runtime_api or not self._comm_port:
            return

        restart_signal = Path.home() / ".vco-restart-requested"
        is_restart = restart_signal.exists()
        if is_restart:
            restart_signal.unlink(missing_ok=True)

        alerts_id = self._runtime_api.get_channel_id("alerts")
        if alerts_id:
            msg = (
                "vCompany restarted successfully. All systems online."
                if is_restart
                else "vCompany is online."
            )
            await self._comm_port.send_message(SendMessagePayload(channel_id=alerts_id, content=msg))

        strategist_id = self._runtime_api.get_channel_id("strategist")
        if strategist_id:
            msg = (
                "[system] `vco restart` complete - vCompany is back online."
                if is_restart
                else "[system] `vco up` - vCompany is online."
            )
            await self._comm_port.send_message(SendMessagePayload(channel_id=strategist_id, content=msg))

    # ── Signal and lifecycle ──────────────────────────────────────────

    def _signal_shutdown(self) -> None:
        """Signal handler. Sets event only -- NO async work."""
        if not self._shutdown_event.is_set():
            self._shutdown_event.set()

    async def _handle_shutdown(self, params: dict) -> dict:
        """Socket API shutdown method. Sets shutdown event."""
        self._shutdown_event.set()
        return {"status": "shutting_down"}

    def _check_already_running(self) -> None:
        """Refuse to start if daemon already running. Clean stale files."""
        if self._pid_path.exists():
            try:
                old_pid = int(self._pid_path.read_text().strip())
                os.kill(old_pid, 0)  # Signal 0 = existence check
                raise SystemExit(f"Daemon already running (PID {old_pid})")
            except ProcessLookupError:
                logger.warning(
                    "Stale PID file found (PID %s not running), cleaning up",
                    old_pid,
                )
                self._pid_path.unlink(missing_ok=True)
                self._socket_path.unlink(missing_ok=True)
            except PermissionError:
                old_pid_text = self._pid_path.read_text().strip()
                raise SystemExit(f"PID {old_pid_text} exists but is not ours")

    def _write_pid_file(self) -> None:
        """Write current PID to PID file."""
        self._pid_path.parent.mkdir(parents=True, exist_ok=True)
        self._pid_path.write_text(str(os.getpid()))
        logger.info("PID file written: %s (PID %s)", self._pid_path, os.getpid())

    def _cleanup_pid_file(self) -> None:
        """Remove PID file."""
        self._pid_path.unlink(missing_ok=True)

    def _cleanup_socket(self) -> None:
        """Remove socket file."""
        self._socket_path.unlink(missing_ok=True)

    async def _shutdown(self) -> None:
        """Ordered shutdown: CompanyRoot -> socket server -> bot -> files."""
        if self._company_root is not None:
            await self._company_root.stop()
            logger.info("CompanyRoot stopped")
        if self._server:
            await self._server.stop()
            logger.info("Socket server stopped")
        if self._bot_task and not self._bot_task.done():
            await self._bot.close()
            try:
                await asyncio.wait_for(self._bot_task, timeout=10.0)
            except asyncio.TimeoutError:
                self._bot_task.cancel()
            logger.info("Bot stopped")
