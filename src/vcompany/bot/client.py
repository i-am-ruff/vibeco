"""VcoBot: Discord bot client for vCompany orchestration.

Subclasses commands.Bot to provide Cog loading, vco-owner role creation,
and integration with CompanyRoot supervision tree.

Implements D-11, D-12, D-13, D-22, MIGR-01.
"""

from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from vcompany.container.child_spec import ChildSpec
from vcompany.container.context import ContainerContext
from vcompany.models.config import ProjectConfig
from vcompany.supervisor.company_root import CompanyRoot

logger = logging.getLogger("vcompany.bot.client")

# Cog extension paths loaded in setup_hook (D-12)
_COG_EXTENSIONS: list[str] = [
    "vcompany.bot.cogs.commands",
    "vcompany.bot.cogs.alerts",
    "vcompany.bot.cogs.plan_review",
    "vcompany.bot.cogs.strategist",
    "vcompany.bot.cogs.question_handler",
    "vcompany.bot.cogs.workflow_master",
    "vcompany.bot.cogs.workflow_orchestrator_cog",
]


class VcoBot(commands.Bot):
    """Discord bot for vCompany project orchestration.

    All commands are slash commands (no prefix commands). Loads Cogs via
    setup_hook. Creates vco-owner role on first on_ready.
    Uses CompanyRoot supervision tree for agent lifecycle management (MIGR-01).
    """

    def __init__(
        self,
        guild_id: int,
        project_dir: Path | None = None,
        config: ProjectConfig | None = None,
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # privileged intent required for Strategist on_message
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)

        self.project_dir: Path | None = Path(project_dir) if project_dir else None
        self.project_config: ProjectConfig | None = config

        # v2: CompanyRoot supervision tree replaces v1 flat initialization
        self.company_root: CompanyRoot | None = None

        # Guild ID as explicit constructor arg (D-21, D-22: single guild bot)
        self._guild_id: int = guild_id

        # Alert buffer for messages during disconnect (D-15)
        self._alert_buffer: list[str] = []

        # Pitfall 7 guard: on_ready fires on every reconnect, only init once
        self._initialized: bool = False

        # Pitfall 6 guard: cogs can check if bot is ready before operating
        self._ready_flag: bool = False

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
        """First-time initialization: role creation + supervision tree wiring (D-10, D-13, MIGR-01).

        Split into always-run (role, Strategist) and project-only (CompanyRoot
        supervision tree) sections. Guarded with _initialized flag to
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

        # ── Auto-detect active project on restart ─────────────────────
        if self.project_config is None and self.project_dir is None:
            detected = self._detect_active_project()
            if detected:
                self.project_dir, self.project_config = detected
                logger.info("Auto-detected active project: %s", self.project_config.project)

        # ── Project-only initialization (v2: CompanyRoot supervision tree) ──

        if self.project_config is not None and self.project_dir is not None:
            try:
                # Escalation callback for Discord alerts
                async def on_escalation(msg: str) -> None:
                    alerts_ch = self._system_channels.get("alerts")
                    if alerts_ch:
                        await alerts_ch.send(f"ESCALATION: {msg}")

                # Health change callback
                health_cog = self.get_cog("HealthCog")
                on_health_change = health_cog._notify_state_change if health_cog else None

                self.company_root = CompanyRoot(
                    on_escalation=on_escalation,
                    max_restarts=3,
                    window_seconds=600,
                    data_dir=self.project_dir / "state" / "supervision",
                    on_health_change=on_health_change,
                )
                await self.company_root.start()

                # Build child specs from agents.yaml
                specs = []
                for agent_cfg in self.project_config.agents:
                    ctx = ContainerContext(
                        agent_id=agent_cfg.id,
                        agent_type=agent_cfg.type if hasattr(agent_cfg, "type") else "gsd",
                        parent_id="project-supervisor",
                        project_id=self.project_config.project,
                        owned_dirs=agent_cfg.owns if hasattr(agent_cfg, "owns") else [],
                        gsd_mode=agent_cfg.gsd_mode if hasattr(agent_cfg, "gsd_mode") else "",
                        system_prompt=agent_cfg.system_prompt if hasattr(agent_cfg, "system_prompt") else "",
                    )
                    specs.append(ChildSpec(child_id=agent_cfg.id, agent_type=ctx.agent_type, context=ctx))

                await self.company_root.add_project(
                    project_id=self.project_config.project,
                    child_specs=specs,
                )

                logger.info("Supervision tree started with %d agents", len(specs))
            except Exception:
                logger.exception("Failed to initialize supervision tree")

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

                # Wire WorkflowOrchestratorCog with PM and project dir
                wo_cog = self.get_cog("WorkflowOrchestratorCog")
                if wo_cog:
                    wo_cog.set_company_root(pm, self.project_dir)

                    # Wire plan approval/rejection notifications from PlanReviewCog
                    if plan_review_cog_ref:
                        plan_review_cog_ref._workflow_cog = wo_cog

                logger.info("PM/PlanReviewer initialized with Claude CLI")
            except Exception:
                logger.exception("Failed to initialize PM/PlanReviewer")
        else:
            logger.info("No project loaded -- running in Strategist-only mode")

        self._initialized = True
        self._ready_flag = True
        logger.info("VcoBot ready in guild %s", guild.name)

        # ── Boot notifications ──────────────────────────────────────────
        await self._send_boot_notifications(guild)

    def _detect_active_project(self) -> tuple[Path, ProjectConfig] | None:
        """Scan ~/vco-projects/ for the most recently active project.

        Looks for projects with state/agents.json (meaning they were dispatched).
        Returns the one with the newest agents.json mtime.
        """
        from vcompany.shared.paths import PROJECTS_BASE

        if not PROJECTS_BASE.exists():
            return None

        best: tuple[Path, float] | None = None
        for project_dir in PROJECTS_BASE.iterdir():
            if not project_dir.is_dir():
                continue
            agents_json = project_dir / "state" / "agents.json"
            agents_yaml = project_dir / "agents.yaml"
            if agents_json.exists() and agents_yaml.exists():
                mtime = agents_json.stat().st_mtime
                if best is None or mtime > best[1]:
                    best = (project_dir, mtime)

        if best is None:
            return None

        try:
            from vcompany.models.config import load_config
            config = load_config(best[0] / "agents.yaml")
            return (best[0], config)
        except Exception:
            logger.warning("Failed to load config for detected project %s", best[0])
            return None

    async def _send_boot_notifications(self, guild: discord.Guild) -> None:
        """Ping owner in #alerts and notify Strategist that system is online."""
        restart_signal = Path.home() / ".vco-restart-requested"
        is_restart = restart_signal.exists()
        if is_restart:
            restart_signal.unlink(missing_ok=True)

        try:
            # Ping owner in #alerts
            alerts_channel = self._system_channels.get("alerts")
            if alerts_channel:
                owner_role = discord.utils.get(guild.roles, name="vco-owner")
                mention = owner_role.mention if owner_role else "@owner"
                if is_restart:
                    await alerts_channel.send(
                        f"{mention} vCompany restarted successfully. All systems online."
                    )
                else:
                    await alerts_channel.send(
                        f"{mention} vCompany is online."
                    )

            # Send system message to Strategist so it knows to greet
            strategist_channel = self._system_channels.get("strategist")
            if strategist_channel:
                if is_restart:
                    await strategist_channel.send(
                        "[system] `vco restart` complete - vCompany is back online."
                    )
                else:
                    await strategist_channel.send(
                        "[system] `vco up` - vCompany is online."
                    )
        except Exception:
            logger.exception("Failed to send boot notifications")

    async def close(self) -> None:
        """Graceful shutdown: stop supervision tree, then close bot."""
        if self.company_root is not None:
            await self.company_root.stop()
        await super().close()

    @property
    def is_bot_ready(self) -> bool:
        """Check if bot has completed on_ready initialization (Pitfall 6)."""
        return self._ready_flag
