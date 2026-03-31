"""Integration tests for worker main loop."""

import asyncio

import pytest

from vco_worker.channel.framing import decode_worker, encode
from vco_worker.channel.messages import (
    GiveTaskMessage,
    HealthCheckMessage,
    InboundMessage,
    StartMessage,
    StopMessage,
)
from vco_worker.main import run_worker


class MockStream:
    """Mock writer that captures written bytes."""

    def __init__(self):
        self.buffer = bytearray()

    def write(self, data: bytes):
        self.buffer.extend(data)

    async def drain(self):
        pass

    def get_messages(self) -> list:
        msgs = []
        for line in self.buffer.decode().strip().split("\n"):
            if line.strip():
                msgs.append(decode_worker(line.encode()))
        return msgs


def make_reader(messages: list) -> asyncio.StreamReader:
    """Create a StreamReader pre-loaded with encoded messages."""
    reader = asyncio.StreamReader()
    for msg in messages:
        reader.feed_data(encode(msg))
    reader.feed_eof()
    return reader


@pytest.mark.asyncio
async def test_worker_start_and_stop():
    """Worker bootstraps on StartMessage and stops on StopMessage."""
    reader = make_reader([
        StartMessage(agent_id="test-1", config={"handler_type": "session", "agent_type": "gsd"}),
        StopMessage(reason="test"),
    ])
    writer = MockStream()
    await run_worker(reader, writer)
    msgs = writer.get_messages()
    signals = [m for m in msgs if hasattr(m, "signal")]
    assert any(s.signal == "ready" for s in signals), "Should send ready signal"
    assert any(s.signal == "stopped" for s in signals), "Should send stopped signal"


@pytest.mark.asyncio
async def test_worker_health_check():
    """Worker responds to HealthCheckMessage with HealthReportMessage."""
    reader = make_reader([
        StartMessage(agent_id="test-2", config={"handler_type": "session", "agent_type": "gsd"}),
        HealthCheckMessage(),
        StopMessage(),
    ])
    writer = MockStream()
    await run_worker(reader, writer)
    msgs = writer.get_messages()
    health_reports = [m for m in msgs if hasattr(m, "status")]
    assert len(health_reports) >= 1, "Should have health report"
    assert health_reports[0].status == "running"


@pytest.mark.asyncio
async def test_worker_ignores_messages_before_start():
    """Messages before StartMessage are logged but don't crash."""
    reader = make_reader([
        GiveTaskMessage(task_id="t1", description="do stuff"),
        StartMessage(agent_id="test-3", config={"handler_type": "session", "agent_type": "gsd"}),
        StopMessage(),
    ])
    writer = MockStream()
    await run_worker(reader, writer)
    # Should not crash -- GiveTask before Start is just logged
    msgs = writer.get_messages()
    assert any(hasattr(m, "signal") and m.signal == "ready" for m in msgs)


@pytest.mark.asyncio
async def test_worker_handles_eof_gracefully():
    """Worker stops cleanly when reader reaches EOF without StopMessage."""
    reader = make_reader([
        StartMessage(agent_id="test-4", config={"handler_type": "session", "agent_type": "gsd"}),
    ])
    writer = MockStream()
    await run_worker(reader, writer)
    # Should not hang or crash -- EOF triggers cleanup
    msgs = writer.get_messages()
    assert any(hasattr(m, "signal") and m.signal == "ready" for m in msgs)
