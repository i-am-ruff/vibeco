"""Tests for workflow-master: persona, cog, channel setup, worktree, and conversation tools."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from vcompany.bot.cogs.workflow_master import WorkflowMasterCog
from vcompany.strategist.conversation import StrategistConversation, _SESSION_UUID
from vcompany.strategist.workflow_master_persona import (
    WORKFLOW_MASTER_SESSION_UUID,
    build_workflow_master_persona,
)


# --- Helpers ---


def _make_bot() -> MagicMock:
    """Create a mock VcoBot with loop and user."""
    bot = MagicMock(spec=commands.Bot)
    bot.loop = asyncio.get_event_loop()
    bot_user = MagicMock(spec=discord.User)
    bot_user.id = 999
    bot.user = bot_user
    return bot


def _make_message(
    *,
    content: str = "Fix the tests",
    author_id: int = 100,
    channel_name: str = "workflow-master",
    has_owner_role: bool = True,
    webhook_id: int | None = None,
) -> MagicMock:
    """Create a mock Discord message."""
    msg = MagicMock(spec=discord.Message)
    msg.content = content
    msg.webhook_id = webhook_id
    msg.attachments = []
    msg.reference = None

    author = MagicMock(spec=discord.Member)
    author.id = author_id
    if has_owner_role:
        role = MagicMock(spec=discord.Role)
        role.name = "vco-owner"
        author.roles = [role]
    else:
        author.roles = []
    msg.author = author

    channel = AsyncMock(spec=discord.TextChannel)
    channel.name = channel_name
    msg.channel = channel

    return msg


def _make_cog_with_conversation(bot: MagicMock | None = None) -> tuple[WorkflowMasterCog, AsyncMock]:
    """Create a WorkflowMasterCog with mocked conversation."""
    if bot is None:
        bot = _make_bot()
    cog = WorkflowMasterCog(bot)

    conversation = AsyncMock()
    conversation.send = AsyncMock(return_value="Done, tests pass now.")
    conversation.send_streaming = AsyncMock(return_value="Done, tests pass now.")
    cog._conversation = conversation

    channel = AsyncMock(spec=discord.TextChannel)
    channel.name = "workflow-master"
    cog._wm_channel = channel

    return cog, conversation


# --- Persona tests ---


def test_session_uuid_distinct() -> None:
    """workflow-master UUID is distinct from Strategist UUID."""
    assert WORKFLOW_MASTER_SESSION_UUID != _SESSION_UUID


def test_build_persona_injects_path() -> None:
    """build_workflow_master_persona injects the worktree path into the persona."""
    persona = build_workflow_master_persona(Path("/tmp/test-wt"))
    assert "/tmp/test-wt" in persona


# --- Channel filter tests ---


@pytest.mark.asyncio
async def test_channel_filter_routes_workflow_master() -> None:
    """Messages in #workflow-master from owner are forwarded to conversation."""
    cog, conversation = _make_cog_with_conversation()
    msg = _make_message(content="Run the test suite")
    msg.channel = cog._wm_channel

    # Make channel.send return a placeholder message for _send_to_channel
    placeholder = AsyncMock(spec=discord.Message)
    cog._wm_channel.send.return_value = placeholder

    await cog.on_message(msg)
    conversation.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_ignores_non_workflow_master_channel() -> None:
    """Messages from non-workflow-master channels are ignored."""
    cog, conversation = _make_cog_with_conversation()
    msg = _make_message(channel_name="general")

    await cog.on_message(msg)
    conversation.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_ignores_bot_own_messages() -> None:
    """Bot's own messages are ignored."""
    bot = _make_bot()
    cog, conversation = _make_cog_with_conversation(bot)
    msg = _make_message(author_id=999)  # Same as bot user ID
    msg.channel = cog._wm_channel

    await cog.on_message(msg)
    conversation.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_ignores_non_owner() -> None:
    """Messages from users without vco-owner role are ignored."""
    cog, conversation = _make_cog_with_conversation()
    msg = _make_message(has_owner_role=False)
    msg.channel = cog._wm_channel

    await cog.on_message(msg)
    conversation.send.assert_not_awaited()


# --- Worktree tests ---


@patch("vcompany.cli.up_cmd.WORKTREE_PATH")
def test_worktree_idempotent(mock_path: MagicMock) -> None:
    """_ensure_worktree is a no-op when worktree directory already exists."""
    mock_path.exists.return_value = True

    from vcompany.cli.up_cmd import _ensure_worktree

    with patch("vcompany.cli.up_cmd.subprocess") as mock_subprocess:
        result = _ensure_worktree(Path("/fake/repo"))
        mock_subprocess.run.assert_not_called()
    assert result == mock_path


@patch("vcompany.cli.up_cmd.WORKTREE_PATH")
@patch("vcompany.cli.up_cmd.subprocess")
def test_worktree_creates_new(mock_subprocess: MagicMock, mock_path: MagicMock) -> None:
    """_ensure_worktree creates a new worktree when directory does not exist."""
    mock_path.exists.return_value = False
    mock_path.__str__ = lambda self: "/home/developer/vco-workflow-master-worktree"

    # No existing branch
    branch_result = MagicMock()
    branch_result.stdout = ""
    mock_subprocess.run.return_value = branch_result

    from vcompany.cli.up_cmd import _ensure_worktree

    _ensure_worktree(Path("/fake/repo"))

    # Should have been called twice: branch check + worktree add
    assert mock_subprocess.run.call_count == 2
    worktree_call = mock_subprocess.run.call_args_list[1]
    cmd = worktree_call[0][0]
    assert "worktree" in cmd
    assert "add" in cmd
    assert "-b" in cmd


# --- Channel setup test ---


def test_channel_setup_includes_workflow_master() -> None:
    """_SYSTEM_CHANNELS includes workflow-master."""
    from vcompany.bot.channel_setup import _SYSTEM_CHANNELS

    assert "workflow-master" in _SYSTEM_CHANNELS


# --- Conversation allowed_tools test ---


def test_conversation_allowed_tools() -> None:
    """StrategistConversation accepts allowed_tools and uses it in commands."""
    conv = StrategistConversation(allowed_tools="Bash Read Write Edit")
    resume_cmd = conv._resume_command()
    create_cmd = conv._create_command()

    assert "Bash Read Write Edit" in resume_cmd
    assert "Bash Read Write Edit" in create_cmd

    # Default should still be "Bash Read Write"
    default_conv = StrategistConversation()
    assert "Bash Read Write" in default_conv._resume_command()
    assert "Bash Read Write" in default_conv._create_command()
