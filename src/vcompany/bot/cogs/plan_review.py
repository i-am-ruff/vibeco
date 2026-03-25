"""PlanReviewCog: Placeholder for Phase 5 plan gate.

Plan detection alerts are handled by AlertsCog. This Cog will be expanded
in Phase 5 to implement the full plan gate workflow: pause agent, post plan
to #plan-review, wait for PM approval before execution proceeds.
"""

from __future__ import annotations

from discord.ext import commands

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot


class PlanReviewCog(commands.Cog):
    """Placeholder for Phase 5 plan gate. Plan detection alerts handled by AlertsCog."""

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    """Load PlanReviewCog into the bot."""
    await bot.add_cog(PlanReviewCog(bot))
