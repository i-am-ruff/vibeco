"""NativeTransport -- local subprocess implementation of ChannelTransport.

Spawns vco-worker as a local Python subprocess with --socket flag for
Unix domain socket communication. Workers run in their own session
(start_new_session=True) so they survive daemon death.

Communication happens via Unix domain sockets, not stdin/stdout pipes.
This enables reconnection after daemon restart.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("vcompany.transport.native")


class NativeTransport:
    """Spawn vco-worker as a local subprocess with socket-based communication.

    Workers are spawned with start_new_session=True so they survive daemon
    death. Communication uses Unix domain sockets rather than stdin/stdout
    pipes, enabling reconnection after daemon restart.
    """

    SOCKET_DIR = Path("/tmp")

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    def _socket_path(self, agent_id: str) -> Path:
        """Return the Unix socket path for a given agent."""
        return self.SOCKET_DIR / f"vco-worker-{agent_id}.sock"

    async def spawn(
        self,
        agent_id: str,
        *,
        config: dict,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Spawn vco-worker as a detached local subprocess.

        Uses sys.executable to ensure the same Python interpreter is used.
        Worker is spawned with --socket flag and start_new_session=True
        so it survives daemon death. stdin is DEVNULL (not piped).
        """
        socket_path = self._socket_path(agent_id)
        cmd = [sys.executable, "-m", "vco_worker", "--socket", str(socket_path)]

        # Build merged environment
        merged_env = dict(os.environ)
        if env:
            merged_env.update(env)
        merged_env["VCO_AGENT_ID"] = agent_id

        logger.info("Spawning vco-worker for agent %s (cwd=%s, socket=%s)", agent_id, working_dir, socket_path)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
            env=merged_env,
            start_new_session=True,  # Survive daemon death
        )

        self._processes[agent_id] = process
        logger.info(
            "Worker spawned for %s (pid=%d, socket=%s)", agent_id, process.pid or -1, socket_path
        )

        # Wait for socket to appear (worker needs time to bind)
        reader, writer = await self._wait_for_socket(agent_id, timeout=10.0)
        return reader, writer

    async def connect(self, agent_id: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Connect to an already-running worker's socket.

        Used for reconnection after daemon restart. Raises ConnectionError
        if the worker's socket does not exist.
        """
        socket_path = self._socket_path(agent_id)
        if not socket_path.exists():
            raise ConnectionError(f"No socket for agent {agent_id} at {socket_path}")
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        logger.info("Connected to existing worker %s via %s", agent_id, socket_path)
        return reader, writer

    async def _wait_for_socket(
        self, agent_id: str, timeout: float = 10.0
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Wait for worker to create socket, then connect."""
        socket_path = self._socket_path(agent_id)
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if socket_path.exists():
                try:
                    return await asyncio.open_unix_connection(str(socket_path))
                except (ConnectionRefusedError, FileNotFoundError):
                    pass
            await asyncio.sleep(0.1)
        raise TimeoutError(f"Worker {agent_id} did not create socket within {timeout}s")

    async def terminate(self, agent_id: str) -> None:
        """Terminate the local subprocess for an agent.

        Sends SIGTERM first, waits up to 5 seconds, then SIGKILL.
        Cleans up the socket file.
        """
        process = self._processes.pop(agent_id, None)
        socket_path = self._socket_path(agent_id)

        if process:
            logger.info("Terminating worker for agent %s", agent_id)
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "Worker for agent %s did not exit after SIGTERM, sending SIGKILL",
                    agent_id,
                )
                process.kill()

        socket_path.unlink(missing_ok=True)

    @property
    def transport_type(self) -> str:
        """Return 'native' transport type."""
        return "native"
