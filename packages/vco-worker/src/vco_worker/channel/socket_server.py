"""Unix domain socket server for worker channel protocol.

Worker listens on a well-known socket path. Head connects to send
HeadMessages and receive WorkerMessages. Socket survives head death --
worker keeps running and accepts new connections when head reconnects.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def start_socket_server(
    socket_path: Path,
    on_connected: callable,
) -> asyncio.Server:
    """Start Unix domain socket server for channel protocol.

    Args:
        socket_path: Path for the Unix domain socket file.
        on_connected: Async callback (reader, writer) -> None called
            when head connects. May be called multiple times (reconnect).

    Returns:
        asyncio.Server that can be closed to stop listening.
    """
    # Clean up stale socket file (left behind after crash)
    if socket_path.exists():
        # Check if socket is still live before removing
        try:
            _, writer = await asyncio.open_unix_connection(str(socket_path))
            writer.close()
            await writer.wait_closed()
            # Socket is live -- another worker is running
            raise RuntimeError(
                f"Socket {socket_path} is already in use by another worker"
            )
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            # Socket is stale -- safe to remove
            socket_path.unlink(missing_ok=True)

    socket_path.parent.mkdir(parents=True, exist_ok=True)

    server = await asyncio.start_unix_server(
        on_connected,
        path=str(socket_path),
    )
    logger.info("Socket server listening on %s", socket_path)
    return server
