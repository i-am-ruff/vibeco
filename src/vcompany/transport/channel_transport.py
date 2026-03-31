"""ChannelTransport protocol for v4.0 transport channel architecture.

Defines the socket-based transport protocol where the transport spawns a
worker process and communicates via Unix domain sockets. Supports reconnection
to surviving workers after daemon restart.

Replaces the v3.1 AgentTransport protocol (exec/send_keys/read_file) with
a simpler model: spawn a worker, connect via Unix socket, communicate via
NDJSON channel protocol.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable


@runtime_checkable
class ChannelTransport(Protocol):
    """Transport protocol for spawning and connecting to vco-worker processes.

    Implementations create an execution environment (local subprocess,
    Docker container, network connection) and return a (reader, writer)
    pair connected via Unix domain socket for NDJSON channel protocol
    communication.

    The caller is responsible for sending StartMessage and reading
    WorkerMessages through the reader/writer pair.
    """

    async def spawn(
        self,
        agent_id: str,
        *,
        config: dict,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Spawn vco-worker and return (reader, writer) for channel protocol.

        Spawns the worker process and connects to its Unix domain socket.
        The returned reader/writer are for NDJSON channel messages.

        Args:
            agent_id: Unique identifier for the agent.
            config: Configuration blob to pass to the worker.
            env: Additional environment variables for the worker process.
            working_dir: Working directory for the worker process.

        Returns:
            Tuple of (asyncio.StreamReader, asyncio.StreamWriter) connected
            to the worker's Unix domain socket.
        """
        ...

    async def connect(self, agent_id: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Connect to an already-running worker's socket.

        Used for reconnection after daemon restart. Raises ConnectionError
        if the worker is not reachable.

        Args:
            agent_id: The agent to reconnect to.

        Returns:
            Tuple of (asyncio.StreamReader, asyncio.StreamWriter) connected
            to the worker's Unix domain socket.

        Raises:
            ConnectionError: If the worker's socket does not exist or is
                not accepting connections.
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
