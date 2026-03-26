"""vco clone command -- creates per-agent repository clones with artifact deployment."""

import shutil
import sys
from pathlib import Path

import click

from vcompany.git import ops as git
from vcompany.models.config import load_config
from vcompany.shared.file_ops import write_atomic
from vcompany.shared.paths import PROJECTS_BASE
from vcompany.shared.templates import render_template

# Source directory for vco command files (project root / commands / vco)
_COMMANDS_SOURCE = Path(__file__).parent.parent.parent.parent / "commands" / "vco"


def _deploy_artifacts(clone_dir: Path, agent, config, project_dir: Path) -> None:
    """Deploy all artifact types to an agent clone.

    Args:
        clone_dir: Root of the agent's cloned repository.
        agent: AgentConfig for this agent.
        config: Full ProjectConfig (needed for other_agents list).
        project_dir: Project root (for planning artifacts).
    """
    claude_dir = clone_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)

    # 1. .claude/settings.json (AskUserQuestion hook config)
    settings_content = render_template("settings.json.j2")
    write_atomic(claude_dir / "settings.json", settings_content)

    # 2. .planning/config.json (GSD yolo mode config)
    planning_dir = clone_dir / ".planning"
    planning_dir.mkdir(exist_ok=True)
    gsd_config = render_template("gsd_config.json.j2")
    write_atomic(planning_dir / "config.json", gsd_config)

    # 3. CLAUDE.md (agent identity and cross-agent awareness)
    other_agents = [a for a in config.agents if a.id != agent.id]
    claude_md = render_template(
        "claude_md.md.j2",
        agent_id=agent.id,
        role=agent.role,
        owned_dirs=agent.owns,
        consumes=agent.consumes,
        other_agents=other_agents,
    )
    write_atomic(clone_dir / "CLAUDE.md", claude_md)

    # 4. .claude/commands/vco/checkin.md and standup.md
    commands_dir = claude_dir / "commands" / "vco"
    commands_dir.mkdir(parents=True, exist_ok=True)
    for cmd_file in ["checkin.md", "standup.md", "report.md"]:
        src = _COMMANDS_SOURCE / cmd_file
        if src.exists():
            shutil.copy2(src, commands_dir / cmd_file)

    # 5. Deploy planning artifacts if they exist in project context.
    #    These are pre-built by the Strategist or owner so agents don't
    #    need to run /gsd:new-project (which requires interactive input).
    planning_source = project_dir / "planning"
    if planning_source.is_dir():
        for artifact in planning_source.iterdir():
            if artifact.is_file() and artifact.suffix == ".md":
                shutil.copy2(artifact, planning_dir / artifact.name)


@click.command()
@click.argument("project_name")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Delete and re-clone existing agent directories",
)
def clone(project_name: str, force: bool) -> None:
    """Clone repos and deploy artifacts for all agents in a project."""
    project_dir = PROJECTS_BASE / project_name
    if not project_dir.is_dir():
        click.echo(f"Error: Project '{project_name}' not found at {project_dir}")
        click.echo("Run 'vco init' first to create the project.")
        sys.exit(1)

    config_path = project_dir / "agents.yaml"
    try:
        config = load_config(config_path)
    except Exception as e:
        click.echo(f"Error loading config: {e}")
        sys.exit(1)

    cloned_count = 0

    for agent in config.agents:
        clone_dir = project_dir / "clones" / agent.id

        # Handle existing clone
        if clone_dir.exists():
            if force:
                click.echo(f"  Removing existing clone for {agent.id}...")
                shutil.rmtree(clone_dir)
            else:
                click.echo(
                    f"  Clone already exists for {agent.id}, use --force to re-clone"
                )
                continue

        # Clone the repository
        click.echo(f"  Cloning {config.repo} for {agent.id}...")
        result = git.clone(config.repo, clone_dir)
        if not result.success:
            click.echo(f"  Error cloning for {agent.id}: {result.stderr}")
            # Clean up partial state (Pitfall 5)
            if clone_dir.exists():
                shutil.rmtree(clone_dir)
            continue

        # Create agent branch (lowercase per Pitfall 7)
        branch_result = git.checkout_new_branch(
            f"agent/{agent.id.lower()}", cwd=clone_dir
        )
        if not branch_result.success:
            click.echo(f"  Error creating branch for {agent.id}: {branch_result.stderr}")
            shutil.rmtree(clone_dir)
            continue

        # Deploy all artifacts
        _deploy_artifacts(clone_dir, agent, config, project_dir)
        cloned_count += 1
        click.echo(f"  {agent.id} ready")

    click.echo(f"Cloned {cloned_count} agents for project '{project_name}'")
