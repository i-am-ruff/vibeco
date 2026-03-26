"""Bot configuration loaded from environment variables via pydantic-settings."""

from pydantic_settings import BaseSettings


class BotConfig(BaseSettings):
    """Discord bot configuration.

    Loads DISCORD_BOT_TOKEN and DISCORD_GUILD_ID from environment variables
    or .env file. Used by the bot entry point to connect to Discord.

    Phase 6 additions:
    - anthropic_api_key: For PM/Strategist Claude API calls (empty = disabled).
    - strategist_persona_path: Path to STRATEGIST-PERSONA.md (D-03/D-21).
    - status_digest_interval: Seconds between status digests to Strategist (D-13).
    """

    discord_bot_token: str
    discord_guild_id: int
    project_dir: str = ""
    anthropic_api_key: str = ""
    strategist_persona_path: str = ""
    status_digest_interval: int = 1800

    model_config = {"env_prefix": "", "env_file": ".env", "env_file_encoding": "utf-8"}
