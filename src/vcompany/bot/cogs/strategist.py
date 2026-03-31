"""StrategistCog: Bridges #strategist channel to persistent Claude conversation.

Expands from placeholder to full persistent conversation manager per D-11.
Owner messages in #strategist are forwarded via RuntimeAPI.relay_strategist_message().
PM escalation supported via make_sync_callbacks().
Owner escalation posts @mention and waits indefinitely per D-07.
Uses routing framework for message filtering (D-07) with replied-to content fetch.

All conversation logic (StrategistConversation, DecisionLogger) now runs in the
daemon layer. This cog is a pure I/O adapter: Discord in, RuntimeAPI call out.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands

from vcompany.bot.routing import EntityRegistry, RouteResult, RouteTarget, route_message
from vcompany.models.messages import MessageContext

# Persistent directory for files sent to the Strategist via Discord
_STRATEGIST_FILES_DIR = Path.home() / "vco-strategist-files"

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot
    from vcompany.daemon.runtime_api import RuntimeAPI

logger = logging.getLogger(__name__)

# Discord message character limit
_DISCORD_MAX_CHARS = 2000


def _get_runtime_api(bot: VcoBot) -> RuntimeAPI | None:
    """Get RuntimeAPI from daemon if available."""
    daemon = getattr(bot, "_daemon", None)
    if daemon is None:
        return None
    return getattr(daemon, "runtime_api", None)


class StrategistCog(commands.Cog):
    """Bridges #strategist channel to persistent Claude conversation.

    Owner messages are forwarded to the Strategist via RuntimeAPI,
    responses stream back with rate-limited edits. Provides PM escalation
    pathway and indefinite-wait owner escalation per D-07.

    This cog is a pure Discord I/O adapter -- all conversation and
    decision logic lives in the daemon layer.
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._strategist_channel: discord.TextChannel | None = None
        self._decisions_channel: discord.TextChannel | None = None
        self._owner_role_name = "vco-owner"
        self._pending_escalations: dict[int, asyncio.Future] = {}

    async def initialize(
        self,
        persona_path: Path | None = None,
        decisions_path: Path | None = None,
    ) -> None:
        """Initialize channels.

        Conversation and DecisionLogger initialization now happens in the
        daemon layer (RuntimeAPI.new_project). This method only resolves
        Discord channels.

        Args:
            persona_path: Kept for backward compat signature; stored for daemon to use.
            decisions_path: Kept for backward compat signature; unused by cog.
        """
        await self._resolve_channels()
        logger.info("StrategistCog initialized (channels resolved)")

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
        """Process messages routed to the Strategist via routing framework.

        Uses route_message() for filtering (D-07). Fetches replied-to message
        content so route_message can correctly determine entity targets.

        If message is a reply to a pending escalation, resolves
        the escalation future instead of forwarding to conversation.
        """
        # Build registry for routing
        registry = EntityRegistry(
            bot_user_id=self.bot.user.id,
            entity_prefixes={"pm": "[PM]"},
            strategist_user_ids=set(),
        )

        # Fetch replied-to message content for correct routing (D-07)
        replied_to_content: str | None = None
        if message.reference is not None and getattr(message.reference, "message_id", None) is not None:
            try:
                replied_msg = await message.channel.fetch_message(
                    message.reference.message_id
                )
                replied_to_content = replied_msg.content
            except discord.NotFound:
                pass  # Message deleted; route_message handles None gracefully
            except Exception:
                logger.debug("Failed to fetch replied-to message, routing with None")

        route = route_message(
            message,
            channel_name=getattr(message.channel, "name", ""),
            registry=registry,
            replied_to_content=replied_to_content,
        )

        # D-07: Strategist only processes messages routed to it
        if route.target != RouteTarget.STRATEGIST:
            # Exception: check pending escalation replies (owner replying to escalation msg)
            if (
                message.reference is not None
                and getattr(message.reference, "message_id", None) is not None
                and message.reference.message_id in self._pending_escalations
            ):
                future = self._pending_escalations.pop(message.reference.message_id)
                if not future.done():
                    future.set_result(message.content)
            return

        # Filter: skip non-owners (but allow [system] messages from bot)
        is_system = (
            message.author.id == self.bot.user.id
            and message.content.startswith("[system]")
        )
        if not is_system and not self._has_owner_role(message.author):
            return

        # Check for pending escalation replies routed to Strategist
        if (
            message.reference is not None
            and getattr(message.reference, "message_id", None) is not None
            and message.reference.message_id in self._pending_escalations
        ):
            future = self._pending_escalations.pop(message.reference.message_id)
            if not future.done():
                future.set_result(message.content)
            return

        # Route through container's receive_discord_message (same as MentionRouter)
        runtime_api = _get_runtime_api(self.bot)

        if runtime_api is not None:
            container = await runtime_api._root._find_container("strategist")
            if container is not None:
                content = await self._build_message_with_attachments(message)
                context = MessageContext(
                    sender=message.author.display_name,
                    channel=getattr(message.channel, "name", "strategist"),
                    content=content,
                    message_id=str(message.id),
                )
                await container.receive_discord_message(context)
                return

        # No RuntimeAPI or Strategist container available
        await message.reply("Strategist not initialized yet.")

    @staticmethod
    def _has_owner_role(member: discord.Member) -> bool:
        """Check if member has the vco-owner role."""
        return any(role.name == "vco-owner" for role in getattr(member, "roles", []))

    async def _build_message_with_attachments(self, message: discord.Message) -> str:
        """Download attachments and build a message referencing their file paths.

        Files are saved to ~/vco-strategist-files/{timestamp}_{filename} so the
        Strategist can reference them later with Read tool.

        Args:
            message: Discord message potentially containing attachments.

        Returns:
            Message content with file paths appended.
        """
        content = message.content or ""

        if not message.attachments:
            return content

        _STRATEGIST_FILES_DIR.mkdir(exist_ok=True)

        file_refs = []
        for att in message.attachments:
            # Save with timestamp prefix to avoid collisions
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            safe_name = att.filename.replace(" ", "_")
            dest = _STRATEGIST_FILES_DIR / f"{ts}_{safe_name}"

            try:
                data = await att.read()
                dest.write_bytes(data)
                file_refs.append(f"[attached file: {dest}]")
                logger.info("Saved attachment: %s (%d bytes)", dest, len(data))
            except Exception:
                logger.exception("Failed to download attachment %s", att.filename)
                file_refs.append(f"[failed to download: {att.filename}]")

        if file_refs:
            content = content + "\n" + "\n".join(file_refs) if content else "\n".join(file_refs)

        return content

    async def handle_pm_escalation(
        self, agent_id: str, question: str, confidence_score: float
    ) -> str | None:
        """Handle PM escalation: forward question to Strategist via RuntimeAPI.

        Args:
            agent_id: ID of the agent asking the question.
            question: The agent's question.
            confidence_score: PM's confidence score (0.0 to 1.0).

        Returns:
            Response text if Strategist is confident, None if owner
            escalation is needed.
        """
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is not None:
            return await runtime_api.handle_pm_escalation(
                agent_id, question, confidence_score
            )
        return None

    async def post_owner_escalation(
        self,
        agent_id: str,
        question: str,
        confidence_score: float,
        channel: discord.TextChannel | None = None,
    ) -> str:
        """Post escalation and wait indefinitely for owner reply.

        Per D-07: LOW confidence escalations to the owner wait indefinitely --
        no timeout fallback for strategic decisions. Posts @Owner mention and
        creates a Future that resolves when the owner replies to the escalation
        message.

        Per D-03: Supports posting in agent channels (not just #strategist)
        via the optional channel parameter.

        Args:
            agent_id: ID of the agent needing a decision.
            question: The strategic question.
            confidence_score: Combined PM+Strategist confidence.
            channel: Target channel for escalation. Defaults to #strategist.

        Returns:
            Owner's reply text.
        """
        target_channel = channel or self._strategist_channel
        if target_channel is None:
            raise RuntimeError("No channel available for owner escalation")

        # Find the vco-owner role for @mention
        owner_role = discord.utils.get(
            target_channel.guild.roles, name=self._owner_role_name
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

        sent_msg = await target_channel.send(content=message_text)

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
            agent_id: str,
            question: str,
            confidence_score: float,
            channel: discord.TextChannel | None = None,
        ) -> asyncio.Future:
            return asyncio.run_coroutine_threadsafe(
                self.post_owner_escalation(
                    agent_id, question, confidence_score, channel=channel
                ),
                loop,
            )

        return {
            "on_pm_escalation": on_pm_escalation,
            "on_owner_escalation": on_owner_escalation,
        }



async def setup(bot: commands.Bot) -> None:
    """Load StrategistCog into the bot."""
    await bot.add_cog(StrategistCog(bot))
