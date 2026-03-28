"""Tests for VcoBot client class (DISC-01, MIGR-01)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from vcompany.bot.client import VcoBot, _COG_EXTENSIONS
from vcompany.models.config import AgentConfig, ProjectConfig
from vcompany.resilience.message_queue import MessagePriority, MessageQueue


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

    @pytest.mark.asyncio
    async def test_close_stops_message_queue(self):
        """close() calls message_queue.stop() if message_queue exists."""
        bot = _make_bot()
        mock_queue = AsyncMock(spec=MessageQueue)
        bot.message_queue = mock_queue
        bot.company_root = None

        with patch.object(type(bot).__bases__[0], "close", new_callable=AsyncMock):
            await bot.close()

        mock_queue.stop.assert_called_once()


class TestHealthCogExtension:
    """HealthCog wiring tests (HLTH-03, HLTH-04)."""

    def test_health_cog_in_extensions(self):
        """HealthCog extension is registered in _COG_EXTENSIONS (HLTH-03, HLTH-04)."""
        assert "vcompany.bot.cogs.health" in _COG_EXTENSIONS


class TestHealthCheckWiring:
    """DegradedModeManager health_check wiring tests (RESL-03)."""

    @pytest.mark.asyncio
    async def test_health_check_passed_to_company_root(self):
        """CompanyRoot receives health_check callable when on_ready runs with project."""
        bot = _make_bot()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        with patch("vcompany.bot.client.CompanyRoot") as MockRoot:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_instance.add_project = AsyncMock()
            MockRoot.return_value = mock_instance

            await bot.on_ready()

            # CompanyRoot was called with health_check as non-None callable
            MockRoot.assert_called_once()
            call_kwargs = MockRoot.call_args.kwargs
            assert "health_check" in call_kwargs
            assert callable(call_kwargs["health_check"])
            assert call_kwargs["on_degraded"] is not None
            assert call_kwargs["on_recovered"] is not None


class TestMessageQueueWiring:
    """MessageQueue wiring tests (RESL-01)."""

    @pytest.mark.asyncio
    async def test_message_queue_created_on_ready(self):
        """MessageQueue is created and started during on_ready with project."""
        bot = _make_bot()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        with patch("vcompany.bot.client.CompanyRoot") as MockRoot, \
             patch("vcompany.bot.client.MessageQueue") as MockQueue:
            mock_root = AsyncMock()
            mock_root.start = AsyncMock()
            mock_root.add_project = AsyncMock()
            MockRoot.return_value = mock_root

            mock_queue_instance = AsyncMock()
            mock_queue_instance.start = AsyncMock()
            MockQueue.return_value = mock_queue_instance

            await bot.on_ready()

            # MessageQueue was instantiated with a send_func
            MockQueue.assert_called_once()
            call_kwargs = MockQueue.call_args.kwargs
            assert "send_func" in call_kwargs
            assert callable(call_kwargs["send_func"])

            # start() was called
            mock_queue_instance.start.assert_called_once()

            # bot attribute was set
            assert bot.message_queue is mock_queue_instance

    def test_message_queue_init_none(self):
        """Bot starts with message_queue=None."""
        bot = _make_bot()
        assert bot.message_queue is None


class TestPMBacklogWiring:
    """PM backlog and project state wiring tests (AUTO-01, AUTO-02, AUTO-05)."""

    @pytest.mark.asyncio
    async def test_pm_backlog_assigned_after_add_project(self):
        """PM's backlog and _project_state are assigned after add_project (AUTO-01)."""
        from vcompany.agent.fulltime_agent import FulltimeAgent
        from vcompany.autonomy.backlog import BacklogQueue
        from vcompany.autonomy.project_state import ProjectStateManager

        bot = _make_bot()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        # Create a mock PM container that is an actual FulltimeAgent subtype
        pm_mock = MagicMock(spec=FulltimeAgent)
        pm_mock.backlog = None
        pm_mock._project_state = None
        pm_mock.memory = AsyncMock()
        pm_mock.memory.get = AsyncMock(return_value=None)
        pm_mock.memory.set = AsyncMock()
        pm_mock.context = MagicMock()
        pm_mock.context.agent_id = "pm-agent"

        # Make isinstance(pm_mock, FulltimeAgent) return True
        pm_mock.__class__ = FulltimeAgent

        mock_project_sup = MagicMock()
        mock_project_sup.children = MagicMock()
        mock_project_sup.children.values = MagicMock(return_value=[pm_mock])

        with patch("vcompany.bot.client.CompanyRoot") as MockRoot, \
             patch("vcompany.bot.client.MessageQueue") as MockQueue, \
             patch("vcompany.bot.client.BacklogQueue") as MockBacklog, \
             patch("vcompany.bot.client.ProjectStateManager") as MockState:

            mock_root = AsyncMock()
            mock_root.start = AsyncMock()
            mock_root.add_project = AsyncMock(return_value=mock_project_sup)
            MockRoot.return_value = mock_root

            mock_queue_instance = AsyncMock()
            MockQueue.return_value = mock_queue_instance

            mock_backlog_instance = MagicMock()
            mock_backlog_instance.load = AsyncMock()
            MockBacklog.return_value = mock_backlog_instance

            mock_state_instance = MagicMock()
            MockState.return_value = mock_state_instance

            await bot.on_ready()

            # BacklogQueue was created with PM's memory
            MockBacklog.assert_called_once_with(pm_mock.memory)
            mock_backlog_instance.load.assert_called_once()

            # ProjectStateManager was created with backlog and PM's memory
            MockState.assert_called_once_with(mock_backlog_instance, pm_mock.memory)

            # Both assigned to PM
            assert pm_mock.backlog is mock_backlog_instance
            assert pm_mock._project_state is mock_state_instance

            # PM stored on bot
            assert bot._pm_container is pm_mock

    @pytest.mark.asyncio
    async def test_no_pm_graceful_skip(self):
        """Wiring skips gracefully when no FulltimeAgent exists in children (AUTO-01)."""
        bot = _make_bot()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        # Project with no FulltimeAgent children (all are generic mocks)
        gsd_mock = MagicMock()
        gsd_mock.__class__ = type("NotFulltimeAgent", (), {})

        mock_project_sup = MagicMock()
        mock_project_sup.children = MagicMock()
        mock_project_sup.children.values = MagicMock(return_value=[gsd_mock])

        with patch("vcompany.bot.client.CompanyRoot") as MockRoot, \
             patch("vcompany.bot.client.MessageQueue") as MockQueue, \
             patch("vcompany.bot.client.BacklogQueue") as MockBacklog:

            mock_root = AsyncMock()
            mock_root.start = AsyncMock()
            mock_root.add_project = AsyncMock(return_value=mock_project_sup)
            MockRoot.return_value = mock_root

            mock_queue_instance = AsyncMock()
            MockQueue.return_value = mock_queue_instance

            await bot.on_ready()

            # BacklogQueue never created since no PM found
            MockBacklog.assert_not_called()

            # PM container stays None
            assert bot._pm_container is None

    def test_pm_container_init_none(self):
        """Bot starts with _pm_container=None."""
        bot = _make_bot()
        assert bot._pm_container is None


