"""Tests for agent state Pydantic models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from vcompany.models.agent_state import AgentEntry, AgentsRegistry, CrashLog, CrashRecord


class TestAgentEntry:
    """Tests for the AgentEntry model."""

    def test_agent_entry_validates_all_fields(self) -> None:
        """AgentEntry with all fields validates and serializes to JSON with ISO datetime."""
        now = datetime.now(timezone.utc)
        entry = AgentEntry(
            agent_id="BACKEND",
            pane_id="%1",
            pid=12345,
            session_name="vco-test-project",
            status="running",
            launched_at=now,
            last_crash=now,
        )
        assert entry.agent_id == "BACKEND"
        assert entry.pane_id == "%1"
        assert entry.pid == 12345
        assert entry.session_name == "vco-test-project"
        assert entry.status == "running"
        assert entry.launched_at == now
        assert entry.last_crash == now

        # Serializes to JSON with ISO datetime
        json_str = entry.model_dump_json()
        assert "BACKEND" in json_str
        assert "%1" in json_str

    def test_agent_entry_status_running_valid(self) -> None:
        """AgentEntry with status='running' is valid."""
        entry = AgentEntry(
            agent_id="BACKEND",
            pane_id="%1",
            session_name="vco-test",
            status="running",
            launched_at=datetime.now(timezone.utc),
        )
        assert entry.status == "running"

    def test_agent_entry_all_valid_statuses(self) -> None:
        """Status must be one of: starting, running, stopped, crashed, circuit_open."""
        for status in ("starting", "running", "stopped", "crashed", "circuit_open"):
            entry = AgentEntry(
                agent_id="BACKEND",
                pane_id="%1",
                session_name="vco-test",
                status=status,
                launched_at=datetime.now(timezone.utc),
            )
            assert entry.status == status

    def test_agent_entry_invalid_status_rejected(self) -> None:
        """Invalid status value is rejected."""
        with pytest.raises(ValidationError):
            AgentEntry(
                agent_id="BACKEND",
                pane_id="%1",
                session_name="vco-test",
                status="invalid",
                launched_at=datetime.now(timezone.utc),
            )

    def test_agent_entry_optional_fields(self) -> None:
        """pid and last_crash are optional (default None)."""
        entry = AgentEntry(
            agent_id="BACKEND",
            pane_id="%1",
            session_name="vco-test",
            status="starting",
            launched_at=datetime.now(timezone.utc),
        )
        assert entry.pid is None
        assert entry.last_crash is None


class TestAgentsRegistry:
    """Tests for the AgentsRegistry model."""

    def test_agents_registry_dict_keyed_by_id(self) -> None:
        """AgentsRegistry.agents is a dict[str, AgentEntry], keyed by agent_id."""
        now = datetime.now(timezone.utc)
        entry = AgentEntry(
            agent_id="BACKEND",
            pane_id="%1",
            session_name="vco-test",
            status="running",
            launched_at=now,
        )
        registry = AgentsRegistry(project="test-project", agents={"BACKEND": entry})
        assert "BACKEND" in registry.agents
        assert registry.agents["BACKEND"].agent_id == "BACKEND"

    def test_agents_registry_round_trips_json(self) -> None:
        """AgentsRegistry round-trips through model_dump_json() / model_validate_json()."""
        now = datetime.now(timezone.utc)
        entry = AgentEntry(
            agent_id="BACKEND",
            pane_id="%1",
            session_name="vco-test",
            status="running",
            launched_at=now,
        )
        registry = AgentsRegistry(project="test-project", agents={"BACKEND": entry})

        json_str = registry.model_dump_json()
        restored = AgentsRegistry.model_validate_json(json_str)

        assert restored.project == registry.project
        assert "BACKEND" in restored.agents
        assert restored.agents["BACKEND"].agent_id == "BACKEND"
        assert restored.agents["BACKEND"].status == "running"

    def test_agents_registry_empty_agents_default(self) -> None:
        """AgentsRegistry defaults to empty agents dict."""
        registry = AgentsRegistry(project="test-project")
        assert registry.agents == {}


class TestCrashRecord:
    """Tests for the CrashRecord model."""

    def test_crash_record_stores_all_fields(self) -> None:
        """CrashRecord stores agent_id, timestamp, exit_code, classification, pane_output."""
        now = datetime.now(timezone.utc)
        record = CrashRecord(
            agent_id="BACKEND",
            timestamp=now,
            exit_code=1,
            classification="transient_runtime_error",
            pane_output=["Error: something failed", "Traceback ..."],
        )
        assert record.agent_id == "BACKEND"
        assert record.timestamp == now
        assert record.exit_code == 1
        assert record.classification == "transient_runtime_error"
        assert record.pane_output == ["Error: something failed", "Traceback ..."]

    def test_crash_record_pane_output_defaults_empty(self) -> None:
        """pane_output defaults to empty list."""
        record = CrashRecord(
            agent_id="BACKEND",
            timestamp=datetime.now(timezone.utc),
            exit_code=0,
            classification="transient_context_exhaustion",
        )
        assert record.pane_output == []


class TestCrashLog:
    """Tests for the CrashLog model."""

    def test_crash_log_stores_project_and_records(self) -> None:
        """CrashLog stores project (str) and records (list[CrashRecord])."""
        now = datetime.now(timezone.utc)
        record = CrashRecord(
            agent_id="BACKEND",
            timestamp=now,
            exit_code=1,
            classification="transient_runtime_error",
        )
        log = CrashLog(project="test-project", records=[record])
        assert log.project == "test-project"
        assert len(log.records) == 1
        assert log.records[0].agent_id == "BACKEND"

    def test_crash_log_defaults_empty_records(self) -> None:
        """CrashLog defaults to empty records list."""
        log = CrashLog(project="test-project")
        assert log.records == []
