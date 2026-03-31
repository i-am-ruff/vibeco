"""DockerChannelTransport -- Docker container implementation of ChannelTransport.

Spawns vco-worker inside a Docker container via `docker run -d` (detached)
with a socket directory mounted for Unix domain socket communication.

Key differences from v3.1 DockerTransport:
- No docker-py SDK (uses subprocess `docker run -d`)
- Socket directory mounted for communication (/var/run/vco)
- No TTY (-t flag omitted to prevent NDJSON corruption)
- Detached mode (-d, no -i, no --rm) -- containers survive daemon death
- Returns (reader, writer) pair connected via Unix domain socket
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("vcompany.transport.docker_channel")


class DockerChannelTransport:
    """Spawn vco-worker inside Docker containers with socket-based communication.

    Each agent gets an isolated container running vco-worker in detached mode.
    Communication happens through Unix domain sockets via a mounted directory.
    Containers survive daemon death (no --rm, no -i).
    """

    SOCKET_DIR = Path("/tmp/vco-sockets")

    def __init__(self, docker_image: str = "vco-agent:latest") -> None:
        self._image = docker_image
        self._containers: dict[str, str] = {}  # agent_id -> container_name
        self.SOCKET_DIR.mkdir(parents=True, exist_ok=True)

    def _socket_path(self, agent_id: str) -> Path:
        """Return the Unix socket path on the host for a given agent."""
        return self.SOCKET_DIR / f"vco-worker-{agent_id}.sock"

    async def spawn(
        self,
        agent_id: str,
        *,
        config: dict,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Spawn vco-worker inside a Docker container in detached mode.

        Uses `docker run -d` (no -i, no --rm) so the container survives
        daemon death. Communication via Unix domain socket mounted at
        /var/run/vco inside the container.
        """
        container_name = f"vco-{agent_id}"
        socket_path = self._socket_path(agent_id)
        # Socket path inside container
        container_socket = f"/var/run/vco/vco-worker-{agent_id}.sock"

        cmd: list[str] = [
            "docker", "run", "-d",
            "--name", container_name,
            "--network", "none",
        ]

        # Environment variables
        if env:
            for key, value in env.items():
                cmd.extend(["-e", f"{key}={value}"])
        cmd.extend(["-e", f"VCO_AGENT_ID={agent_id}"])

        # Optional workspace mount
        if working_dir:
            cmd.extend(["-v", f"{working_dir}:/workspace", "-w", "/workspace"])

        # Mount socket directory
        cmd.extend(["-v", f"{self.SOCKET_DIR}:/var/run/vco"])

        # Image and entrypoint
        cmd.extend([
            self._image, "python", "-m", "vco_worker",
            "--socket", container_socket,
        ])

        logger.info(
            "Spawning Docker container %s for agent %s (image=%s)",
            container_name,
            agent_id,
            self._image,
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"docker run failed: {stderr.decode()}")

        self._containers[agent_id] = container_name
        logger.info("Docker container %s started for %s", container_name, agent_id)

        # Wait for socket to appear on host (via mount)
        reader, writer = await self._wait_for_socket(agent_id, timeout=15.0)
        return reader, writer

    async def connect(self, agent_id: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Connect to an already-running Docker worker's socket.

        Used for reconnection after daemon restart. Raises ConnectionError
        if the worker's socket does not exist on the host.
        """
        socket_path = self._socket_path(agent_id)
        if not socket_path.exists():
            raise ConnectionError(f"No socket for agent {agent_id} at {socket_path}")
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        logger.info("Connected to existing Docker worker %s", agent_id)
        return reader, writer

    async def _wait_for_socket(
        self, agent_id: str, timeout: float = 15.0
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Wait for Docker worker to create socket on host, then connect."""
        socket_path = self._socket_path(agent_id)
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if socket_path.exists():
                try:
                    return await asyncio.open_unix_connection(str(socket_path))
                except (ConnectionRefusedError, FileNotFoundError):
                    pass
            await asyncio.sleep(0.2)
        raise TimeoutError(f"Docker worker {agent_id} socket not ready within {timeout}s")

    async def terminate(self, agent_id: str) -> None:
        """Terminate the Docker container for an agent.

        Uses `docker stop` then `docker rm -f` to clean up. Also removes
        the socket file from the host.
        """
        container_name = self._containers.pop(agent_id, None)

        if container_name:
            logger.info("Stopping Docker container %s for agent %s", container_name, agent_id)
            subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                timeout=5,
            )

        socket_path = self._socket_path(agent_id)
        socket_path.unlink(missing_ok=True)

    @property
    def transport_type(self) -> str:
        """Return 'docker' transport type."""
        return "docker"
