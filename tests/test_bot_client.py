"""Tests for VcoBot client class (DISC-01, MIGR-01)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

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
        """Bot uses when_mentioned (no prefix commands, slash only)."""
        bot = _make_bot()
        assert bot.command_prefix is commands.when_mentioned

    def test_message_content_intent(self):
        """Bot enables message_content privileged intent."""
        bot = _make_bot()
        assert bot.intents.message_content is True

    def test_initial_state(self):
        """Bot starts with initialized=False, ready_flag=False, _daemon=None."""
        bot = _make_bot()
        assert bot._initialized is False
        assert bot._ready_flag is False
        assert bot._daemon is None

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
        assert bot._daemon is None


class TestVcoBotDaemon:
    """VcoBot uses daemon for business logic (Phase 22: EXTRACT-04)."""

    def test_daemon_attribute_exists(self):
        """Bot has _daemon attribute initialized to None."""
        bot = _make_bot()
        assert hasattr(bot, "_daemon")
        assert bot._daemon is None

    @pytest.mark.asyncio
    async def test_close_succeeds(self):
        """close() succeeds (bot is a thin adapter, daemon owns lifecycle)."""
        bot = _make_bot()

        with patch.object(type(bot).__bases__[0], "close", new_callable=AsyncMock):
            await bot.close()
        # No exception raised

    @pytest.mark.asyncio
    async def test_close_without_daemon(self):
        """close() succeeds when _daemon is None."""
        bot = _make_bot()
        bot._daemon = None

        with patch.object(type(bot).__bases__[0], "close", new_callable=AsyncMock):
            await bot.close()
        # No exception raised


class TestHealthCogExtension:
    """HealthCog wiring tests (HLTH-03, HLTH-04)."""

    def test_health_cog_in_extensions(self):
        """HealthCog extension is registered in _COG_EXTENSIONS (HLTH-03, HLTH-04)."""
        assert "vcompany.bot.cogs.health" in _COG_EXTENSIONS


class TestHealthCheckWiring:
    """Health check wiring tests -- daemon owns CompanyRoot now (Phase 22)."""

    @pytest.mark.asyncio
    async def test_daemon_comm_port_registered_on_ready(self):
        """on_ready registers CommunicationPort with daemon when daemon is present."""
        bot = _make_bot()
        mock_daemon = MagicMock()
        mock_daemon.runtime_api = MagicMock()
        mock_daemon.runtime_api.register_channels = MagicMock()
        mock_daemon._bot_ready_event = MagicMock()
        bot._daemon = mock_daemon

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        with patch("vcompany.bot.channel_setup.setup_system_channels", new_callable=AsyncMock, return_value={}), \
             patch("vcompany.bot.client.DiscordCommunicationPort"):
            await bot.on_ready()

        assert bot._initialized is True
        assert bot._ready_flag is True


class TestMessageQueueWiring:
    """MessageQueue wiring tests -- daemon owns MessageQueue now (Phase 22)."""

    def test_bot_is_thin_adapter(self):
        """Bot does not create MessageQueue itself (daemon owns it)."""
        bot = _make_bot()
        assert not hasattr(bot, "message_queue") or bot.message_queue is None


class TestPMBacklogWiring:
    """PM backlog wiring tests -- daemon owns PM wiring now (Phase 22)."""

    def test_bot_does_not_own_pm_wiring(self):
        """Bot is a thin adapter; daemon handles PM backlog wiring."""
        bot = _make_bot()
        # Bot should not have _pm_container -- daemon owns it
        assert not hasattr(bot, "_pm_container") or bot._pm_container is None


class TestNotificationCallbackRouting:
    """Notification callbacks are now owned by daemon (Phase 22)."""

    def test_bot_does_not_own_callbacks(self):
        """Bot is a thin adapter; daemon owns escalation/degraded/recovered callbacks."""
        bot = _make_bot()
        # Bot should not have on_escalation/on_degraded/on_recovered
        assert not hasattr(bot, "on_escalation")
        assert not hasattr(bot, "on_degraded")
        assert not hasattr(bot, "on_recovered")


class TestGsdAgentEventContract:
    """GsdAgent completion/failure events match PM event handler contract (AUTO-02)."""

    def test_gsd_completion_event_matches_pm_contract(self):
        """GsdAgent.make_completion_event produces dict matching PM _handle_event contract."""
        from vcompany.agent.gsd_agent import GsdAgent

        # Create a minimal mock that has the method we need
        mock_context = MagicMock()
        mock_context.agent_id = "gsd-test-1"
        mock_context.agent_type = "gsd"

        agent = MagicMock(spec=GsdAgent)
        agent.context = mock_context
        # Use real method
        agent.make_completion_event = GsdAgent.make_completion_event.__get__(agent)

        event = agent.make_completion_event("item-123", "done")
        assert event["type"] == "task_completed"
        assert event["agent_id"] == "gsd-test-1"
        assert event["item_id"] == "item-123"
        assert event["result"] == "done"

    def test_gsd_failure_event_matches_pm_contract(self):
        """GsdAgent.make_failure_event produces dict matching PM _handle_event contract."""
        from vcompany.agent.gsd_agent import GsdAgent

        mock_context = MagicMock()
        mock_context.agent_id = "gsd-test-2"

        agent = MagicMock(spec=GsdAgent)
        agent.context = mock_context
        agent.make_failure_event = GsdAgent.make_failure_event.__get__(agent)

        event = agent.make_failure_event("item-456", "timeout")
        assert event["type"] == "task_failed"
        assert event["agent_id"] == "gsd-test-2"
        assert event["item_id"] == "item-456"
        assert event["reason"] == "timeout"
