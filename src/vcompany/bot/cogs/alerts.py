"""AlertsCog: Monitors agent health and posts alerts to Discord channels.

Receives MonitorLoop and CrashTracker callbacks (sync), bridges them to
async Discord sends via run_coroutine_threadsafe (Pitfall 4). Buffers alerts
during disconnects and flushes on reconnect (D-15, DISC-12).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands

from vcompany.bot.embeds import build_alert_embed

logger = logging.getLogger("vcompany.bot.cogs.alerts")

# TYPE_CHECKING import to avoid circular import at runtime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot


class AlertsCog(commands.Cog):
    """Posts monitor and crash tracker alerts to #alerts and #plan-review.

    Buffers embeds when bot is disconnected and flushes on reconnect (D-15).
    Provides make_sync_callbacks() to bridge sync MonitorLoop/CrashTracker
    callbacks to async Discord sends via run_coroutine_threadsafe (Pitfall 4).
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._alert_buffer: list[discord.Embed] = []
        self._alerts_channel: discord.TextChannel | None = None
        self._plan_review_channel: discord.TextChannel | None = None

    async def _resolve_channels(self) -> None:
        """Find #alerts and #plan-review channels in the guild."""
        guild = self.bot.get_guild(self.bot._guild_id)
        if guild:
            for channel in guild.text_channels:
                if channel.name == "alerts":
                    self._alerts_channel = channel
                elif channel.name == "plan-review":
                    self._plan_review_channel = channel

    async def _send_or_buffer(self, embed: discord.Embed) -> None:
        """Send embed to #alerts, or buffer if bot is disconnected (D-15)."""
        if self.bot.is_closed() or not self.bot.is_bot_ready:
            self._alert_buffer.append(embed)
            return
        if self._alerts_channel:
            try:
                await self._alerts_channel.send(embed=embed)
            except Exception:
                self._alert_buffer.append(embed)
        else:
            self._alert_buffer.append(embed)

    @commands.Cog.listener()
    async def on_resumed(self) -> None:
        """Flush buffered alerts after reconnect per D-15."""
        await self._resolve_channels()
        if self._alert_buffer and self._alerts_channel:
            for embed in self._alert_buffer:
                try:
                    await self._alerts_channel.send(embed=embed)
                except Exception:
                    break  # stop flushing if we hit errors
            self._alert_buffer.clear()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Resolve channels on ready."""
        await self._resolve_channels()

    async def alert_agent_dead(self, agent_id: str) -> None:
        """Post alert for a dead agent."""
        embed = build_alert_embed(
            title="Agent Dead",
            description=f"Agent **{agent_id}** is no longer responding. Automatic relaunch will be attempted.",
            alert_type="error",
        )
        await self._send_or_buffer(embed)

    async def alert_agent_stuck(self, agent_id: str) -> None:
        """Post alert for a stuck agent."""
        embed = build_alert_embed(
            title="Agent Stuck",
            description=f"Agent **{agent_id}** has had no git commits for 30+ minutes.",
            alert_type="warning",
        )
        await self._send_or_buffer(embed)

    async def alert_circuit_open(self, agent_id: str, crash_count: int) -> None:
        """Post alert when circuit breaker opens for an agent."""
        embed = build_alert_embed(
            title="Circuit Breaker Open",
            description=f"Agent **{agent_id}** has crashed {crash_count} times in the last hour. Automatic relaunch disabled.",
            alert_type="error",
        )
        await self._send_or_buffer(embed)

    async def alert_plan_detected(self, agent_id: str, plan_path: Path) -> None:
        """Post plan detection notice to #plan-review channel."""
        embed = build_alert_embed(
            title="New Plan Detected",
            description=f"Agent **{agent_id}** created: `{plan_path.name}`",
            alert_type="info",
        )
        if self._plan_review_channel:
            try:
                await self._plan_review_channel.send(embed=embed)
                return
            except Exception:
                pass
        # Fallback: buffer if plan-review channel not available
        self._alert_buffer.append(embed)

    def make_sync_callbacks(self) -> dict:
        """Create sync callback wrappers for MonitorLoop and CrashTracker.

        Returns dict with keys: on_agent_dead, on_agent_stuck, on_plan_detected,
        on_circuit_open. Each is a sync callable that schedules the async alert
        method via run_coroutine_threadsafe (Pitfall 4).
        """
        loop = self.bot.loop

        def on_agent_dead(agent_id: str) -> None:
            asyncio.run_coroutine_threadsafe(self.alert_agent_dead(agent_id), loop)

        def on_agent_stuck(agent_id: str) -> None:
            asyncio.run_coroutine_threadsafe(self.alert_agent_stuck(agent_id), loop)

        def on_plan_detected(agent_id: str, plan_path: Path) -> None:
            asyncio.run_coroutine_threadsafe(
                self.alert_plan_detected(agent_id, plan_path), loop
            )

        def on_circuit_open(agent_id: str, crash_count: int) -> None:
            asyncio.run_coroutine_threadsafe(
                self.alert_circuit_open(agent_id, crash_count), loop
            )

        return {
            "on_agent_dead": on_agent_dead,
            "on_agent_stuck": on_agent_stuck,
            "on_plan_detected": on_plan_detected,
            "on_circuit_open": on_circuit_open,
        }


async def setup(bot: commands.Bot) -> None:
    """Load AlertsCog into the bot."""
    await bot.add_cog(AlertsCog(bot))
