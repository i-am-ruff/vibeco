"""AgentTransport protocol and NoopTransport for testing.

Defines the AgentTransport protocol that any execution environment adapter
(local tmux, Docker, network) must satisfy. The container layer uses this
protocol exclusively for all agent execution -- no tmux/subprocess imports
allowed here.

Follows the same @runtime_checkable Protocol pattern as CommunicationPort
in daemon/comm.py (decision D-01).
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class AgentTransport(Protocol):
    """Execution environment abstraction for agents (D-01: thin transport).

    Any adapter (local tmux+subprocess, Docker, network) must implement
    these async methods. Used by the container layer for all agent execution.
    """

    async def setup(self, agent_id: str, working_dir: Path, **kwargs) -> None:
        """Prepare the execution environment.

        kwargs may include:
          - interactive: bool (True = tmux, False = piped subprocess)
          - session_name: str (tmux session name)
          - window_name: str (tmux window/pane name)
        """
        ...

    async def teardown(self, agent_id: str) -> None:
        """Clean up the execution environment."""
        ...

    async def exec(
        self,
        agent_id: str,
        command: str | list[str],
        *,
        stdin: str | None = None,
        timeout: float | None = None,
    ) -> str:
        """Execute a command and return stdout.

        For interactive (tmux) agents: sends command to pane, returns empty string.
        For piped agents: runs subprocess, returns stdout.
        """
        ...

    async def exec_streaming(
        self,
        agent_id: str,
        command: list[str],
        *,
        stdin: str | None = None,
    ) -> AsyncIterator[str]:
        """Execute a command and yield stdout lines as they arrive.

        Used by StrategistConversation for streaming tool-use progress.
        Only meaningful for piped (subprocess) mode.
        """
        ...

    def is_alive(self, agent_id: str) -> bool:
        """Check if the agent's execution environment is still running."""
        ...

    async def send_keys(self, agent_id: str, keys: str, *, enter: bool = False) -> None:
        """Send raw keystrokes to the agent's execution environment.

        For interactive (tmux) agents: sends keys to the pane.
        For piped agents: no-op (no interactive terminal to send to).

        Used for workspace trust acceptance and similar interactive prompts
        that require raw key input rather than command execution.
        """
        ...

    async def read_file(self, agent_id: str, path: Path) -> str:
        """Read a file from the agent's environment (D-02)."""
        ...

    async def write_file(self, agent_id: str, path: Path, content: str) -> None:
        """Write a file to the agent's environment (D-02)."""
        ...


class NoopTransport:
    """No-op implementation of AgentTransport for testing and fallback."""

    async def setup(self, agent_id: str, working_dir: Path, **kwargs) -> None:
        pass

    async def teardown(self, agent_id: str) -> None:
        pass

    async def exec(
        self,
        agent_id: str,
        command: str | list[str],
        *,
        stdin: str | None = None,
        timeout: float | None = None,
    ) -> str:
        return ""

    async def exec_streaming(
        self,
        agent_id: str,
        command: list[str],
        *,
        stdin: str | None = None,
    ) -> AsyncIterator[str]:
        return
        yield  # Make this an async generator

    def is_alive(self, agent_id: str) -> bool:
        return True

    async def send_keys(self, agent_id: str, keys: str, *, enter: bool = False) -> None:
        pass

    async def read_file(self, agent_id: str, path: Path) -> str:
        return ""

    async def write_file(self, agent_id: str, path: Path, content: str) -> None:
        pass
