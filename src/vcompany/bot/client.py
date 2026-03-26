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
    "vcompany.bot.cogs.workflow_master",
]


class VcoBot(commands.Bot):
    """Discord bot for vCompany project orchestration.

    Loads 4 Cogs via setup_hook. Creates vco-owner role on first on_ready.
    Holds references to AgentManager, MonitorLoop, and CrashTracker for
    use by Cogs (injected after construction, before bot.start()).
    """

    def __init__(
        self,
        guild_id: int,
        project_dir: Path | None = None,
        config: ProjectConfig | None = None,
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # privileged intent required for Strategist on_message
        super().__init__(command_prefix="!", intents=intents)

        self.project_dir: Path | None = Path(project_dir) if project_dir else None
        self.project_config: ProjectConfig | None = config

        # Injected by caller before bot.start()
        self.agent_manager: AgentManager | None = None
        self.monitor_loop: MonitorLoop | None = None
        self.crash_tracker: CrashTracker | None = None

        # Guild ID as explicit constructor arg (D-21, D-22: single guild bot)
        self._guild_id: int = guild_id

        # Alert buffer for messages during disconnect (D-15)
        self._alert_buffer: list[str] = []

        # Pitfall 7 guard: on_ready fires on every reconnect, only init once
        self._initialized: bool = False

        # Pitfall 6 guard: cogs can check if bot is ready before operating
        self._ready_flag: bool = False

        # Monitor loop background task reference
        self._monitor_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        """Load Cog extensions and sync slash commands to guild (D-12, DISC-01)."""
        for ext in _COG_EXTENSIONS:
            await self.load_extension(ext)
        logger.info("Loaded %d cog extensions", len(_COG_EXTENSIONS))

        # Sync slash commands to guild (in setup_hook, NOT on_ready, to avoid
        # double-sync on reconnect per Research Pitfall 2)
        guild = discord.Object(id=self._guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info("Synced slash command tree to guild %d", self._guild_id)

    async def on_ready(self) -> None:
        """First-time initialization: role creation + orchestration wiring (D-10, D-13).

        Split into always-run (role, Strategist) and project-only (AgentManager,
        MonitorLoop, CrashTracker) sections. Guarded with _initialized flag to
        handle reconnect events (Pitfall 7).
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

        # ── Always-run initialization ──────────────────────────────────

        # Create vco-owner role if it doesn't exist (D-10)
        existing_role = discord.utils.get(guild.roles, name="vco-owner")
        if existing_role is None:
            existing_role = await guild.create_role(
                name="vco-owner",
                reason="VcoBot auto-created owner role",
            )
            logger.info("Created vco-owner role in guild %s", guild.name)
        else:
            logger.info("vco-owner role already exists in guild %s", guild.name)

        # Create system channels (idempotent)
        try:
            from vcompany.bot.channel_setup import setup_system_channels

            self._system_channels = await setup_system_channels(guild, existing_role)
            logger.info("System channels ready: %s", list(self._system_channels.keys()))
        except Exception:
            logger.exception("Failed to set up system channels")
            self._system_channels = {}

        # Initialize Strategist (always available, even without project)
        try:
            from vcompany.bot.config import BotConfig

            bot_config = BotConfig()

            strategist_cog = self.get_cog("StrategistCog")
            if strategist_cog:
                persona_path = (
                    Path(bot_config.strategist_persona_path)
                    if bot_config.strategist_persona_path
                    else None
                )
                # decisions_path only when project is loaded
                decisions_path = (
                    self.project_dir / "state" / "decisions.jsonl"
                    if self.project_dir
                    else None
                )
                await strategist_cog.initialize(persona_path, decisions_path)

            logger.info("Strategist initialized (always available)")
        except Exception:
            logger.exception("Failed to initialize Strategist")

        # Initialize WorkflowMaster (always available, like Strategist)
        try:
            wm_cog = self.get_cog("WorkflowMasterCog")
            if wm_cog:
                worktree_path = Path.home() / "vco-workflow-master-worktree"
                await wm_cog.initialize(
                    persona_path=None,
                    worktree_path=worktree_path,
                )
            logger.info("WorkflowMasterCog initialized")
        except Exception:
            logger.exception("Failed to initialize WorkflowMasterCog")

        # ── Project-only initialization ────────────────────────────────

        if self.project_config is not None and self.project_dir is not None:
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

            # Initialize PM and PlanReviewer (project-dependent)
            try:
                from vcompany.strategist.plan_reviewer import PlanReviewer
                from vcompany.strategist.pm import PMTier

                # Initialize PMTier and inject into QuestionHandlerCog
                pm = PMTier(project_dir=self.project_dir)
                question_cog = self.get_cog("QuestionHandlerCog")
                if question_cog:
                    question_cog.set_pm(pm)

                # Initialize PlanReviewer and inject into PlanReviewCog
                plan_reviewer = PlanReviewer(self.project_dir, self.project_config)
                plan_review_cog_ref = self.get_cog("PlanReviewCog")
                if plan_review_cog_ref:
                    plan_review_cog_ref.set_plan_reviewer(plan_reviewer)

                # Wire status digest callback from MonitorLoop to StrategistCog
                strategist_cog_ref = self.get_cog("StrategistCog")
                if self.monitor_loop and strategist_cog_ref:
                    def _digest_callback(status_content: str) -> None:
                        loop = self.loop
                        if strategist_cog_ref._conversation:
                            asyncio.run_coroutine_threadsafe(
                                strategist_cog_ref._conversation.send(
                                    f"[Status Digest]\n{status_content}"
                                ).__anext__(),
                                loop,
                            )

                    self.monitor_loop._on_status_digest = _digest_callback

                logger.info("PM/PlanReviewer initialized with Claude CLI")
            except Exception:
                logger.exception("Failed to initialize PM/PlanReviewer")
        else:
            logger.info("No project loaded -- running in Strategist-only mode")

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
