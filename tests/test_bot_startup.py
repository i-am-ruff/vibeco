"""Tests for VcoBot startup wiring: CompanyRoot supervision tree (MIGR-01).

Updated during MIGR-03 to test v2 CompanyRoot wiring instead of v1
AgentManager/MonitorLoop/CrashTracker initialization.
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


class TestOnReadyInitializesCompanyRoot:
    """on_ready initializes CompanyRoot supervision tree (MIGR-01)."""

    @pytest.mark.asyncio
    @patch("vcompany.bot.client.CompanyRoot")
    async def test_on_ready_creates_company_root(self, mock_cr_cls):
        """Verify CompanyRoot created and started with project."""
        mock_cr = AsyncMock()
        mock_cr.start = AsyncMock()
        mock_cr.add_project = AsyncMock()
        mock_cr_cls.return_value = mock_cr

        bot = _make_bot()
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        await bot.on_ready()

        mock_cr_cls.assert_called_once()
        mock_cr.start.assert_awaited_once()
        mock_cr.add_project.assert_awaited_once()
        assert bot.company_root is mock_cr

    @pytest.mark.asyncio
    @patch("vcompany.bot.client.CompanyRoot")
    async def test_on_ready_idempotent(self, mock_cr_cls):
        """Call on_ready twice, verify CompanyRoot initialized only once (Pitfall 7)."""
        mock_cr = AsyncMock()
        mock_cr.start = AsyncMock()
        mock_cr.add_project = AsyncMock()
        mock_cr_cls.return_value = mock_cr

        bot = _make_bot()
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        await bot.on_ready()
        await bot.on_ready()

        assert mock_cr_cls.call_count == 1

    @pytest.mark.asyncio
    @patch("vcompany.bot.client.CompanyRoot")
    async def test_on_ready_survives_init_failure(self, mock_cr_cls):
        """If CompanyRoot raises, _ready_flag still set, bot still functional."""
        mock_cr_cls.side_effect = RuntimeError("tmux not available")

        bot = _make_bot()
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        await bot.on_ready()

        assert bot._initialized is True
        assert bot._ready_flag is True


class TestOnReadyProjectless:
    """on_ready in project-less mode skips CompanyRoot."""

    @pytest.mark.asyncio
    async def test_on_ready_no_project_skips_supervision_tree(self):
        """Without project_config, CompanyRoot not created."""
        bot = _make_bot(with_project=False)
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        # Prevent auto-detection of existing projects on the filesystem
        with patch.object(bot, "_detect_active_project", return_value=None):
            await bot.on_ready()

        assert bot._initialized is True
        assert bot._ready_flag is True
        assert bot.company_root is None


class TestClose:
    """Graceful shutdown stops CompanyRoot supervision tree."""

    @pytest.mark.asyncio
    async def test_close_stops_company_root(self):
        """Verify company_root.stop() called on close."""
        bot = _make_bot()
        mock_root = AsyncMock()
        mock_root.stop = AsyncMock()
        bot.company_root = mock_root

        with patch.object(type(bot).__bases__[0], "close", new_callable=AsyncMock):
            await bot.close()

        mock_root.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_without_company_root(self):
        """close() works even if CompanyRoot was never initialized."""
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
