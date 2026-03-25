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

logger = logging.getLogger("vcompany.bot.client")

# Cog extension paths loaded in setup_hook (D-12)
_COG_EXTENSIONS: list[str] = [
    "vcompany.bot.cogs.commands",
    "vcompany.bot.cogs.alerts",
    "vcompany.bot.cogs.plan_review",
    "vcompany.bot.cogs.strategist",
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
        """First-time initialization: create vco-owner role if missing (D-10).

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

        self._initialized = True
        self._ready_flag = True
        logger.info("VcoBot ready in guild %s", guild.name)

    @property
    def is_bot_ready(self) -> bool:
        """Check if bot has completed on_ready initialization (Pitfall 6)."""
        return self._ready_flag
