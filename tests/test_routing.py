"""Tests for the message routing framework (D-06, D-07, D-08).

Tests cover:
- Reply-based routing (D-06 rule 1)
- Mention-based routing (D-06 rule 2)
- Channel-owner default (D-06 rule 3)
- Strategist default (D-06 rule 4)
- Ignore cases (bot messages, webhooks, unrecognized channels)
- D-07 Strategist filtering
- Helper functions (is_question_embed, extract_entity_from_prefix)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from vcompany.bot.routing import (
    EntityRegistry,
    RouteResult,
    RouteTarget,
    extract_entity_from_prefix,
    is_question_embed,
    route_message,
)


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_registry(bot_user_id: int = 100) -> EntityRegistry:
    """Create a test EntityRegistry."""
    return EntityRegistry(
        bot_user_id=bot_user_id,
        entity_prefixes={
            "pm": "[PM]",
            "frontend": "[agent-frontend]",
            "backend": "[agent-backend]",
        },
        strategist_user_ids={100},  # bot is the strategist
    )


def _make_message(
    *,
    author_id: int = 200,
    author_bot: bool = False,
    channel_name: str = "agent-frontend",
    content: str = "Hello",
    webhook_id: int | None = None,
    reference_message_id: int | None = None,
    mentions: list | None = None,
    embeds: list | None = None,
) -> MagicMock:
    """Create a mock discord.Message."""
    msg = MagicMock()
    msg.author.id = author_id
    msg.author.bot = author_bot
    msg.channel.name = channel_name
    msg.content = content
    msg.webhook_id = webhook_id
    msg.embeds = embeds or []

    if reference_message_id is not None:
        msg.reference = MagicMock()
        msg.reference.message_id = reference_message_id
    else:
        msg.reference = None

    msg.mentions = mentions or []
    return msg


# ── Reply-based routing tests (D-06 rule 1) ──────────────────────────


class TestReplyBasedRouting:
    """Reply to a specific message determines route target."""

    def test_reply_to_strategist_message(self):
        """Reply to Strategist message -> RouteTarget.STRATEGIST."""
        msg = _make_message(
            channel_name="agent-frontend",
            reference_message_id=999,
        )
        registry = _make_registry()
        # Strategist speaks without prefix (per D-05)
        result = route_message(
            msg, "agent-frontend", registry, replied_to_content="This is a strategist response"
        )
        assert result.target == RouteTarget.STRATEGIST
        assert result.is_reply_to == 999

    def test_reply_to_pm_message(self):
        """Reply to PM message -> RouteTarget.PM."""
        msg = _make_message(
            channel_name="agent-frontend",
            reference_message_id=888,
        )
        registry = _make_registry()
        result = route_message(
            msg, "agent-frontend", registry, replied_to_content="[PM] Here is my answer"
        )
        assert result.target == RouteTarget.PM
        assert result.is_reply_to == 888

    def test_reply_to_agent_question_message(self):
        """Reply to agent question message -> RouteTarget.AGENT with entity_id."""
        msg = _make_message(
            channel_name="agent-frontend",
            reference_message_id=777,
        )
        registry = _make_registry()
        result = route_message(
            msg,
            "agent-frontend",
            registry,
            replied_to_content="[agent-frontend] What database should I use?",
        )
        assert result.target == RouteTarget.AGENT
        assert result.entity_id == "frontend"
        assert result.is_reply_to == 777


# ── Mention-based routing tests (D-06 rule 2) ─────────────────────────


class TestMentionBasedRouting:
    """@mention determines route target."""

    def test_strategist_mention_in_any_channel(self):
        """@Strategist mention -> RouteTarget.STRATEGIST."""
        bot_member = MagicMock()
        bot_member.id = 100
        msg = _make_message(
            channel_name="agent-frontend",
            content="@Strategist what do you think?",
            mentions=[bot_member],
        )
        registry = _make_registry(bot_user_id=100)
        result = route_message(msg, "agent-frontend", registry)
        assert result.target == RouteTarget.STRATEGIST

    def test_pm_mention_in_any_channel(self):
        """@PM mention -> RouteTarget.PM (not implemented as Discord user, uses content)."""
        msg = _make_message(
            channel_name="agent-frontend",
            content="@PM please review this",
        )
        registry = _make_registry()
        result = route_message(msg, "agent-frontend", registry)
        assert result.target == RouteTarget.PM


# ── Channel-owner default tests (D-06 rule 3) ─────────────────────────


class TestChannelOwnerDefault:
    """Unaddressed messages in #agent-{id} go to that agent."""

    def test_unaddressed_in_agent_channel(self):
        """Unaddressed owner message in #agent-frontend -> AGENT with entity_id=frontend."""
        msg = _make_message(
            channel_name="agent-frontend",
            content="How is progress going?",
        )
        registry = _make_registry()
        result = route_message(msg, "agent-frontend", registry)
        assert result.target == RouteTarget.AGENT
        assert result.entity_id == "frontend"


