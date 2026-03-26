"""Tests for BotConfig pydantic-settings model."""

import pytest
from pydantic import ValidationError

from vcompany.bot.config import BotConfig


class TestBotConfig:
    """BotConfig loads Discord credentials from environment."""

    def test_loads_from_env_vars(self, monkeypatch):
        """BotConfig reads DISCORD_BOT_TOKEN and DISCORD_GUILD_ID from env."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token-abc123")
        monkeypatch.setenv("DISCORD_GUILD_ID", "123456789")
        # Prevent .env file from interfering
        monkeypatch.delenv("PROJECT_DIR", raising=False)

        config = BotConfig()

        assert config.discord_bot_token == "test-token-abc123"
        assert config.discord_guild_id == 123456789

    def test_raises_on_missing_token(self, monkeypatch):
        """BotConfig raises ValidationError when DISCORD_BOT_TOKEN is missing."""
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.setenv("DISCORD_GUILD_ID", "123456789")

        with pytest.raises(ValidationError):
            BotConfig(_env_file=None)

    def test_raises_on_missing_guild_id(self, monkeypatch):
        """BotConfig raises ValidationError when DISCORD_GUILD_ID is missing."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.delenv("DISCORD_GUILD_ID", raising=False)

        with pytest.raises(ValidationError):
            BotConfig(_env_file=None)

    def test_default_project_dir(self, monkeypatch):
        """project_dir defaults to '.' when not set."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setenv("DISCORD_GUILD_ID", "123456789")

        config = BotConfig()

        assert config.project_dir == "."

    def test_custom_project_dir(self, monkeypatch):
        """project_dir can be overridden via env var."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setenv("DISCORD_GUILD_ID", "123456789")
        monkeypatch.setenv("PROJECT_DIR", "/opt/myproject")

        config = BotConfig()

        assert config.project_dir == "/opt/myproject"
