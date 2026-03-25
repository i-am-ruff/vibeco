"""Tests for VcoBot client class (DISC-01)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from vcompany.bot.client import VcoBot, _COG_EXTENSIONS
from vcompany.models.config import AgentConfig, ProjectConfig


def _make_config() -> ProjectConfig:
    """Create a minimal ProjectConfig for testing."""
    return ProjectConfig(
        project="testproject",
        repo="https://github.com/test/repo",
        agents=[
            AgentConfig(
                id="agent-1",
                role="backend",
                owns=["src/backend/"],
                consumes="INTERFACES.md",
                gsd_mode="full",
                system_prompt="You are a backend agent.",
            ),
        ],
    )


class TestVcoBotInit:
    """VcoBot constructor sets expected defaults."""

    def test_command_prefix(self):
        """Bot uses '!' command prefix."""
        bot = VcoBot(Path("/tmp/test"), _make_config())
        assert bot.command_prefix == "!"

    def test_message_content_intent(self):
        """Bot enables message_content privileged intent."""
        bot = VcoBot(Path("/tmp/test"), _make_config())
        assert bot.intents.message_content is True

    def test_initial_state(self):
        """Bot starts with initialized=False, ready_flag=False."""
        bot = VcoBot(Path("/tmp/test"), _make_config())
        assert bot._initialized is False
        assert bot._ready_flag is False
        assert bot.agent_manager is None
        assert bot.monitor_loop is None
        assert bot.crash_tracker is None


class TestVcoBotSetupHook:
    """setup_hook loads all 4 Cog extensions (DISC-01)."""

    @pytest.mark.asyncio
    async def test_loads_all_cog_extensions(self):
        """setup_hook calls load_extension for all 5 cog paths."""
        bot = VcoBot(Path("/tmp/test"), _make_config())
        bot.load_extension = AsyncMock()

        await bot.setup_hook()

        assert bot.load_extension.call_count == 5
        loaded = [call.args[0] for call in bot.load_extension.call_args_list]
        assert loaded == _COG_EXTENSIONS

    @pytest.mark.asyncio
    async def test_cog_extension_paths(self):
        """All 5 expected cog extension paths are defined."""
        assert "vcompany.bot.cogs.commands" in _COG_EXTENSIONS
        assert "vcompany.bot.cogs.alerts" in _COG_EXTENSIONS
        assert "vcompany.bot.cogs.plan_review" in _COG_EXTENSIONS
        assert "vcompany.bot.cogs.strategist" in _COG_EXTENSIONS
        assert "vcompany.bot.cogs.question_handler" in _COG_EXTENSIONS


class TestVcoBotOnReady:
    """on_ready creates vco-owner role and guards against repeated init."""

    @pytest.mark.asyncio
    async def test_creates_vco_owner_role_when_missing(self, monkeypatch):
        """on_ready creates vco-owner role when it doesn't exist (D-10)."""
        monkeypatch.setenv("DISCORD_GUILD_ID", "12345")
        bot = VcoBot(Path("/tmp/test"), _make_config())

        # Mock guild with no vco-owner role
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []  # No roles exist
        mock_guild.create_role = AsyncMock()

        bot.get_guild = MagicMock(return_value=mock_guild)

        await bot.on_ready()

        mock_guild.create_role.assert_called_once_with(
            name="vco-owner",
            reason="VcoBot auto-created owner role",
        )
        assert bot._initialized is True
        assert bot._ready_flag is True

    @pytest.mark.asyncio
    async def test_skips_role_creation_when_exists(self, monkeypatch):
        """on_ready skips role creation when vco-owner already exists."""
        monkeypatch.setenv("DISCORD_GUILD_ID", "12345")
        bot = VcoBot(Path("/tmp/test"), _make_config())

        # Mock guild with existing vco-owner role
        mock_role = MagicMock(spec=discord.Role)
        mock_role.name = "vco-owner"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = [mock_role]
        mock_guild.create_role = AsyncMock()

        bot.get_guild = MagicMock(return_value=mock_guild)

        await bot.on_ready()

        mock_guild.create_role.assert_not_called()
        assert bot._initialized is True

    @pytest.mark.asyncio
    async def test_guards_against_repeated_init(self, monkeypatch):
        """on_ready skips initialization on second call (Pitfall 7)."""
        monkeypatch.setenv("DISCORD_GUILD_ID", "12345")
        bot = VcoBot(Path("/tmp/test"), _make_config())

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        # First call: should create role
        await bot.on_ready()
        assert mock_guild.create_role.call_count == 1

        # Second call: should skip entirely
        await bot.on_ready()
        assert mock_guild.create_role.call_count == 1  # Still 1, not 2

    @pytest.mark.asyncio
    async def test_handles_missing_guild(self, monkeypatch):
        """on_ready handles guild not found gracefully."""
        monkeypatch.setenv("DISCORD_GUILD_ID", "99999")
        bot = VcoBot(Path("/tmp/test"), _make_config())
        bot.get_guild = MagicMock(return_value=None)

        await bot.on_ready()

        assert bot._initialized is True
        assert bot._ready_flag is True

    def test_is_bot_ready_property(self):
        """is_bot_ready returns _ready_flag value."""
        bot = VcoBot(Path("/tmp/test"), _make_config())
        assert bot.is_bot_ready is False
        bot._ready_flag = True
        assert bot.is_bot_ready is True
