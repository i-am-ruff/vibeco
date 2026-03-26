"""Integration tests for vco init command."""

import shutil
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from vcompany.cli.init_cmd import init


@pytest.fixture()
def runner():
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture()
def projects_base(tmp_path, monkeypatch):
    """Override PROJECTS_BASE to use a temporary directory."""
    import vcompany.cli.init_cmd as init_mod

    monkeypatch.setattr(init_mod, "PROJECTS_BASE", tmp_path)
    return tmp_path


@pytest.fixture()
def valid_config(tmp_path):
    """Create a valid agents.yaml in a temporary directory."""
    config_path = tmp_path / "agents.yaml"
    config_path.write_text(
        textwrap.dedent("""\
        project: testproject
        repo: https://github.com/test/repo.git
        agents:
          - id: BACKEND
            role: backend developer
            owns:
              - src/backend/
            consumes: INTERFACES.md
            gsd_mode: full
            system_prompt: agents/BACKEND.md
          - id: FRONTEND
            role: frontend developer
            owns:
              - src/frontend/
            consumes: INTERFACES.md
            gsd_mode: full
            system_prompt: agents/FRONTEND.md
        shared_readonly:
          - package.json
        """)
    )
    return config_path


@pytest.fixture()
def context_files(tmp_path):
    """Create temporary context documents."""
    blueprint = tmp_path / "blueprint.md"
    blueprint.write_text("# Project Blueprint\nThis is the blueprint.")

    interfaces = tmp_path / "interfaces.md"
    interfaces.write_text("# Interfaces\nAPI contracts here.")

    milestone = tmp_path / "milestone.md"
    milestone.write_text("# Milestone v1\nBuild the core.")

    return {"blueprint": blueprint, "interfaces": interfaces, "milestone": milestone}


def test_init_creates_directory_structure(runner, projects_base, valid_config):
    """vco init creates clones/, context/, and context/agents/ directories."""
    result = runner.invoke(init, ["myproject", "--config", str(valid_config)])
    assert result.exit_code == 0, f"Failed: {result.output}"

    project_dir = projects_base / "myproject"
    assert (project_dir / "clones").is_dir()
    assert (project_dir / "context").is_dir()
    assert (project_dir / "context" / "agents").is_dir()


def test_init_copies_agents_yaml(runner, projects_base, valid_config):
    """vco init copies agents.yaml to the project root."""
    result = runner.invoke(init, ["myproject", "--config", str(valid_config)])
    assert result.exit_code == 0, f"Failed: {result.output}"

    project_dir = projects_base / "myproject"
    copied = project_dir / "agents.yaml"
    assert copied.exists()
    assert "testproject" in copied.read_text()


def test_init_copies_context_docs(runner, projects_base, valid_config, context_files):
    """vco init copies blueprint, interfaces, and milestone when provided."""
    result = runner.invoke(
        init,
        [
            "myproject",
            "--config",
            str(valid_config),
            "--blueprint",
            str(context_files["blueprint"]),
            "--interfaces",
            str(context_files["interfaces"]),
            "--milestone",
            str(context_files["milestone"]),
        ],
    )
    assert result.exit_code == 0, f"Failed: {result.output}"

    ctx = projects_base / "myproject" / "context"
    assert (ctx / "PROJECT-BLUEPRINT.md").exists()
    assert (ctx / "INTERFACES.md").exists()
    assert (ctx / "MILESTONE-SCOPE.md").exists()
    assert "Project Blueprint" in (ctx / "PROJECT-BLUEPRINT.md").read_text()


def test_init_generates_agent_prompts(runner, projects_base, valid_config):
    """vco init generates system prompt files for each agent."""
    result = runner.invoke(init, ["myproject", "--config", str(valid_config)])
    assert result.exit_code == 0, f"Failed: {result.output}"

    agents_dir = projects_base / "myproject" / "context" / "agents"
    assert (agents_dir / "BACKEND.md").exists()
    assert (agents_dir / "FRONTEND.md").exists()


def test_init_agent_prompt_content(runner, projects_base, valid_config):
    """Generated agent prompts contain correct agent ID and rules."""
    result = runner.invoke(init, ["myproject", "--config", str(valid_config)])
    assert result.exit_code == 0, f"Failed: {result.output}"

    backend_prompt = (
        projects_base / "myproject" / "context" / "agents" / "BACKEND.md"
    ).read_text()
    assert "You are BACKEND" in backend_prompt
    assert "NEVER create or modify files outside" in backend_prompt
    assert "backend developer" in backend_prompt


def test_init_rejects_invalid_config(runner, projects_base, tmp_path):
    """vco init exits 1 on invalid YAML config and creates no directories."""
    bad_config = tmp_path / "bad.yaml"
    bad_config.write_text("not: valid: yaml: [")

    result = runner.invoke(init, ["myproject", "--config", str(bad_config)])
    assert result.exit_code == 1

    # No project directory should have been created
    assert not (projects_base / "myproject").exists()


def test_init_rejects_existing_project(runner, projects_base, valid_config):
    """vco init fails if the project directory already exists."""
    # First init succeeds
    result1 = runner.invoke(init, ["myproject", "--config", str(valid_config)])
    assert result1.exit_code == 0

    # Second init fails
    result2 = runner.invoke(init, ["myproject", "--config", str(valid_config)])
    assert result2.exit_code == 1
    assert "already exists" in result2.output.lower()


def test_init_without_optional_docs(runner, projects_base, valid_config):
    """vco init succeeds without blueprint/interfaces/milestone."""
    result = runner.invoke(init, ["myproject", "--config", str(valid_config)])
    assert result.exit_code == 0

    ctx = projects_base / "myproject" / "context"
    assert not (ctx / "PROJECT-BLUEPRINT.md").exists()
    assert not (ctx / "INTERFACES.md").exists()
    assert not (ctx / "MILESTONE-SCOPE.md").exists()
