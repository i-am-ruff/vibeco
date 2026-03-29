"""vco status -- Display active projects and agents."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from vcompany.cli.helpers import daemon_client


@click.command()
def status() -> None:
    """Show active projects and company agents."""
    with daemon_client() as client:
        data = client.call("status")

    projects: dict = data.get("projects", {})
    company_agents: list = data.get("company_agents", [])

    if not projects and not company_agents:
        click.echo("No active projects or agents")
        return

    table = Table(title="vCompany Status")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Info")

    for pid, info in projects.items():
        agent_count = info.get("agents", 0)
        table.add_row("Project", pid, f"{agent_count} agents")

    for agent_id in company_agents:
        table.add_row("Agent", agent_id, "company")

    Console().print(table)
