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
import sys
from typing import Any

from vco_worker.channel.framing import decode_head, encode
from vco_worker.channel.messages import (
    GiveTaskMessage,
    HealthCheckMessage,
    HealthReportMessage,
    InboundMessage,
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,  # Log to stderr, keep stdout for channel messages
    )
    asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
