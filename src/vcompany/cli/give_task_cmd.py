"""vco give-task -- Queue a task for an agent via the daemon."""

from __future__ import annotations

import click
from rich.console import Console

from vcompany.cli.helpers import daemon_client


@click.command("give-task")
@click.argument("agent_name")
@click.argument("task")
def give_task(agent_name: str, task: str) -> None:
    """Give a task to an agent. Usage: vco give-task AGENT_NAME TASK"""
    with daemon_client() as client:
        client.call("give_task", {"agent_id": agent_name, "task": task})
        Console().print(f"[green]Task queued for {agent_name}[/green]")
