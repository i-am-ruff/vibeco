"""vco relaunch command -- kill then re-dispatch an agent with resume."""

import sys
from pathlib import Path

import click

from vcompany.shared.paths import PROJECTS_BASE
from vcompany.models.config import load_config
from vcompany.orchestrator.agent_manager import AgentManager


@click.command()
@click.argument("project_name")
@click.argument("agent_id")
def relaunch(project_name: str, agent_id: str) -> None:
    """Relaunch an agent with /gsd:resume-work."""
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
    result = manager.relaunch(agent_id)

    if result.success:
        click.echo(f"Relaunched '{agent_id}' (pane={result.pane_id}, pid={result.pid})")
    else:
        click.echo(f"Error: {result.error}", err=True)
        sys.exit(1)
