"""vco dismiss -- Dismiss an agent via the daemon."""

from __future__ import annotations

import click
from rich.console import Console

from vcompany.cli.helpers import daemon_client


@click.command()
@click.argument("agent_name")
def dismiss(agent_name: str) -> None:
    """Dismiss an agent. Usage: vco dismiss AGENT_NAME"""
    with daemon_client() as client:
        client.call("dismiss", {"agent_id": agent_name})
        Console().print(f"[green]Dismissed agent: {agent_name}[/green]")
