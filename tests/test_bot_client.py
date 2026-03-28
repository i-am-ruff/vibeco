"""Tests for VcoBot client class (DISC-01, MIGR-01)."""

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


def _make_bot(**kwargs) -> VcoBot:
    """Create VcoBot with new constructor signature."""
    return VcoBot(
        guild_id=kwargs.get("guild_id", 12345),
        project_dir=kwargs.get("project_dir", Path("/tmp/test")),
        config=kwargs.get("config", _make_config()),
    )


class TestVcoBotInit:
    """VcoBot constructor sets expected defaults."""

    def test_command_prefix(self):
        """Bot uses '!' command prefix."""
        bot = _make_bot()
        assert bot.command_prefix == "!"

    def test_message_content_intent(self):
        """Bot enables message_content privileged intent."""
        bot = _make_bot()
        assert bot.intents.message_content is True

    def test_initial_state(self):
        """Bot starts with initialized=False, ready_flag=False, company_root=None."""
        bot = _make_bot()
        assert bot._initialized is False
        assert bot._ready_flag is False
        assert bot.company_root is None

    def test_project_optional(self):
        """Bot can be created without project."""
        bot = VcoBot(guild_id=12345)
        assert bot.project_dir is None
        assert bot.project_config is None
        assert bot._guild_id == 12345

    def test_no_v1_attributes(self):
        """Bot no longer has v1 agent_manager, monitor_loop, crash_tracker attributes."""
        bot = _make_bot()
        assert not hasattr(bot, "agent_manager")
        assert not hasattr(bot, "monitor_loop")
        assert not hasattr(bot, "crash_tracker")
        assert not hasattr(bot, "workflow_orchestrator")


class TestVcoBotSetupHook:
    """setup_hook loads all Cog extensions (DISC-01)."""

    @pytest.mark.asyncio
    async def test_loads_all_cog_extensions(self):
        """setup_hook calls load_extension for all cog paths."""
        bot = _make_bot()
        bot.load_extension = AsyncMock()

        mock_tree = MagicMock()
        mock_tree.copy_global_to = MagicMock()
        mock_tree.sync = AsyncMock()

        with patch.object(type(bot), "tree", new_callable=lambda: property(lambda self: mock_tree)):
            await bot.setup_hook()

        assert bot.load_extension.call_count == len(_COG_EXTENSIONS)
        loaded = [call.args[0] for call in bot.load_extension.call_args_list]
        assert loaded == _COG_EXTENSIONS

    @pytest.mark.asyncio
    async def test_cog_extension_paths(self):
        """All expected cog extension paths are defined."""
        assert "vcompany.bot.cogs.commands" in _COG_EXTENSIONS
        assert "vcompany.bot.cogs.alerts" in _COG_EXTENSIONS
        assert "vcompany.bot.cogs.plan_review" in _COG_EXTENSIONS
        assert "vcompany.bot.cogs.strategist" in _COG_EXTENSIONS
        assert "vcompany.bot.cogs.question_handler" in _COG_EXTENSIONS


class TestVcoBotOnReady:
    """on_ready creates vco-owner role and guards against repeated init."""

    @pytest.mark.asyncio
    async def test_creates_vco_owner_role_when_missing(self):
        """on_ready creates vco-owner role when it doesn't exist (D-10)."""
        bot = _make_bot()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
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
    async def test_skips_role_creation_when_exists(self):
        """on_ready skips role creation when vco-owner already exists."""
        bot = _make_bot()

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
    async def test_guards_against_repeated_init(self):
        """on_ready skips initialization on second call (Pitfall 7)."""
        bot = _make_bot()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        await bot.on_ready()
        assert mock_guild.create_role.call_count == 1

        await bot.on_ready()
        assert mock_guild.create_role.call_count == 1

    @pytest.mark.asyncio
    async def test_handles_missing_guild(self):
        """on_ready handles guild not found gracefully."""
        bot = _make_bot()
        bot.get_guild = MagicMock(return_value=None)

        await bot.on_ready()

        assert bot._initialized is True
        assert bot._ready_flag is True

    def test_is_bot_ready_property(self):
        """is_bot_ready returns _ready_flag value."""
        bot = _make_bot()
        assert bot.is_bot_ready is False
        bot._ready_flag = True
        assert bot.is_bot_ready is True


class TestVcoBotProjectless:
    """VcoBot works without a project loaded."""

    @pytest.mark.asyncio
    async def test_on_ready_without_project(self):
        """on_ready succeeds without project_config."""
        bot = VcoBot(guild_id=12345)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        # Prevent auto-detection from picking up real projects on disk
        with patch.object(bot, "_detect_active_project", return_value=None):
            await bot.on_ready()

        assert bot._initialized is True
        assert bot._ready_flag is True
        assert bot.company_root is None


class TestVcoBotCompanyRoot:
    """VcoBot uses CompanyRoot supervision tree (MIGR-01)."""

    def test_company_root_attribute_exists(self):
        """Bot has company_root attribute initialized to None."""
        bot = _make_bot()
        assert hasattr(bot, "company_root")
        assert bot.company_root is None

    @pytest.mark.asyncio
    async def test_close_stops_company_root(self):
        """close() calls company_root.stop() if company_root exists."""
        bot = _make_bot()
        mock_root = AsyncMock()
        bot.company_root = mock_root

        # Mock super().close()
        with patch.object(type(bot).__bases__[0], "close", new_callable=AsyncMock):
            await bot.close()

        mock_root.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_company_root(self):
        """close() succeeds when company_root is None."""
        bot = _make_bot()
        bot.company_root = None

        with patch.object(type(bot).__bases__[0], "close", new_callable=AsyncMock):
            await bot.close()
        # No exception raised
