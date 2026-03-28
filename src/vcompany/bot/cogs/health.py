"""HealthCog: /health slash command and state-change notification delivery.

Implements HLTH-03 (health tree rendering in Discord) and HLTH-04
(notification delivery to Discord alerts channel on significant transitions).
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
    from vcompany.container.health import HealthReport

logger = logging.getLogger("vcompany.bot.cogs.health")


class HealthCog(commands.Cog):
    """Health tree rendering and state-change notifications.

    Provides the /health slash command to display the supervision tree
    as a color-coded Discord embed, and a _notify_state_change method
    that pushes significant transitions to the #alerts channel.
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

        company_root = getattr(self.bot, "company_root", None)
        if company_root is None:
            await interaction.followup.send(
                "No supervision tree active.", ephemeral=True
            )
            return

        tree = company_root.health_tree()
        embed = build_health_tree_embed(
            tree, project_filter=project, agent_filter=agent_id
        )
        await interaction.followup.send(embed=embed)

    async def _notify_state_change(self, report: HealthReport) -> None:
        """Push significant state transitions to #alerts channel (HLTH-04).

        Only notifies on errored, running, and stopped transitions.
        Wraps in try/except to prevent notification failures from
        breaking the callback chain.

        Args:
            report: HealthReport from the container that changed state.
        """
        try:
            if report.state not in ("errored", "running", "stopped"):
                return

            # Find the alerts channel in the first guild
            if not self.bot.guilds:
                return

            guild = self.bot.guilds[0]
            alerts_channel = discord.utils.get(guild.text_channels, name="alerts")
            if alerts_channel is None:
                return

            emoji = STATE_INDICATORS.get(report.state, "")
            inner = f" ({report.inner_state})" if report.inner_state else ""
            msg = f"{emoji} **{report.agent_id}** -> {report.state}{inner}"
            await alerts_channel.send(msg)
        except Exception:
            logger.exception(
                "Failed to send state-change notification for %s",
                report.agent_id,
            )



async def setup(bot: commands.Bot) -> None:
    """Module-level setup function for discord.py Cog loading."""
    cog = HealthCog(bot)
    await bot.add_cog(cog)
