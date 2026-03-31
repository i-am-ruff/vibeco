"""NetworkTransport -- TCP-based transport for remote vco-worker connections.

Stub implementation for CHAN-04. Defines the contract for connecting to
workers over TCP instead of Unix domain sockets. The existing NDJSON channel
protocol framing works over any byte stream, so TCP works without changes.

Not production-ready: no TLS, no authentication, no automatic reconnection.
Those are v5 concerns.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class NetworkTransport:
    """TCP-based transport for remote vco-worker connections.

    Unlike NativeTransport and DockerChannelTransport, NetworkTransport
    does NOT spawn the worker process. The worker must be started
    independently on the remote machine and be listening on the
    configured host:port.

    spawn() and connect() both establish a TCP connection. The difference
    is semantic: spawn() is called on first hire, connect() on reconnection.
    Neither starts a remote process.

    Constructor args:
        host: Remote worker hostname or IP. Default "127.0.0.1" for local testing.
        port: Remote worker port. Default 0 means "use per-agent port from config".
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._host = host
        self._port = port
        self._connections: dict[str, tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}

    async def spawn(
        self,
        agent_id: str,
        *,
        config: dict,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Connect to a remote worker listening on host:port.

        Unlike Native/Docker transports, this does NOT start the worker.
        The worker must already be running on the remote machine.
        The config dict may contain 'port' to override the default port.
        """
        port = config.get("port", self._port) if config else self._port
        host = config.get("host", self._host) if config else self._host
        logger.info("Connecting to remote worker %s at %s:%d", agent_id, host, port)
        reader, writer = await asyncio.open_connection(host, port)
        self._connections[agent_id] = (reader, writer)
        return reader, writer

    async def connect(self, agent_id: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Reconnect to a remote worker.

        Establishes a new TCP connection. The worker must still be
        listening on the configured host:port.
        """
        logger.info("Reconnecting to remote worker %s at %s:%d", agent_id, self._host, self._port)
        reader, writer = await asyncio.open_connection(self._host, self._port)
        self._connections[agent_id] = (reader, writer)
        return reader, writer

    async def terminate(self, agent_id: str) -> None:
        """Close the TCP connection to a remote worker.

        Does NOT stop the remote worker process. The remote worker
        continues running and can be reconnected to later.
        """
        conn = self._connections.pop(agent_id, None)
        if conn:
            _, writer = conn
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                logger.debug("Error closing connection to %s", agent_id, exc_info=True)
        logger.info("Terminated connection to remote worker %s", agent_id)

    @property
    def transport_type(self) -> str:
        return "network"
