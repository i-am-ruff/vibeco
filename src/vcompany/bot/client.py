"""VcoBot: Discord bot client for vCompany orchestration.

Subclasses commands.Bot to provide Cog loading, vco-owner role creation,
and integration with CompanyRoot supervision tree.

Implements D-11, D-12, D-13, D-22, MIGR-01.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Callable

import discord
from discord.ext import commands

from vcompany.agent.company_agent import CompanyAgent
from vcompany.agent.continuous_agent import ContinuousAgent
from vcompany.agent.fulltime_agent import FulltimeAgent
from vcompany.agent.gsd_agent import GsdAgent
from vcompany.autonomy.backlog import BacklogQueue
from vcompany.autonomy.project_state import ProjectStateManager
from vcompany.container.child_spec import ChildSpec
from vcompany.container.context import ContainerContext
from vcompany.models.config import ProjectConfig
from vcompany.resilience.message_queue import MessageQueue, MessagePriority, QueuedMessage, RateLimited
from vcompany.supervisor.company_root import CompanyRoot
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
    "vcompany.bot.cogs.workflow_orchestrator_cog",
    "vcompany.bot.cogs.health",
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

        # Resilience: outbound message queue with priority and debounce (RESL-01)
        self.message_queue: MessageQueue | None = None

        # Guild ID as explicit constructor arg (D-21, D-22: single guild bot)
        self._guild_id: int = guild_id

        # Alert buffer for messages during disconnect (D-15)
        self._alert_buffer: list[str] = []

        # Pitfall 7 guard: on_ready fires on every reconnect, only init once
        self._initialized: bool = False

        # Pitfall 6 guard: cogs can check if bot is ready before operating
        self._ready_flag: bool = False

        # PM container reference for GsdAgent event routing (AUTO-01, AUTO-02)
        self._pm_container: FulltimeAgent | None = None

        # TmuxManager for real agent session management (Phase 8.2)
        self._tmux_manager: TmuxManager | None = None

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

        # Initialize Strategist channels/logger (always available, even without project)
        # The conversation itself is now owned by CompanyAgent (ARCH-01).
        # We store persona_path here so CompanyAgent wiring below can use it.
        _strategist_persona_path: Path | None = None
        try:
            from vcompany.bot.config import BotConfig

            bot_config = BotConfig()

            strategist_cog = self.get_cog("StrategistCog")
            if strategist_cog:
                _strategist_persona_path = (
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
                # Pass persona_path for backward-compat fallback; CompanyAgent will
                # own the conversation once wired in the project section below.
                await strategist_cog.initialize(_strategist_persona_path, decisions_path)

            logger.info("Strategist channels initialized (always available)")
        except Exception:
            logger.exception("Failed to initialize Strategist channels")

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
                    if alerts_ch and self.message_queue:
                        await self.message_queue.enqueue(QueuedMessage(
                            priority=MessagePriority.ESCALATION,
                            timestamp=time.monotonic(),
                            channel_id=alerts_ch.id,
                            content=f"ESCALATION: {msg}",
                        ))

                # Health change callback
                health_cog = self.get_cog("HealthCog")
                on_health_change = health_cog._notify_state_change if health_cog else None

                # Claude API health check for DegradedModeManager (RESL-03)
                async def claude_health_check() -> bool:
                    try:
                        import anthropic

                        client = anthropic.AsyncAnthropic()
                        await client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=1,
                            messages=[{"role": "user", "content": "ping"}],
                        )
                        return True
                    except Exception:
                        return False

                # Degraded/recovered callbacks notify #alerts channel
                async def on_degraded() -> None:
                    alerts_ch = self._system_channels.get("alerts")
                    if alerts_ch and self.message_queue:
                        await self.message_queue.enqueue(QueuedMessage(
                            priority=MessagePriority.SUPERVISOR,
                            timestamp=time.monotonic(),
                            channel_id=alerts_ch.id,
                            content="WARNING: System entered degraded mode (Claude API unreachable). "
                            "New dispatches blocked. Will auto-recover.",
                        ))

                async def on_recovered() -> None:
                    alerts_ch = self._system_channels.get("alerts")
                    if alerts_ch and self.message_queue:
                        await self.message_queue.enqueue(QueuedMessage(
                            priority=MessagePriority.SUPERVISOR,
                            timestamp=time.monotonic(),
                            channel_id=alerts_ch.id,
                            content="RECOVERED: System recovered from degraded mode. "
                            "Claude API reachable. Normal operations resumed.",
                        ))

                # Create TmuxManager for real agent session management
                tmux_manager = TmuxManager()
                self._tmux_manager = tmux_manager

                self.company_root = CompanyRoot(
                    on_escalation=on_escalation,
                    max_restarts=3,
                    window_seconds=600,
                    data_dir=self.project_dir / "state" / "supervision",
                    on_health_change=on_health_change,
                    health_check=claude_health_check,
                    on_degraded=on_degraded,
                    on_recovered=on_recovered,
                    tmux_manager=tmux_manager,
                    project_dir=self.project_dir,
                )
                await self.company_root.start()

                # Add Strategist as a direct company-level agent (ARCH-02)
                strategist_ctx = ContainerContext(
                    agent_id="strategist",
                    agent_type="company",
                    parent_id="company-root",
                    project_id=None,
                )
                strategist_spec = ChildSpec(
                    child_id="strategist",
                    agent_type="company",
                    context=strategist_ctx,
                )
                strategist_container = await self.company_root.add_company_agent(strategist_spec)
                logger.info("Strategist CompanyAgent added to CompanyRoot")

                # Wire Strategist conversation and callbacks (ARCH-01)
                if isinstance(strategist_container, CompanyAgent):
                    # CompanyAgent owns the conversation
                    strategist_container.initialize_conversation(_strategist_persona_path)

                    # Response callback: post text to the originating Discord channel
                    async def _on_strategist_response(response: str, channel_id: int) -> None:
                        channel = self.get_channel(channel_id)
                        if channel is not None:
                            if len(response) > 2000:
                                remaining = response
                                while remaining:
                                    chunk = remaining[:2000]
                                    await channel.send(chunk)  # type: ignore[union-attr]
                                    remaining = remaining[2000:]
                            else:
                                await channel.send(response)  # type: ignore[union-attr]

                    strategist_container._on_response = _on_strategist_response

                    # Wire StrategistCog to forward events to CompanyAgent
                    strategist_cog_ref = self.get_cog("StrategistCog")
                    if strategist_cog_ref is not None:
                        strategist_cog_ref.set_company_agent(strategist_container)

                    logger.info("Strategist CompanyAgent wired (conversation + callbacks)")

                # MessageQueue for outbound notifications (RESL-01)
                async def _send_message(msg: QueuedMessage) -> None:
                    channel = self.get_channel(msg.channel_id)
                    if channel is None:
                        logger.warning("Channel %d not found, dropping message", msg.channel_id)
                        return
                    try:
                        if msg.embed is not None:
                            await channel.send(embed=msg.embed)  # type: ignore[union-attr]
                        elif msg.content is not None:
                            await channel.send(msg.content)  # type: ignore[union-attr]
                    except discord.HTTPException as exc:
                        if exc.status == 429:
                            raise RateLimited() from exc
                        raise

                self.message_queue = MessageQueue(send_func=_send_message)
                await self.message_queue.start()
                logger.info("MessageQueue started")

                # Build child specs from agents.yaml
                specs = []
                for agent_cfg in self.project_config.agents:
                    ctx = ContainerContext(
                        agent_id=agent_cfg.id,
                        agent_type=agent_cfg.type,
                        parent_id="project-supervisor",
                        project_id=self.project_config.project,
                        owned_dirs=agent_cfg.owns,
                        gsd_mode=agent_cfg.gsd_mode,
                        system_prompt=agent_cfg.system_prompt,
                        gsd_command="/gsd:discuss-phase 1" if agent_cfg.type == "gsd" else None,
                    )
                    specs.append(ChildSpec(child_id=agent_cfg.id, agent_type=ctx.agent_type, context=ctx))

                project_sup = await self.company_root.add_project(
                    project_id=self.project_config.project,
                    child_specs=specs,
                )

                # Wire PM backlog and project state (AUTO-01, AUTO-02, AUTO-05)
                pm_container: FulltimeAgent | None = None
                for child in project_sup.children.values():
                    if isinstance(child, FulltimeAgent):
                        pm_container = child
                        break

                if pm_container is not None:
                    backlog = BacklogQueue(pm_container.memory)
                    await backlog.load()
                    state_mgr = ProjectStateManager(backlog, pm_container.memory)
                    pm_container.backlog = backlog
                    pm_container._project_state = state_mgr
                    self._pm_container = pm_container
                    logger.info(
                        "PM backlog and project state wired for %s",
                        pm_container.context.agent_id,
                    )

                    # Wire PM event routing (PMRT-01, PMRT-02, PMRT-03, PMRT-04)
                    async def pm_event_sink(event: dict[str, Any]) -> None:
                        await pm_container.post_event(event)

                    # Factory closures -- defined here so Phase 15 wiring can reuse them
                    # for newly recruited agents without re-defining inline.
                    def _make_gsd_cb(sink: Callable[[dict[str, Any]], Any]) -> Callable:
                        async def _cb(agent_id: str, from_phase: str, to_phase: str) -> None:
                            await sink({
                                "type": "gsd_transition",
                                "agent_id": agent_id,
                                "from_phase": from_phase,
                                "to_phase": to_phase,
                            })
                        return _cb

                    def _make_briefing_cb(sink: Callable[[dict[str, Any]], Any]) -> Callable:
                        async def _cb(agent_id: str, content: str) -> None:
                            await sink({
                                "type": "briefing",
                                "agent_id": agent_id,
                                "content": content,
                            })
                        return _cb

                    # PMRT-02 + PMRT-03: GSD transitions and briefings via agent callbacks
                    for child in project_sup.children.values():
                        if isinstance(child, GsdAgent):
                            child._on_phase_transition = _make_gsd_cb(pm_event_sink)
                        elif isinstance(child, ContinuousAgent):
                            child._on_briefing = _make_briefing_cb(pm_event_sink)
                            child._request_delegation = project_sup.handle_delegation_request

                    logger.info("PM event routing wired for %s", pm_container.context.agent_id)

                else:
                    logger.info("No FulltimeAgent (PM) found in project children, skipping backlog wiring")

                # GATE-01 + GATE-02: Wire Phase 14 review gate callbacks.
                # GATE-01 wired regardless of PM -- only requires PlanReviewCog.
                # GATE-02 wired only when pm_container found.
                plan_review_cog = self.get_cog("PlanReviewCog")
                if plan_review_cog is not None:
                    # GATE-01: Wire _on_review_request on every GsdAgent -> post_review_request
                    for child in project_sup.children.values():
                        if isinstance(child, GsdAgent):
                            def _make_review_cb(cog: Any) -> Callable:
                                async def _cb(agent_id: str, stage: str) -> None:
                                    await cog.post_review_request(agent_id, stage)
                                return _cb
                            child._on_review_request = _make_review_cb(plan_review_cog)

                    # GATE-02: Wire _on_gsd_review on FulltimeAgent -> dispatch_pm_review
                    if pm_container is not None:
                        def _make_gsd_review_cb(cog: Any) -> Callable:
                            async def _cb(agent_id: str, stage: str) -> None:
                                await cog.dispatch_pm_review(agent_id, stage)
                            return _cb
                        pm_container._on_gsd_review = _make_gsd_review_cb(plan_review_cog)

                    logger.info("Phase 14 review gate callbacks wired")

                # ── Phase 15: PM action callbacks ─────────────────────────
                if pm_container is not None:
                    plan_review_cog_for_assign = self.get_cog("PlanReviewCog")

                    async def _on_assign_task(agent_id: str, item: Any) -> None:
                        # Write assignment to agent's own MemoryStore
                        for child in project_sup.children.values():
                            if isinstance(child, GsdAgent) and child.context.agent_id == agent_id:
                                await child.set_assignment(item.model_dump())
                                break
                        # Send GSD command to agent's tmux pane
                        if plan_review_cog_for_assign is not None:
                            gsd_cmd = "/gsd:discuss-phase 1"
                            for child in project_sup.children.values():
                                if isinstance(child, GsdAgent) and child.context.agent_id == agent_id:
                                    gsd_cmd = child.context.gsd_command or "/gsd:discuss-phase 1"
                                    break
                            await plan_review_cog_for_assign._send_tmux_command(agent_id, gsd_cmd)

                    pm_container._on_assign_task = _on_assign_task

                    async def _on_trigger_integration_review() -> None:
                        alerts_ch = self._system_channels.get("alerts")
                        if alerts_ch and self.message_queue:
                            await self.message_queue.enqueue(QueuedMessage(
                                priority=MessagePriority.SUPERVISOR,
                                timestamp=time.monotonic(),
                                channel_id=alerts_ch.id,
                                content=(
                                    f"[PM] Integration review requested for project "
                                    f"{self.project_config.project}. "
                                    "Please review agent branches for merge readiness."
                                ),
                            ))

                    pm_container._on_trigger_integration_review = _on_trigger_integration_review

                    async def _on_recruit_agent(spec: Any) -> None:
                        await project_sup.add_child_spec(spec)
                        # Wire PM event callbacks on the new agent (same as initial wiring)
                        new_child = project_sup.children.get(spec.child_id)
                        if isinstance(new_child, GsdAgent):
                            new_child._on_phase_transition = _make_gsd_cb(pm_event_sink)
                            if plan_review_cog is not None:
                                new_child._on_review_request = _make_review_cb(plan_review_cog)
                        elif isinstance(new_child, ContinuousAgent):
                            new_child._on_briefing = _make_briefing_cb(pm_event_sink)
                            new_child._request_delegation = project_sup.handle_delegation_request

                    async def _on_remove_agent(agent_id: str) -> None:
                        await project_sup.remove_child(agent_id)

                    pm_container._on_recruit_agent = _on_recruit_agent
                    pm_container._on_remove_agent = _on_remove_agent

                    # Route PM escalations through CompanyAgent container (ARCH-01)
                    # strategist_container is set from add_company_agent() above.
                    if isinstance(strategist_container, CompanyAgent):
                        async def _on_escalate_to_strategist(
                            agent_id: str, question: str, score: float
                        ) -> str | None:
                            future: asyncio.Future[str | None] = asyncio.get_event_loop().create_future()
                            await strategist_container.post_event({
                                "type": "pm_escalation",
                                "agent_id": agent_id,
                                "question": question,
                                "confidence": score,
                                "_response_future": future,
                            })
                            return await future
                        pm_container._on_escalate_to_strategist = _on_escalate_to_strategist
                    else:
                        # Fallback: route through cog (backward compat)
                        strategist_cog_ref2 = self.get_cog("StrategistCog")
                        if strategist_cog_ref2 is not None:
                            async def _on_escalate_to_strategist_fallback(
                                agent_id: str, question: str, score: float
                            ) -> str | None:
                                return await strategist_cog_ref2.handle_pm_escalation(
                                    agent_id, question, score
                                )
                            pm_container._on_escalate_to_strategist = _on_escalate_to_strategist_fallback

                    async def _on_send_intervention(agent_id: str, message: str) -> None:
                        if self.message_queue and guild:
                            agent_channel = discord.utils.get(
                                guild.text_channels, name=agent_id
                            )
                            if agent_channel:
                                await self.message_queue.enqueue(QueuedMessage(
                                    priority=MessagePriority.SUPERVISOR,
                                    timestamp=time.monotonic(),
                                    channel_id=agent_channel.id,
                                    content=f"[PM] {message}",
                                ))
                            else:
                                alerts_ch = self._system_channels.get("alerts")
                                if alerts_ch:
                                    await self.message_queue.enqueue(QueuedMessage(
                                        priority=MessagePriority.SUPERVISOR,
                                        timestamp=time.monotonic(),
                                        channel_id=alerts_ch.id,
                                        content=f"[PM] {message}",
                                    ))

                    pm_container._on_send_intervention = _on_send_intervention

                    logger.info(
                        "Phase 15 PM action callbacks wired for %s",
                        pm_container.context.agent_id,
                    )

                # PMRT-01 + PMRT-04: health_change and escalation events via supervisor callback.
                # Called LAST -- after all callbacks are wired -- to avoid race condition
                # where events arrive before handlers are set (Research Pitfall 3).
                if pm_container is not None:
                    project_sup.set_pm_event_sink(pm_event_sink)

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
        """Graceful shutdown: stop message queue, supervision tree, then close bot."""
        if self.message_queue is not None:
            await self.message_queue.stop()
        if self.company_root is not None:
            await self.company_root.stop()
        self._tmux_manager = None
        await super().close()

    @property
    def is_bot_ready(self) -> bool:
        """Check if bot has completed on_ready initialization (Pitfall 6)."""
        return self._ready_flag
