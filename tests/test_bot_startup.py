"""Tests for VcoBot startup wiring: AgentManager, MonitorLoop, CrashTracker (D-13)."""

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


def _make_bot(monkeypatch, guild_id: int = 12345) -> VcoBot:
    """Create a VcoBot with mocked guild."""
    monkeypatch.setenv("DISCORD_GUILD_ID", str(guild_id))
    return VcoBot(Path("/tmp/test"), _make_config())


def _mock_guild() -> MagicMock:
    """Create a mock guild with vco-owner role already existing."""
    mock_role = MagicMock(spec=discord.Role)
    mock_role.name = "vco-owner"

    guild = MagicMock(spec=discord.Guild)
    guild.name = "TestGuild"
    guild.roles = [mock_role]
    guild.create_role = AsyncMock()
    return guild


class TestOnReadyInitializesComponents:
    """on_ready initializes AgentManager, MonitorLoop, CrashTracker (D-13)."""

    @pytest.mark.asyncio
    @patch("vcompany.bot.client.MonitorLoop")
    @patch("vcompany.bot.client.CrashTracker")
    @patch("vcompany.bot.client.AgentManager")
    @patch("vcompany.bot.client.TmuxManager", create=True)
    async def test_on_ready_initializes_components(
        self, mock_tmux_cls, mock_am_cls, mock_ct_cls, mock_ml_cls, monkeypatch
    ):
        """Verify AgentManager, CrashTracker, MonitorLoop all instantiated."""
        bot = _make_bot(monkeypatch)
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        # MonitorLoop.run must return a coroutine for create_task
        mock_ml_instance = MagicMock()
        mock_ml_instance.run = AsyncMock()
        mock_ml_cls.return_value = mock_ml_instance

        with patch("vcompany.bot.client.asyncio.create_task") as mock_create_task:
            await bot.on_ready()

        mock_am_cls.assert_called_once()
        mock_ct_cls.assert_called_once()
        mock_ml_cls.assert_called_once()
        assert bot.agent_manager is not None
        assert bot.crash_tracker is not None
        assert bot.monitor_loop is not None

    @pytest.mark.asyncio
    @patch("vcompany.bot.client.MonitorLoop")
    @patch("vcompany.bot.client.CrashTracker")
    @patch("vcompany.bot.client.AgentManager")
    @patch("vcompany.bot.client.TmuxManager", create=True)
    async def test_on_ready_injects_callbacks(
        self, mock_tmux_cls, mock_am_cls, mock_ct_cls, mock_ml_cls, monkeypatch
    ):
        """Verify MonitorLoop receives callbacks from AlertsCog and PlanReviewCog."""
        bot = _make_bot(monkeypatch)
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)

        # Mock AlertsCog with callbacks
        mock_alerts_cog = MagicMock()
        fake_callbacks = {
            "on_agent_dead": MagicMock(),
            "on_agent_stuck": MagicMock(),
            "on_plan_detected": MagicMock(),
            "on_circuit_open": MagicMock(),
        }
        mock_alerts_cog.make_sync_callbacks.return_value = fake_callbacks

        # Mock PlanReviewCog with plan detected callback
        mock_plan_review_cog = MagicMock()
        plan_review_on_plan_detected = MagicMock()
        mock_plan_review_cog.make_sync_callback.return_value = {
            "on_plan_detected": plan_review_on_plan_detected,
        }

        def get_cog_side_effect(name):
            if name == "AlertsCog":
                return mock_alerts_cog
            if name == "PlanReviewCog":
                return mock_plan_review_cog
            return None

        bot.get_cog = MagicMock(side_effect=get_cog_side_effect)

        mock_ml_instance = MagicMock()
        mock_ml_instance.run = AsyncMock()
        mock_ml_cls.return_value = mock_ml_instance

        with patch("vcompany.bot.client.asyncio.create_task"):
            await bot.on_ready()

        # Check MonitorLoop received alert callbacks
        ml_call_kwargs = mock_ml_cls.call_args
        assert ml_call_kwargs.kwargs["on_agent_dead"] == fake_callbacks["on_agent_dead"]
        assert ml_call_kwargs.kwargs["on_agent_stuck"] == fake_callbacks["on_agent_stuck"]

        # PlanReviewCog's on_plan_detected should be preferred over AlertsCog's
        assert ml_call_kwargs.kwargs["on_plan_detected"] == plan_review_on_plan_detected

        # Check CrashTracker received circuit_open callback
        ct_call_kwargs = mock_ct_cls.call_args
        assert ct_call_kwargs.kwargs["on_circuit_open"] == fake_callbacks["on_circuit_open"]

    @pytest.mark.asyncio
    @patch("vcompany.bot.client.MonitorLoop")
    @patch("vcompany.bot.client.CrashTracker")
    @patch("vcompany.bot.client.AgentManager")
    @patch("vcompany.bot.client.TmuxManager", create=True)
    async def test_on_ready_falls_back_to_alerts_plan_detected(
        self, mock_tmux_cls, mock_am_cls, mock_ct_cls, mock_ml_cls, monkeypatch
    ):
        """When PlanReviewCog not available, falls back to AlertsCog on_plan_detected."""
        bot = _make_bot(monkeypatch)
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)

        # Mock AlertsCog with callbacks
        mock_alerts_cog = MagicMock()
        alerts_plan_detected = MagicMock()
        fake_callbacks = {
            "on_agent_dead": MagicMock(),
            "on_agent_stuck": MagicMock(),
            "on_plan_detected": alerts_plan_detected,
            "on_circuit_open": MagicMock(),
        }
        mock_alerts_cog.make_sync_callbacks.return_value = fake_callbacks

        def get_cog_side_effect(name):
            if name == "AlertsCog":
                return mock_alerts_cog
            return None  # PlanReviewCog not available

        bot.get_cog = MagicMock(side_effect=get_cog_side_effect)

        mock_ml_instance = MagicMock()
        mock_ml_instance.run = AsyncMock()
        mock_ml_cls.return_value = mock_ml_instance

        with patch("vcompany.bot.client.asyncio.create_task"):
            await bot.on_ready()

        # Should fall back to AlertsCog's on_plan_detected
        ml_call_kwargs = mock_ml_cls.call_args
        assert ml_call_kwargs.kwargs["on_plan_detected"] == alerts_plan_detected

    @pytest.mark.asyncio
    @patch("vcompany.bot.client.MonitorLoop")
    @patch("vcompany.bot.client.CrashTracker")
    @patch("vcompany.bot.client.AgentManager")
    @patch("vcompany.bot.client.TmuxManager", create=True)
    async def test_on_ready_starts_monitor_task(
        self, mock_tmux_cls, mock_am_cls, mock_ct_cls, mock_ml_cls, monkeypatch
    ):
        """Verify asyncio.create_task called with monitor_loop.run()."""
        bot = _make_bot(monkeypatch)
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        mock_ml_instance = MagicMock()
        mock_run_coro = AsyncMock()
        mock_ml_instance.run = mock_run_coro
        mock_ml_cls.return_value = mock_ml_instance

        with patch("vcompany.bot.client.asyncio.create_task") as mock_create_task:
            await bot.on_ready()

        mock_create_task.assert_called_once()
        # Verify the name kwarg
        _, kwargs = mock_create_task.call_args
        assert kwargs.get("name") == "monitor-loop"

    @pytest.mark.asyncio
    @patch("vcompany.bot.client.MonitorLoop")
    @patch("vcompany.bot.client.CrashTracker")
    @patch("vcompany.bot.client.AgentManager")
    @patch("vcompany.bot.client.TmuxManager", create=True)
    async def test_on_ready_idempotent(
        self, mock_tmux_cls, mock_am_cls, mock_ct_cls, mock_ml_cls, monkeypatch
    ):
        """Call on_ready twice, verify components initialized only once (Pitfall 7)."""
        bot = _make_bot(monkeypatch)
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        mock_ml_instance = MagicMock()
        mock_ml_instance.run = AsyncMock()
        mock_ml_cls.return_value = mock_ml_instance

        with patch("vcompany.bot.client.asyncio.create_task"):
            await bot.on_ready()
            await bot.on_ready()

        # AgentManager should only be instantiated once
        assert mock_am_cls.call_count == 1

    @pytest.mark.asyncio
    @patch("vcompany.bot.client.MonitorLoop")
    @patch("vcompany.bot.client.CrashTracker")
    @patch("vcompany.bot.client.AgentManager")
    @patch("vcompany.bot.client.TmuxManager", create=True)
    async def test_on_ready_survives_init_failure(
        self, mock_tmux_cls, mock_am_cls, mock_ct_cls, mock_ml_cls, monkeypatch
    ):
        """If AgentManager raises, _ready_flag still set, bot still functional."""
        bot = _make_bot(monkeypatch)
        guild = _mock_guild()
        bot.get_guild = MagicMock(return_value=guild)
        bot.get_cog = MagicMock(return_value=None)

        # Make AgentManager raise
        mock_am_cls.side_effect = RuntimeError("tmux not available")

        await bot.on_ready()

        assert bot._initialized is True
        assert bot._ready_flag is True
        # Components should be None since init failed
        assert bot.agent_manager is None


