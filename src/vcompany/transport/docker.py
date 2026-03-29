"""DockerTransport -- Docker container execution via docker-py SDK.

Implements the AgentTransport protocol for running agents inside Docker
containers. Each agent gets an isolated container with volume-mounted
workspace, daemon socket, and signal socket.

Container lifecycle follows create-once, start/stop pattern (DOCK-06):
existing containers are reused across teardown/setup cycles.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

import docker
import docker.errors

from vcompany.shared.paths import VCO_SOCKET_PATH

logger = logging.getLogger("vcompany.transport.docker")


@dataclass
class _DockerSession:
    """Internal tracking for a single agent's Docker container session."""

    container_name: str
    working_dir: Path  # host path to agent clone
    container_workdir: str = "/workspace"
    interactive: bool = True
    container_id: str | None = None  # set after create/find


class DockerTransport:
    """Docker container execution via docker-py SDK.

    Implements all 8 AgentTransport protocol methods. Interactive agents
    get a tmux session inside the container; piped agents use docker exec
    directly.
    """

    def __init__(
        self, docker_image: str = "vco-agent:latest", project_name: str = ""
    ) -> None:
        self._client: docker.DockerClient = docker.from_env()
        self._image = docker_image
        self._project = project_name
        self._sessions: dict[str, _DockerSession] = {}

    async def setup(self, agent_id: str, working_dir: Path, **kwargs) -> None:
        """Prepare Docker container for agent execution.

        Reuses existing containers (running or stopped) per DOCK-06.
        Mounts workspace, daemon socket, and signal socket per DOCK-03/04.
        Starts tmux session inside container for interactive agents.
        """
        interactive = kwargs.get("interactive", True)
        container_name = f"vco-{self._project}-{agent_id}"

        session = _DockerSession(
            container_name=container_name,
            working_dir=working_dir,
            interactive=interactive,
        )
        self._sessions[agent_id] = session

        # Try to find existing container (D-06: container reuse)
        container = None
        try:
            container = await asyncio.to_thread(
                self._client.containers.get, container_name
            )
            if container.status == "running":
                logger.info("Reusing running container %s", container_name)
            else:
                logger.info("Restarting stopped container %s", container_name)
                await asyncio.to_thread(container.start)
        except docker.errors.NotFound:
            # Create new container
            signal_sock = str(VCO_SOCKET_PATH.parent / "vco-signal.sock")
            volumes = {
                str(working_dir): {"bind": "/workspace", "mode": "rw"},
                str(VCO_SOCKET_PATH): {
                    "bind": str(VCO_SOCKET_PATH),
                    "mode": "rw",
                },
                signal_sock: {"bind": signal_sock, "mode": "rw"},
            }
            environment = {
                "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
                "VCO_AGENT_ID": agent_id,
            }
            container = await asyncio.to_thread(
                self._client.containers.create,
                image=self._image,
                name=container_name,
                volumes=volumes,
                environment=environment,
                stdin_open=True,
                tty=True,
                network_mode="none",
                working_dir="/workspace",
            )
            await asyncio.to_thread(container.start)
            logger.info("Created and started container %s", container_name)

        # Refresh status after start (pitfall 5: stale status)
        await asyncio.to_thread(container.reload)
        session.container_id = container.id

        # Parametric customization (D-06)
        tweakcc_profile = kwargs.get("tweakcc_profile")
        settings_json = kwargs.get("settings_json")

        if tweakcc_profile:
            await self._apply_tweakcc_profile(container, tweakcc_profile)

        if settings_json:
            await self._apply_settings(container, settings_json)

        # Start tmux session inside container for interactive mode
        if interactive:
            await asyncio.to_thread(
                container.exec_run,
                ["tmux", "new-session", "-d", "-s", "main"],
            )

    async def _apply_tweakcc_profile(self, container, profile_name: str) -> None:
        """Copy tweakcc profile into container's Claude config directory."""
        host_profile_dir = Path.home() / ".claude" / "tweakcc" / profile_name
        if not host_profile_dir.exists():
            logger.warning(
                "tweakcc profile %s not found at %s, skipping",
                profile_name,
                host_profile_dir,
            )
            return

        # Use docker cp to copy profile directory into container
        container_id = container.id
        dest = f"{container_id}:/root/.claude/tweakcc/{profile_name}"
        await asyncio.to_thread(
            subprocess.run,
            ["docker", "cp", str(host_profile_dir), dest],
            check=True,
            capture_output=True,
        )
        logger.info(
            "Applied tweakcc profile %s to container %s",
            profile_name,
            container.name,
        )

    async def _apply_settings(self, container, settings_content: str) -> None:
        """Write custom settings.json into container's Claude config directory."""
        await asyncio.to_thread(
            container.exec_run,
            [
                "sh",
                "-c",
                f"mkdir -p /root/.claude && cat > /root/.claude/settings.json << 'SETTINGSEOF'\n{settings_content}\nSETTINGSEOF",
            ],
        )
        logger.info("Applied custom settings.json to container %s", container.name)

    async def teardown(self, agent_id: str) -> None:
        """Stop container but keep it for restart (D-05).

        Container is stopped, not removed, so it can be reused on next setup().
        """
        session = self._sessions.pop(agent_id, None)
        if session is None:
            return
        try:
            container = await asyncio.to_thread(
                self._client.containers.get, session.container_id
            )
            await asyncio.to_thread(container.stop)
            logger.info(
                "Stopped container %s, kept for restart",
                session.container_name,
            )
        except docker.errors.NotFound:
            logger.warning(
                "Container %s already removed", session.container_name
            )

    async def exec(
        self,
        agent_id: str,
        command: str | list[str],
        *,
        stdin: str | None = None,
        timeout: float | None = None,
    ) -> str:
        """Execute command via tmux send-keys (interactive) or docker exec (piped)."""
        session = self._sessions.get(agent_id)
        if session is None:
            raise RuntimeError(f"No session for agent {agent_id}")

        container = await asyncio.to_thread(
            self._client.containers.get, session.container_id
        )

        if session.interactive:
            # Send command to tmux pane (fire-and-forget)
            cmd_str = command if isinstance(command, str) else " ".join(command)
            await asyncio.to_thread(
                container.exec_run,
                ["tmux", "send-keys", "-t", "main", cmd_str, "Enter"],
                detach=True,
            )
            return ""
        else:
            # Piped: run command and capture output
            cmd_list = command if isinstance(command, list) else command.split()
            exit_code, output = await asyncio.to_thread(
                container.exec_run,
                cmd_list,
                workdir=session.container_workdir,
            )
            if exit_code != 0:
                out_text = output.decode()[:500] if output else ""
                raise RuntimeError(
                    f"Command failed (exit {exit_code}): {out_text}"
                )
            return output.decode() if output else ""

    async def exec_streaming(
        self,
        agent_id: str,
        command: list[str],
        *,
        stdin: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield stdout chunks from docker exec (piped mode only).

        Bridges the sync docker-py generator to async using run_in_executor.
        """
        session = self._sessions.get(agent_id)
        if session is None:
            raise RuntimeError(f"No session for agent {agent_id}")

        if session.interactive:
            return  # No streaming for interactive tmux mode

        container = await asyncio.to_thread(
            self._client.containers.get, session.container_id
        )

        _, output_gen = await asyncio.to_thread(
            container.exec_run,
            command,
            stream=True,
            workdir=session.container_workdir,
        )

        # Bridge sync generator to async
        loop = asyncio.get_event_loop()
        sentinel = object()
        while True:
            chunk = await loop.run_in_executor(
                None, next, output_gen, sentinel
            )
            if chunk is sentinel:
                break
            yield chunk.decode() if isinstance(chunk, bytes) else chunk

    def is_alive(self, agent_id: str) -> bool:
        """Two-layer liveness check: container running + tmux session exists (D-11).

        Synchronous -- called from health check loops.
        """
        session = self._sessions.get(agent_id)
        if session is None:
            return False

        try:
            container = self._client.containers.get(session.container_id)
            container.reload()  # Refresh status (pitfall 5)

            # Layer 1: container must be running
            if container.status != "running":
                return False

            # Layer 2: tmux session must exist inside container
            exit_code, _ = container.exec_run(
                ["tmux", "has-session", "-t", "main"]
            )
            return exit_code == 0
        except docker.errors.NotFound:
            return False

    async def send_keys(
        self, agent_id: str, keys: str, *, enter: bool = False
    ) -> None:
        """Send raw keystrokes to tmux pane inside container."""
        session = self._sessions.get(agent_id)
        if session is None or not session.interactive:
            return

        container = await asyncio.to_thread(
            self._client.containers.get, session.container_id
        )

        cmd = ["tmux", "send-keys", "-t", "main", keys]
        if enter:
            cmd.append("Enter")
        await asyncio.to_thread(container.exec_run, cmd, detach=True)

    def _resolve_host_path(self, session: _DockerSession, path: Path) -> Path:
        """Map container path or relative path to host filesystem path.

        Volume-based file I/O (Pattern 6 from research): since the workspace
        is bind-mounted, we resolve paths through the host filesystem.
        """
        path_str = str(path)
        if path_str.startswith(session.container_workdir):
            relative = path_str[len(session.container_workdir) :].lstrip("/")
            return session.working_dir / relative
        if not path.is_absolute():
            return session.working_dir / path
        return path  # Assume host path if absolute and not in container

    async def read_file(self, agent_id: str, path: Path) -> str:
        """Read file via host filesystem (volume-mounted workspace)."""
        session = self._sessions.get(agent_id)
        if session is None:
            raise RuntimeError(f"No session for agent {agent_id}")
        host_path = self._resolve_host_path(session, path)
        return await asyncio.to_thread(host_path.read_text)

    async def write_file(self, agent_id: str, path: Path, content: str) -> None:
        """Write file via host filesystem (volume-mounted workspace)."""
        session = self._sessions.get(agent_id)
        if session is None:
            raise RuntimeError(f"No session for agent {agent_id}")
        host_path = self._resolve_host_path(session, path)
        await asyncio.to_thread(host_path.write_text, content)
