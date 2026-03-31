"""AgentHandle -- lightweight daemon-side agent representation.

Stores agent metadata and provides transport communication to the worker
process via socket or stdin. No container runtime logic -- that lives in
vco-worker.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from vcompany.container.health import HealthReport
from vcompany.transport.channel.framing import encode
from vcompany.transport.channel.messages import (
    HeadMessage,
    HealthReportMessage,
    StopMessage,
)

STALENESS_THRESHOLD_SECONDS: int = 120


class AgentHandle(BaseModel):
    """Daemon-side representation of a running agent.

    Holds metadata (id, type, capabilities, channel binding) and references
    to the worker's socket or subprocess. Communicates with the worker
    exclusively through the transport channel protocol (NDJSON over socket
    or stdin).

    Runtime state (process, socket, health cache) uses Pydantic PrivateAttr
    so it is excluded from serialization.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_id: str
    agent_type: str
    capabilities: list[str] = Field(default_factory=list)
    channel_id: str | None = None
    handler_type: str = "session"
    config: dict = Field(default_factory=dict)

    # Runtime state -- excluded from serialization
    _process: Any = PrivateAttr(default=None)
    _socket_reader: asyncio.StreamReader | None = PrivateAttr(default=None)
    _socket_writer: asyncio.StreamWriter | None = PrivateAttr(default=None)
    _reader_task: asyncio.Task | None = PrivateAttr(default=None)
    _last_health: HealthReportMessage | None = PrivateAttr(default=None)
    _last_health_time: datetime | None = PrivateAttr(default=None)

    def attach_process(self, process: Any) -> None:
        """Attach a subprocess to this handle."""
        self._process = process

    def attach_socket(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Attach a socket reader/writer pair for channel communication."""
        self._socket_reader = reader
        self._socket_writer = writer

    async def send(self, msg: HeadMessage) -> None:
        """Send a HeadMessage to the worker via socket or process stdin.

        Prefers socket writer when available, falls back to process stdin.
        Raises RuntimeError if no connection is available.
        """
        data = encode(msg)
        if self._socket_writer is not None:
            self._socket_writer.write(data)
            await self._socket_writer.drain()
        elif self._process is not None:
            self._process.stdin.write(data)
            await self._process.stdin.drain()
        else:
            raise RuntimeError(f"No connection to agent {self.agent_id}")

    @property
    def reader(self) -> asyncio.StreamReader | None:
        """Return the active reader (socket or process stdout)."""
        if self._socket_reader is not None:
            return self._socket_reader
        if self._process is not None and self._process.stdout is not None:
            return self._process.stdout
        return None

    def update_health(self, report: HealthReportMessage) -> None:
        """Cache a health report received from the worker."""
        self._last_health = report
        self._last_health_time = datetime.now(UTC)

    @property
    def state(self) -> str:
        """Current agent state from last health report, or 'unknown'."""
        if self._last_health is None:
            return "unknown"
        return self._last_health.status

    def health_report(self) -> HealthReport:
        """Build a HealthReport from cached health data.

        Returns state='unreachable' if last health is older than the
        staleness threshold. Returns state='unknown' if no health received.
        """
        now = datetime.now(UTC)

        if self._last_health is None:
            return HealthReport(
                agent_id=self.agent_id,
                state="unknown",
                uptime=0.0,
                last_heartbeat=now,
                last_activity=now,
            )

        # Check staleness
        is_stale = (
            self._last_health_time is not None
            and (now - self._last_health_time).total_seconds()
            > STALENESS_THRESHOLD_SECONDS
        )

        return HealthReport(
            agent_id=self.agent_id,
            state="unreachable" if is_stale else self._last_health.status,
            inner_state=self._last_health.agent_state or None,
            uptime=self._last_health.uptime_seconds,
            last_heartbeat=self._last_health_time or now,
            last_activity=self._last_health_time or now,
        )

    @property
    def is_alive(self) -> bool:
        """True if the worker is reachable (socket connected or process running)."""
        if self._socket_writer is not None and not self._socket_writer.is_closing():
            return True
        return self._process is not None and self._process.returncode is None

    async def stop_process(self, timeout: float = 10.0) -> None:
        """Gracefully stop the worker process.

        Sends a StopMessage, waits for the process to exit, and terminates
        if the timeout is exceeded. Closes socket if present.
        """
        if not self.is_alive:
            return
        try:
            await self.send(StopMessage(reason="daemon shutdown"))
        except (RuntimeError, OSError):
            pass
        # Close socket if present
        if self._socket_writer is not None:
            if not self._socket_writer.is_closing():
                self._socket_writer.close()
            self._socket_writer = None
            self._socket_reader = None
        # Terminate process if present
        if self._process is not None and self._process.returncode is None:
            try:
                await asyncio.wait_for(self._process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
