"""vco dispatch command -- launch Claude Code agent sessions in tmux panes."""

import sys
from pathlib import Path

import click

from vcompany.cli.init_cmd import PROJECTS_BASE
from vcompany.models.config import load_config
from vcompany.orchestrator.agent_manager import AgentManager


@click.command()
@click.argument("project_name")
@click.argument("agent_id", required=False, default=None)
@click.option("--all", "dispatch_all", is_flag=True, help="Dispatch all agents")
def dispatch(project_name: str, agent_id: str | None, dispatch_all: bool) -> None:
    """Launch Claude Code sessions for agents in a project."""
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

    if dispatch_all:
        results = manager.dispatch_all()
        for r in results:
            status = "OK" if r.success else f"FAIL: {r.error}"
            click.echo(f"  {r.agent_id}: {status}")
        ok_count = sum(1 for r in results if r.success)
        click.echo(f"Dispatched {ok_count}/{len(results)} agents for '{project_name}'")
    elif agent_id:
        result = manager.dispatch(agent_id)
        if result.success:
            click.echo(f"Dispatched '{agent_id}' (pane={result.pane_id}, pid={result.pid})")
        else:
            click.echo(f"Error: {result.error}", err=True)
            sys.exit(1)
    else:
        click.echo("Specify agent ID or use --all", err=True)
        sys.exit(1)
