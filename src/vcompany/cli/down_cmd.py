"""vco down -- Stop the vCompany daemon.

Reads the PID file, sends SIGTERM, and waits for the daemon to exit.
Handles stale PID files gracefully.
"""

from __future__ import annotations

import os
import signal
import time

import click

from vcompany.shared.paths import VCO_PID_PATH


@click.command()
@click.option("--timeout", default=10, help="Seconds to wait for daemon shutdown")
def down(timeout: int) -> None:
    """Stop the vCompany daemon."""
    if not VCO_PID_PATH.exists():
        click.echo("Daemon is not running (no PID file)")
        raise SystemExit(1)

    pid_text = VCO_PID_PATH.read_text().strip()
    try:
        pid = int(pid_text)
    except ValueError:
        click.echo(f"Invalid PID file contents: {pid_text!r}")
        VCO_PID_PATH.unlink(missing_ok=True)
        raise SystemExit(1)

    # Check if process is alive
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        VCO_PID_PATH.unlink(missing_ok=True)
        click.echo("Daemon was not running (stale PID file cleaned up)")
        return
    except PermissionError:
        # Process exists but we can't signal it
        click.echo(f"Daemon process (PID {pid}) exists but is not ours")
        raise SystemExit(1)

    # Send SIGTERM
    os.kill(pid, signal.SIGTERM)
    click.echo(f"Sent SIGTERM to daemon (PID {pid})")

    # Wait for clean shutdown (poll PID existence)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            click.echo("Daemon stopped.")
            return
        except PermissionError:
            # Changed ownership mid-shutdown -- treat as stopped
            click.echo("Daemon stopped.")
            return

    click.echo(f"Daemon did not stop within {timeout}s. Use kill -9 {pid} to force.")
    raise SystemExit(1)
