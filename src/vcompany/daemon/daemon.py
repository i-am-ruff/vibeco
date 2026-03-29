"""Runtime daemon managing bot, socket API, and RuntimeAPI gateway.

Owns: PID file, signal handlers, SocketServer, bot lifecycle, RuntimeAPI.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

from vcompany.daemon.comm import CommunicationPort
from vcompany.daemon.runtime_api import RuntimeAPI
from vcompany.daemon.server import SocketServer
from vcompany.shared.paths import VCO_PID_PATH, VCO_SOCKET_PATH

logger = logging.getLogger("vcompany.daemon")


class Daemon:
    """Runtime daemon managing bot, socket API, and RuntimeAPI gateway.

    Owns: PID file, signal handlers, SocketServer, bot lifecycle, RuntimeAPI.
    """

    def __init__(
        self,
        bot: object,
        bot_token: str,
        socket_path: Path | None = None,
        pid_path: Path | None = None,
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
        """Main async lifecycle: PID -> signals -> socket -> bot -> wait -> shutdown."""
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

            # Start Discord bot (DAEMON-06: bot.start() not bot.run())
            self._bot_task = asyncio.create_task(self._bot.start(self._bot_token))
            logger.info("Bot starting...")

            # Wait for shutdown signal
            await self._shutdown_event.wait()
            logger.info("Shutdown signal received, cleaning up...")

            # Graceful shutdown sequence
            await self._shutdown()
        finally:
            self._cleanup_pid_file()
            self._cleanup_socket()

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
        """Ordered shutdown: socket server -> bot -> files."""
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
