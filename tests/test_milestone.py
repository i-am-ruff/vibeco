"""Tests for vco new-milestone CLI command and sync-context PM-CONTEXT.md update.

TDD RED phase: these tests define the expected behavior.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from vcompany.coordination.sync_context import SYNC_FILES, sync_context_files


# ---------------------------------------------------------------------------
# sync-context tests
# ---------------------------------------------------------------------------


def test_sync_files_includes_pm_context_md():
    """SYNC_FILES should include PM-CONTEXT.md (renamed from STRATEGIST-PROMPT.md per D-20)."""
    assert "PM-CONTEXT.md" in SYNC_FILES


def test_sync_files_does_not_include_strategist_prompt():
    """SYNC_FILES should not include STRATEGIST-PROMPT.md after D-20 rename."""
    assert "STRATEGIST-PROMPT.md" not in SYNC_FILES


def test_sync_context_generates_pm_context_before_syncing(tmp_path: Path):
    """sync_context_files should generate PM-CONTEXT.md before syncing if context_builder available."""
    # Setup minimal project structure
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    (context_dir / "INTERFACES.md").write_text("# Interfaces")
    (context_dir / "MILESTONE-SCOPE.md").write_text("# Milestone")

    # Create a clone dir
    clone_dir = tmp_path / "clones" / "agent-a"
    clone_dir.mkdir(parents=True)

    config = MagicMock()
    config.agents = [MagicMock(id="agent-a")]

    result = sync_context_files(tmp_path, config)
    assert result.clones_updated >= 1
    # PM-CONTEXT.md should have been generated in context dir
    assert (context_dir / "PM-CONTEXT.md").exists()


def test_sync_context_backward_compat_renames_strategist_prompt(tmp_path: Path):
    """If STRATEGIST-PROMPT.md exists and PM-CONTEXT.md doesn't, rename it."""
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    (context_dir / "STRATEGIST-PROMPT.md").write_text("# Old strategist prompt")

    clone_dir = tmp_path / "clones" / "agent-a"
    clone_dir.mkdir(parents=True)

    config = MagicMock()
    config.agents = [MagicMock(id="agent-a")]

    sync_context_files(tmp_path, config)
    # Old file should be renamed
    assert (context_dir / "PM-CONTEXT.md").exists()


