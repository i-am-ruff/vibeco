"""vco monitor command -- DEPRECATED.

The standalone monitor loop has been replaced by the supervision tree health
system built into the Discord bot. Use 'vco up' to start the bot with
built-in monitoring, or use the /health slash command in Discord.
"""

import click


@click.command("monitor")
@click.argument("project_name")
@click.option("--interval", default=60, help="(deprecated) Cycle interval in seconds")
def monitor(project_name: str, interval: int) -> None:
    """[DEPRECATED] Start the monitor loop for a project.

    The standalone monitor loop has been replaced by the supervision tree
    health system. Use 'vco up' instead.
    """
    click.echo(
        "DEPRECATED: The standalone 'vco monitor' command has been replaced by the "
        "supervision tree health system.\n"
        "\n"
        "The v2 supervision tree provides:\n"
        "  - Event-driven health monitoring (no polling)\n"
        "  - Automatic restart with backoff\n"
        "  - Bulk failure detection\n"
        "  - Degraded mode management\n"
        "\n"
        "Use instead:\n"
        "  vco up              Start the bot with built-in monitoring\n"
        "  /health             Check agent health via Discord slash command\n"
    )
