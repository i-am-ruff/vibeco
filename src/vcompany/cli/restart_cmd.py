"""vco restart -- Gracefully restart the vCompany bot.

Checks agent activity before restarting. Sends SIGTERM to the bot process
so vco-runner.sh can restart it with updated code.
"""

import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from vcompany.shared.paths import PROJECTS_BASE

PIDFILE = Path.home() / ".vco-runner.pid"
# File the bot watches to know a restart was requested
RESTART_SIGNAL = Path.home() / ".vco-restart-requested"


def _find_bot_pid() -> int | None:
    """Find the vco up process PID (child of the runner)."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "vco up"], capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            # May return multiple PIDs, take the first
            return int(result.stdout.strip().splitlines()[0])
    except Exception:
        pass
    return None


def _agents_are_active() -> tuple[bool, list[str]]:
    """Check if any agents have recent commits (active work).

    Returns (is_active, list of active agent descriptions).
    """
    active = []
    now = datetime.now(timezone.utc)

    for project_dir in PROJECTS_BASE.iterdir():
        if not project_dir.is_dir():
            continue
        clones_dir = project_dir / "clones"
        if not clones_dir.exists():
            continue

        for clone_dir in clones_dir.iterdir():
            if not clone_dir.is_dir() or not (clone_dir / ".git").exists():
                continue

            try:
                result = subprocess.run(
                    ["git", "-C", str(clone_dir), "log", "--format=%aI", "-1"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    commit_time = datetime.fromisoformat(result.stdout.strip())
                    if commit_time.tzinfo is None:
                        commit_time = commit_time.replace(tzinfo=timezone.utc)
                    elapsed = (now - commit_time).total_seconds()
                    if elapsed < 300:  # 5 minutes
                        agent_id = clone_dir.name
                        mins = int(elapsed / 60)
                        active.append(f"{agent_id} (last commit {mins}m ago)")
            except Exception:
                continue

    return (len(active) > 0, active)


@click.command()
@click.option("--force", is_flag=True, help="Restart even if agents are active")
def restart(force: bool) -> None:
    """Gracefully restart the vCompany bot.

    Checks that no agents are actively working before restarting.
    Requires vco-runner.sh to be running (auto-restarts the bot).
    """
    # Check runner is running
    if not PIDFILE.exists():
        click.echo(
            "ERROR: vco-runner.sh is not running (no pidfile at ~/.vco-runner.pid).\n"
            "Start it with: ./vco-runner.sh",
            err=True,
        )
        sys.exit(1)

    runner_pid = int(PIDFILE.read_text().strip())
    try:
        os.kill(runner_pid, 0)
    except ProcessLookupError:
        click.echo(
            f"ERROR: vco-runner.sh PID {runner_pid} is dead. Clean up and restart.",
            err=True,
        )
        PIDFILE.unlink(missing_ok=True)
        sys.exit(1)

    # Check agent activity
    if not force:
        is_active, active_agents = _agents_are_active()
        if is_active:
            click.echo("WARNING: Agents are actively working:")
            for desc in active_agents:
                click.echo(f"  - {desc}")
            click.echo("\nUse --force to restart anyway.")
            sys.exit(1)

    # Write restart signal file (bot reads this to know restart was requested)
    RESTART_SIGNAL.write_text(datetime.now(timezone.utc).isoformat())

    # Find and kill the bot process
    bot_pid = _find_bot_pid()
    if bot_pid:
        click.echo(f"Sending SIGTERM to bot (PID {bot_pid})...")
        try:
            os.kill(bot_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        # Wait for it to die
        for _ in range(20):
            try:
                os.kill(bot_pid, 0)
                time.sleep(0.5)
            except ProcessLookupError:
                break

        click.echo("Bot stopped. Runner will restart it in ~5s.")
    else:
        click.echo("WARNING: Could not find bot process. Runner will start a fresh one.")
