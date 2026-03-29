"""Platform-agnostic communication port protocol and payload models.

Defines the CommunicationPort protocol that any platform adapter (Discord, Slack,
test noop) must satisfy. The daemon layer uses this protocol exclusively for all
outbound messaging -- no discord.py imports allowed here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


# --- Payload models ---


class EmbedField(BaseModel):
    """Single field within an embed."""

    name: str
    value: str
    inline: bool = False


class SendMessagePayload(BaseModel):
    """Payload for sending a plain text message to a channel."""

    channel_id: str
    content: str


class SendEmbedPayload(BaseModel):
    """Payload for sending a rich embed to a channel."""

    channel_id: str
    title: str
    description: str = ""
    color: int | None = None
    fields: list[EmbedField] = Field(default_factory=list)


class CreateThreadPayload(BaseModel):
    """Payload for creating a thread in a channel."""

    channel_id: str
    name: str
    initial_message: str | None = None


class ThreadResult(BaseModel):
    """Result returned after thread creation."""

    thread_id: str
    name: str


class SubscribePayload(BaseModel):
    """Payload for subscribing to channel events."""

    channel_id: str


class CreateChannelPayload(BaseModel):
    """Payload for creating a text channel, optionally under a category."""

    category_name: str
    channel_name: str


class CreateChannelResult(BaseModel):
    """Result returned after channel creation."""

    channel_id: str
    name: str


class EditMessagePayload(BaseModel):
    """Payload for editing an existing message."""

    channel_id: str
    message_id: str
    content: str


# --- Protocol ---


@runtime_checkable
class CommunicationPort(Protocol):
    """Platform-agnostic communication interface.

    Any adapter (Discord, Slack, noop) must implement these six async methods.
    Used by the daemon layer for all outbound messaging.
    """

    async def send_message(self, payload: SendMessagePayload) -> bool: ...

    async def send_embed(self, payload: SendEmbedPayload) -> bool: ...

    async def create_thread(
        self, payload: CreateThreadPayload
    ) -> ThreadResult | None: ...

    async def subscribe_to_channel(self, payload: SubscribePayload) -> bool: ...

    async def create_channel(
        self, payload: CreateChannelPayload
    ) -> CreateChannelResult | None: ...

    async def edit_message(self, payload: EditMessagePayload) -> bool: ...


# --- Noop adapter (testing / fallback) ---


class NoopCommunicationPort:
    """No-op implementation of CommunicationPort for testing and fallback."""

    async def send_message(self, payload: SendMessagePayload) -> bool:
        return True

    async def send_embed(self, payload: SendEmbedPayload) -> bool:
        return True

    async def create_thread(
        self, payload: CreateThreadPayload
    ) -> ThreadResult | None:
        return ThreadResult(thread_id="noop-thread", name=payload.name)

    async def subscribe_to_channel(self, payload: SubscribePayload) -> bool:
        return True

    async def create_channel(
        self, payload: CreateChannelPayload
    ) -> CreateChannelResult | None:
        return CreateChannelResult(
            channel_id="noop-channel", name=payload.channel_name
        )

    async def edit_message(self, payload: EditMessagePayload) -> bool:
        return True
