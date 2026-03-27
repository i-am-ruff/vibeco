"""Tests for HealthReport — HLTH-01."""

from datetime import datetime, timezone

from vcompany.container.health import HealthReport


class TestHealthReport:
    """HLTH-01: HealthReport model with all required fields."""

    def test_accepts_all_fields(self):
        now = datetime.now(timezone.utc)
        report = HealthReport(
            agent_id="agent-1",
            state="running",
            inner_state=None,
            uptime=120.5,
            last_heartbeat=now,
            error_count=0,
            last_activity=now,
        )
        assert report.agent_id == "agent-1"
        assert report.state == "running"
        assert report.inner_state is None
        assert report.uptime == 120.5
        assert report.last_heartbeat == now
        assert report.error_count == 0
        assert report.last_activity == now

    def test_inner_state_defaults_to_none(self):
        now = datetime.now(timezone.utc)
        report = HealthReport(
            agent_id="agent-1",
            state="creating",
            uptime=0.0,
            last_heartbeat=now,
            last_activity=now,
        )
        assert report.inner_state is None

    def test_error_count_defaults_to_zero(self):
        now = datetime.now(timezone.utc)
        report = HealthReport(
            agent_id="agent-1",
            state="errored",
            uptime=60.0,
            last_heartbeat=now,
            last_activity=now,
        )
        assert report.error_count == 0

    def test_serializable_to_dict(self):
        now = datetime.now(timezone.utc)
        report = HealthReport(
            agent_id="agent-1",
            state="running",
            uptime=10.0,
            last_heartbeat=now,
            last_activity=now,
        )
        d = report.model_dump()
        assert isinstance(d, dict)
        assert d["agent_id"] == "agent-1"
        assert d["state"] == "running"
