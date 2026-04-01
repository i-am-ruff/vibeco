"""MentionRouterCog: Unified message routing for all agent types.

Two routing modes:
- **Channel-based**: All messages in an agent's primary channel go to that agent
  (no @mention needed -- if you're in #strategist, you're talking to the Strategist)
- **@mention-based**: Messages in any channel containing @Handle go to that agent

Design decisions:
- D-01: Discord is the ONLY interaction channel for inter-agent communication
- D-02: All agent communication surfaces through Discord channels
- D-04: No agent-type-specific routing -- all agents receive the same InboundMessage

All agents are routed via AgentHandle + InboundMessage through transport channel.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from vcompany.transport.channel.messages import InboundMessage

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot
    from vcompany.daemon.agent_handle import AgentHandle

logger = logging.getLogger(__name__)

# Shared directory for files attached to Discord messages
_ATTACHMENT_DIR = Path.home() / "vco-attachments"


class MentionRouterCog(commands.Cog):
    """Unified message router: channel-based + @mention-based delivery.

    Maintains a registry of handle -> agent mappings and channel_id -> handle
    reverse lookups. Messages are delivered via InboundMessage through
    transport channel (AgentHandle.send()).
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._agent_handles: dict[str, Any] = {}
        self._handle_channels: dict[str, str] = {}  # handle -> channel_id
        self._channel_handles: dict[str, str] = {}  # channel_id -> handle (reverse)

    def register_agent(
        self,
        handle: str,
        agent: Any,
        channel_id: str | None = None,
    ) -> None:
        """Register an agent for message routing.

        Args:
            handle: Text handle (e.g. "Strategist", "agent-sprint-dev").
            agent: Agent object that supports send() for InboundMessage delivery.
            channel_id: Primary channel ID -- all messages in this channel
                route to this agent without needing @mention.
        """
        self._agent_handles[handle] = agent
        if channel_id is not None:
            self._handle_channels[handle] = channel_id
            self._channel_handles[channel_id] = handle
        agent_id = getattr(agent, "agent_id", str(agent))
        logger.info(
            "Registered agent handle @%s -> %s (channel=%s)",
            handle,
            agent_id,
            channel_id or "none",
        )

    def register_agent_handle(
        self,
        handle_name: str,
        agent_handle: AgentHandle,
        channel_id: str | None = None,
    ) -> None:
        """Register an AgentHandle for message routing (Phase 31+).

        Args:
            handle_name: Text handle (e.g. "agent-sprint-dev").
            agent_handle: AgentHandle to deliver messages to via InboundMessage.
            channel_id: Primary channel ID -- all messages in this channel
                route to this agent without needing @mention.
        """
        self._agent_handles[handle_name] = agent_handle
        if channel_id is not None:
            self._handle_channels[handle_name] = channel_id
            self._channel_handles[channel_id] = handle_name
        logger.info(
            "Registered agent handle @%s -> %s (channel=%s)",
            handle_name,
            agent_handle.agent_id,
            channel_id or "none",
        )

    def unregister_agent(self, handle: str) -> None:
        """Remove an agent handle from the routing registry."""
        channel_id = self._handle_channels.pop(handle, None)
        if channel_id:
            self._channel_handles.pop(channel_id, None)
        agent = self._agent_handles.pop(handle, None)
        if agent is not None and channel_id is not None and hasattr(agent, '_channel_id'):
            agent._channel_id = None
        logger.info("Unregistered agent handle @%s", handle)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Route messages to agents via channel ownership or @mention.

        Priority:
        1. If message is in an agent's primary channel → deliver to that agent
        2. If message contains @Handle text → deliver to matching agent(s)
        """
        if message.author.bot and not (self.bot.user and message.author.id == self.bot.user.id):
            return  # Ignore other bots, but process our own bot's messages (agent reports)
        if not self._agent_handles:
            logger.debug("No agent handles registered, skipping message")
            return

        is_own_bot = self.bot.user and message.author.id == self.bot.user.id
        channel_id = str(message.channel.id)
        logger.debug(
            "on_message: channel=%s is_bot=%s handles=%s channel_handles=%s",
            channel_id, is_own_bot, list(self._agent_handles.keys()), dict(self._channel_handles),
        )

        # Channel-based routing: message is in an agent's own channel
        # Skip for bot messages — prevents agents receiving their own output
        if not is_own_bot:
            handle = self._channel_handles.get(channel_id)
            if handle is not None:
                logger.info("Channel-routing message to @%s from %s", handle, message.author.display_name)
                await self._deliver_to_agent(handle, message)
                return

        # @mention-based routing: scan for @Handle patterns
        # Works for both human messages and agent reports (bot messages)
        content = message.content
        source_handle = self._channel_handles.get(channel_id)
        for h in self._agent_handles:
            if h == source_handle:
                continue  # Don't route back to the agent whose channel this is
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
        """Deliver a Discord message to the agent registered under *handle*.

        Sends InboundMessage through transport channel via agent.send().
        Downloads attachments to local files before delivery.
        """
        try:
            agent = self._agent_handles.get(handle)
            if agent is None:
                return

            content = await self._build_content_with_attachments(message)

            inbound = InboundMessage(
                sender=message.author.display_name,
                channel=getattr(message.channel, "name", "unknown"),
                content=content,
                message_id=str(message.id),
            )
            await agent.send(inbound)

        except Exception:
            logger.exception(
                "Failed to deliver message to agent @%s", handle
            )


async def setup(bot: VcoBot) -> None:
    """Load MentionRouterCog into the bot."""
    await bot.add_cog(MentionRouterCog(bot))
