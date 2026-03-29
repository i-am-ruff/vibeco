"""MentionRouterCog: Generic @mention routing for all agent types.

Watches all messages for @AgentHandle text patterns and delivers
matching messages to the target container via receive_discord_message().

Design decisions:
- D-01: Discord is the ONLY interaction channel for inter-agent communication
- D-02: All agent communication surfaces through Discord channels
- D-04: No agent-type-specific routing -- all agents receive the same MessageContext

The routing is completely generic: register_agent(handle, container) maps
a text handle to any AgentContainer subclass. No isinstance checks, no
agent-type conditionals.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from vcompany.models.messages import MessageContext

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot
    from vcompany.container.container import AgentContainer

logger = logging.getLogger(__name__)


class MentionRouterCog(commands.Cog):
    """Generic @mention router that delivers Discord messages to agent containers.

    Maintains a registry of handle -> container mappings. When a message
    contains @Handle text, it builds a MessageContext and calls
    container.receive_discord_message(context).

    Per D-04: completely agent-type-agnostic. Any AgentContainer subclass
    can be registered with any handle string.
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._agent_handles: dict[str, AgentContainer] = {}
        self._handle_channels: dict[str, str] = {}

    def register_agent(
        self,
        handle: str,
        container: AgentContainer,
        channel_id: str | None = None,
    ) -> None:
        """Register an agent handle for @mention routing.

        Args:
            handle: Text handle (e.g. "Strategist", "PMProjectX").
            container: AgentContainer to deliver messages to.
            channel_id: Optional primary channel ID for this agent.
        """
        self._agent_handles[handle] = container
        if channel_id is not None:
            self._handle_channels[handle] = channel_id
        logger.info(
            "Registered agent handle @%s -> %s",
            handle,
            container.context.agent_id,
        )

    def unregister_agent(self, handle: str) -> None:
        """Remove an agent handle from the routing registry.

        Args:
            handle: Text handle to unregister.
        """
        self._agent_handles.pop(handle, None)
        self._handle_channels.pop(handle, None)
        logger.info("Unregistered agent handle @%s", handle)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Scan messages for @Handle patterns and route to registered agents.

        Skips bot messages (D-04, prevents bot loop -- Pitfall 1) and
        the bot's own messages for extra safety.
        """
        # Skip bot messages to prevent loops (D-04, Pitfall 1)
        if message.author.bot:
            return

        # Extra safety: skip own messages
        if self.bot.user and message.author.id == self.bot.user.id:
            return

        if not self._agent_handles:
            return

        content = message.content
        for handle in self._agent_handles:
            if f"@{handle}" in content:
                await self._deliver_to_agent(handle, message)

    async def _deliver_to_agent(
        self, handle: str, message: discord.Message
    ) -> None:
        """Build MessageContext and deliver to the agent container.

        Fetches reply parent content if the message is a reply (D-15:
        immediate parent only, not full chain).

        Args:
            handle: Matched agent handle.
            message: Discord message to deliver.
        """
        try:
            container = self._agent_handles.get(handle)
            if container is None:
                return

            # Build base context
            context = MessageContext(
                sender=message.author.display_name,
                channel=getattr(message.channel, "name", "unknown"),
                content=message.content,
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
                    # Parent message deleted -- deliver without parent context
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
