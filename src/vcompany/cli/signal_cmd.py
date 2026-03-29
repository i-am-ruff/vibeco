"""CLI command: vco signal -- send readiness/idle signals to daemon."""

from __future__ import annotations

import sys

import click


@click.command("signal")
@click.option("--ready", "signal_type", flag_value="ready", help="Signal agent is ready")
@click.option("--idle", "signal_type", flag_value="idle", help="Signal agent is idle")
@click.option("--agent-id", required=True, envvar="VCO_AGENT_ID", help="Agent ID (defaults to $VCO_AGENT_ID)")
def signal(signal_type: str | None, agent_id: str) -> None:
    """Send a readiness or idle signal to the vco daemon.

    Called by Claude Code hooks (SessionStart, Stop) to notify the daemon
    of agent state changes. Replaces sentinel temp file approach.
    """
    if signal_type is None:
        click.echo("Error: specify --ready or --idle", err=True)
        sys.exit(1)

    import httpx
    from vcompany.shared.paths import VCO_SOCKET_PATH

    signal_socket_path = VCO_SOCKET_PATH.parent / "vco-signal.sock"

    try:
        # Use httpx with Unix socket transport
        transport = httpx.HTTPTransport(uds=str(signal_socket_path))
        with httpx.Client(transport=transport, timeout=5.0) as client:
            resp = client.post(
                "http://localhost/signal",
                json={"agent_id": agent_id, "signal": signal_type},
            )
            if resp.status_code == 200:
                return  # Success, silent exit
            else:
                # Non-200 but don't crash -- Claude Code hooks must not error
                click.echo(f"Warning: signal delivery returned {resp.status_code}", err=True)
    except Exception:
        # Daemon unreachable -- fail silently per Pitfall: signal race / daemon down
        # Claude Code hooks must not error out or they block the agent
        pass
