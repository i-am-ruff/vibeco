"""StrategistCog: Bridges #strategist channel to persistent Claude conversation.

Expands from placeholder to full persistent conversation manager per D-11.
Owner messages in #strategist are forwarded to StrategistConversation.
Responses stream back with rate-limited edits (1/sec) per Pitfall 1.
PM escalation supported via make_sync_callbacks().
Owner escalation posts @mention and waits indefinitely per D-07.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import discord
from discord.ext import commands

from vcompany.strategist.conversation import StrategistConversation
from vcompany.strategist.decision_log import DecisionLogger

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic
    from vcompany.bot.client import VcoBot

logger = logging.getLogger(__name__)

# Discord message character limit
_DISCORD_MAX_CHARS = 2000

# Minimum interval between message edits (rate limiting per Pitfall 1)
_EDIT_INTERVAL_SECS = 1.0


class StrategistCog(commands.Cog):
    """Bridges #strategist channel to persistent Claude conversation.

    Owner messages are forwarded to the Strategist, responses stream back
    with rate-limited edits. Provides PM escalation pathway and indefinite-
    wait owner escalation per D-07.
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._conversation: StrategistConversation | None = None
        self._strategist_channel: discord.TextChannel | None = None
        self._decisions_channel: discord.TextChannel | None = None
        self._decision_logger: DecisionLogger | None = None
        self._owner_role_name = "vco-owner"
        self._pending_escalations: dict[int, asyncio.Future] = {}

    async def initialize(
        self,
        client: AsyncAnthropic,
        persona_path: Path | None,
        decisions_path: Path,
    ) -> None:
        """Initialize the Strategist conversation and decision logger.

        Args:
            client: AsyncAnthropic client for Claude API calls.
            persona_path: Path to STRATEGIST-PERSONA.md, or None for default.
            decisions_path: Path to state/decisions.jsonl file.
        """
        self._conversation = StrategistConversation(client, persona_path)
        await self._resolve_channels()
        self._decision_logger = DecisionLogger(
            decisions_path=decisions_path,
            decisions_channel=self._decisions_channel,
        )
        logger.info("StrategistCog initialized with persistent conversation")

    async def _resolve_channels(self) -> None:
        """Find #strategist and #decisions channels in the guild."""
        guild = self.bot.get_guild(self.bot._guild_id)
        if guild:
            for channel in guild.text_channels:
                if channel.name == "strategist":
                    self._strategist_channel = channel
                elif channel.name == "decisions":
                    self._decisions_channel = channel

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Resolve channels on ready."""
        await self._resolve_channels()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Process messages in #strategist from the owner.

        Filters per Research Open Question 4:
        - Skip webhook messages
        - Skip bot's own messages
        - Skip messages from non-strategist channels
        - Skip messages from users without vco-owner role

        If message is a reply to a pending escalation, resolves
        the escalation future instead of forwarding to conversation.
        """
        # Filter: skip webhooks
        if message.webhook_id is not None:
            return

        # Filter: skip bot's own messages
        if message.author.id == self.bot.user.id:
            return

        # Filter: skip non-strategist channels
        if (
            self._strategist_channel is None
            or message.channel.id != self._strategist_channel.id
        ):
            # Fall back to channel name comparison for cases where
            # _strategist_channel is set but IDs differ (e.g., test mocks)
            if not (
                self._strategist_channel is not None
                and message.channel is self._strategist_channel
            ):
                return

        # Filter: skip non-owners
        if not self._has_owner_role(message.author):
            return

        # Check for pending escalation replies first (D-07)
        if (
            message.reference is not None
            and message.reference.message_id in self._pending_escalations
        ):
            future = self._pending_escalations.pop(message.reference.message_id)
            if not future.done():
                future.set_result(message.content)
            return

        # Check if conversation is initialized
        if self._conversation is None:
            await message.reply("Strategist not initialized yet. Please wait for bot startup to complete.")
            return

        # Forward to conversation and stream response
        await self._stream_to_channel(message.channel, message.content)

    @staticmethod
    def _has_owner_role(member: discord.Member) -> bool:
        """Check if member has the vco-owner role."""
        return any(role.name == "vco-owner" for role in getattr(member, "roles", []))

    async def _stream_to_channel(
        self, channel: discord.TextChannel, content: str
    ) -> str:
        """Stream conversation response to channel with rate-limited edits.

        Sends a "Thinking..." placeholder, then edits it as chunks arrive.
        Edits are rate-limited to 1/sec per Pitfall 1. Long responses (>2000
        chars) are truncated in the main message with overflow sent as follow-up.

        Args:
            channel: Discord channel to send response to.
            content: User message content to send to conversation.

        Returns:
            Full response text (not truncated).
        """
        placeholder = await channel.send("Thinking...")
        buffer = ""
        last_edit = time.monotonic()

        async for chunk in self._conversation.send(content):
            buffer += chunk
            now = time.monotonic()
            if now - last_edit >= _EDIT_INTERVAL_SECS:
                display = buffer[:_DISCORD_MAX_CHARS]
                await placeholder.edit(content=display)
                last_edit = now

        # Final edit with complete (truncated if needed) response
        if len(buffer) > _DISCORD_MAX_CHARS:
            await placeholder.edit(content=buffer[:_DISCORD_MAX_CHARS - 3] + "...")
            # Send overflow as follow-up messages
            remaining = buffer[_DISCORD_MAX_CHARS - 3:]
            while remaining:
                chunk = remaining[:_DISCORD_MAX_CHARS]
                await channel.send(chunk)
                remaining = remaining[_DISCORD_MAX_CHARS:]
        else:
            await placeholder.edit(content=buffer)

        return buffer

    async def handle_pm_escalation(
        self, agent_id: str, question: str, confidence_score: float
    ) -> str | None:
        """Handle PM escalation: forward question to Strategist conversation.

        Formats the question as a PM escalation and sends to the persistent
        conversation. Collects the full response (does not stream to channel
        for escalations -- they are internal).

        Args:
            agent_id: ID of the agent asking the question.
            question: The agent's question.
            confidence_score: PM's confidence score (0.0 to 1.0).

        Returns:
            Response text if Strategist is confident, None if owner
            escalation is needed.
        """
        if self._conversation is None:
            return None

        formatted = (
            f"[PM Escalation] Agent {agent_id} asks: {question}\n"
            f"PM confidence: {confidence_score:.0%}. Please provide your assessment."
        )

        full_response = ""
        async for chunk in self._conversation.send(formatted):
            full_response += chunk

        # Check if Strategist indicates low confidence
        low_confidence_signals = [
            "i'm not sure",
            "escalate to owner",
            "owner should decide",
            "not confident",
            "cannot determine",
        ]
        if any(signal in full_response.lower() for signal in low_confidence_signals):
            return None

        return full_response

    async def post_owner_escalation(
        self, agent_id: str, question: str, confidence_score: float
    ) -> str:
        """Post escalation to #strategist and wait indefinitely for owner reply.

        Per D-07: LOW confidence escalations to the owner wait indefinitely --
        no timeout fallback for strategic decisions. Posts @Owner mention in
        #strategist and creates a Future that resolves when the owner replies
        to the escalation message.

        Args:
            agent_id: ID of the agent needing a decision.
            question: The strategic question.
            confidence_score: Combined PM+Strategist confidence.

        Returns:
            Owner's reply text.
        """
        if self._strategist_channel is None:
            raise RuntimeError("Strategist channel not available for owner escalation")

        # Find the vco-owner role for @mention
        owner_role = discord.utils.get(
            self._strategist_channel.guild.roles, name=self._owner_role_name
        )
        mention = owner_role.mention if owner_role else "@Owner"

        message_text = (
            f"{mention} -- Strategic decision needed\n\n"
            f"**Agent:** {agent_id}\n"
            f"**Question:** {question}\n"
            f"**PM confidence:** {confidence_score:.0%}\n"
            f"**Both PM and Strategist could not answer with confidence.**\n\n"
            f"Please reply to this message with your decision."
        )

        sent_msg = await self._strategist_channel.send(content=message_text)

        # Create future and register for resolution by on_message
        future: asyncio.Future[str] = self.bot.loop.create_future()
        self._pending_escalations[sent_msg.id] = future

        # Wait indefinitely per D-07 -- no asyncio.wait_for timeout wrapper
        owner_answer: str = await future
        return owner_answer

    def make_sync_callbacks(self) -> dict:
        """Create sync callback wrappers for PM escalation from sync context.

        Follows AlertsCog pattern: uses run_coroutine_threadsafe to bridge
        sync callers (like PM tier running in a thread) to async methods.

        Returns:
            Dict with keys: on_pm_escalation, on_owner_escalation.
        """
        loop = self.bot.loop

        def on_pm_escalation(
            agent_id: str, question: str, confidence_score: float
        ) -> asyncio.Future:
            return asyncio.run_coroutine_threadsafe(
                self.handle_pm_escalation(agent_id, question, confidence_score),
                loop,
            )

        def on_owner_escalation(
            agent_id: str, question: str, confidence_score: float
        ) -> asyncio.Future:
            return asyncio.run_coroutine_threadsafe(
                self.post_owner_escalation(agent_id, question, confidence_score),
                loop,
            )

        return {
            "on_pm_escalation": on_pm_escalation,
            "on_owner_escalation": on_owner_escalation,
        }

    @property
    def decision_logger(self) -> DecisionLogger | None:
        """Expose DecisionLogger for other cogs."""
        return self._decision_logger


async def setup(bot: commands.Bot) -> None:
    """Load StrategistCog into the bot."""
    await bot.add_cog(StrategistCog(bot))
