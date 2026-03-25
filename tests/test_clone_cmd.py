"""Integration tests for vco clone command."""

import subprocess
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner


AGENTS_YAML = textwrap.dedent("""\
project: testproject
repo: {repo_url}
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


@pytest.fixture()
def runner():
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture()
def bare_repo(tmp_path):
    """Create a bare git repo with one commit for cloning."""
    repo_dir = tmp_path / "source-repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", str(repo_dir)], capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_dir, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_dir, capture_output=True, check=True,
    )
    # Create initial commit
    readme = repo_dir / "README.md"
    readme.write_text("# Test Repo")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo_dir, capture_output=True, check=True,
    )
    return repo_dir


@pytest.fixture()
def initialized_project(tmp_path, bare_repo, monkeypatch):
    """Create an initialized project directory with agents.yaml pointing to bare_repo."""
    import vcompany.cli.clone_cmd as clone_mod

    monkeypatch.setattr(clone_mod, "PROJECTS_BASE", tmp_path)

    project_dir = tmp_path / "testproject"
    project_dir.mkdir()
    (project_dir / "clones").mkdir()
    (project_dir / "context").mkdir()
    (project_dir / "agents.yaml").write_text(
        AGENTS_YAML.format(repo_url=str(bare_repo))
    )
    return project_dir


def test_clone_creates_agent_repos(runner, initialized_project):
    """Clone creates clones/BACKEND/ and clones/FRONTEND/ directories."""
    from vcompany.cli.clone_cmd import clone

    result = runner.invoke(clone, ["testproject"])
    assert result.exit_code == 0, f"Failed: {result.output}"

    clones_dir = initialized_project / "clones"
    assert (clones_dir / "BACKEND").is_dir()
    assert (clones_dir / "FRONTEND").is_dir()


def test_clone_creates_agent_branches(runner, initialized_project):
    """Each clone is on branch agent/{id} (lowercase)."""
    from vcompany.cli.clone_cmd import clone

    result = runner.invoke(clone, ["testproject"])
    assert result.exit_code == 0, f"Failed: {result.output}"

    clones_dir = initialized_project / "clones"
    for agent_id in ["BACKEND", "FRONTEND"]:
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=clones_dir / agent_id,
            capture_output=True, text=True,
        )
        assert branch_result.stdout.strip() == f"agent/{agent_id.lower()}"


def test_clone_deploys_settings_json(runner, initialized_project):
    """Verify .claude/settings.json exists and contains AskUserQuestion."""
    from vcompany.cli.clone_cmd import clone

    result = runner.invoke(clone, ["testproject"])
    assert result.exit_code == 0, f"Failed: {result.output}"

    settings = initialized_project / "clones" / "BACKEND" / ".claude" / "settings.json"
    assert settings.exists()
    content = settings.read_text()
    assert "AskUserQuestion" in content


def test_clone_deploys_gsd_config(runner, initialized_project):
    """Verify .planning/config.json exists and contains yolo mode."""
    from vcompany.cli.clone_cmd import clone

    result = runner.invoke(clone, ["testproject"])
    assert result.exit_code == 0, f"Failed: {result.output}"

    config = initialized_project / "clones" / "BACKEND" / ".planning" / "config.json"
    assert config.exists()
    content = config.read_text()
    assert '"mode": "yolo"' in content


def test_claude_md_content(runner, initialized_project):
    """Verify CLAUDE.md contains agent ID, Cross-Agent Context, and lists other agents."""
    from vcompany.cli.clone_cmd import clone

    result = runner.invoke(clone, ["testproject"])
    assert result.exit_code == 0, f"Failed: {result.output}"

    claude_md = initialized_project / "clones" / "BACKEND" / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text()
    assert "Cross-Agent Context" in content
    assert "BACKEND" in content
    assert "FRONTEND" in content


def test_command_files_deployed(runner, initialized_project):
    """Verify .claude/commands/vco/checkin.md and standup.md exist."""
    from vcompany.cli.clone_cmd import clone

    result = runner.invoke(clone, ["testproject"])
    assert result.exit_code == 0, f"Failed: {result.output}"

    commands_dir = initialized_project / "clones" / "BACKEND" / ".claude" / "commands" / "vco"
    assert (commands_dir / "checkin.md").exists()
    assert (commands_dir / "standup.md").exists()


def test_checkin_md_content(runner, initialized_project):
    """Verify deployed checkin.md contains 'Post a checkin'."""
    from vcompany.cli.clone_cmd import clone

    result = runner.invoke(clone, ["testproject"])
    assert result.exit_code == 0, f"Failed: {result.output}"

    checkin = initialized_project / "clones" / "BACKEND" / ".claude" / "commands" / "vco" / "checkin.md"
    assert "Post a checkin" in checkin.read_text()


def test_standup_md_content(runner, initialized_project):
    """Verify deployed standup.md contains 'interactive group standup'."""
    from vcompany.cli.clone_cmd import clone

    result = runner.invoke(clone, ["testproject"])
    assert result.exit_code == 0, f"Failed: {result.output}"

    standup = initialized_project / "clones" / "BACKEND" / ".claude" / "commands" / "vco" / "standup.md"
    assert "interactive group standup" in standup.read_text()


def test_clone_force_reclone(runner, initialized_project):
    """Clone once, then clone with --force, verify fresh clone."""
    from vcompany.cli.clone_cmd import clone

    # First clone
    result1 = runner.invoke(clone, ["testproject"])
    assert result1.exit_code == 0, f"Failed: {result1.output}"

    # Create a marker file to verify re-clone
    marker = initialized_project / "clones" / "BACKEND" / "MARKER.txt"
    marker.write_text("should be gone after force")

    # Force re-clone
    result2 = runner.invoke(clone, ["testproject", "--force"])
    assert result2.exit_code == 0, f"Failed: {result2.output}"

    # Marker should be gone (fresh clone)
    assert not marker.exists()
    # But clone should still work
    assert (initialized_project / "clones" / "BACKEND").is_dir()


def test_clone_skip_existing(runner, initialized_project):
    """Clone twice without force, verify skip message."""
    from vcompany.cli.clone_cmd import clone

    # First clone
    result1 = runner.invoke(clone, ["testproject"])
    assert result1.exit_code == 0, f"Failed: {result1.output}"

    # Second clone without force
    result2 = runner.invoke(clone, ["testproject"])
    assert result2.exit_code == 0, f"Failed: {result2.output}"
    assert "already exists" in result2.output.lower() or "use --force" in result2.output.lower()


def test_clone_project_not_found(runner, tmp_path, monkeypatch):
    """Clone nonexistent project, verify error exit."""
    import vcompany.cli.clone_cmd as clone_mod

    monkeypatch.setattr(clone_mod, "PROJECTS_BASE", tmp_path)
    from vcompany.cli.clone_cmd import clone

    result = runner.invoke(clone, ["nonexistent"])
    assert result.exit_code == 1


def test_clone_failed_git_no_partial(runner, tmp_path, monkeypatch):
    """Point to bad repo URL, verify no partial clone_dir left."""
    import vcompany.cli.clone_cmd as clone_mod

    monkeypatch.setattr(clone_mod, "PROJECTS_BASE", tmp_path)

    project_dir = tmp_path / "badproject"
    project_dir.mkdir()
    (project_dir / "clones").mkdir()
    (project_dir / "agents.yaml").write_text(
        AGENTS_YAML.format(repo_url="https://invalid.example.com/no-repo.git")
    )

    from vcompany.cli.clone_cmd import clone

    result = runner.invoke(clone, ["badproject"])
    # Command should still exit 0 (continues past failed agents) but no clone dirs
    clones_dir = project_dir / "clones"
    assert not (clones_dir / "BACKEND").exists()
    assert not (clones_dir / "FRONTEND").exists()
