"""vco dispatch command -- launch Claude Code agent sessions in tmux panes.

Uses TmuxManager directly for CLI-only dispatch (independent of the supervision
tree / Discord bot). When 'vco up' is running, the bot's CompanyRoot handles
agent lifecycle; this command is for manual operator use.
"""

import os
import sys
import time
from pathlib import Path

import click

from vcompany.models.config import load_config
from vcompany.shared.paths import PROJECTS_BASE
from vcompany.tmux.session import TmuxManager


def _dispatch_agent(
    tmux: TmuxManager,
    session,
    agent_cfg,
    project_dir: Path,
    project_name: str,
) -> tuple[str, bool]:
    """Dispatch a single agent into a tmux pane. Returns (pane_id, success)."""
    pane = tmux.create_pane(session, window_name=agent_cfg.id)
    clone_dir = project_dir / "clones" / agent_cfg.id
    prompt_path = project_dir / "context" / "agents" / f"{agent_cfg.id}.md"

    chained_cmd = (
        f"cd {clone_dir} "
        f"&& export DISCORD_BOT_TOKEN='{os.environ.get('DISCORD_BOT_TOKEN', '')}' "
        f"&& export DISCORD_GUILD_ID='{os.environ.get('DISCORD_GUILD_ID', '')}' "
        f"&& export PROJECT_NAME='{project_name}' "
        f"&& export AGENT_ID='{agent_cfg.id}' "
        f"&& export VCO_AGENT_ID='{agent_cfg.id}' "
        f"&& export AGENT_ROLE='{agent_cfg.role}' "
        f"&& claude --dangerously-skip-permissions "
        f"--append-system-prompt-file {prompt_path}"
    )

    ok = tmux.send_command(pane, chained_cmd)
    if ok:
        # Auto-accept workspace trust prompt
        time.sleep(3)
        pane.send_keys("", enter=True)

    pane_id = str(getattr(pane, "pane_id", ""))
    return pane_id, ok


@click.command()
@click.argument("project_name")
@click.argument("agent_id", required=False, default=None)
@click.option("--all", "dispatch_all", is_flag=True, help="Dispatch all agents")
@click.option("--command", "-cmd", default=None, help="GSD command to send after launch (e.g., '/gsd:plan-phase 1 --auto')")
@click.option("--resume", is_flag=True, help="Send /gsd:resume-work after launch")
def dispatch(project_name: str, agent_id: str | None, dispatch_all: bool, command: str | None, resume: bool) -> None:
    """Launch Claude Code sessions for agents in a project."""
    # Warn if vco up is not running (no supervision tree watching agents)
    import subprocess
    try:
        result = subprocess.run(
            ["pgrep", "-f", "vco up"], capture_output=True, text=True
        )
        if result.returncode != 0:
            click.echo(
                "WARNING: 'vco up' is not running. Agents will launch but the supervision "
                "tree will not supervise them (no health monitoring, no auto-restart).\n"
                "Run 'vco up' first for full orchestration.",
                err=True,
            )
    except Exception:
        pass  # pgrep not available, skip check

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

    tmux = TmuxManager()
    session_name = f"vco-{project_name}"

    # Determine what work command to send after Claude starts
    work_cmd = command
    if resume and not work_cmd:
        work_cmd = "/gsd:resume-work"

    if dispatch_all:
        session = tmux.create_session(session_name)
        ok_count = 0
        for agent_cfg in config.agents:
            pane_id, ok = _dispatch_agent(tmux, session, agent_cfg, project_dir, project_name)
            status = "OK" if ok else "FAIL"
            click.echo(f"  {agent_cfg.id}: {status} (pane={pane_id})")
            if ok:
                ok_count += 1
        click.echo(f"Dispatched {ok_count}/{len(config.agents)} agents for '{project_name}'")

        if work_cmd and ok_count > 0:
            click.echo(f"  Note: work command '{work_cmd}' must be sent manually via tmux or 'vco up'.")

    elif agent_id:
        # Find agent in config
        agent_cfg = None
        for a in config.agents:
            if a.id == agent_id:
                agent_cfg = a
                break
        if agent_cfg is None:
            click.echo(f"Error: Agent '{agent_id}' not found in config", err=True)
            sys.exit(1)

        session = tmux.get_or_create_session(session_name)
        pane_id, ok = _dispatch_agent(tmux, session, agent_cfg, project_dir, project_name)
        if ok:
            click.echo(f"Dispatched '{agent_id}' (pane={pane_id})")
            if work_cmd:
                click.echo(f"  Note: work command '{work_cmd}' must be sent manually via tmux or 'vco up'.")
        else:
            click.echo(f"Error: Failed to dispatch '{agent_id}'", err=True)
            sys.exit(1)
    else:
        click.echo("Specify agent ID or use --all", err=True)
        sys.exit(1)
