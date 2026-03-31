"""WorkerConversationHandler -- ConversationHandler for worker-side agents.

Adapted from daemon-side StrategistConversationHandler. Key changes:
- No anthropic SDK import -- conversation is subprocess-based (claude -p)
- MessageContext replaced with InboundMessage
- container._send_discord() replaced with container.send_report()
- Named WorkerConversationHandler to distinguish from daemon-side
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vco_worker.channel.messages import InboundMessage
    from vco_worker.container.container import WorkerContainer

logger = logging.getLogger("vco_worker.handler.conversation")


class WorkerConversationHandler:
    """ConversationHandler implementation for worker-side agents.

    In worker context, the conversation is managed as a subprocess
    (claude -p --resume) rather than through the anthropic SDK.
    If container._conversation exists, uses it. Otherwise, relays
    the message content via channel report (relay mode).
    """

    async def handle_message(self, container: WorkerContainer, message: InboundMessage) -> None:
        """Forward message to conversation subprocess and post response back.

        Uses container._conversation (wired via external setup).
        Uses container.send_report() for channel-based output.
        Wraps in lifecycle transitions: start_processing() / done_processing().
        """
        container._lifecycle.start_processing()
        try:
            if container._conversation is None:
                # Relay mode -- forward message content via channel report
                logger.info(
                    "Conversation handler relaying message from %s (no conversation instance)",
                    message.sender,
                )
                await container.send_report(
                    message.channel,
                    f"[Relay] {message.content}",
                )
                return

            response = await container._conversation.send(message.content)
            await container.send_report(message.channel, response)
            logger.info(
                "Conversation responded to message from %s (len=%d)",
                message.sender, len(response),
            )
        finally:
            container._lifecycle.done_processing()

    async def on_start(self, container: WorkerContainer) -> None:
        """No-op -- conversation subprocess is initialized separately."""

    async def on_stop(self, container: WorkerContainer) -> None:
        """No-op -- no cleanup needed for conversation handler."""
