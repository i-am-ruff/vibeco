"""Tests for AlertsCog: buffer, flush, callback wiring, and alert methods."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from vcompany.bot.cogs.alerts import AlertsCog


@pytest.fixture
def mock_bot():
    """Create a mock VcoBot with required attributes."""
    bot = MagicMock()
    bot.is_closed.return_value = False
    bot._ready_flag = True
    bot.is_bot_ready = True
    bot._guild_id = 123456
    bot.loop = asyncio.new_event_loop()
    yield bot
    bot.loop.close()


@pytest.fixture
def cog(mock_bot):
    """Create an AlertsCog with mock bot."""
    return AlertsCog(mock_bot)


@pytest.fixture
def mock_channel():
    """Create a mock text channel with async send."""
    channel = AsyncMock(spec=discord.TextChannel)
    channel.name = "alerts"
    return channel


@pytest.mark.asyncio
async def test_send_or_buffer_sends_when_ready(cog, mock_channel):
    """When bot is ready and channel exists, send embed directly."""
    cog._alerts_channel = mock_channel
    embed = discord.Embed(title="Test")

    await cog._send_or_buffer(embed)

    mock_channel.send.assert_awaited_once_with(embed=embed)
    assert len(cog._alert_buffer) == 0


@pytest.mark.asyncio
async def test_send_or_buffer_buffers_when_closed(cog):
    """When bot is closed, buffer the embed instead of sending."""
    cog.bot.is_closed.return_value = True
    embed = discord.Embed(title="Test")

    await cog._send_or_buffer(embed)

    assert len(cog._alert_buffer) == 1
    assert cog._alert_buffer[0] is embed


@pytest.mark.asyncio
async def test_send_or_buffer_buffers_when_not_ready(cog):
    """When bot is not ready, buffer the embed."""
    cog.bot.is_bot_ready = False
    embed = discord.Embed(title="Test")

    await cog._send_or_buffer(embed)

    assert len(cog._alert_buffer) == 1
    assert cog._alert_buffer[0] is embed


@pytest.mark.asyncio
async def test_send_or_buffer_buffers_when_no_channel(cog):
    """When alerts channel is None, buffer the embed."""
    cog._alerts_channel = None
    embed = discord.Embed(title="Test")

    await cog._send_or_buffer(embed)

    assert len(cog._alert_buffer) == 1


@pytest.mark.asyncio
async def test_send_or_buffer_buffers_on_send_exception(cog, mock_channel):
    """When channel.send raises, buffer the embed."""
    mock_channel.send.side_effect = discord.HTTPException(MagicMock(), "error")
    cog._alerts_channel = mock_channel
    embed = discord.Embed(title="Test")

    await cog._send_or_buffer(embed)

    assert len(cog._alert_buffer) == 1


@pytest.mark.asyncio
async def test_flush_on_resumed(cog, mock_channel):
    """on_resumed should flush all buffered embeds and clear the buffer."""
    # Pre-populate buffer
    embeds = [discord.Embed(title=f"Alert {i}") for i in range(3)]
    cog._alert_buffer = list(embeds)
    cog._alerts_channel = mock_channel

    # Mock _resolve_channels to be a no-op (channels already set)
    cog._resolve_channels = AsyncMock()

    await cog.on_resumed()

    assert mock_channel.send.await_count == 3
    assert len(cog._alert_buffer) == 0


@pytest.mark.asyncio
async def test_flush_stops_on_error(cog, mock_channel):
    """on_resumed stops flushing if send raises, but still clears buffer."""
    embeds = [discord.Embed(title=f"Alert {i}") for i in range(3)]
    cog._alert_buffer = list(embeds)
    cog._alerts_channel = mock_channel

    # Fail on second send
    mock_channel.send.side_effect = [None, discord.HTTPException(MagicMock(), "err"), None]
    cog._resolve_channels = AsyncMock()

    await cog.on_resumed()

    # Should have attempted 2 sends (first succeeded, second failed, then break)
    assert mock_channel.send.await_count == 2
    # Buffer is cleared regardless
    assert len(cog._alert_buffer) == 0


@pytest.mark.asyncio
async def test_alert_agent_dead(cog, mock_channel):
    """alert_agent_dead sends error embed with correct title."""
    cog._alerts_channel = mock_channel

    await cog.alert_agent_dead("frontend-1")

    mock_channel.send.assert_awaited_once()
    embed = mock_channel.send.call_args.kwargs["embed"]
    assert embed.title == "Agent Dead"
    assert "frontend-1" in embed.description
    assert embed.color == discord.Color.red()


@pytest.mark.asyncio
async def test_alert_agent_stuck(cog, mock_channel):
    """alert_agent_stuck sends warning embed with correct title."""
    cog._alerts_channel = mock_channel

    await cog.alert_agent_stuck("backend-2")

    mock_channel.send.assert_awaited_once()
    embed = mock_channel.send.call_args.kwargs["embed"]
    assert embed.title == "Agent Stuck"
    assert "backend-2" in embed.description
    assert embed.color == discord.Color.orange()


@pytest.mark.asyncio
async def test_alert_circuit_open(cog, mock_channel):
    """alert_circuit_open sends error embed with crash count."""
    cog._alerts_channel = mock_channel

    await cog.alert_circuit_open("worker-3", 5)

    mock_channel.send.assert_awaited_once()
    embed = mock_channel.send.call_args.kwargs["embed"]
    assert embed.title == "Circuit Breaker Open"
    assert "worker-3" in embed.description
    assert "5" in embed.description
    assert embed.color == discord.Color.red()


@pytest.mark.asyncio
async def test_alert_plan_detected(cog):
    """alert_plan_detected posts to #plan-review, not #alerts."""
    plan_review = AsyncMock(spec=discord.TextChannel)
    plan_review.name = "plan-review"
    alerts = AsyncMock(spec=discord.TextChannel)
    alerts.name = "alerts"

    cog._plan_review_channel = plan_review
    cog._alerts_channel = alerts

    await cog.alert_plan_detected("designer-1", Path("/project/plans/PLAN.md"))

    plan_review.send.assert_awaited_once()
    alerts.send.assert_not_awaited()
    embed = plan_review.send.call_args.kwargs["embed"]
    assert embed.title == "New Plan Detected"
    assert "designer-1" in embed.description
    assert "PLAN.md" in embed.description


