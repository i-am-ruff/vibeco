"""Discord adapter for the CommunicationPort protocol.

Translates platform-agnostic protocol calls into discord.py API calls.
Lives in the bot layer -- the daemon layer never imports discord.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from vcompany.daemon.comm import (
    CreateThreadPayload,
    SendEmbedPayload,
    SendMessagePayload,
    SubscribePayload,
    ThreadResult,
)

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot

logger = logging.getLogger(__name__)


class DiscordCommunicationPort:
    """CommunicationPort implementation backed by discord.py.

    Constructed with a VcoBot reference. Resolves channel IDs to
    discord.TextChannel objects via the bot's cache.
    """

    def __init__(self, bot: VcoBot) -> None:
        self._bot = bot

    def _resolve_channel(self, channel_id: str) -> discord.TextChannel | None:
        """Resolve a string channel ID to a TextChannel, or None."""
        try:
            ch = self._bot.get_channel(int(channel_id))
        except (ValueError, TypeError):
            logger.warning("Invalid channel ID (not numeric): %s", channel_id)
            return None
        if not isinstance(ch, discord.TextChannel):
            return None
        return ch

    async def send_message(self, payload: SendMessagePayload) -> bool:
        """Send a plain text message to a channel."""
        channel = self._resolve_channel(payload.channel_id)
        if channel is None:
            logger.warning("send_message: channel %s not found", payload.channel_id)
            return False
        await channel.send(payload.content)
        return True

    async def send_embed(self, payload: SendEmbedPayload) -> bool:
        """Build a discord.Embed from payload and send it."""
        channel = self._resolve_channel(payload.channel_id)
        if channel is None:
            logger.warning("send_embed: channel %s not found", payload.channel_id)
            return False
        embed = discord.Embed(
            title=payload.title,
            description=payload.description,
            color=discord.Colour(payload.color) if payload.color is not None else None,
        )
        for field in payload.fields:
            embed.add_field(name=field.name, value=field.value, inline=field.inline)
        await channel.send(embed=embed)
        return True

    async def create_thread(
        self, payload: CreateThreadPayload
    ) -> ThreadResult | None:
        """Create a public thread in a channel, optionally sending an initial message."""
        channel = self._resolve_channel(payload.channel_id)
        if channel is None:
            logger.warning("create_thread: channel %s not found", payload.channel_id)
            return None
        thread = await channel.create_thread(
            name=payload.name, type=discord.ChannelType.public_thread
        )
        if payload.initial_message is not None:
            await thread.send(payload.initial_message)
        return ThreadResult(thread_id=str(thread.id), name=thread.name)

    async def subscribe_to_channel(self, payload: SubscribePayload) -> bool:
        """Check if a channel is visible to the bot."""
        channel = self._resolve_channel(payload.channel_id)
        return channel is not None