class TestClose:
    """Graceful shutdown stops monitor loop and cancels task."""

    @pytest.mark.asyncio
    async def test_close_stops_monitor(self, monkeypatch):
        """Verify monitor_loop.stop() called and task cancelled."""
        import asyncio

        bot = _make_bot(monkeypatch)

        mock_loop = MagicMock()
        mock_loop.stop = MagicMock()
        bot.monitor_loop = mock_loop

        # Create a real asyncio task that we can cancel
        async def _noop():
            await asyncio.sleep(999)

        task = asyncio.create_task(_noop())
        bot._monitor_task = task

        with patch.object(type(bot).__bases__[0], "close", new_callable=AsyncMock):
            await bot.close()

        mock_loop.stop.assert_called_once()
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_close_without_monitor(self, monkeypatch):
        """close() works even if monitor was never initialized."""
        bot = _make_bot(monkeypatch)

        with patch.object(type(bot).__bases__[0], "close", new_callable=AsyncMock):
            await bot.close()

        # Should not raise


class TestGuildIdFromConfig:
    """Verify _guild_id read from env correctly."""

    def test_guild_id_from_env(self, monkeypatch):
        """_guild_id is set from DISCORD_GUILD_ID env var."""
        monkeypatch.setenv("DISCORD_GUILD_ID", "98765")
        bot = VcoBot(Path("/tmp/test"), _make_config())
        assert bot._guild_id == 98765

    def test_guild_id_default(self, monkeypatch):
        """_guild_id defaults to 0 when env var not set."""
        monkeypatch.delenv("DISCORD_GUILD_ID", raising=False)
        bot = VcoBot(Path("/tmp/test"), _make_config())
        assert bot._guild_id == 0
