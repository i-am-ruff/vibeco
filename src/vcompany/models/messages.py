"""Pydantic models for Discord message delivery to agent containers.

MessageContext captures the essential information from a Discord message
for delivery to an agent via AgentContainer.receive_discord_message().
"""

from __future__ import annotations

from pydantic import BaseModel


class MessageContext(BaseModel):
    """Inbound Discord message context delivered to an agent container.

    Attributes:
        sender: Display name of the message author (human or bot-as-agent-name).
        channel: Channel name (e.g. "agent-alpha", "strategist").
        content: Full message text.
        parent_message: Content of the message being replied to (D-15:
            immediate parent only, not full chain). None if not a reply
            or if the parent message was deleted.
        message_id: Discord message ID for reference tracking.
        is_reply: Whether this message is a reply to a previous message.
    """

    sender: str
    channel: str
    content: str
    parent_message: str | None = None
    message_id: str | None = None
    is_reply: bool = False
