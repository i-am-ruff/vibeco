"""VcoBot: Discord bot client for vCompany orchestration.

Subclasses commands.Bot to provide Cog loading, vco-owner role creation,
and integration points for AgentManager, MonitorLoop, and CrashTracker.

Implements D-11, D-12, D-13, D-22.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

from vcompany.models.config import ProjectConfig
from vcompany.monitor.loop import MonitorLoop
from vcompany.orchestrator.agent_manager import AgentManager
from vcompany.orchestrator.crash_tracker import CrashTracker
from vcompany.tmux.session import TmuxManager

logger = logging.getLogger("vcompany.bot.client")

# Cog extension paths loaded in setup_hook (D-12)
_COG_EXTENSIONS: list[str] = [
    "vcompany.bot.cogs.commands",
    "vcompany.bot.cogs.alerts",
    "vcompany.bot.cogs.plan_review",
    "vcompany.bot.cogs.strategist",
    "vcompany.bot.cogs.question_handler",
]


class VcoBot(commands.Bot):
    """Discord bot for vCompany project orchestration.

    Loads 4 Cogs via setup_hook. Creates vco-owner role on first on_ready.
    Holds references to AgentManager, MonitorLoop, and CrashTracker for
    use by Cogs (injected after construction, before bot.start()).
    """

    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # privileged intent required for prefix commands
        super().__init__(command_prefix="!", intents=intents)

        self.project_dir = Path(project_dir)
        self.project_config = config

        # Injected by caller before bot.start()
        self.agent_manager: AgentManager | None = None
        self.monitor_loop: MonitorLoop | None = None
        self.crash_tracker: CrashTracker | None = None

        # Guild ID from env (D-21, D-22: single guild bot)
        self._guild_id: int = int(os.environ.get("DISCORD_GUILD_ID", "0"))

        # Alert buffer for messages during disconnect (D-15)
        self._alert_buffer: list[str] = []

        # Pitfall 7 guard: on_ready fires on every reconnect, only init once
        self._initialized: bool = False

        # Pitfall 6 guard: cogs can check if bot is ready before operating
        self._ready_flag: bool = False

        # Monitor loop background task reference
        self._monitor_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        """Load all 4 Cog extensions (D-12, DISC-01)."""
        for ext in _COG_EXTENSIONS:
            await self.load_extension(ext)
        logger.info("Loaded %d cog extensions", len(_COG_EXTENSIONS))

    async def on_ready(self) -> None:
        """First-time initialization: role creation + orchestration wiring (D-10, D-13).

        Guarded with _initialized flag to handle reconnect events (Pitfall 7).
        """
        if self._initialized:
            logger.info("on_ready fired again (reconnect), skipping init")
            return

        guild = self.get_guild(self._guild_id)
        if guild is None:
            logger.error("Guild %d not found. Bot may not be in the guild.", self._guild_id)
            self._ready_flag = True
            self._initialized = True
            return

        # Create vco-owner role if it doesn't exist (D-10)
        existing_role = discord.utils.get(guild.roles, name="vco-owner")
        if existing_role is None:
            await guild.create_role(
                name="vco-owner",
                reason="VcoBot auto-created owner role",
            )
            logger.info("Created vco-owner role in guild %s", guild.name)
        else:
            logger.info("vco-owner role already exists in guild %s", guild.name)

        # D-13: Initialize AgentManager, MonitorLoop, CrashTracker
        try:
            tmux = TmuxManager()

            # Get AlertsCog for callback injection
            alerts_cog = self.get_cog("AlertsCog")
            callbacks = alerts_cog.make_sync_callbacks() if alerts_cog else {}

            # Initialize AgentManager
            self.agent_manager = AgentManager(self.project_dir, self.project_config, tmux)

            # Initialize CrashTracker with circuit breaker callback
            self.crash_tracker = CrashTracker(
                crash_log_path=self.project_dir / "state" / "crash_log.json",
                on_circuit_open=callbacks.get("on_circuit_open"),
            )

            # Get PlanReviewCog for plan gate callback (Phase 5: D-07 through D-12)
            plan_review_cog = self.get_cog("PlanReviewCog")
            plan_review_callbacks = plan_review_cog.make_sync_callback() if plan_review_cog else {}

            # Use PlanReviewCog's on_plan_detected instead of AlertsCog's
            # PlanReviewCog handles the full plan gate workflow;
            # AlertsCog still gets alert-only notification via separate method
            plan_detected_callback = plan_review_callbacks.get(
                "on_plan_detected"
            ) or callbacks.get("on_plan_detected")

            # Initialize MonitorLoop with alert callbacks + plan review callback
            self.monitor_loop = MonitorLoop(
                project_dir=self.project_dir,
                config=self.project_config,
                tmux=tmux,
                on_agent_dead=callbacks.get("on_agent_dead"),
                on_agent_stuck=callbacks.get("on_agent_stuck"),
                on_plan_detected=plan_detected_callback,
            )

            # Phase 7: Wire checkin callback from CommandsCog into monitor (D-09)
            commands_cog = self.get_cog("CommandsCog")
            if commands_cog:
                commands_cog.wire_monitor_callbacks()

            # Start monitor loop as background task per D-13
            self._monitor_task = asyncio.create_task(
                self.monitor_loop.run(), name="monitor-loop"
            )
            logger.info("Monitor loop started as background task")

        except Exception:
            logger.exception("Failed to initialize orchestration components")
            # Bot still works for commands, just without monitor

        # Phase 6: Initialize PM/Strategist if ANTHROPIC_API_KEY is set
        try:
            from anthropic import AsyncAnthropic

            from vcompany.bot.config import BotConfig
            from vcompany.strategist.plan_reviewer import PlanReviewer
            from vcompany.strategist.pm import PMTier

            bot_config = BotConfig()
            if bot_config.anthropic_api_key:
                anthropic_client = AsyncAnthropic(api_key=bot_config.anthropic_api_key)

                # Initialize StrategistCog
                strategist_cog = self.get_cog("StrategistCog")
                if strategist_cog:
                    persona_path = (
                        Path(bot_config.strategist_persona_path)
                        if bot_config.strategist_persona_path
                        else None
                    )
                    decisions_path = self.project_dir / "state" / "decisions.jsonl"
                    await strategist_cog.initialize(anthropic_client, persona_path, decisions_path)

                # Initialize PMTier and inject into QuestionHandlerCog
                pm = PMTier(anthropic_client, self.project_dir)
                question_cog = self.get_cog("QuestionHandlerCog")
                if question_cog:
                    question_cog.set_pm(pm)

                # Initialize PlanReviewer and inject into PlanReviewCog
                plan_reviewer = PlanReviewer(self.project_dir, self.project_config)
                plan_review_cog_ref = self.get_cog("PlanReviewCog")
                if plan_review_cog_ref:
                    plan_review_cog_ref.set_plan_reviewer(plan_reviewer)

                # Wire status digest callback from MonitorLoop to StrategistCog
                if self.monitor_loop and strategist_cog:
                    callbacks = strategist_cog.make_sync_callbacks()
                    # Status digests feed project status to Strategist conversation

                    def _digest_callback(status_content: str) -> None:
                        loop = self.loop
                        if strategist_cog._conversation:
                            asyncio.run_coroutine_threadsafe(
                                strategist_cog._conversation.send(
                                    f"[Status Digest]\n{status_content}"
                                ).__anext__(),
                                loop,
                            )

                    self.monitor_loop._on_status_digest = _digest_callback

                logger.info("PM/Strategist initialized with Anthropic API")
            else:
                logger.warning("ANTHROPIC_API_KEY not set -- PM/Strategist disabled")
        except ImportError:
            logger.warning("anthropic SDK not installed -- PM/Strategist disabled")
        except Exception:
            logger.exception("Failed to initialize PM/Strategist")

        self._initialized = True
        self._ready_flag = True
        logger.info("VcoBot ready in guild %s", guild.name)

    async def close(self) -> None:
        """Graceful shutdown: stop monitor loop, then close bot."""
        if self.monitor_loop:
            self.monitor_loop.stop()
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        await super().close()

    @property
    def is_bot_ready(self) -> bool:
        """Check if bot has completed on_ready initialization (Pitfall 6)."""
        return self._ready_flag
