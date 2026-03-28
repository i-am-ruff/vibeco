"""DiscordCommunicationPort: Discord implementation of CommunicationPort (MIGR-04).

Implements the CommunicationPort Protocol using Discord channels for message routing.
This module is the ONLY place where Discord types are used for communication --
container code imports CommunicationPort from communication.py and never sees Discord.

Structural subtyping: does NOT inherit from CommunicationPort (it's a Protocol).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from vcompany.container.communication import Message

logger = logging.getLogger("vcompany.container.discord_communication")


class DiscordCommunicationPort:
    """Discord-backed communication port for agent containers.

    Routes messages to agent-specific Discord channels within a guild.
    Satisfies the CommunicationPort Protocol via structural subtyping --
    no inheritance from the Protocol class.

    Constructor args and deliver_message are implementation-specific
    (not part of the Protocol interface). This is the extension point
    for v3 -- SlackCommunicationPort etc. would implement the same
    Protocol differently.
    """

    def __init__(self, bot: Any, agent_id: str, guild_id: int) -> None:
        """Initialize with a bot reference, agent identity, and guild.

        Args:
            bot: Any object with a get_guild(int) method (e.g., VcoBot).
            agent_id: The ID of the agent this port belongs to.
            guild_id: The Discord guild ID to route messages through.
        """
        self._bot = bot
        self._agent_id = agent_id
        self._guild_id = guild_id
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()

    async def send_message(self, target: str, content: str) -> bool:
        """Send a message to a target agent's Discord channel.

        Looks up the guild, finds the channel named "agent-{target}",
        and sends the message with a source prefix.

        Args:
            target: The target agent ID (channel will be "agent-{target}").
            content: The message content to send.

        Returns:
            True on success, False on any failure.
        """
        try:
            guild = self._bot.get_guild(self._guild_id)
            if guild is None:
                logger.warning(
                    "Guild %d not found when sending message to %s",
                    self._guild_id,
                    target,
                )
                return False

            channel_name = f"agent-{target}"
            channel = None
            for ch in guild.text_channels:
                if ch.name == channel_name:
                    channel = ch
                    break

            if channel is None:
                logger.warning(
                    "Channel %s not found in guild %d",
                    channel_name,
                    self._guild_id,
                )
                return False

            await channel.send(f"[from:{self._agent_id}] {content}")
            return True
        except Exception:
            logger.exception(
                "Failed to send message to %s in guild %d",
                target,
                self._guild_id,
            )
            return False

    async def receive_message(self) -> Message | None:
        """Receive the next pending message, or None if queue is empty.

        Non-blocking: returns immediately with None if no messages.

        Returns:
            The next Message from the inbox, or None if empty.
        """
        try:
            return self._inbox.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def deliver_message(self, msg: Message) -> None:
        """Enqueue an incoming message into this port's inbox.

        Used by the bot to route incoming Discord messages to the
        correct agent's communication port. This method is
        implementation-specific and NOT part of the CommunicationPort Protocol.

        Args:
            msg: The Message to enqueue.
        """
        await self._inbox.put(msg)
