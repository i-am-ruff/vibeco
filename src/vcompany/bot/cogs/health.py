"""HealthCog: /health slash command and state-change notification delivery.

Implements HLTH-03 (health tree rendering in Discord) and HLTH-04
(notification delivery to Discord alerts channel on significant transitions).

Pure I/O adapter: uses RuntimeAPI.health_tree() for data, formats as Discord embed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from vcompany.bot.embeds import STATE_INDICATORS, build_health_tree_embed
from vcompany.bot.permissions import is_owner_app_check

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot
    from vcompany.daemon.runtime_api import RuntimeAPI

logger = logging.getLogger("vcompany.bot.cogs.health")


def _get_runtime_api(bot: VcoBot) -> RuntimeAPI | None:
    """Get RuntimeAPI from daemon if available."""
    daemon = getattr(bot, "_daemon", None)
    if daemon is None:
        return None
    return getattr(daemon, "runtime_api", None)


class HealthCog(commands.Cog):
    """Health tree rendering and state-change notifications.

    Provides the /health slash command to display the supervision tree
    as a color-coded Discord embed via RuntimeAPI.health_tree().

    Pure Discord I/O adapter -- all health data comes from the daemon.
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot: VcoBot = bot

    @app_commands.command(name="health", description="Show supervision tree health")
    @app_commands.describe(
        project="Filter by project supervisor ID",
        agent_id="Filter by agent ID",
    )
    @is_owner_app_check()
    async def health(
        self,
        interaction: discord.Interaction,
        project: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        """Show the supervision health tree as a Discord embed (HLTH-03).

        Optionally filter by project or agent_id.
        """
        await interaction.response.defer()

        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is None:
            await interaction.followup.send(
                "No supervision tree active.", ephemeral=True
            )
            return

        from vcompany.container.health import CompanyHealthTree

        tree_data = await runtime_api.health_tree()
        tree = CompanyHealthTree(**tree_data)
        embed = build_health_tree_embed(
            tree, project_filter=project, agent_filter=agent_id
        )
        await interaction.followup.send(embed=embed)

    async def _notify_state_change(self, report: dict) -> None:
        """Push significant state transitions to #alerts channel (HLTH-04).

        Only notifies on errored, running, and stopped transitions.
        Wraps in try/except to prevent notification failures from
        breaking the callback chain.

        Args:
            report: Dict with state, agent_id, inner_state, blocked_reason fields.
        """
        try:
            state = report.get("state", "")
            if state not in ("errored", "running", "stopped", "blocked", "stopping"):
                return

            # Find the alerts channel in the first guild
            if not self.bot.guilds:
                return

            guild = self.bot.guilds[0]
            alerts_channel = discord.utils.get(guild.text_channels, name="alerts")
            if alerts_channel is None:
                return

            agent_id = report.get("agent_id", "unknown")
            inner_state = report.get("inner_state", "")
            blocked_reason = report.get("blocked_reason", "")

            emoji = STATE_INDICATORS.get(state, "")
            inner = f" ({inner_state})" if inner_state else ""
            blocked = f" -- {blocked_reason}" if blocked_reason else ""
            msg = f"{emoji} **{agent_id}** -> {state}{inner}{blocked}"
            await alerts_channel.send(msg)
        except Exception:
            logger.exception(
                "Failed to send state-change notification for %s",
                report.get("agent_id", "unknown"),
            )



async def setup(bot: commands.Bot) -> None:
    """Module-level setup function for discord.py Cog loading."""
    cog = HealthCog(bot)
    await bot.add_cog(cog)
