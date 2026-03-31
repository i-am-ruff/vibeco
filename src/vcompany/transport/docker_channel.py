"""DockerChannelTransport — Docker container implementation of ChannelTransport.

Spawns vco-worker inside a Docker container via `docker run -i` with
stdin/stdout piped for NDJSON channel protocol communication.

Key differences from v3.1 DockerTransport:
- No docker-py SDK (uses subprocess `docker run -i`)
- No socket mounts (no daemon socket, no signal socket)
- No TTY (-t flag omitted to prevent NDJSON corruption)
- No tmux inside container
- Uses --rm for auto-cleanup
- Returns process with stdin/stdout — identical interface to NativeTransport
"""

from __future__ import annotations

import asyncio
import logging
import subprocess

logger = logging.getLogger("vcompany.transport.docker_channel")


class DockerChannelTransport:
    """Spawn vco-worker inside Docker containers.

    Each agent gets an isolated container running vco-worker. Communication
    happens exclusively through stdin/stdout pipes (NDJSON channel protocol).
    No filesystem sharing beyond an optional workspace mount.
    """

    def __init__(self, docker_image: str = "vco-agent:latest") -> None:
        self._image = docker_image
        self._containers: dict[str, str] = {}  # agent_id -> container_name
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def spawn(
        self,
        agent_id: str,
        *,
        config: dict,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> asyncio.subprocess.Process:
        """Spawn vco-worker inside a Docker container.

        Uses `docker run -i` (no -t) to get clean stdin/stdout pipes.
        Container runs with --rm for auto-cleanup and --network none
        for isolation.
        """
        container_name = f"vco-{agent_id}"

        cmd: list[str] = [
            "docker", "run", "-i", "--rm",
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

        # Image and entrypoint
        cmd.extend([self._image, "python", "-m", "vco_worker"])

        logger.info(
            "Spawning Docker container %s for agent %s (image=%s)",
            container_name,
            agent_id,
            self._image,
        )

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._containers[agent_id] = container_name
        self._processes[agent_id] = process
        logger.info(
            "Docker worker spawned for agent %s (container=%s, pid=%d)",
            agent_id,
            container_name,
            process.pid or -1,
        )
        return process

    async def terminate(self, agent_id: str) -> None:
        """Terminate the Docker container for an agent.

        Uses `docker kill` to stop the container, then cleans up
        the local docker client process.
        """
        container_name = self._containers.pop(agent_id, None)
        process = self._processes.pop(agent_id, None)

        if container_name:
            logger.info("Killing Docker container %s for agent %s", container_name, agent_id)
            subprocess.run(
                ["docker", "kill", container_name],
                capture_output=True,
            )

        if process:
            process.terminate()

    @property
    def transport_type(self) -> str:
        """Return 'docker' transport type."""
        return "docker"
