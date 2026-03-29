"""vco hire -- Hire an agent via the daemon."""

from __future__ import annotations

import click
from rich.console import Console

from vcompany.cli.helpers import daemon_client


@click.command()
@click.argument("type_", metavar="TYPE")
@click.argument("name")
def hire(type_: str, name: str) -> None:
    """Hire an agent. Usage: vco hire TYPE NAME"""
    with daemon_client() as client:
        result = client.call("hire", {"agent_id": name, "template": type_})
        Console().print(f"[green]Hired agent: {result['agent_id']}[/green]")
