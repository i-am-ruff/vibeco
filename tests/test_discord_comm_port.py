"""Tests for DiscordCommunicationPort (MIGR-04).

Verifies that DiscordCommunicationPort satisfies the CommunicationPort Protocol
at runtime and correctly routes messages through Discord channels.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from vcompany.container.communication import CommunicationPort, Message
from vcompany.container.discord_communication import DiscordCommunicationPort


def _make_mock_bot(guild=None):
    """Create a mock bot with get_guild method."""
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=guild)
    return bot


def _make_mock_guild(channels=None):
    """Create a mock guild with text_channels."""
    guild = MagicMock()
    guild.text_channels = channels or []
    return guild


def _make_mock_channel(name: str):
    """Create a mock text channel with given name."""
    channel = MagicMock()
    channel.name = name
    channel.send = AsyncMock()
    return channel


class TestProtocolConformance:
    """DiscordCommunicationPort satisfies CommunicationPort Protocol."""

    def test_isinstance_check(self):
        """DiscordCommunicationPort passes isinstance(port, CommunicationPort) check."""
        bot = _make_mock_bot()
        port = DiscordCommunicationPort(bot=bot, agent_id="agent-1", guild_id=12345)
        assert isinstance(port, CommunicationPort)


class TestSendMessage:
    """send_message routes to Discord channels."""

    @pytest.mark.asyncio
    async def test_send_success(self):
        """send_message returns True when target channel exists and send succeeds."""
        channel = _make_mock_channel("agent-backend")
        guild = _make_mock_guild(channels=[channel])
        bot = _make_mock_bot(guild=guild)
        port = DiscordCommunicationPort(bot=bot, agent_id="agent-1", guild_id=12345)

        result = await port.send_message("backend", "hello")

        assert result is True
        channel.send.assert_awaited_once_with("[from:agent-1] hello")

    @pytest.mark.asyncio
    async def test_send_guild_not_found(self):
        """send_message returns False when guild is not found."""
        bot = _make_mock_bot(guild=None)
        port = DiscordCommunicationPort(bot=bot, agent_id="agent-1", guild_id=12345)

        result = await port.send_message("backend", "hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_channel_not_found(self):
        """send_message returns False when target channel is not found."""
        guild = _make_mock_guild(channels=[_make_mock_channel("agent-other")])
        bot = _make_mock_bot(guild=guild)
        port = DiscordCommunicationPort(bot=bot, agent_id="agent-1", guild_id=12345)

        result = await port.send_message("backend", "hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_exception(self):
        """send_message returns False when channel.send raises an exception."""
        channel = _make_mock_channel("agent-backend")
        channel.send = AsyncMock(side_effect=Exception("Discord API error"))
        guild = _make_mock_guild(channels=[channel])
        bot = _make_mock_bot(guild=guild)
        port = DiscordCommunicationPort(bot=bot, agent_id="agent-1", guild_id=12345)

        result = await port.send_message("backend", "hello")

        assert result is False


class TestReceiveMessage:
    """receive_message reads from internal inbox queue."""

    @pytest.mark.asyncio
    async def test_receive_empty(self):
        """receive_message returns None when inbox is empty."""
        bot = _make_mock_bot()
        port = DiscordCommunicationPort(bot=bot, agent_id="agent-1", guild_id=12345)

        result = await port.receive_message()

        assert result is None

    @pytest.mark.asyncio
    async def test_receive_with_message(self):
        """receive_message returns Message from inbox when one has been enqueued."""
        bot = _make_mock_bot()
        port = DiscordCommunicationPort(bot=bot, agent_id="agent-1", guild_id=12345)

        msg = Message(
            source="agent-2",
            target="agent-1",
            content="ping",
            timestamp=datetime.now(timezone.utc),
        )
        await port.deliver_message(msg)

        result = await port.receive_message()

        assert result is not None
        assert result.source == "agent-2"
        assert result.content == "ping"


class TestDeliverMessage:
    """deliver_message enqueues messages into the inbox."""

    @pytest.mark.asyncio
    async def test_deliver_enqueues(self):
        """deliver_message enqueues a Message into the inbox."""
        bot = _make_mock_bot()
        port = DiscordCommunicationPort(bot=bot, agent_id="agent-1", guild_id=12345)

        msg = Message(
            source="agent-2",
            target="agent-1",
            content="task complete",
            timestamp=datetime.now(timezone.utc),
        )
        await port.deliver_message(msg)

        # Verify the message is in the inbox by receiving it
        result = await port.receive_message()
        assert result is msg
