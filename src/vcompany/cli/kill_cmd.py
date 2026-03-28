"""vco kill command -- terminate a running agent session or entire project.

Uses TmuxManager directly. When the bot is running, prefer the /kill slash
command which routes through the supervision tree for graceful shutdown.
"""

import sys

import click

from vcompany.tmux.session import TmuxManager


@click.command()
@click.argument("project_name")
@click.argument("agent_id", required=False, default=None)
@click.option("--all", "kill_all", is_flag=True, help="Kill entire tmux session for the project")
def kill(project_name: str, agent_id: str | None, kill_all: bool) -> None:
    """Kill a running agent session or the whole project session."""
    tmux = TmuxManager()
    session_name = f"vco-{project_name}"

    if kill_all:
        if tmux.kill_session(session_name):
            click.echo(f"Killed session '{session_name}' (all agents)")
        else:
            click.echo(f"Error: Session '{session_name}' not found", err=True)
            sys.exit(1)
    elif agent_id:
        # Find the agent's window in the session and kill it
        session = tmux.get_session(session_name)
        if session is None:
            click.echo(f"Error: Session '{session_name}' not found", err=True)
            sys.exit(1)

        killed = False
        for window in session.windows:
            if window.window_name == agent_id:
                try:
                    window.kill()
                    killed = True
                    click.echo(f"Killed agent '{agent_id}' (window in {session_name})")
                except Exception as e:
                    click.echo(f"Error killing agent '{agent_id}': {e}", err=True)
                    sys.exit(1)
                break

        if not killed:
            click.echo(f"Error: Agent '{agent_id}' not found in session '{session_name}'", err=True)
            sys.exit(1)
    else:
        click.echo("Specify agent ID or use --all", err=True)
        sys.exit(1)
