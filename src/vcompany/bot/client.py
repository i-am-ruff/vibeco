"""VcoBot: Discord bot client for vCompany orchestration.

Subclasses commands.Bot to provide Cog loading, vco-owner role creation,
and CommunicationPort registration with the daemon.

The bot is a thin Discord adapter. All business logic (CompanyRoot,
supervision tree, PM wiring) lives in the daemon via RuntimeAPI.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

import discord
from discord.ext import commands

from vcompany.bot.comm_adapter import DiscordCommunicationPort
from vcompany.daemon.comm import SendMessagePayload

if TYPE_CHECKING:
    from vcompany.models.config import ProjectConfig

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
    "vcompany.bot.cogs.task_relay",
]


class VcoBot(commands.Bot):
    """Discord bot for vCompany project orchestration.

    All commands are slash commands (no prefix commands). Loads Cogs via
    setup_hook. Creates vco-owner role on first on_ready.

    The bot is a thin Discord adapter -- all business logic is owned by
    the daemon and accessed through RuntimeAPI.
    """

    def __init__(
        self,
        guild_id: int,
        project_dir: Path | None = None,
        config: ProjectConfig | None = None,
        daemon: object | None = None,
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # privileged intent required for Strategist on_message
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)

        self.project_dir: Path | None = Path(project_dir) if project_dir else None
        self.project_config: ProjectConfig | None = config

        # Guild ID as explicit constructor arg (D-21, D-22: single guild bot)
        self._guild_id: int = guild_id

        # Alert buffer for messages during disconnect (D-15)
        self._alert_buffer: list[str] = []

        # Pitfall 7 guard: on_ready fires on every reconnect, only init once
        self._initialized: bool = False

        # Pitfall 6 guard: cogs can check if bot is ready before operating
        self._ready_flag: bool = False

        # Daemon reference for CommunicationPort registration (COMM-03)
        self._daemon = daemon
        self._comm_registered: bool = False

        # System channels populated during on_ready
        self._system_channels: dict[str, Any] = {}

        # Strategist persona path -- stored for daemon to use during project init
        self._strategist_persona_path: Path | None = None

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
        """Discord-only initialization: role, channels, CommunicationPort registration.

        All business logic (CompanyRoot, supervision tree, PM wiring) is now
        handled by the daemon via RuntimeAPI. This method only does Discord
        setup and signals the daemon that Discord is ready.
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

        # -- Discord-only concerns --

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

        # Initialize Strategist cog channels (always available)
        try:
            from vcompany.bot.config import BotConfig
            bot_config = BotConfig()
            strategist_cog = self.get_cog("StrategistCog")
            if strategist_cog:
                self._strategist_persona_path = (
                    Path(bot_config.strategist_persona_path)
                    if bot_config.strategist_persona_path
                    else None
                )
                decisions_path = (
                    self.project_dir / "state" / "decisions.jsonl"
                    if self.project_dir
                    else None
                )
                await strategist_cog.initialize(self._strategist_persona_path, decisions_path)
            logger.info("Strategist channels initialized")
        except Exception:
            logger.exception("Failed to initialize Strategist channels")

        # Initialize WorkflowMaster (always available)
        try:
            wm_cog = self.get_cog("WorkflowMasterCog")
            if wm_cog:
                worktree_path = Path.home() / "vco-workflow-master-worktree"
                await wm_cog.initialize(persona_path=None, worktree_path=worktree_path)
            logger.info("WorkflowMasterCog initialized")
        except Exception:
            logger.exception("Failed to initialize WorkflowMasterCog")

        # -- Register CommunicationPort with daemon --
        if self._daemon is not None and not self._comm_registered:
            adapter = DiscordCommunicationPort(bot=self)
            self._daemon.set_comm_port(adapter)
            self._comm_registered = True
            logger.info("CommunicationPort registered with daemon")

        # -- Register channel IDs with daemon RuntimeAPI --
        if self._daemon is not None and self._daemon.runtime_api is not None:
            channel_map = {
                name: str(ch.id)
                for name, ch in self._system_channels.items()
            }
            self._daemon.runtime_api.register_channels(channel_map)
            logger.info("Channel IDs registered with RuntimeAPI: %s", list(channel_map.keys()))

        self._initialized = True
        self._ready_flag = True
        logger.info("VcoBot ready in guild %s", guild.name)

        # Signal daemon that bot is ready (daemon will init CompanyRoot)
        if self._daemon is not None and hasattr(self._daemon, '_bot_ready_event'):
            self._daemon._bot_ready_event.set()

    def _detect_active_project(self) -> tuple[Path, object] | None:
        """Scan ~/vco-projects/ for the most recently active project.

        Delegates to RuntimeAPI.detect_active_project() if available,
        otherwise returns None.
        """
        if self._daemon is not None and hasattr(self._daemon, 'runtime_api') and self._daemon.runtime_api is not None:
            return self._daemon.runtime_api.detect_active_project()
        return None

    async def _send_boot_notifications(self, guild: discord.Guild) -> None:
        """Send boot notifications through CommunicationPort if available."""
        restart_signal = Path.home() / ".vco-restart-requested"
        is_restart = restart_signal.exists()
        if is_restart:
            restart_signal.unlink(missing_ok=True)

        if self._daemon is not None and self._daemon.runtime_api is not None:
            api = self._daemon.runtime_api
            alerts_id = api.get_channel_id("alerts")
            if alerts_id:
                owner_role = discord.utils.get(guild.roles, name="vco-owner")
                mention = owner_role.mention if owner_role else "@owner"
                msg = (
                    f"{mention} vCompany restarted successfully. All systems online."
                    if is_restart
                    else f"{mention} vCompany is online."
                )
                await self._daemon.comm_port.send_message(
                    SendMessagePayload(channel_id=alerts_id, content=msg)
                )
            strategist_id = api.get_channel_id("strategist")
            if strategist_id:
                msg = (
                    "[system] `vco restart` complete - vCompany is back online."
                    if is_restart
                    else "[system] `vco up` - vCompany is online."
                )
                await self._daemon.comm_port.send_message(
                    SendMessagePayload(channel_id=strategist_id, content=msg)
                )
        else:
            # Fallback: send directly via Discord channels (no daemon available)
            try:
                alerts_channel = self._system_channels.get("alerts")
                if alerts_channel:
                    owner_role = discord.utils.get(guild.roles, name="vco-owner")
                    mention = owner_role.mention if owner_role else "@owner"
                    if is_restart:
                        await alerts_channel.send(
                            f"{mention} vCompany restarted successfully. All systems online."
                        )
                    else:
                        await alerts_channel.send(f"{mention} vCompany is online.")
                strategist_channel = self._system_channels.get("strategist")
                if strategist_channel:
                    if is_restart:
                        await strategist_channel.send(
                            "[system] `vco restart` complete - vCompany is back online."
                        )
                    else:
                        await strategist_channel.send("[system] `vco up` - vCompany is online.")
            except Exception:
                logger.exception("Failed to send boot notifications")

    async def close(self) -> None:
        """Graceful shutdown: close bot connection."""
        await super().close()

    @property
    def is_bot_ready(self) -> bool:
        """Check if bot has completed on_ready initialization (Pitfall 6)."""
        return self._ready_flag
