"""vco health -- Display color-coded health tree."""

from __future__ import annotations

import click
from rich.console import Console
from rich.tree import Tree

from vcompany.cli.helpers import daemon_client

_STATE_COLORS: dict[str, str] = {
    "running": "green",
    "idle": "blue",
    "sleeping": "dim",
    "error": "red",
    "blocked": "yellow",
    "creating": "cyan",
}


def _state_label(state: str) -> str:
    """Return a Rich-markup colored state label."""
    color = _STATE_COLORS.get(state, "white")
    return f"[{color}]{state}[/{color}]"


def _format_uptime(seconds: float) -> str:
    """Format uptime as human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.0f}m"
    return f"{seconds / 3600:.1f}h"


@click.command()
def health() -> None:
    """Show color-coded health tree of all agents."""
    with daemon_client() as client:
        data = client.call("health_tree")

    root_id = data.get("supervisor_id", "company-root")
    root_state = data.get("state", "unknown")
    tree = Tree(f"[bold]{root_id}[/bold] {_state_label(root_state)}")

    # Projects section
    projects = data.get("projects", [])
    if projects:
        proj_branch = tree.add("[bold]Projects[/bold]")
        for proj in projects:
            proj_id = proj.get("supervisor_id", "?")
            proj_state = proj.get("state", "unknown")
            proj_node = proj_branch.add(f"{proj_id} {_state_label(proj_state)}")
            for child in proj.get("children", []):
                report = child.get("report", {})
                aid = report.get("agent_id", "?")
                astate = report.get("state", "unknown")
                inner = report.get("inner_state", "")
                uptime = report.get("uptime", 0.0)
                proj_node.add(
                    f"{aid} {_state_label(astate)} "
                    f"inner={inner} up={_format_uptime(uptime)}"
                )

    # Company agents section
    company_agents = data.get("company_agents", [])
    if company_agents:
        ca_branch = tree.add("[bold]Company Agents[/bold]")
        for entry in company_agents:
            report = entry.get("report", {})
            aid = report.get("agent_id", "?")
            astate = report.get("state", "unknown")
            inner = report.get("inner_state", "")
            uptime = report.get("uptime", 0.0)
            ca_branch.add(
                f"{aid} {_state_label(astate)} "
                f"inner={inner} up={_format_uptime(uptime)}"
            )

    Console().print(tree)
