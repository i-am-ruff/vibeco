"""Tests for interface change logging and canonical management."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from vcompany.coordination.interfaces import apply_interface_change, log_interface_change
from vcompany.models.coordination_state import InterfaceChangeLog, InterfaceChangeRecord

from tests.test_sync_context import _make_config, _setup_project


def _make_record(**overrides) -> InterfaceChangeRecord:
    """Create a test InterfaceChangeRecord with sensible defaults."""
    defaults = {
        "timestamp": datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc),
        "agent_id": "agent-a",
        "action": "proposed",
        "description": "Add new endpoint",
        "diff": "+GET /api/v2/status",
    }
    defaults.update(overrides)
    return InterfaceChangeRecord(**defaults)


class TestLogInterfaceChange:
    def test_log_interface_change_appends(self, tmp_path: Path) -> None:
        """log_interface_change adds record to interface_changes.json."""
        context_dir = tmp_path / "context"
        context_dir.mkdir()

        record = _make_record()
        log_interface_change(tmp_path, record)

        changes_path = context_dir / "interface_changes.json"
        assert changes_path.exists()
        log = InterfaceChangeLog.model_validate_json(changes_path.read_text())
        assert len(log.records) == 1
        assert log.records[0].agent_id == "agent-a"

    def test_log_interface_change_creates_file(self, tmp_path: Path) -> None:
        """If interface_changes.json doesn't exist, creates it."""
        context_dir = tmp_path / "context"
        context_dir.mkdir()

        record = _make_record()
        log_interface_change(tmp_path, record)

        changes_path = context_dir / "interface_changes.json"
        assert changes_path.exists()
        log = InterfaceChangeLog.model_validate_json(changes_path.read_text())
        assert log.project == ""  # default project
        assert len(log.records) == 1

    def test_log_interface_change_preserves_existing(self, tmp_path: Path) -> None:
        """Appending does not overwrite existing records."""
        context_dir = tmp_path / "context"
        context_dir.mkdir()

        record1 = _make_record(agent_id="agent-a", description="First change")
        record2 = _make_record(agent_id="agent-b", description="Second change")

        log_interface_change(tmp_path, record1)
        log_interface_change(tmp_path, record2)

        changes_path = context_dir / "interface_changes.json"
        log = InterfaceChangeLog.model_validate_json(changes_path.read_text())
        assert len(log.records) == 2
        assert log.records[0].description == "First change"
        assert log.records[1].description == "Second change"


class TestApplyInterfaceChange:
    def test_apply_interface_change(self, tmp_path: Path) -> None:
        """apply_interface_change writes new INTERFACES.md content atomically and calls sync_context_files."""
        project_dir = _setup_project(
            tmp_path,
            ["agent-a"],
            {"INTERFACES.md": "old content"},
        )
        config = _make_config("agent-a")
        record = _make_record(action="applied")

        result = apply_interface_change(project_dir, config, "new interface content", record)

        # INTERFACES.md should be updated
        assert (project_dir / "context" / "INTERFACES.md").read_text() == "new interface content"
        # Should be synced to clones
        assert (project_dir / "clones" / "agent-a" / "INTERFACES.md").read_text() == "new interface content"
        # Change should be logged
        changes_path = project_dir / "context" / "interface_changes.json"
        assert changes_path.exists()
        log = InterfaceChangeLog.model_validate_json(changes_path.read_text())
        assert len(log.records) == 1
        assert log.records[0].action == "applied"
        # Should return SyncResult
        assert result.clones_updated == 1


class TestInterfaceChangeRecordModel:
    def test_interface_change_record_model(self) -> None:
        """InterfaceChangeRecord validates Literal action field."""
        # Valid actions
        for action in ["proposed", "approved", "rejected", "applied"]:
            record = _make_record(action=action)
            assert record.action == action

        # Invalid action should raise
        import pytest

        with pytest.raises(Exception):
            _make_record(action="invalid")
