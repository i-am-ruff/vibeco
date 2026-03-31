"""ChannelTransport protocol for v4.0 transport channel architecture.

Defines the spawn-based transport protocol where the transport only creates
the execution environment and pipes stdin/stdout. All agent logic lives in
vco-worker on the other side of the channel.

Replaces the v3.1 AgentTransport protocol (exec/send_keys/read_file) with
a simpler model: spawn a process, get stdin/stdout pipes, communicate via
NDJSON channel protocol.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable


@runtime_checkable
class ChannelTransport(Protocol):
    """Transport protocol for spawning vco-worker processes.

    Implementations create an execution environment (local subprocess,
    Docker container, network connection) and return a process handle
    with stdin/stdout piped for NDJSON channel protocol communication.

    The caller is responsible for sending StartMessage and reading
    WorkerMessages through the process pipes.
    """

    async def spawn(
        self,
        agent_id: str,
        *,
        config: dict,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> asyncio.subprocess.Process:
        """Spawn vco-worker and return process with stdin/stdout piped.

        Args:
            agent_id: Unique identifier for the agent.
            config: Configuration blob to pass to the worker.
            env: Additional environment variables for the worker process.
            working_dir: Working directory for the worker process.

        Returns:
            asyncio.subprocess.Process with stdin/stdout/stderr piped.
        """
        ...

    async def terminate(self, agent_id: str) -> None:
        """Force-terminate the execution environment for an agent.

        Args:
            agent_id: The agent whose environment to terminate.
        """
        ...

    @property
    def transport_type(self) -> str:
        """Return the transport type identifier (e.g. 'native', 'docker')."""
        ...
