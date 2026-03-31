"""AgentHandle — lightweight daemon-side agent representation.

Stores agent metadata and provides transport communication to the worker
process via stdin. No container runtime logic — that lives in vco-worker.
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

    Holds metadata (id, type, capabilities, channel binding) and a reference
    to the worker subprocess. Communicates with the worker exclusively through
    the transport channel protocol (NDJSON over stdin).

    Runtime state (process, health cache) uses Pydantic PrivateAttr so it is
    excluded from serialization.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_id: str
    agent_type: str
    capabilities: list[str] = Field(default_factory=list)
    channel_id: str | None = None
    handler_type: str = "session"
    config: dict = Field(default_factory=dict)

    # Runtime state — excluded from serialization
    _process: Any = PrivateAttr(default=None)
    _reader_task: asyncio.Task | None = PrivateAttr(default=None)
    _last_health: HealthReportMessage | None = PrivateAttr(default=None)
    _last_health_time: datetime | None = PrivateAttr(default=None)

    def attach_process(self, process: Any) -> None:
        """Attach a subprocess to this handle."""
        self._process = process

    async def send(self, msg: HeadMessage) -> None:
        """Send a HeadMessage to the worker process via stdin.

        Raises RuntimeError if no process is attached.
        """
        if self._process is None:
            raise RuntimeError(f"No process attached to agent {self.agent_id}")
        data = encode(msg)
        self._process.stdin.write(data)
        await self._process.stdin.drain()

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
        """True if the worker process exists and has not exited."""
        return self._process is not None and self._process.returncode is None

    async def stop_process(self, timeout: float = 10.0) -> None:
        """Gracefully stop the worker process.

        Sends a StopMessage, waits for the process to exit, and terminates
        if the timeout is exceeded.
        """
        if not self.is_alive:
            return
        try:
            await self.send(StopMessage(reason="daemon shutdown"))
        except (RuntimeError, OSError):
            pass
        try:
            await asyncio.wait_for(self._process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
