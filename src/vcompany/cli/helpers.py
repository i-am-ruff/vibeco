"""Shared helpers for CLI commands."""

from __future__ import annotations

import contextlib
from collections.abc import Generator

import click

from vcompany.daemon.client import DaemonClient
from vcompany.shared.paths import VCO_SOCKET_PATH


@contextlib.contextmanager
def daemon_client() -> Generator[DaemonClient, None, None]:
    """Connect to the daemon, yielding a DaemonClient.

    Catches connection errors and RPC errors, printing user-friendly
    messages and exiting with code 1.
    """
    client = DaemonClient(VCO_SOCKET_PATH)
    try:
        client.connect()
        yield client
    except (ConnectionRefusedError, FileNotFoundError, ConnectionError):
        click.echo("Error: Daemon not running. Start with: vco up", err=True)
        raise SystemExit(1)
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    finally:
        client.close()
