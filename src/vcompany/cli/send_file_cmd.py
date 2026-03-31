"""vco send-file -- agents send files to their Discord channel via daemon socket."""

from __future__ import annotations

import os

import click

from vcompany.cli.helpers import daemon_client


@click.command("send-file")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("-m", "--message", default="", help="Message text alongside the file")
@click.option("--name", default=None, help="Display filename (defaults to basename)")
def send_file(file_path: str, message: str, name: str | None) -> None:
    """Send a file to the agent's Discord channel via daemon.

    Usage: vco send-file ./path/to/file.md
           vco send-file ./plan.md -m "Here's my plan for review"
    """
    agent_id = os.environ.get("AGENT_ID", os.environ.get("VCO_AGENT_ID", ""))
    if not agent_id:
        click.echo("Warning: AGENT_ID not set, cannot resolve channel", err=True)
        return

    abs_path = os.path.abspath(file_path)
    try:
        with daemon_client() as client:
            result = client.call("send_file", {
                "agent_id": agent_id,
                "file_path": abs_path,
                "filename": name,
                "content": message,
            })
            if result.get("status") == "ok":
                click.echo(f"Sent: {os.path.basename(abs_path)}")
            else:
                click.echo(f"Error: {result.get('message', 'unknown')}", err=True)
    except Exception as e:
        click.echo(f"Failed to send file: {e}", err=True)
