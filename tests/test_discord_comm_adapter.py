"""Tests for DiscordCommunicationPort adapter.

Verifies the Discord adapter satisfies CommunicationPort protocol and
translates protocol calls to discord.py API calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from vcompany.daemon.comm import (
    CommunicationPort,
    CreateThreadPayload,
    SendEmbedPayload,
    SendMessagePayload,
    SubscribePayload,
)


def _make_bot_with_channel(channel=None):
    """Create a mock VcoBot that returns the given channel from get_channel."""
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=channel)
    return bot


def _make_text_channel():
    """Create a mock TextChannel with send and create_thread."""
    ch = MagicMock(spec=discord.TextChannel)
    ch.send = AsyncMock()
    ch.create_thread = AsyncMock()
    return ch


# --- Protocol compliance ---


class TestProtocolCompliance:
    def test_satisfies_communication_port(self):
        from vcompany.bot.comm_adapter import DiscordCommunicationPort

        bot = MagicMock()
        adapter = DiscordCommunicationPort(bot)
        assert isinstance(adapter, CommunicationPort)


# --- send_message ---


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_success(self):
        from vcompany.bot.comm_adapter import DiscordCommunicationPort

        ch = _make_text_channel()
        bot = _make_bot_with_channel(ch)
        adapter = DiscordCommunicationPort(bot)

        payload = SendMessagePayload(channel_id="12345", content="hello")
        result = await adapter.send_message(payload)

        assert result is True
        bot.get_channel.assert_called_once_with(12345)
        ch.send.assert_awaited_once_with("hello")

    @pytest.mark.asyncio
    async def test_send_message_channel_not_found(self):
        from vcompany.bot.comm_adapter import DiscordCommunicationPort

        bot = _make_bot_with_channel(None)
        adapter = DiscordCommunicationPort(bot)

        payload = SendMessagePayload(channel_id="99999", content="hello")
        result = await adapter.send_message(payload)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_non_text_channel(self):
        """Non-TextChannel (e.g. VoiceChannel) should return False."""
        from vcompany.bot.comm_adapter import DiscordCommunicationPort

        voice_ch = MagicMock(spec=discord.VoiceChannel)
        bot = _make_bot_with_channel(voice_ch)
        adapter = DiscordCommunicationPort(bot)

        payload = SendMessagePayload(channel_id="12345", content="hello")
        result = await adapter.send_message(payload)

        assert result is False


# --- send_embed ---


class TestSendEmbed:
    @pytest.mark.asyncio
    async def test_send_embed_success(self):
        from vcompany.bot.comm_adapter import DiscordCommunicationPort

        ch = _make_text_channel()
        bot = _make_bot_with_channel(ch)
        adapter = DiscordCommunicationPort(bot)

        payload = SendEmbedPayload(
            channel_id="12345",
            title="Status",
            description="All good",
            color=0x00FF00,
            fields=[{"name": "f1", "value": "v1", "inline": True}],
        )
        result = await adapter.send_embed(payload)

        assert result is True
        ch.send.assert_awaited_once()
        call_kwargs = ch.send.call_args[1]
        embed = call_kwargs["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.title == "Status"
        assert embed.description == "All good"

    @pytest.mark.asyncio
    async def test_send_embed_channel_not_found(self):
        from vcompany.bot.comm_adapter import DiscordCommunicationPort

        bot = _make_bot_with_channel(None)
        adapter = DiscordCommunicationPort(bot)

        payload = SendEmbedPayload(channel_id="99999", title="X")
        result = await adapter.send_embed(payload)

        assert result is False


# --- create_thread ---


class TestCreateThread:
    @pytest.mark.asyncio
    async def test_create_thread_success(self):
        from vcompany.bot.comm_adapter import DiscordCommunicationPort

        thread = MagicMock()
        thread.id = 77777
        thread.name = "my-thread"
        thread.send = AsyncMock()

        ch = _make_text_channel()
        ch.create_thread = AsyncMock(return_value=thread)
        bot = _make_bot_with_channel(ch)
        adapter = DiscordCommunicationPort(bot)

        payload = CreateThreadPayload(
            channel_id="12345", name="my-thread", initial_message="hello thread"
        )
        result = await adapter.create_thread(payload)

        assert result is not None
        assert result.thread_id == "77777"
        assert result.name == "my-thread"
        thread.send.assert_awaited_once_with("hello thread")

    @pytest.mark.asyncio
    async def test_create_thread_no_initial_message(self):
        from vcompany.bot.comm_adapter import DiscordCommunicationPort

        thread = MagicMock()
        thread.id = 77777
        thread.name = "my-thread"
        thread.send = AsyncMock()

        ch = _make_text_channel()
        ch.create_thread = AsyncMock(return_value=thread)
        bot = _make_bot_with_channel(ch)
        adapter = DiscordCommunicationPort(bot)

        payload = CreateThreadPayload(channel_id="12345", name="my-thread")
        result = await adapter.create_thread(payload)

        assert result is not None
        assert result.thread_id == "77777"
        thread.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_thread_channel_not_found(self):
        from vcompany.bot.comm_adapter import DiscordCommunicationPort

        bot = _make_bot_with_channel(None)
        adapter = DiscordCommunicationPort(bot)

        payload = CreateThreadPayload(channel_id="99999", name="thread")
        result = await adapter.create_thread(payload)

        assert result is None


# --- subscribe_to_channel ---


class TestSubscribeToChannel:
    @pytest.mark.asyncio
    async def test_subscribe_channel_exists(self):
        from vcompany.bot.comm_adapter import DiscordCommunicationPort

        ch = _make_text_channel()
        bot = _make_bot_with_channel(ch)
        adapter = DiscordCommunicationPort(bot)

        payload = SubscribePayload(channel_id="12345")
        result = await adapter.subscribe_to_channel(payload)

        assert result is True

    @pytest.mark.asyncio
    async def test_subscribe_channel_not_found(self):
        from vcompany.bot.comm_adapter import DiscordCommunicationPort

        bot = _make_bot_with_channel(None)
        adapter = DiscordCommunicationPort(bot)

        payload = SubscribePayload(channel_id="99999")
        result = await adapter.subscribe_to_channel(payload)

        assert result is False
