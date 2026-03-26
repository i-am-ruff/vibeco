"""vco dispatch command -- launch Claude Code agent sessions in tmux panes."""

import sys
import time
from pathlib import Path

import click

from vcompany.shared.paths import PROJECTS_BASE
from vcompany.models.config import load_config
from vcompany.orchestrator.agent_manager import AgentManager

# Time to wait for Claude Code to start before sending work command
_CLAUDE_STARTUP_DELAY = 15


@click.command()
@click.argument("project_name")
@click.argument("agent_id", required=False, default=None)
@click.option("--all", "dispatch_all", is_flag=True, help="Dispatch all agents")
@click.option("--command", "-cmd", default=None, help="GSD command to send after launch (e.g., '/gsd:plan-phase 1 --auto')")
@click.option("--resume", is_flag=True, help="Send /gsd:resume-work after launch")
def dispatch(project_name: str, agent_id: str | None, dispatch_all: bool, command: str | None, resume: bool) -> None:
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

    # Determine what work command to send after Claude starts
    work_cmd = command
    if resume and not work_cmd:
        work_cmd = "/gsd:resume-work"

    if dispatch_all:
        results = manager.dispatch_all()
        for r in results:
            status = "OK" if r.success else f"FAIL: {r.error}"
            click.echo(f"  {r.agent_id}: {status}")
        ok_count = sum(1 for r in results if r.success)
        click.echo(f"Dispatched {ok_count}/{len(results)} agents for '{project_name}'")

        # Send work command to all agents after Claude starts
        if work_cmd and ok_count > 0:
            click.echo(f"  Waiting {_CLAUDE_STARTUP_DELAY}s for Claude to start...")
            time.sleep(_CLAUDE_STARTUP_DELAY)
            sent = manager.send_work_command_all(work_cmd)
            for aid, ok in sent.items():
                if ok:
                    click.echo(f"  {aid}: sent '{work_cmd}'")
                else:
                    click.echo(f"  {aid}: FAILED to send command")
    elif agent_id:
        result = manager.dispatch(agent_id)
        if result.success:
            click.echo(f"Dispatched '{agent_id}' (pane={result.pane_id}, pid={result.pid})")
            if work_cmd:
                click.echo(f"  Waiting {_CLAUDE_STARTUP_DELAY}s for Claude to start...")
                time.sleep(_CLAUDE_STARTUP_DELAY)
                if manager.send_work_command(agent_id, work_cmd):
                    click.echo(f"  Sent '{work_cmd}'")
                else:
                    click.echo(f"  FAILED to send command", err=True)
        else:
            click.echo(f"Error: {result.error}", err=True)
            sys.exit(1)
    else:
        click.echo("Specify agent ID or use --all", err=True)
        sys.exit(1)
