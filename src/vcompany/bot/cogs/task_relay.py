"""ChannelRelayCog -- unified message relay from Discord channels to agent tmux panes.

Handles both ``#agent-*`` and ``#task-*`` channels. When a non-bot user
posts in these channels, the message text is forwarded to the corresponding
agent's tmux pane via RuntimeAPI.relay_channel_message().

For ``#agent-*`` channels, only owner messages (vco-owner role) that don't
contain ``@PM`` are relayed -- PM-specific traffic is handled by PlanReviewCog.
For ``#task-*`` channels, all non-bot messages are relayed.

Pure I/O adapter: routes Discord messages to daemon via RuntimeAPI.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot
    from vcompany.daemon.runtime_api import RuntimeAPI

logger = logging.getLogger("vcompany.bot.cogs.channel_relay")


def _get_runtime_api(bot: VcoBot) -> RuntimeAPI | None:
    """Get RuntimeAPI from daemon if available."""
    daemon = getattr(bot, "_daemon", None)
    if daemon is None:
        return None
    return getattr(daemon, "runtime_api", None)


class ChannelRelayCog(commands.Cog):
    """Relay Discord channel messages to agent tmux panes via RuntimeAPI."""

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot

    async def _relay_to_pane(self, agent_id: str, content: str) -> bool:
        """Send message text to an agent's tmux pane via RuntimeAPI."""
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is None:
            logger.debug("No RuntimeAPI available for relay to %s", agent_id)
            return False

        sent = await runtime_api.relay_channel_message(agent_id, content)
        if sent:
            logger.info("Relayed message to %s: %s", agent_id, content[:80])
        else:
            logger.warning("Failed to relay message to %s", agent_id)
        return sent

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Watch agent/task channels and relay messages to tmux panes."""
        if not hasattr(message.channel, "name"):
            return

        channel_name = message.channel.name

        # Skip bot messages
        if message.author.bot:
            return

        content = message.content.strip()
        if not content:
            return

        # --- Task channels: relay all non-bot messages ---
        if channel_name.startswith("task-"):
            task_id = channel_name.removeprefix("task-")
            await self._relay_to_pane(task_id, content)
            return

        # --- Agent channels: relay owner messages (skip @PM traffic) ---
        if channel_name.startswith("agent-"):
            # Don't relay @PM mentions -- PlanReviewCog handles those
            if "@PM" in content:
                return

            # Only relay from users with vco-owner role
            if isinstance(message.author, discord.Member):
                owner_role = discord.utils.get(message.author.roles, name="vco-owner")
                if owner_role is None:
                    return

            agent_id = channel_name.removeprefix("agent-")
            await self._relay_to_pane(agent_id, content)
            return


async def setup(bot: commands.Bot) -> None:
    """Load ChannelRelayCog into the bot."""
    await bot.add_cog(ChannelRelayCog(bot))
