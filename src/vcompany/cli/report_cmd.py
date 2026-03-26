"""vco report command -- agents report status to Discord via monitor."""

from datetime import datetime, timezone
from pathlib import Path

import click

from vcompany.shared.paths import PROJECTS_BASE


@click.command()
@click.argument("status", nargs=-1, required=True)
def report(status: tuple[str, ...]) -> None:
    """Report agent status. Picked up by monitor and posted to Discord.

    Usage: vco report starting plan-phase 1
           vco report phase 1 complete - all tests passing

    Reads PROJECT_NAME and AGENT_ID from environment variables (set by dispatch).
    """
    import os

    project_name = os.environ.get("PROJECT_NAME", "")
    agent_id = os.environ.get("AGENT_ID", "")

    if not project_name or not agent_id:
        click.echo("Error: PROJECT_NAME and AGENT_ID env vars must be set", err=True)
        raise SystemExit(1)

    status_text = " ".join(status)
    reports_dir = PROJECTS_BASE / project_name / "state" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} {agent_id}: {status_text}\n"

    report_file = reports_dir / f"{agent_id}.log"
    with open(report_file, "a") as f:
        f.write(line)

    click.echo(f"Reported: {agent_id}: {status_text}")
