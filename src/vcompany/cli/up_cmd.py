"""vco up -- Start the vCompany system (bot + tmux session).

Starts the Discord bot with optional project loading. Creates a tmux
session 'vco-system' with windows for strategist and monitor. The bot
works without a project -- Strategist is always available in #strategist.
"""

import logging
from pathlib import Path

import click

logger = logging.getLogger("vcompany.cli.up")


@click.command()
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default=None,
    help="Project directory containing agents.yaml (optional)",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
    help="Logging level",
)
def up(project_dir: str | None, log_level: str) -> None:
    """Start the vCompany system.

    Launches the Discord bot + Strategist tmux pane + monitor tmux pane.
    Works without a project -- Strategist is always available in #strategist.
    """
    logging.basicConfig(level=getattr(logging, log_level))

    from vcompany.bot.client import VcoBot
    from vcompany.bot.config import BotConfig
    from vcompany.tmux.session import TmuxManager

    # Set up tmux session for monitor and agents (Strategist runs via subprocess, not tmux)
    tmux = TmuxManager()
    session = tmux.get_or_create_session("vco-system")

    # First window: monitor (placeholder until project loads)
    active_window = session.active_window
    active_window.rename_window("monitor")
    active_pane = active_window.active_pane
    tmux.send_command(active_pane, "echo 'vCompany monitor: waiting for project...'")

    # Load bot config from environment
    bot_config = BotConfig()

    # Optionally load project config
    project_path = None
    project_config = None

    if project_dir:
        project_path = Path(project_dir)
        agents_yaml = project_path / "agents.yaml"
        if agents_yaml.exists():
            from vcompany.models.config import load_config

            project_config = load_config(agents_yaml)
            logger.info("Loaded project config from %s", agents_yaml)
        else:
            logger.info("No agents.yaml found at %s, starting without project", project_path)
            project_path = None

    # Create and run bot
    if project_path and project_config:
        logger.info("Starting VcoBot with project at %s", project_path)
        bot_instance = VcoBot(
            guild_id=bot_config.discord_guild_id,
            project_dir=project_path,
            config=project_config,
        )
    else:
        logger.info("Starting VcoBot without project (Strategist-only mode)")
        bot_instance = VcoBot(guild_id=bot_config.discord_guild_id)

    bot_instance.run(bot_config.discord_bot_token, log_handler=None)
