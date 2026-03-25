"""vco bot -- Start the Discord bot."""

import logging
from pathlib import Path

import click

logger = logging.getLogger("vcompany.cli.bot")


@click.command()
@click.option(
    "--project-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    help="Project directory containing agents.yaml",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
    help="Logging level",
)
def bot(project_dir: str, log_level: str) -> None:
    """Start the Discord bot."""
    logging.basicConfig(level=getattr(logging, log_level))

    from vcompany.bot.client import VcoBot
    from vcompany.bot.config import BotConfig
    from vcompany.models.config import load_config

    project_path = Path(project_dir)
    config_path = project_path / "agents.yaml"

    if not config_path.exists():
        raise click.ClickException(f"agents.yaml not found in {project_path}")

    bot_config = BotConfig()  # loads from env
    project_config = load_config(config_path)

    logger.info("Starting VcoBot for project '%s'", project_config.project)

    bot_instance = VcoBot(project_path, project_config)
    bot_instance._guild_id = bot_config.discord_guild_id
    bot_instance.run(bot_config.discord_bot_token, log_handler=None)
