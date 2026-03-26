"""vco init command -- initialize a new vCompany project."""

import shutil
from pathlib import Path

import click
import yaml
from pydantic import ValidationError

from vcompany.models.config import load_config
from vcompany.shared.file_ops import write_atomic
from vcompany.shared.paths import PROJECTS_BASE
from vcompany.shared.templates import render_template


@click.command()
@click.argument("project_name")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    required=True,
    help="Path to agents.yaml",
)
@click.option(
    "--blueprint",
    type=click.Path(exists=True),
    default=None,
    help="Path to PROJECT-BLUEPRINT.md",
)
@click.option(
    "--interfaces",
    type=click.Path(exists=True),
    default=None,
    help="Path to INTERFACES.md",
)
@click.option(
    "--milestone",
    type=click.Path(exists=True),
    default=None,
    help="Path to MILESTONE-SCOPE.md",
)
def init(
    project_name: str,
    config_path: str,
    blueprint: str | None,
    interfaces: str | None,
    milestone: str | None,
) -> None:
    """Initialize a new vCompany project."""
    # 1. Validate config -- fail fast with clear error (per D-04)
    try:
        config = load_config(Path(config_path))
    except (ValidationError, yaml.YAMLError) as e:
        click.echo(f"Error: Invalid configuration file: {e}", err=True)
        raise SystemExit(1)

    # 2. Check for existing project
    project_dir = PROJECTS_BASE / project_name
    if project_dir.exists():
        click.echo(f"Error: Project already exists: {project_dir}", err=True)
        raise SystemExit(1)

    # 3. Create directory structure (per D-10)
    clones_dir = project_dir / "clones"
    context_dir = project_dir / "context"
    agents_dir = context_dir / "agents"

    clones_dir.mkdir(parents=True)
    context_dir.mkdir(parents=True)
    agents_dir.mkdir(parents=True)

    # 4. Copy agents.yaml to project root
    shutil.copy2(config_path, project_dir / "agents.yaml")

    # 5. Copy context documents if provided (per D-11)
    if blueprint:
        shutil.copy2(blueprint, context_dir / "PROJECT-BLUEPRINT.md")
    if interfaces:
        shutil.copy2(interfaces, context_dir / "INTERFACES.md")
    if milestone:
        shutil.copy2(milestone, context_dir / "MILESTONE-SCOPE.md")

    # 6. Generate agent system prompts (per COORD-04, D-08)
    for agent in config.agents:
        prompt_content = render_template(
            "agent_prompt.md.j2",
            agent_id=agent.id,
            role=agent.role,
            project_name=config.project,
            owned_dirs=agent.owns,
            consumes=agent.consumes,
            milestone_name="TBD",
            milestone_scope="See MILESTONE-SCOPE.md",
        )
        write_atomic(agents_dir / f"{agent.id}.md", prompt_content)

    # 7. Success message
    click.echo(f"Project '{project_name}' initialized at {project_dir}")
