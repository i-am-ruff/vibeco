"""CLI entry points for worker channel commands.

These are invoked by agent processes (Claude Code hooks, GSD scripts)
to send messages through the transport channel. Each command is purely
synchronous -- encode a message, write to stdout, exit. No asyncio needed.

Transport mechanism: writes NDJSON to stdout. The worker main loop or
transport layer reads stdout from the agent process.
"""

import sys

import click

from vco_worker.channel.framing import encode
from vco_worker.channel.messages import (
    AskMessage,
    ReportMessage,
    SendFileMessage,
    SignalMessage,
)


@click.command()
@click.argument("channel")
@click.argument("content")
@click.option("--task-id", default=None, help="Associated task ID")
def report(channel: str, content: str, task_id: str | None) -> None:
    """Send a report message through the transport channel."""
    msg = ReportMessage(channel=channel, content=content, task_id=task_id)
    sys.stdout.buffer.write(encode(msg))
    sys.stdout.buffer.flush()


@click.command()
@click.argument("channel")
@click.argument("question")
def ask(channel: str, question: str) -> None:
    """Send an ask message through the transport channel."""
    msg = AskMessage(channel=channel, question=question)
    sys.stdout.buffer.write(encode(msg))
    sys.stdout.buffer.flush()


@click.command("signal")
@click.argument("signal_name")
@click.option("--detail", default="", help="Additional detail")
def signal_cmd(signal_name: str, detail: str) -> None:
    """Send a signal message through the transport channel."""
    msg = SignalMessage(signal=signal_name, detail=detail)
    sys.stdout.buffer.write(encode(msg))
    sys.stdout.buffer.flush()


@click.command()
@click.argument("channel")
@click.argument("filename")
@click.argument("content_b64")
@click.option("--description", default="", help="File description")
def send_file(channel: str, filename: str, content_b64: str, description: str) -> None:
    """Send a file message through the transport channel."""
    msg = SendFileMessage(
        channel=channel,
        filename=filename,
        content_b64=content_b64,
        description=description,
    )
    sys.stdout.buffer.write(encode(msg))
    sys.stdout.buffer.flush()
