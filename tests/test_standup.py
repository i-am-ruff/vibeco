"""Tests for standup session, release view, and standup embed."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from vcompany.communication.standup import StandupSession
from vcompany.bot.views.standup_release import ReleaseView
from vcompany.bot.embeds import build_standup_embed


class TestStandupSession:
    """Tests for StandupSession blocking interlock."""

    @pytest.mark.asyncio
    async def test_block_agent_blocks_until_release(self) -> None:
        """block_agent blocks until release_agent is called."""
        session = StandupSession()
        released = False

        async def block_and_mark() -> None:
            nonlocal released
            await session.block_agent("agent-01")
            released = True

        task = asyncio.create_task(block_and_mark())
        await asyncio.sleep(0.05)
        assert not released, "Agent should still be blocked"

        session.release_agent("agent-01")
        await asyncio.sleep(0.05)
        assert released, "Agent should be released"
        await task

    @pytest.mark.asyncio
    async def test_release_agent_unblocks_awaiting_coroutine(self) -> None:
        """release_agent resolves the future so block_agent returns."""
        session = StandupSession()
        done = asyncio.Event()

        async def blocker() -> None:
            await session.block_agent("agent-02")
            done.set()

        task = asyncio.create_task(blocker())
        await asyncio.sleep(0.05)
        assert not done.is_set()

        session.release_agent("agent-02")
        await asyncio.wait_for(done.wait(), timeout=1.0)
        assert done.is_set()
        await task

    @pytest.mark.asyncio
    async def test_release_all_releases_all_agents(self) -> None:
        """release_all releases all blocked agents at once."""
        session = StandupSession()
        results: dict[str, bool] = {}

        async def block(aid: str) -> None:
            await session.block_agent(aid)
            results[aid] = True

        tasks = [asyncio.create_task(block(f"agent-{i}")) for i in range(3)]
        await asyncio.sleep(0.05)
        assert len(results) == 0

        session.release_all()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_is_active_true_when_agents_blocked(self) -> None:
        """is_active returns True when agents are blocked."""
        session = StandupSession()
        assert not session.is_active

        task = asyncio.create_task(session.block_agent("agent-01"))
        await asyncio.sleep(0.05)
        assert session.is_active

        session.release_agent("agent-01")
        await task
        assert not session.is_active

    @pytest.mark.asyncio
    async def test_route_message_to_agent_sends_gsd_quick(self) -> None:
        """route_message_to_agent sends /gsd:quick command to tmux pane."""
        mock_tmux = MagicMock()
        mock_tmux.send_command.return_value = True
        session = StandupSession(tmux=mock_tmux)

        result = await session.route_message_to_agent("agent-01", "focus on auth", "pane-123")
        assert result is True
        mock_tmux.send_command.assert_called_once()
        call_args = mock_tmux.send_command.call_args
        assert "pane-123" in call_args[0]
        assert "gsd:quick" in call_args[0][1]
        assert "focus on auth" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_route_message_returns_false_without_tmux(self) -> None:
        """route_message_to_agent returns False when no tmux manager."""
        session = StandupSession(tmux=None)
        result = await session.route_message_to_agent("agent-01", "test", "pane-1")
        assert result is False

    def test_register_and_get_agent_for_thread(self) -> None:
        """register_thread and get_agent_for_thread map correctly."""
        session = StandupSession()
        session.register_thread("agent-01", 12345)
        session.register_thread("agent-02", 67890)

        assert session.get_agent_for_thread(12345) == "agent-01"
        assert session.get_agent_for_thread(67890) == "agent-02"
        assert session.get_agent_for_thread(99999) is None


class TestReleaseView:
    """Tests for ReleaseView Discord UI component."""

    def test_timeout_is_none(self) -> None:
        """ReleaseView has timeout=None per D-11 (no timeout)."""
        view = ReleaseView(agent_id="agent-01")
        assert view.timeout is None

    @pytest.mark.asyncio
    async def test_release_button_calls_callback(self) -> None:
        """Release button calls the release callback with agent_id."""
        view = ReleaseView(agent_id="agent-01")
        callback_called_with: list[str] = []
        view.set_release_callback(lambda aid: callback_called_with.append(aid))

        # Simulate button press
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        # Get the release button
        button = None
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.label == "Release":
                button = child
                break
        assert button is not None

        await view.release.callback(interaction, button)
        assert callback_called_with == ["agent-01"]

    @pytest.mark.asyncio
    async def test_release_button_disables_after_click(self) -> None:
        """Release button disables itself after being clicked."""
        view = ReleaseView(agent_id="agent-01")

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        button = None
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.label == "Release":
                button = child
                break
        assert button is not None

        await view.release.callback(interaction, button)
        assert button.disabled is True
        assert view.released is True


class TestBuildStandupEmbed:
    """Tests for build_standup_embed function."""

    def test_creates_embed_with_agent_fields(self) -> None:
        """build_standup_embed creates embed with Phase, Status, Recent Work fields."""
        embed = build_standup_embed(
            agent_id="agent-01",
            phase="03",
            status="active",
            summary="abc1234 feat: add auth\ndef5678 fix: token refresh",
        )

        assert isinstance(embed, discord.Embed)
        assert "agent-01" in embed.title
        field_names = [f.name for f in embed.fields]
        assert "Phase" in field_names
        assert "Status" in field_names
        assert "Recent Work" in field_names

    def test_embed_truncates_summary(self) -> None:
        """build_standup_embed truncates summary to 1024 chars."""
        long_summary = "x" * 2000
        embed = build_standup_embed(
            agent_id="agent-01",
            phase="03",
            status="active",
            summary=long_summary,
        )
        work_field = next(f for f in embed.fields if f.name == "Recent Work")
        assert len(work_field.value) <= 1024

    def test_embed_handles_empty_summary(self) -> None:
        """build_standup_embed shows default text for empty summary."""
        embed = build_standup_embed(
            agent_id="agent-01",
            phase="03",
            status="active",
            summary="",
        )
        work_field = next(f for f in embed.fields if f.name == "Recent Work")
        assert work_field.value == "No recent commits"
