"""vco report -- agents report status to their Discord channel via daemon socket.

Routes through the daemon's CommunicationPort abstraction instead of hitting
Discord API directly. Works for both local and Docker agents — only needs
the daemon socket (no network, no bot token).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import click

from vcompany.cli.helpers import daemon_client


@click.command()
@click.argument("status", nargs=-1, required=True)
def report(status: tuple[str, ...]) -> None:
    """Report agent status to Discord via daemon.

    Usage: vco report starting plan-phase 1
           vco report phase 1 complete - all tests passing

    Reads AGENT_ID (or VCO_AGENT_ID) from environment to identify which
    agent's channel to post in.
    """
    agent_id = os.environ.get("AGENT_ID", os.environ.get("VCO_AGENT_ID", ""))
    if not agent_id:
        # Silent no-op when not running as an agent (e.g. manual CLI use)
        status_text = " ".join(status)
        click.echo(f"Reported (local only): {status_text}")
        return

    status_text = " ".join(status)
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    message = f"`{ts}` **{agent_id}**: {status_text}"

    try:
        with daemon_client() as client:
            result = client.call("send_message", {
                "agent_id": agent_id,
                "content": message,
            })
            if result.get("status") == "ok":
                click.echo(f"Reported: {agent_id}: {status_text}")
            else:
                click.echo(f"Warning: {result.get('message', 'unknown error')}", err=True)
                click.echo(f"Reported (local only): {agent_id}: {status_text}")
    except Exception:
        # Graceful fallback — never block the agent
        click.echo(f"Reported (local only): {agent_id}: {status_text}")
