"""Tests for AgentHandle — daemon-side lightweight agent representation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vcompany.daemon.agent_handle import STALENESS_THRESHOLD_SECONDS, AgentHandle
from vcompany.transport.channel.messages import (
    GiveTaskMessage,
    HealthReportMessage,
    InboundMessage,
    WorkerMessageType,
)


def _make_handle(**kwargs) -> AgentHandle:
    defaults = {
        "agent_id": "test-agent-1",
        "agent_type": "task",
    }
    defaults.update(kwargs)
    return AgentHandle(**defaults)


class TestAgentHandleConstruction:
    """Test 1: AgentHandle can be constructed with metadata fields."""

    def test_construct_with_required_fields(self):
        h = AgentHandle(agent_id="a1", agent_type="task")
        assert h.agent_id == "a1"
        assert h.agent_type == "task"
        assert h.capabilities == []
        assert h.channel_id is None
        assert h.handler_type == "session"
        assert h.config == {}

    def test_construct_with_all_fields(self):
        h = AgentHandle(
            agent_id="a2",
            agent_type="continuous",
            capabilities=["code", "review"],
            channel_id="discord-123",
            handler_type="conversation",
            config={"persona": "reviewer"},
        )
        assert h.agent_id == "a2"
        assert h.capabilities == ["code", "review"]
        assert h.channel_id == "discord-123"
        assert h.handler_type == "conversation"
        assert h.config == {"persona": "reviewer"}


class TestAgentHandleSend:
    """Test 2 & 3: send() writes to stdin or raises RuntimeError."""

    @pytest.mark.asyncio
    async def test_send_writes_encoded_message_to_stdin(self):
        h = _make_handle()
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.drain = AsyncMock()
        mock_proc.returncode = None
        h.attach_process(mock_proc)

        msg = GiveTaskMessage(task_id="t1", description="do stuff")
        await h.send(msg)

        mock_proc.stdin.write.assert_called_once()
        written = mock_proc.stdin.write.call_args[0][0]
        assert b'"type":"give-task"' in written
        assert b'"task_id":"t1"' in written
        mock_proc.stdin.drain.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_raises_when_no_process(self):
        h = _make_handle()
        msg = InboundMessage(sender="user", channel="general", content="hi")
        with pytest.raises(RuntimeError, match="No connection to agent"):
            await h.send(msg)


class TestAgentHandleHealth:
    """Test 4 & 5: update_health caches report, state property works."""

    def test_update_health_caches_report(self):
        h = _make_handle()
        report = HealthReportMessage(
            status="running",
            agent_state="IDLE",
            uptime_seconds=42.0,
        )
        h.update_health(report)
        assert h._last_health is report
        assert h._last_health_time is not None

    def test_state_returns_unknown_when_no_health(self):
        h = _make_handle()
        assert h.state == "unknown"

    def test_state_returns_status_from_last_report(self):
        h = _make_handle()
        report = HealthReportMessage(status="running", uptime_seconds=10.0)
        h.update_health(report)
        assert h.state == "running"


class TestAgentHandleHealthReport:
    """Test 6 & 7: health_report() returns HealthReport-compatible dict."""

    def test_health_report_returns_correct_fields(self):
        h = _make_handle()
        report = HealthReportMessage(
            status="running",
            agent_state="PLAN",
            uptime_seconds=99.5,
        )
        h.update_health(report)
        hr = h.health_report()
        assert hr.agent_id == "test-agent-1"
        assert hr.state == "running"
        assert hr.inner_state == "PLAN"
        assert hr.uptime == 99.5

    def test_health_report_returns_unreachable_when_stale(self):
        h = _make_handle()
        report = HealthReportMessage(status="running", uptime_seconds=50.0)
        h.update_health(report)
        # Force stale timestamp
        h._last_health_time = datetime.now(UTC) - timedelta(
            seconds=STALENESS_THRESHOLD_SECONDS + 10
        )
        hr = h.health_report()
        assert hr.state == "unreachable"

    def test_health_report_returns_unknown_when_no_health(self):
        h = _make_handle()
        hr = h.health_report()
        assert hr.agent_id == "test-agent-1"
        assert hr.state == "unknown"
        assert hr.uptime == 0.0


class TestAgentHandleIsAlive:
    """Test 8: is_alive property checks process state."""

    def test_is_alive_true_when_process_running(self):
        h = _make_handle()
        mock_proc = MagicMock()
        mock_proc.returncode = None
        h.attach_process(mock_proc)
        assert h.is_alive is True

    def test_is_alive_false_when_process_exited(self):
        h = _make_handle()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        h.attach_process(mock_proc)
        assert h.is_alive is False

    def test_is_alive_false_when_no_process(self):
        h = _make_handle()
        assert h.is_alive is False
