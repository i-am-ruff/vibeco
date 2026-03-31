"""CLI command: vco clean -- wipe all local runtime state for a fresh start."""

import glob
import shutil
from pathlib import Path

import click


@click.command("clean")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def clean(force: bool) -> None:
    """Wipe all local runtime state for a completely fresh start.

    Removes:
    - Worker socket files (/tmp/vco-worker-*.sock)
    - Worker state directories (.vco-state/)
    - Agent working directories (~/vco-tasks/)
    - Routing state (state/supervision/routing.json)
    - Daemon socket and PID files
    - Scheduler database

    Does NOT remove:
    - Discord channels (use discord_clean.py for that)
    - Project config (agents.yaml, blueprints)
    - .planning/ artifacts
    - Git history
    """
    items: list[tuple[str, Path | str]] = []

    # Worker sockets
    sockets = glob.glob("/tmp/vco-worker-*.sock")
    for s in sockets:
        items.append(("Worker socket", Path(s)))

    # Daemon socket + PID
    daemon_sock = Path("/tmp/vco-daemon.sock")
    daemon_pid = Path("/tmp/vco-daemon.pid")
    signal_sock = Path("/tmp/vco-signal.sock")
    for f in (daemon_sock, daemon_pid, signal_sock):
        if f.exists():
            items.append(("Daemon file", f))

    # Worker state dirs
    vco_state = Path.cwd() / ".vco-state"
    if vco_state.exists():
        items.append(("Worker state dir", vco_state))

    # Agent working directories
    tasks_dir = Path.home() / "vco-tasks"
    if tasks_dir.exists():
        items.append(("Agent tasks dir", tasks_dir))

    # Routing state (project-specific)
    for routing in Path.cwd().glob("**/state/supervision/routing.json"):
        items.append(("Routing state", routing))

    # Scheduler DB
    for sched in Path.cwd().glob("**/state/supervision/scheduler/memory.db"):
        items.append(("Scheduler DB", sched))

    if not items:
        click.echo("Nothing to clean -- already fresh.")
        return

    click.echo("Will remove:")
    for label, path in items:
        click.echo(f"  {label}: {path}")
    click.echo(f"\nTotal: {len(items)} items")

    if not force:
        click.confirm("\nProceed?", abort=True)

    removed = 0
    for label, path in items:
        p = Path(path)
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink(missing_ok=True)
            removed += 1
        except OSError as e:
            click.echo(f"  Warning: could not remove {path}: {e}", err=True)

    click.echo(f"\nCleaned {removed}/{len(items)} items. Ready for fresh start.")
