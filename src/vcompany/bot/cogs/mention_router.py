"""MentionRouterCog: Unified message routing for all agent types.

Two routing modes:
- **Channel-based**: All messages in an agent's primary channel go to that agent
  (no @mention needed — if you're in #strategist, you're talking to the Strategist)
- **@mention-based**: Messages in any channel containing @Handle go to that agent

Design decisions:
- D-01: Discord is the ONLY interaction channel for inter-agent communication
- D-02: All agent communication surfaces through Discord channels
- D-04: No agent-type-specific routing -- all agents receive the same MessageContext

Completely generic: register_agent(handle, container, channel_id) maps a handle
to any AgentContainer subclass. No isinstance checks, no agent-type conditionals.
No separate cogs per agent type.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from vcompany.models.messages import MessageContext

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot
    from vcompany.container.container import AgentContainer

logger = logging.getLogger(__name__)

# Shared directory for files attached to Discord messages
_ATTACHMENT_DIR = Path.home() / "vco-attachments"


class MentionRouterCog(commands.Cog):
    """Unified message router: channel-based + @mention-based delivery.

    Maintains a registry of handle -> container mappings and
    channel_id -> handle reverse lookups. Messages are delivered via
    container.receive_discord_message(context).
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._agent_handles: dict[str, AgentContainer] = {}
        self._handle_channels: dict[str, str] = {}  # handle -> channel_id
        self._channel_handles: dict[str, str] = {}  # channel_id -> handle (reverse)

    def register_agent(
        self,
        handle: str,
        container: AgentContainer,
        channel_id: str | None = None,
    ) -> None:
        """Register an agent handle for message routing.

        Args:
            handle: Text handle (e.g. "Strategist", "agent-sprint-dev").
            container: AgentContainer to deliver messages to.
            channel_id: Primary channel ID — all messages in this channel
                route to this agent without needing @mention.
        """
        self._agent_handles[handle] = container
        if channel_id is not None:
            self._handle_channels[handle] = channel_id
            self._channel_handles[channel_id] = handle
            # D-05: Store channel_id on container for outbound messages
            container._channel_id = channel_id
        logger.info(
            "Registered agent handle @%s -> %s (channel=%s)",
            handle,
            container.context.agent_id,
            channel_id or "none",
        )

    def unregister_agent(self, handle: str) -> None:
        """Remove an agent handle from the routing registry."""
        channel_id = self._handle_channels.pop(handle, None)
        if channel_id:
            self._channel_handles.pop(channel_id, None)
        container = self._agent_handles.pop(handle, None)
        if container is not None and channel_id is not None:
            container._channel_id = None
        logger.info("Unregistered agent handle @%s", handle)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Route messages to agents via channel ownership or @mention.

        Priority:
        1. If message is in an agent's primary channel → deliver to that agent
        2. If message contains @Handle text → deliver to matching agent(s)
        """
        if message.author.bot:
            return
        if self.bot.user and message.author.id == self.bot.user.id:
            return
        if not self._agent_handles:
            return

        channel_id = str(message.channel.id)

        # Channel-based routing: message is in an agent's own channel
        handle = self._channel_handles.get(channel_id)
        if handle is not None:
            await self._deliver_to_agent(handle, message)
            return

        # @mention-based routing: scan for @Handle patterns
        content = message.content
        for h in self._agent_handles:
            if f"@{h}" in content:
                await self._deliver_to_agent(h, message)

    async def _build_content_with_attachments(self, message: discord.Message) -> str:
        """Download attachments and append file paths to message content.

        Files saved to ~/vco-attachments/{timestamp}_{filename} so agents
        can reference them via Read tool. Works for all agent types.
        """
        content = message.content or ""
        if not message.attachments:
            return content

        _ATTACHMENT_DIR.mkdir(exist_ok=True)
        file_refs = []
        for att in message.attachments:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            safe_name = att.filename.replace(" ", "_")
            dest = _ATTACHMENT_DIR / f"{ts}_{safe_name}"
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

    async def _deliver_to_agent(
        self, handle: str, message: discord.Message
    ) -> None:
        """Build MessageContext and deliver to the agent container.

        Downloads attachments to local files and fetches reply parent
        content if the message is a reply (D-15: immediate parent only).
        """
        try:
            container = self._agent_handles.get(handle)
            if container is None:
                return

            content = await self._build_content_with_attachments(message)

            context = MessageContext(
                sender=message.author.display_name,
                channel=getattr(message.channel, "name", "unknown"),
                channel_id=str(message.channel.id),
                content=content,
                message_id=str(message.id),
            )

            # Fetch reply parent content (D-15)
            if (
                message.reference is not None
                and message.reference.message_id is not None
            ):
                try:
                    parent = await message.channel.fetch_message(
                        message.reference.message_id
                    )
                    context = context.model_copy(
                        update={
                            "parent_message": parent.content,
                            "is_reply": True,
                        }
                    )
                except discord.NotFound:
                    context = context.model_copy(
                        update={
                            "parent_message": None,
                            "is_reply": True,
                        }
                    )

            await container.receive_discord_message(context)

        except Exception:
            logger.exception(
                "Failed to deliver message to agent @%s", handle
            )


async def setup(bot: VcoBot) -> None:
    """Load MentionRouterCog into the bot."""
    await bot.add_cog(MentionRouterCog(bot))
