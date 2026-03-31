"""LocalTransport -- local execution via tmux (interactive) or subprocess (piped).

Wraps TmuxManager for interactive agents and asyncio.create_subprocess_exec
for piped agents, behind the AgentTransport protocol (D-06).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from vcompany.tmux.session import TmuxManager

logger = logging.getLogger("vcompany.transport.local")


@dataclass
class _AgentSession:
    """Internal tracking for a single agent's execution session."""

    working_dir: Path
    interactive: bool = True
    session_name: str | None = None
    window_name: str | None = None
    pane_id: str | None = None  # set after tmux setup


class LocalTransport:
    """Local execution via tmux (interactive) or subprocess (piped) -- D-06."""

    def __init__(self, tmux_manager: TmuxManager | None = None) -> None:
        self._tmux: TmuxManager | None = tmux_manager
        self._sessions: dict[str, _AgentSession] = {}

    async def setup(self, agent_id: str, working_dir: Path, **kwargs) -> None:
        """Prepare local execution environment (tmux pane or subprocess config)."""
        interactive = kwargs.get("interactive", True)
        session_name = kwargs.get("session_name")
        window_name = kwargs.get("window_name", agent_id)
        session = _AgentSession(
            working_dir=working_dir,
            interactive=interactive,
            session_name=session_name,
            window_name=window_name,
        )
        self._sessions[agent_id] = session

        if interactive and self._tmux is not None and session_name is not None:
            tmux_session = await asyncio.to_thread(
                self._tmux.get_or_create_session, session_name
            )
            pane = await asyncio.to_thread(
                self._tmux.create_pane, tmux_session, window_name=window_name
            )
            session.pane_id = pane.pane_id

    async def teardown(self, agent_id: str) -> None:
        """Clean up execution environment (kill tmux pane if interactive)."""
        session = self._sessions.pop(agent_id, None)
        if session is None:
            return
        if session.interactive and session.pane_id and self._tmux:
            pane = await asyncio.to_thread(
                self._tmux.get_pane_by_id, session.pane_id
            )
            if pane is not None:
                await asyncio.to_thread(self._tmux.kill_pane, pane)

    async def exec(
        self,
        agent_id: str,
        command: str | list[str],
        *,
        stdin: str | None = None,
        timeout: float | None = None,
    ) -> str:
        """Execute command via tmux (fire-and-forget) or subprocess (returns stdout)."""
        session = self._sessions.get(agent_id)
        if session is None:
            raise RuntimeError(f"No session for agent {agent_id}")

        if session.interactive:
            # Tmux: send command to pane (fire-and-forget)
            if self._tmux is None:
                return ""
            cmd_str = command if isinstance(command, str) else " ".join(command)
            target = session.pane_id or cmd_str
            await asyncio.to_thread(self._tmux.send_command, target, cmd_str)
            return ""
        else:
            # Piped subprocess — inject AGENT_ID so vco commands know who's talking
            import os
            env = {**os.environ, "AGENT_ID": agent_id, "VCO_AGENT_ID": agent_id}
            cmd_list = command if isinstance(command, list) else command.split()
            proc = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdin=asyncio.subprocess.PIPE if stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(session.working_dir),
                env=env,
            )
            coro = proc.communicate(input=stdin.encode() if stdin else None)
            if timeout:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(coro, timeout=timeout)
            else:
                stdout_bytes, stderr_bytes = await coro
            if proc.returncode != 0:
                stderr_text = stderr_bytes.decode()[:500] if stderr_bytes else ""
                raise RuntimeError(
                    f"Command failed (exit {proc.returncode}): {stderr_text}"
                )
            return stdout_bytes.decode() if stdout_bytes else ""

    async def exec_streaming(
        self,
        agent_id: str,
        command: list[str],
        *,
        stdin: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield stdout lines as they arrive (for piped subprocess mode).

        For interactive mode, yields nothing.
        """
        session = self._sessions.get(agent_id)
        if session is None:
            raise RuntimeError(f"No session for agent {agent_id}")

        if session.interactive:
            return  # No streaming for tmux mode

        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if stdin else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(session.working_dir),
        )
        if stdin and proc.stdin:
            proc.stdin.write(stdin.encode())
            await proc.stdin.drain()
            proc.stdin.close()

        if proc.stdout:
            async for line in proc.stdout:
                yield line.decode()

        await proc.wait()

    def is_alive(self, agent_id: str) -> bool:
        """Check if the agent's execution environment is still running."""
        session = self._sessions.get(agent_id)
        if session is None:
            return False
        if not session.interactive:
            return True  # Piped sessions are one-shot
        if self._tmux is None or session.pane_id is None:
            return True  # No tmux = test mode, assume alive
        pane = self._tmux.get_pane_by_id(session.pane_id)
        return pane is not None and self._tmux.is_alive(pane)

    async def send_keys(self, agent_id: str, keys: str, *, enter: bool = False) -> None:
        """Send raw keystrokes to the agent's tmux pane.

        For interactive agents: sends keys via TmuxManager's pane.send_keys().
        For piped agents: no-op (no interactive terminal).

        Args:
            agent_id: Agent whose pane receives the keys.
            keys: The key string to send (e.g., "" for empty, "y" for confirmation).
            enter: Whether to press Enter after sending keys.
        """
        session = self._sessions.get(agent_id)
        if session is None or not session.interactive:
            return  # No-op for piped or unknown agents
        if self._tmux is None or session.pane_id is None:
            return
        pane = await asyncio.to_thread(self._tmux.get_pane_by_id, session.pane_id)
        if pane is not None:
            await asyncio.to_thread(pane.send_keys, keys, enter=enter)

    async def read_file(self, agent_id: str, path: Path) -> str:
        """Read file from local filesystem (D-02 -- trivial for local)."""
        return await asyncio.to_thread(path.read_text)

    async def write_file(self, agent_id: str, path: Path, content: str) -> None:
        """Write file to local filesystem (D-02 -- trivial for local)."""
        await asyncio.to_thread(path.write_text, content)
