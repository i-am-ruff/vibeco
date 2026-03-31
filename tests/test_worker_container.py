"""Tests for WorkerContainer lifecycle, health, handlers, and channel output."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from vco_worker.channel.messages import InboundMessage, ReportMessage
from vco_worker.config import WorkerConfig
from vco_worker.container.container import WorkerContainer
from vco_worker.container.health import HealthReport
from vco_worker.handler.conversation import WorkerConversationHandler
from vco_worker.handler.protocol import (
    ConversationHandler,
    SessionHandler,
    TransientHandler,
)
from vco_worker.handler.session import GsdSessionHandler
from vco_worker.handler.transient import PMTransientHandler


def _make_config(**overrides) -> WorkerConfig:
    """Create a WorkerConfig with defaults."""
    defaults = {
        "handler_type": "session",
        "agent_type": "gsd",
        "data_dir": "/tmp/vco-worker-test/data",
    }
    defaults.update(overrides)
    return WorkerConfig(**defaults)


@pytest.mark.asyncio
async def test_container_lifecycle_basic(tmp_path):
    """Create WorkerContainer, start, verify running, stop, verify stopped."""
    config = _make_config(data_dir=str(tmp_path))
    container = WorkerContainer(config=config, agent_id="test-agent-1")
    await container.start()
    assert "running" in container.state
    await container.stop()
    assert container.state == "stopped"


@pytest.mark.asyncio
async def test_container_health_report(tmp_path):
    """After start(), health_report() returns correct HealthReport."""
    config = _make_config(data_dir=str(tmp_path))
    container = WorkerContainer(config=config, agent_id="test-health")
    await container.start()
    try:
        report = container.health_report()
        assert isinstance(report, HealthReport)
        assert report.agent_id == "test-health"
        assert "running" in report.state
        assert report.uptime >= 0.0
        assert report.error_count == 0
    finally:
        await container.stop()


@pytest.mark.asyncio
async def test_container_give_task_when_idle(tmp_path):
    """When idle, give_task drains the queue immediately."""
    config = _make_config(data_dir=str(tmp_path))
    container = WorkerContainer(config=config, agent_id="test-task")
    await container.start()
    try:
        container._is_idle = True
        await container.give_task("test task description")
        # Queue should be drained (empty) after give_task when idle
        assert container._task_queue.empty()
        # After draining, idle should be False
        assert container._is_idle is False
    finally:
        await container.stop()


@pytest.mark.asyncio
async def test_gsd_handler_on_start_no_checkpoint(tmp_path):
    """GsdSessionHandler.on_start works with empty memory (no checkpoint)."""
    config = _make_config(data_dir=str(tmp_path))
    container = WorkerContainer(config=config, agent_id="test-gsd")
    handler = GsdSessionHandler()
    container.set_handler(handler)
    # start() calls handler.on_start internally
    await container.start()
    try:
        # Should not raise -- clean start with empty memory
        assert "running" in container.state
    finally:
        await container.stop()


def test_conversation_handler_instantiation():
    """WorkerConversationHandler has the required protocol methods."""
    handler = WorkerConversationHandler()
    assert hasattr(handler, "handle_message")
    assert hasattr(handler, "on_start")
    assert hasattr(handler, "on_stop")
    assert callable(handler.handle_message)
    assert callable(handler.on_start)
    assert callable(handler.on_stop)


@pytest.mark.asyncio
async def test_transient_handler_health_change(tmp_path):
    """PMTransientHandler processes [Health Change] messages and updates timestamps."""
    config = _make_config(
        handler_type="transient",
        agent_type="fulltime",
        data_dir=str(tmp_path),
    )
    container = WorkerContainer(config=config, agent_id="test-pm")
    handler = PMTransientHandler()
    container.set_handler(handler)
    await container.start()
    try:
        msg = InboundMessage(
            sender="head",
            channel="pm-events",
            content="[Health Change] agent=alpha state=running inner=idle",
        )
        await container.handle_inbound(msg)
        assert "alpha" in container._agent_state_timestamps
        state_name, _ = container._agent_state_timestamps["alpha"]
        assert state_name == "idle"
    finally:
        # Cancel stuck detector before stop
        if container._stuck_detector_task is not None:
            container._stuck_detector_task.cancel()
            try:
                await container._stuck_detector_task
            except asyncio.CancelledError:
                pass
            container._stuck_detector_task = None
        await container.stop()


@pytest.mark.asyncio
async def test_container_channel_output(tmp_path):
    """send_report writes NDJSON ReportMessage to the writer."""
    config = _make_config(data_dir=str(tmp_path))

    # Create a mock writer that captures written bytes
    written_data = bytearray()

    mock_writer = MagicMock()
    mock_writer.write = lambda data: written_data.extend(data)
    mock_writer.drain = AsyncMock()

    container = WorkerContainer(config=config, agent_id="test-channel", writer=mock_writer)
    await container.start()
    try:
        await container.send_report("test-channel", "Hello from worker")
        # Verify NDJSON output
        line = written_data.decode("utf-8").strip()
        parsed = json.loads(line)
        assert parsed["type"] == "report"
        assert parsed["channel"] == "test-channel"
        assert parsed["content"] == "Hello from worker"
    finally:
        await container.stop()


# --- Protocol conformance ---


def test_handlers_satisfy_protocols():
    """All three handler types satisfy their respective protocols."""
    assert isinstance(GsdSessionHandler(), SessionHandler)
    assert isinstance(WorkerConversationHandler(), ConversationHandler)
    assert isinstance(PMTransientHandler(), TransientHandler)
