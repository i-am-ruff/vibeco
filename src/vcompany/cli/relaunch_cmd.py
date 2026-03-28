"""vco relaunch command -- kill then re-dispatch an agent.

Uses TmuxManager directly: kills the agent's tmux window and creates a
new one. When the bot is running, the supervision tree handles restarts
automatically; this command is for manual operator use.
"""

import os
import sys
import time
from pathlib import Path

import click

from vcompany.models.config import load_config
from vcompany.shared.paths import PROJECTS_BASE
from vcompany.tmux.session import TmuxManager


@click.command()
@click.argument("project_name")
@click.argument("agent_id")
def relaunch(project_name: str, agent_id: str) -> None:
    """Relaunch an agent (kill + re-dispatch)."""
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

    # Find agent in config
    agent_cfg = None
    for a in config.agents:
        if a.id == agent_id:
            agent_cfg = a
            break
    if agent_cfg is None:
        click.echo(f"Error: Agent '{agent_id}' not found in config", err=True)
        sys.exit(1)

    tmux = TmuxManager()
    session_name = f"vco-{project_name}"

    session = tmux.get_session(session_name)
    if session is None:
        click.echo(f"Error: Session '{session_name}' not found", err=True)
        sys.exit(1)

    # Kill existing window for this agent
    for window in session.windows:
        if window.window_name == agent_id:
            try:
                window.kill()
                click.echo(f"Killed existing '{agent_id}' window")
            except Exception:
                pass
            break

    # Re-dispatch: create new window and launch Claude
    pane = tmux.create_pane(session, window_name=agent_id)
    clone_dir = project_dir / "clones" / agent_id
    prompt_path = project_dir / "context" / "agents" / f"{agent_id}.md"

    chained_cmd = (
        f"cd {clone_dir} "
        f"&& export DISCORD_BOT_TOKEN='{os.environ.get('DISCORD_BOT_TOKEN', '')}' "
        f"&& export DISCORD_GUILD_ID='{os.environ.get('DISCORD_GUILD_ID', '')}' "
        f"&& export PROJECT_NAME='{project_name}' "
        f"&& export AGENT_ID='{agent_id}' "
        f"&& export VCO_AGENT_ID='{agent_id}' "
        f"&& export AGENT_ROLE='{agent_cfg.role}' "
        f"&& claude --dangerously-skip-permissions "
        f"--append-system-prompt-file {prompt_path}"
    )

    ok = tmux.send_command(pane, chained_cmd)
    if ok:
        time.sleep(3)
        pane.send_keys("", enter=True)
        pane_id = str(getattr(pane, "pane_id", ""))
        click.echo(f"Relaunched '{agent_id}' (pane={pane_id})")
    else:
        click.echo(f"Error: Failed to relaunch '{agent_id}'", err=True)
        sys.exit(1)
