"""vco kill command -- terminate a running agent session."""

import sys
from pathlib import Path

import click

from vcompany.shared.paths import PROJECTS_BASE
from vcompany.models.config import load_config
from vcompany.orchestrator.agent_manager import AgentManager


@click.command()
@click.argument("project_name")
@click.argument("agent_id")
@click.option("--force", is_flag=True, help="Skip SIGTERM, send SIGKILL immediately")
def kill(project_name: str, agent_id: str, force: bool) -> None:
    """Kill a running agent session."""
    project_dir = PROJECTS_BASE / project_name
    if not project_dir.is_dir():
        click.echo(f"Error: Project '{project_name}' not found at {project_dir}", err=True)
        sys.exit(1)

    config_path = project_dir / "agents.yaml"
    try:
        config = load_config(config_path)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(1)

    manager = AgentManager(project_dir, config)
    success = manager.kill(agent_id, force=force)

    if success:
        click.echo(f"Killed agent '{agent_id}'")
    else:
        click.echo(f"Error: Agent '{agent_id}' not found in registry", err=True)
        sys.exit(1)
