"""StrategistCog: Placeholder for Phase 6 PM/Strategist.

Will handle AI-powered question answering and plan review. Uses the Anthropic
SDK to provide context-aware responses to agent questions and review plans
against milestone scope with confidence scoring.
"""

from __future__ import annotations

from discord.ext import commands

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot


class StrategistCog(commands.Cog):
    """Placeholder for Phase 6 PM/Strategist. Will handle AI-powered question answering and plan review."""

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    """Load StrategistCog into the bot."""
    await bot.add_cog(StrategistCog(bot))