class TestNotificationCallbackRouting:
    """Tests that on_escalation/on_degraded/on_recovered route through MessageQueue (RESL-01)."""

    @pytest.mark.asyncio
    async def test_on_escalation_enqueues_with_escalation_priority(self):
        """on_escalation callback routes through message_queue.enqueue."""
        bot = _make_bot()
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        with patch("vcompany.bot.client.CompanyRoot") as MockRoot:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_instance.add_project = AsyncMock()
            MockRoot.return_value = mock_instance

            await bot.on_ready()

            # Extract on_escalation from CompanyRoot constructor call
            on_escalation = MockRoot.call_args.kwargs["on_escalation"]

            # Set up mock queue and alerts channel
            bot.message_queue = AsyncMock()
            mock_alerts = MagicMock()
            mock_alerts.id = 99999
            bot._system_channels["alerts"] = mock_alerts

            await on_escalation("restart budget exceeded")

            bot.message_queue.enqueue.assert_called_once()
            queued = bot.message_queue.enqueue.call_args[0][0]
            assert queued.priority == MessagePriority.ESCALATION
            assert "ESCALATION" in queued.content
            assert "restart budget exceeded" in queued.content
            assert queued.channel_id == 99999

    @pytest.mark.asyncio
    async def test_on_degraded_enqueues_with_supervisor_priority(self):
        """on_degraded callback routes through message_queue.enqueue."""
        bot = _make_bot()
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        with patch("vcompany.bot.client.CompanyRoot") as MockRoot:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_instance.add_project = AsyncMock()
            MockRoot.return_value = mock_instance

            await bot.on_ready()

            on_degraded = MockRoot.call_args.kwargs["on_degraded"]

            bot.message_queue = AsyncMock()
            mock_alerts = MagicMock()
            mock_alerts.id = 88888
            bot._system_channels["alerts"] = mock_alerts

            await on_degraded()

            bot.message_queue.enqueue.assert_called_once()
            queued = bot.message_queue.enqueue.call_args[0][0]
            assert queued.priority == MessagePriority.SUPERVISOR
            assert "degraded mode" in queued.content.lower()

    @pytest.mark.asyncio
    async def test_on_recovered_enqueues_with_supervisor_priority(self):
        """on_recovered callback routes through message_queue.enqueue."""
        bot = _make_bot()
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        with patch("vcompany.bot.client.CompanyRoot") as MockRoot:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_instance.add_project = AsyncMock()
            MockRoot.return_value = mock_instance

            await bot.on_ready()

            on_recovered = MockRoot.call_args.kwargs["on_recovered"]

            bot.message_queue = AsyncMock()
            mock_alerts = MagicMock()
            mock_alerts.id = 77777
            bot._system_channels["alerts"] = mock_alerts

            await on_recovered()

            bot.message_queue.enqueue.assert_called_once()
            queued = bot.message_queue.enqueue.call_args[0][0]
            assert queued.priority == MessagePriority.SUPERVISOR
            assert "recovered" in queued.content.lower()

    @pytest.mark.asyncio
    async def test_callbacks_noop_when_queue_none(self):
        """Callbacks do nothing when message_queue is None (before startup)."""
        bot = _make_bot()
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "TestGuild"
        mock_guild.roles = []
        mock_guild.create_role = AsyncMock()
        bot.get_guild = MagicMock(return_value=mock_guild)

        with patch("vcompany.bot.client.CompanyRoot") as MockRoot:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_instance.add_project = AsyncMock()
            MockRoot.return_value = mock_instance

            await bot.on_ready()

            on_escalation = MockRoot.call_args.kwargs["on_escalation"]

            # message_queue is None (not yet created)
            bot.message_queue = None
            mock_alerts = MagicMock()
            bot._system_channels["alerts"] = mock_alerts

            # Should not raise
            await on_escalation("test message")


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
