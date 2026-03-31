"""StrategistConversationHandler -- ConversationHandler implementation (D-13).

Extracts message forwarding to StrategistConversation from CompanyAgent.
The StrategistConversation instance is stored on the container (not handler)
because it requires transport injection and has lifecycle tied to container.

Handler is stateless per D-02 -- all state accessed via container.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.container.container import AgentContainer
    from vcompany.models.messages import MessageContext

logger = logging.getLogger("vcompany.handler.conversation")


class StrategistConversationHandler:
    """ConversationHandler implementation for Strategist (D-13).

    Extracts message forwarding to StrategistConversation from CompanyAgent.
    The StrategistConversation instance is stored on the container (not handler)
    because it requires transport injection and has lifecycle tied to container.
    """

    async def handle_message(self, container: AgentContainer, context: MessageContext) -> None:
        """Forward message to StrategistConversation and post response back.

        Uses container._conversation (wired via initialize_conversation on the container).
        Uses container._send_discord() (consolidated base method from D-04).
        Wraps in lifecycle transitions: container._lifecycle.start_processing() / done_processing().

        Args:
            container: The AgentContainer this handler is attached to.
            context: Message context with sender, channel, content.
        """
        container._lifecycle.start_processing()
        try:
            if container._conversation is None:
                logger.warning("Strategist received message but conversation not initialized")
                return

            response = await container._conversation.send(context.content)
            await container._send_discord(context.channel_id or context.channel, response)
            logger.info(
                "Strategist responded to message from %s (len=%d)",
                context.sender, len(response),
            )
        finally:
            container._lifecycle.done_processing()

    async def on_start(self, container: AgentContainer) -> None:
        """No-op -- StrategistConversation is initialized separately via container.initialize_conversation()."""

    async def on_stop(self, container: AgentContainer) -> None:
        """No-op -- no cleanup needed for conversation handler."""
