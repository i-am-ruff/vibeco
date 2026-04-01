"""vco-worker main entry point.

Reads HeadMessages from stdin (NDJSON, one message per line),
dispatches to WorkerContainer, writes WorkerMessages to stdout.

Usage:
    vco-worker              # reads from stdin, writes to stdout
    python -m vco_worker    # same thing
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from vco_worker.channel.framing import decode_head, encode
from vco_worker.channel.messages import (
    GiveTaskMessage,
    HealthCheckMessage,
    HealthReportMessage,
    InboundMessage,
    ReconnectMessage,
    SignalMessage,
    StartMessage,
    StopMessage,
)
from vco_worker.config import WorkerConfig
from vco_worker.container.container import WorkerContainer
from vco_worker.handler.registry import get_handler

logger = logging.getLogger("vco_worker")


async def bootstrap_container(
    agent_id: str,
    config_dict: dict,
    write_fn: Any,
) -> WorkerContainer:
    """Create and start a fully configured worker container from config blob."""
    config = WorkerConfig.model_validate(config_dict)
    container = WorkerContainer(config=config, agent_id=agent_id, writer=write_fn)
    handler = get_handler(config.handler_type)
    container.set_handler(handler)

    # Wire conversation session for conversation-type handlers
    if config.handler_type == "conversation" and config.persona:
        from vco_worker.conversation import ConversationSession

        container._conversation = ConversationSession(
            persona=config.persona,
            agent_id=agent_id,
            working_dir=Path.cwd(),
        )

    await container.start()
    return container


async def run_worker(
    reader: asyncio.StreamReader,
    write_fn: Any,
) -> None:
    """Main worker loop: read head messages, dispatch, respond.

    Protocol:
    1. Wait for StartMessage -- bootstrap container from config
    2. Send SignalMessage(signal="ready") once bootstrapped
    3. Dispatch GiveTask, Inbound, HealthCheck messages to container
    4. On StopMessage -- teardown container and exit

    write_fn: A callable or object with .write(bytes) and awaitable .drain().
    In production this wraps sys.stdout.buffer; in tests it's a MockStream.
    """
    container: WorkerContainer | None = None

    async for line in reader:
        stripped = line.strip()
        if not stripped:
            continue

        try:
            msg = decode_head(stripped)
        except Exception:
            logger.warning("Failed to decode message: %s", stripped[:200])
            continue

        if isinstance(msg, StartMessage):
            if container is not None:
                logger.warning("Received StartMessage but container already running")
                continue
            container = await bootstrap_container(msg.agent_id, msg.config, write_fn)
            write_fn.write(encode(SignalMessage(signal="ready")))
            await write_fn.drain()
            logger.info("Worker bootstrapped for agent %s", msg.agent_id)

        elif isinstance(msg, ReconnectMessage):
            # Head has reconnected -- send current state via HealthReport
            if container is not None:
                report = container.health_report()
                write_fn.write(encode(HealthReportMessage(
                    status=report.state,
                    agent_state=report.inner_state or "",
                    uptime_seconds=report.uptime,
                )))
                await write_fn.drain()
                logger.info("Reconnected: sent health report for %s", msg.agent_id)
            else:
                # Container not started yet -- send unknown status
                write_fn.write(encode(HealthReportMessage(status="unknown")))
                await write_fn.drain()

        elif isinstance(msg, GiveTaskMessage):
            if container is None:
                logger.warning("Received GiveTask before StartMessage")
                continue
            await container.give_task(msg.description)

        elif isinstance(msg, InboundMessage):
            if container is None:
                logger.warning("Received InboundMessage before StartMessage")
                continue
            await container.handle_inbound(msg)

        elif isinstance(msg, HealthCheckMessage):
            if container is None:
                logger.warning("Received HealthCheck before StartMessage")
                continue
            report = container.health_report()
            write_fn.write(encode(HealthReportMessage(
                status=report.state,
                agent_state=report.inner_state or "",
                uptime_seconds=report.uptime,
            )))
            await write_fn.drain()

        elif isinstance(msg, StopMessage):
            if container is not None:
                await container.stop()
                write_fn.write(encode(SignalMessage(signal="stopped")))
                await write_fn.drain()
            break

    # Cleanup if loop exits without StopMessage (e.g., EOF)
    if container is not None and container.state != "stopped":
        await container.stop()


class StdioWriter:
    """Thin async wrapper around sys.stdout.buffer for channel output.

    Does NOT use private asyncio APIs. Writes directly to stdout buffer
    (synchronous but fine for NDJSON line output -- each write is a single
    short line, no backpressure concern for stdio pipes).
    """

    def write(self, data: bytes) -> None:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    async def drain(self) -> None:
        # stdout.buffer.flush() already called in write(); nothing to await.
        pass


async def _run_socket(socket_path_str: str) -> None:
    """Run worker using Unix domain socket as the transport channel.

    Worker listens on socket_path. Head connects and communicates via NDJSON.
    When head disconnects, worker keeps running and waits for reconnection.
    """
    from vco_worker.channel.socket_server import start_socket_server

    socket_path = Path(socket_path_str)
    # Outbox socket: child processes (Claude Code hooks) send WorkerMessages here.
    # Worker forwards them to the head via the head socket. Separate from head
    # socket to prevent child connections from displacing the daemon's connection.
    outbox_path = Path(socket_path_str.replace(".sock", "-outbox.sock"))
    os.environ["VCO_WORKER_SOCKET"] = str(outbox_path)
    connection_event = asyncio.Event()

    class SocketWriter:
        """Writer that sends to the currently connected head."""

        def __init__(self) -> None:
            self._writer: asyncio.StreamWriter | None = None

        def write(self, data: bytes) -> None:
            if self._writer is not None and not self._writer.is_closing():
                self._writer.write(data)

        async def drain(self) -> None:
            if self._writer is not None and not self._writer.is_closing():
                await self._writer.drain()

    writer_proxy = SocketWriter()
    container_holder: list[WorkerContainer | None] = [None]

    async def handle_connection(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writer_proxy._writer = writer
        logger.info("Head connected via socket")

        try:
            async for line in reader:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    msg = decode_head(stripped)
                except Exception:
                    logger.warning("Failed to decode: %s", stripped[:200])
                    continue

                if isinstance(msg, StartMessage):
                    if container_holder[0] is not None:
                        logger.warning("StartMessage but container already running")
                        continue
                    container_holder[0] = await bootstrap_container(
                        msg.agent_id, msg.config, writer_proxy
                    )
                    writer_proxy.write(encode(SignalMessage(signal="ready")))
                    await writer_proxy.drain()

                elif isinstance(msg, ReconnectMessage):
                    if container_holder[0] is not None:
                        report = container_holder[0].health_report()
                        writer_proxy.write(encode(HealthReportMessage(
                            status=report.state,
                            agent_state=report.inner_state or "",
                            uptime_seconds=report.uptime,
                        )))
                        await writer_proxy.drain()
                        logger.info("Reconnect: sent health for %s", msg.agent_id)
                    else:
                        writer_proxy.write(encode(HealthReportMessage(status="unknown")))
                        await writer_proxy.drain()

                elif isinstance(msg, GiveTaskMessage):
                    if container_holder[0]:
                        await container_holder[0].give_task(msg.description)

                elif isinstance(msg, InboundMessage):
                    if container_holder[0]:
                        await container_holder[0].handle_inbound(msg)

                elif isinstance(msg, HealthCheckMessage):
                    if container_holder[0]:
                        report = container_holder[0].health_report()
                        writer_proxy.write(encode(HealthReportMessage(
                            status=report.state,
                            agent_state=report.inner_state or "",
                            uptime_seconds=report.uptime,
                        )))
                        await writer_proxy.drain()

                elif isinstance(msg, StopMessage):
                    if container_holder[0]:
                        await container_holder[0].stop()
                        writer_proxy.write(encode(SignalMessage(signal="stopped")))
                        await writer_proxy.drain()
                    # Close the socket server and exit
                    connection_event.set()
                    return

        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, BrokenPipeError):
            logger.info("Head disconnected -- waiting for reconnection")
        finally:
            if not writer.is_closing():
                writer.close()
            writer_proxy._writer = None

    async def handle_outbox_connection(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a child process sending messages via the outbox socket.

        Reads one or more NDJSON lines and forwards them to the head via
        writer_proxy. Does NOT replace writer_proxy._writer.
        """
        try:
            async for line in reader:
                stripped = line.strip()
                if not stripped:
                    continue
                # Forward raw bytes to head (it's already a WorkerMessage)
                writer_proxy.write(stripped + b"\n")
                await writer_proxy.drain()
                logger.debug("Forwarded outbox message to head: %s", stripped[:100])
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        finally:
            if not writer.is_closing():
                writer.close()

    server = await start_socket_server(socket_path, handle_connection)
    logger.info("Worker listening on %s (head socket)", socket_path)

    # Start outbox socket for child→worker→head forwarding
    outbox_server = await asyncio.start_unix_server(handle_outbox_connection, path=str(outbox_path))
    logger.info("Outbox listening on %s (child socket)", outbox_path)

    try:
        await connection_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        server.close()
        await server.wait_closed()
        outbox_server.close()
        await outbox_server.wait_closed()
        socket_path.unlink(missing_ok=True)
        outbox_path.unlink(missing_ok=True)
        if container_holder[0] is not None and container_holder[0].state != "stopped":
            await container_holder[0].stop()


async def _run_stdio() -> None:
    """Run worker using stdin/stdout as the transport channel.

    Uses asyncio.StreamReader + connect_read_pipe for async stdin reading.
    Uses StdioWriter for stdout (simple synchronous writes -- no private
    asyncio StreamWriter construction needed for output).
    """
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    writer = StdioWriter()

    await run_worker(reader, writer)


def main() -> None:
    """Entry point for vco-worker CLI command."""
    import argparse

    # Log to file so logs are visible even when stderr is piped to daemon
    log_file = Path.home() / "vco-worker.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(str(log_file), mode="a"),
        ],
    )
    parser = argparse.ArgumentParser(description="vco-worker agent runtime")
    parser.add_argument(
        "--socket",
        type=str,
        default=None,
        help="Unix socket path for channel communication (default: use stdio)",
    )
    args = parser.parse_args()

    if args.socket:
        asyncio.run(_run_socket(args.socket))
    else:
        asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