# ---------------------------------------------------------------------------
# vco new-milestone CLI tests
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project structure for new-milestone testing."""
    project_dir = tmp_path / "project"
    (project_dir / "context").mkdir(parents=True)
    (project_dir / "state").mkdir(parents=True)
    (project_dir / "clones" / "agent-a").mkdir(parents=True)

    # Write minimal agents.yaml
    agents_yaml = {
        "project": "test-project",
        "agents": [
            {
                "id": "agent-a",
                "role": "backend",
                "owns": ["src/backend/"],
                "consumes": [],
            }
        ],
    }
    (project_dir / "agents.yaml").write_text(yaml.dump(agents_yaml))

    return project_dir


def test_new_milestone_accepts_scope_file(tmp_path: Path):
    """vco new-milestone should accept --scope-file argument."""
    from vcompany.cli.new_milestone_cmd import new_milestone

    runner = CliRunner()
    result = runner.invoke(new_milestone, ["--help"])
    assert result.exit_code == 0
    assert "--scope-file" in result.output


def test_new_milestone_copies_scope_file(tmp_path: Path):
    """new-milestone should copy scope file to project_dir/context/MILESTONE-SCOPE.md."""
    project_dir = _setup_project(tmp_path)
    scope_file = tmp_path / "new-scope.md"
    scope_file.write_text("# New Milestone Scope\nBuild the widget.")

    from vcompany.cli.new_milestone_cmd import new_milestone

    runner = CliRunner()
    result = runner.invoke(new_milestone, [
        "--project-dir", str(project_dir),
        "--scope-file", str(scope_file),
    ])
    assert result.exit_code == 0
    copied = project_dir / "context" / "MILESTONE-SCOPE.md"
    assert copied.exists()
    assert "Build the widget" in copied.read_text()


def test_new_milestone_calls_sync_context(tmp_path: Path):
    """new-milestone should call sync_context_files to distribute updated docs."""
    project_dir = _setup_project(tmp_path)
    scope_file = tmp_path / "scope.md"
    scope_file.write_text("# Scope")

    from vcompany.cli.new_milestone_cmd import new_milestone

    runner = CliRunner()
    with patch("vcompany.cli.new_milestone_cmd.sync_context_files") as mock_sync:
        mock_sync.return_value = MagicMock(clones_updated=1, files_synced=3, errors=[])
        result = runner.invoke(new_milestone, [
            "--project-dir", str(project_dir),
            "--scope-file", str(scope_file),
        ])
    assert result.exit_code == 0
    mock_sync.assert_called_once()


def test_new_milestone_generates_pm_context(tmp_path: Path):
    """new-milestone should generate PM-CONTEXT.md via write_pm_context."""
    project_dir = _setup_project(tmp_path)
    scope_file = tmp_path / "scope.md"
    scope_file.write_text("# Scope")

    from vcompany.cli.new_milestone_cmd import new_milestone

    runner = CliRunner()
    with patch("vcompany.cli.new_milestone_cmd.write_pm_context") as mock_write:
        mock_write.return_value = project_dir / "context" / "PM-CONTEXT.md"
        with patch("vcompany.cli.new_milestone_cmd.sync_context_files") as mock_sync:
            mock_sync.return_value = MagicMock(clones_updated=1, files_synced=3, errors=[])
            result = runner.invoke(new_milestone, [
                "--project-dir", str(project_dir),
                "--scope-file", str(scope_file),
            ])
    assert result.exit_code == 0
    mock_write.assert_called_once()


def test_new_milestone_reset_flag(tmp_path: Path):
    """new-milestone with --reset should reset agent states in agents.json."""
    project_dir = _setup_project(tmp_path)
    scope_file = tmp_path / "scope.md"
    scope_file.write_text("# Scope")

    # Create agents.json with existing state
    agents_json = {
        "project": "test-project",
        "agents": {
            "agent-a": {
                "agent_id": "agent-a",
                "status": "running",
                "phase": 3,
            }
        },
    }
    (project_dir / "state" / "agents.json").write_text(json.dumps(agents_json))

    from vcompany.cli.new_milestone_cmd import new_milestone

    runner = CliRunner()
    with patch("vcompany.cli.new_milestone_cmd.sync_context_files") as mock_sync:
        mock_sync.return_value = MagicMock(clones_updated=1, files_synced=3, errors=[])
        with patch("vcompany.cli.new_milestone_cmd.write_pm_context") as mock_write:
            mock_write.return_value = project_dir / "context" / "PM-CONTEXT.md"
            result = runner.invoke(new_milestone, [
                "--project-dir", str(project_dir),
                "--scope-file", str(scope_file),
                "--reset",
            ])
    assert result.exit_code == 0

    # Check agents.json was reset
    updated = json.loads((project_dir / "state" / "agents.json").read_text())
    agent_state = updated["agents"]["agent-a"]
    assert agent_state["status"] == "idle"
    assert agent_state["phase"] == 1


def test_new_milestone_dispatch_flag(tmp_path: Path):
    """new-milestone with --dispatch should re-dispatch all agents."""
    project_dir = _setup_project(tmp_path)
    scope_file = tmp_path / "scope.md"
    scope_file.write_text("# Scope")

    from vcompany.cli.new_milestone_cmd import new_milestone

    runner = CliRunner()
    with (
        patch("vcompany.cli.new_milestone_cmd.sync_context_files") as mock_sync,
        patch("vcompany.cli.new_milestone_cmd.write_pm_context") as mock_write,
        patch("vcompany.cli.new_milestone_cmd.subprocess") as mock_subprocess,
    ):
        mock_sync.return_value = MagicMock(clones_updated=1, files_synced=3, errors=[])
        mock_write.return_value = project_dir / "context" / "PM-CONTEXT.md"
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        result = runner.invoke(new_milestone, [
            "--project-dir", str(project_dir),
            "--scope-file", str(scope_file),
            "--dispatch",
        ])
    assert result.exit_code == 0
    mock_subprocess.run.assert_called_once()


def test_new_milestone_registered_in_main():
    """new-milestone should be registered as a CLI command."""
    from vcompany.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["new-milestone", "--help"])
    assert result.exit_code == 0
    assert "--scope-file" in result.output
    assert "--reset" in result.output
    assert "--dispatch" in result.output
