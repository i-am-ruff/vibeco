"""vco monitor command -- start the monitor loop for a project."""

import asyncio
import logging
import sys
from pathlib import Path

import click

from vcompany.shared.paths import PROJECTS_BASE
from vcompany.models.config import load_config
from vcompany.monitor.loop import MonitorLoop
from vcompany.tmux.session import TmuxManager

logger = logging.getLogger("vcompany.monitor")


@click.command("monitor")
@click.argument("project_name")
@click.option("--interval", default=60, help="Cycle interval in seconds")
def monitor(project_name: str, interval: int) -> None:
    """Start the monitor loop for a project."""
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

    # Default callbacks log warnings (placeholders for Phase 4 Discord integration)
    def on_agent_dead(agent_id: str) -> None:
        logger.warning("ALERT: Agent %s is dead", agent_id)

    def on_agent_stuck(agent_id: str) -> None:
        logger.warning(
            "ALERT: Agent %s appears stuck (no commits 30+ min)", agent_id
        )

    def on_plan_detected(agent_id: str, plan_path: Path) -> None:
        logger.info("PLAN GATE: New plan detected for %s: %s", agent_id, plan_path)

    loop = MonitorLoop(
        project_dir,
        config,
        tmux,
        on_agent_dead=on_agent_dead,
        on_agent_stuck=on_agent_stuck,
        on_plan_detected=on_plan_detected,
        cycle_interval=interval,
    )

    click.echo(f"Starting monitor loop for '{project_name}' (interval={interval}s)")
    click.echo("Press Ctrl+C to stop.")

    try:
        asyncio.run(loop.run())
    except KeyboardInterrupt:
        loop.stop()
        click.echo("\nMonitor stopped.")
