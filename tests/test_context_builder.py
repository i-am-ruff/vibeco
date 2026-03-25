"""Tests for PM-CONTEXT.md builder."""

import json
from pathlib import Path

import pytest

from vcompany.strategist.context_builder import build_pm_context, write_pm_context


class TestBuildPmContext:
    def test_output_starts_with_pm_context_header(self, tmp_path: Path):
        result = build_pm_context(tmp_path)
        assert result.startswith("# PM Context")

    def test_assembles_sections_from_source_files(self, tmp_path: Path):
        context_dir = tmp_path / "context"
        context_dir.mkdir()
        (context_dir / "PROJECT-BLUEPRINT.md").write_text("Blueprint content here")
        (context_dir / "INTERFACES.md").write_text("Interface contracts here")

        result = build_pm_context(tmp_path)
        assert "## Project Blueprint" in result
        assert "Blueprint content here" in result
        assert "## Interface Contracts" in result
        assert "Interface contracts here" in result

    def test_missing_source_files_gracefully_skipped(self, tmp_path: Path):
        # No context dir at all -- should not crash
        result = build_pm_context(tmp_path)
        assert "# PM Context" in result
        # Should not contain any section headers for missing files
        assert "## Project Blueprint" not in result

    def test_empty_project_dir_returns_minimal_valid_context(self, tmp_path: Path):
        result = build_pm_context(tmp_path)
        assert "# PM Context" in result
        assert len(result) > 10  # Not empty

    def test_each_source_gets_own_section_header(self, tmp_path: Path):
        context_dir = tmp_path / "context"
        context_dir.mkdir()
        (context_dir / "PROJECT-BLUEPRINT.md").write_text("bp")
        (context_dir / "INTERFACES.md").write_text("ifc")
        (context_dir / "MILESTONE-SCOPE.md").write_text("ms")
        (context_dir / "PROJECT-STATUS.md").write_text("ps")

        result = build_pm_context(tmp_path)
        assert "## Project Blueprint" in result
        assert "## Interface Contracts" in result
        assert "## Current Milestone Scope" in result
        assert "## Project Status" in result

    def test_mile_02_three_input_documents_all_present(self, tmp_path: Path):
        """MILE-02: Three input documents define a project."""
        context_dir = tmp_path / "context"
        context_dir.mkdir()
        (context_dir / "PROJECT-BLUEPRINT.md").write_text("The blueprint")
        (context_dir / "INTERFACES.md").write_text("The interfaces")
        (context_dir / "MILESTONE-SCOPE.md").write_text("The scope")

        result = build_pm_context(tmp_path)
        assert "The blueprint" in result
        assert "The interfaces" in result
        assert "The scope" in result

    def test_recent_decisions_appended_from_jsonl(self, tmp_path: Path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        entries = [
            {
                "timestamp": "2026-03-25T10:00:00Z",
                "decided_by": "PM",
                "decision": "Use REST for v1",
                "confidence_level": "HIGH",
            },
            {
                "timestamp": "2026-03-25T11:00:00Z",
                "decided_by": "Owner",
                "decision": "Approve auth plan",
                "confidence_level": "MEDIUM",
            },
        ]
        with (state_dir / "decisions.jsonl").open("w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        result = build_pm_context(tmp_path)
        assert "## Recent Decisions" in result
        assert "Use REST for v1" in result
        assert "Approve auth plan" in result

    def test_decisions_limited_to_last_50(self, tmp_path: Path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        with (state_dir / "decisions.jsonl").open("w") as f:
            for i in range(60):
                entry = {
                    "timestamp": f"2026-03-25T{i:02d}:00:00Z",
                    "decided_by": "PM",
                    "decision": f"Decision {i}",
                    "confidence_level": "HIGH",
                }
                f.write(json.dumps(entry) + "\n")

        result = build_pm_context(tmp_path)
        # Last 50 means decisions 10-59 should be present, 0-9 should not
        assert "Decision 59" in result
        assert "Decision 10" in result
        # First entries should be truncated
        assert "Decision 0\n" not in result


class TestWritePmContext:
    def test_writes_file_to_context_directory(self, tmp_path: Path):
        context_dir = tmp_path / "context"
        context_dir.mkdir()
        (context_dir / "PROJECT-BLUEPRINT.md").write_text("bp content")

        result_path = write_pm_context(tmp_path)
        assert result_path == context_dir / "PM-CONTEXT.md"
        assert result_path.exists()
        content = result_path.read_text()
        assert "# PM Context" in content
        assert "bp content" in content

    def test_creates_context_dir_if_missing(self, tmp_path: Path):
        result_path = write_pm_context(tmp_path)
        assert result_path.exists()
        assert "# PM Context" in result_path.read_text()
