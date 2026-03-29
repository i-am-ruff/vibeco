"""Tests for VcoBot startup wiring (Phase 22: thin adapter, daemon owns CompanyRoot).

Updated during Phase 22 to reflect that VcoBot is a thin Discord adapter.
CompanyRoot creation and PM wiring are now owned by the daemon.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from vcompany.bot.client import VcoBot
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


def _make_bot(guild_id: int = 12345, *, with_project: bool = True) -> VcoBot:
    """Create a VcoBot with explicit guild_id."""
    if with_project:
        return VcoBot(
            guild_id=guild_id,
            project_dir=Path("/tmp/test"),
            config=_make_config(),
        )
    return VcoBot(guild_id=guild_id)


def _mock_guild() -> MagicMock:
    """Create a mock guild with vco-owner role already existing."""
    mock_role = MagicMock(spec=discord.Role)
    mock_role.name = "vco-owner"

    guild = MagicMock(spec=discord.Guild)
    guild.name = "TestGuild"
    guild.roles = [mock_role]
    guild.create_role = AsyncMock()
    return guild


class TestOnReadyInitialization:
    """on_ready does Discord-only setup; daemon owns CompanyRoot (Phase 22)."""

    @pytest.mark.asyncio
    async def test_on_ready_sets_initialized(self):
        """Verify on_ready sets _initialized and _ready_flag."""
        bot = _make_bot()
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        await bot.on_ready()

        assert bot._initialized is True
        assert bot._ready_flag is True

    @pytest.mark.asyncio
    async def test_on_ready_idempotent(self):
        """Call on_ready twice, verify init only runs once (Pitfall 7)."""
        bot = _make_bot()
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        await bot.on_ready()
        await bot.on_ready()

        # create_role should only be called once (role already exists in _mock_guild)
        guild.create_role.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_ready_signals_daemon_bot_ready(self):
        """on_ready sets daemon._bot_ready_event when daemon is present."""
        bot = _make_bot()
        mock_daemon = MagicMock()
        mock_daemon.runtime_api = None
        mock_daemon._bot_ready_event = MagicMock()
        bot._daemon = mock_daemon

        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        await bot.on_ready()

        mock_daemon._bot_ready_event.set.assert_called_once()


class TestOnReadyProjectless:
    """on_ready in project-less mode works (daemon owns supervision tree)."""

    @pytest.mark.asyncio
    async def test_on_ready_no_project_succeeds(self):
        """Without project_config, on_ready still succeeds."""
        bot = _make_bot(with_project=False)
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        # Prevent auto-detection of existing projects on the filesystem
        with patch.object(bot, "_detect_active_project", return_value=None):
            await bot.on_ready()

        assert bot._initialized is True
        assert bot._ready_flag is True
        assert bot._daemon is None


class TestClose:
    """Graceful shutdown (bot is thin adapter, daemon owns lifecycle)."""

    @pytest.mark.asyncio
    async def test_close_succeeds(self):
        """close() completes without error."""
        bot = _make_bot()

        with patch.object(type(bot).__bases__[0], "close", new_callable=AsyncMock):
            await bot.close()

        # Should not raise


class TestGuildIdFromConstructor:
    """Verify _guild_id set from constructor arg."""

    def test_guild_id_from_arg(self):
        """_guild_id is set from constructor argument."""
        bot = VcoBot(guild_id=98765)
        assert bot._guild_id == 98765

    def test_guild_id_with_project(self):
        """_guild_id works alongside project args."""
        bot = VcoBot(
            guild_id=11111,
            project_dir=Path("/tmp/test"),
            config=_make_config(),
        )
        assert bot._guild_id == 11111
        assert bot.project_dir == Path("/tmp/test")
        assert bot.project_config is not None

    def test_project_optional(self):
        """project_dir and config default to None."""
        bot = VcoBot(guild_id=99999)
        assert bot.project_dir is None
        assert bot.project_config is None