# ── Strategist default tests (D-06 rule 4) ────────────────────────────


class TestStrategistDefault:
    """Unaddressed messages in #strategist go to Strategist."""

    def test_unaddressed_in_strategist_channel(self):
        """Unaddressed owner message in #strategist -> STRATEGIST."""
        msg = _make_message(
            channel_name="strategist",
            content="What's the project status?",
        )
        registry = _make_registry()
        result = route_message(msg, "strategist", registry)
        assert result.target == RouteTarget.STRATEGIST


# ── Ignore cases ───────────────────────────────────────────────────────


class TestIgnoreCases:
    """Messages that should be ignored."""

    def test_bot_own_message_not_system(self):
        """Bot's own message (not [system]) -> IGNORE."""
        msg = _make_message(
            author_id=100,
            author_bot=True,
            content="Some bot response",
        )
        registry = _make_registry(bot_user_id=100)
        result = route_message(msg, "agent-frontend", registry)
        assert result.target == RouteTarget.IGNORE

    def test_bot_system_message_not_ignored(self):
        """Bot's [system] message should NOT be ignored."""
        msg = _make_message(
            author_id=100,
            author_bot=True,
            content="[system] Agent deployed",
        )
        registry = _make_registry(bot_user_id=100)
        result = route_message(msg, "agent-frontend", registry)
        # System messages should route normally (channel-owner default)
        assert result.target != RouteTarget.IGNORE

    def test_webhook_message_ignored(self):
        """Webhook message -> IGNORE."""
        msg = _make_message(webhook_id=12345)
        registry = _make_registry()
        result = route_message(msg, "agent-frontend", registry)
        assert result.target == RouteTarget.IGNORE

    def test_unrecognized_channel_ignored(self):
        """Message in unrecognized channel -> IGNORE."""
        msg = _make_message(channel_name="random")
        registry = _make_registry()
        result = route_message(msg, "random", registry)
        assert result.target == RouteTarget.IGNORE


# ── D-07 Strategist filtering ─────────────────────────────────────────


class TestD07StrategistFiltering:
    """D-07: Strategist ignores messages not addressed to it."""

    def test_reply_to_pm_not_strategist(self):
        """Reply to PM message in #agent-x -> NOT STRATEGIST (D-07)."""
        msg = _make_message(
            channel_name="agent-frontend",
            reference_message_id=888,
        )
        registry = _make_registry()
        result = route_message(
            msg, "agent-frontend", registry, replied_to_content="[PM] My answer"
        )
        assert result.target != RouteTarget.STRATEGIST
        assert result.target == RouteTarget.PM


# ── Helper function tests ──────────────────────────────────────────────


class TestIsQuestionEmbed:
    """is_question_embed extracts agent_id and request_id from question embeds."""

    def test_valid_question_embed(self):
        """Embed with matching title and footer returns (agent_id, request_id)."""
        embed = MagicMock()
        embed.title = "Question from frontend"
        embed.footer = MagicMock()
        embed.footer.text = "Request: abc-123"

        msg = _make_message(embeds=[embed])
        result = is_question_embed(msg)
        assert result == ("frontend", "abc-123")

    def test_no_embeds(self):
        """Message with no embeds returns None."""
        msg = _make_message()
        result = is_question_embed(msg)
        assert result is None

    def test_wrong_embed_title(self):
        """Embed with non-matching title returns None."""
        embed = MagicMock()
        embed.title = "Some other title"
        embed.footer = MagicMock()
        embed.footer.text = "Request: abc-123"

        msg = _make_message(embeds=[embed])
        result = is_question_embed(msg)
        assert result is None


class TestExtractEntityFromPrefix:
    """extract_entity_from_prefix parses entity prefixes from message content."""

    def test_pm_prefix(self):
        """[PM] prefix returns ('pm', None)."""
        result = extract_entity_from_prefix("[PM] Here is my answer")
        assert result == ("pm", None)

    def test_agent_prefix(self):
        """[agent-frontend] prefix returns ('agent', 'frontend')."""
        result = extract_entity_from_prefix("[agent-frontend] What should I do?")
        assert result == ("agent", "frontend")

    def test_no_prefix(self):
        """Content without prefix returns None."""
        result = extract_entity_from_prefix("Just a regular message")
        assert result is None

    def test_empty_content(self):
        """Empty content returns None."""
        result = extract_entity_from_prefix("")
        assert result is None
