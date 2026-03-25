"""Bot configuration loaded from environment variables via pydantic-settings."""

from pydantic_settings import BaseSettings


class BotConfig(BaseSettings):
    """Discord bot configuration.

    Loads DISCORD_BOT_TOKEN and DISCORD_GUILD_ID from environment variables
    or .env file. Used by the bot entry point to connect to Discord.
    """

    discord_bot_token: str
    discord_guild_id: int
    project_dir: str = "."

    model_config = {"env_prefix": "", "env_file": ".env", "env_file_encoding": "utf-8"}