@pytest.mark.asyncio
async def test_alert_plan_detected_buffers_when_no_channel(cog):
    """alert_plan_detected buffers when #plan-review channel not available."""
    cog._plan_review_channel = None
    cog._alerts_channel = None

    await cog.alert_plan_detected("designer-1", Path("/project/plans/PLAN.md"))

    assert len(cog._alert_buffer) == 1
    assert cog._alert_buffer[0].title == "New Plan Detected"


def test_make_sync_callbacks(cog):
    """make_sync_callbacks returns dict with all 4 callback keys."""
    callbacks = cog.make_sync_callbacks()

    assert "on_agent_dead" in callbacks
    assert "on_agent_stuck" in callbacks
    assert "on_plan_detected" in callbacks
    assert "on_circuit_open" in callbacks
    assert callable(callbacks["on_agent_dead"])
    assert callable(callbacks["on_agent_stuck"])
    assert callable(callbacks["on_plan_detected"])
    assert callable(callbacks["on_circuit_open"])


def test_make_sync_callbacks_schedules_coroutine(cog):
    """Sync callback should call run_coroutine_threadsafe."""
    callbacks = cog.make_sync_callbacks()

    with patch("asyncio.run_coroutine_threadsafe") as mock_rct:
        callbacks["on_agent_dead"]("test-agent")
        mock_rct.assert_called_once()
        # First arg is the coroutine, second is the loop
        assert mock_rct.call_args[0][1] is cog.bot.loop


@pytest.mark.asyncio
async def test_reconnect_flush_disc12(cog, mock_channel):
    """DISC-12: Buffer alerts during disconnect, flush all on reconnect."""
    # Simulate disconnect: bot is closed
    cog.bot.is_closed.return_value = True

    # Send alerts while disconnected -- they should buffer
    await cog.alert_agent_dead("agent-a")
    await cog.alert_agent_stuck("agent-b")
    await cog.alert_circuit_open("agent-c", 4)

    assert len(cog._alert_buffer) == 3

    # Simulate reconnect
    cog.bot.is_closed.return_value = False
    cog._alerts_channel = mock_channel
    cog._resolve_channels = AsyncMock()

    await cog.on_resumed()

    assert mock_channel.send.await_count == 3
    assert len(cog._alert_buffer) == 0


@pytest.mark.asyncio
async def test_on_ready_resolves_channels(cog):
    """on_ready calls _resolve_channels."""
    cog._resolve_channels = AsyncMock()
    await cog.on_ready()
    cog._resolve_channels.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_channels(cog):
    """_resolve_channels finds #alerts and #plan-review channels."""
    alerts_ch = MagicMock(spec=discord.TextChannel)
    alerts_ch.name = "alerts"
    plan_ch = MagicMock(spec=discord.TextChannel)
    plan_ch.name = "plan-review"
    other_ch = MagicMock(spec=discord.TextChannel)
    other_ch.name = "general"

    guild = MagicMock()
    guild.text_channels = [other_ch, alerts_ch, plan_ch]
    cog.bot.get_guild.return_value = guild

    await cog._resolve_channels()

    assert cog._alerts_channel is alerts_ch
    assert cog._plan_review_channel is plan_ch
