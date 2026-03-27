"""Message routing framework for Discord messages (D-06, D-07, D-08).

Determines which entity (Strategist, PM, Agent, Owner) should process
each Discord message based on priority rules:

1. Reply-based: Reply to a specific message routes to that entity
2. Mention-based: @mention routes to the mentioned entity
3. Channel-owner default: #agent-{id} routes to that agent
4. Strategist default: #strategist routes to Strategist
5. Otherwise: IGNORE

This module is standalone -- no imports from vcompany.bot.cogs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class RouteTarget(str, Enum):
    """Target entity for a routed message."""

    STRATEGIST = "strategist"
    AGENT = "agent"
    PM = "pm"
    OWNER_UNADDRESSED = "owner_unaddressed"
    IGNORE = "ignore"


@dataclass
class RouteResult:
    """Result of routing a Discord message."""

    target: RouteTarget
    entity_id: str | None = None
    is_reply_to: int | None = None
    is_mention_of: str | None = None


@dataclass
class EntityRegistry:
    """Registry of known entities for routing decisions.

    Attributes:
        bot_user_id: Discord user ID of the bot itself.
        entity_prefixes: Mapping of entity_id to message prefix (e.g. "pm" -> "[PM]").
        strategist_user_ids: Set of Discord user IDs that represent the Strategist.
    """

    bot_user_id: int
    entity_prefixes: dict[str, str] = field(default_factory=dict)
    strategist_user_ids: set[int] = field(default_factory=set)


# ── Prefix patterns ──────────────────────────────────────────────────

_PM_PREFIX = "[PM]"
_AGENT_PREFIX_RE = re.compile(r"^\[agent-([a-zA-Z0-9_-]+)\]")


def extract_entity_from_prefix(content: str) -> tuple[str, str | None] | None:
    """Parse entity prefix from message content start.

    Returns:
        ("pm", None) for [PM] prefix
        ("agent", entity_id) for [agent-{id}] prefix
        None if no recognized prefix
    """
    if not content:
        return None

    if content.startswith(_PM_PREFIX):
        return ("pm", None)

    m = _AGENT_PREFIX_RE.match(content)
    if m:
        return ("agent", m.group(1))

    return None


def is_question_embed(message) -> tuple[str, str] | None:
    """Check if a message has a question embed from an agent.

    Looks for embeds with title "Question from {agent_id}" and
    footer "Request: {request_id}".

    Returns:
        (agent_id, request_id) if found, None otherwise.
    """
    if not message.embeds:
        return None

    for embed in message.embeds:
        title = getattr(embed, "title", None)
        if not title or not title.startswith("Question from "):
            continue

        footer = getattr(embed, "footer", None)
        if footer is None:
            continue

        footer_text = getattr(footer, "text", None)
        if not footer_text or not footer_text.startswith("Request: "):
            continue

        agent_id = title[len("Question from "):]
        request_id = footer_text[len("Request: "):]
        return (agent_id, request_id)

    return None


def route_message(
    message,
    channel_name: str,
    registry: EntityRegistry,
    *,
    replied_to_content: str | None = None,
) -> RouteResult:
    """Route a Discord message to the appropriate entity.

    Priority order (D-06):
    1. Bot's own non-system messages -> IGNORE
    2. Webhook messages -> IGNORE
    3. Reply-based routing (check replied-to message entity)
    4. Mention-based routing (@Strategist, @PM)
    5. Channel-owner default (#agent-{id} -> that agent)
    6. Strategist default (#strategist -> Strategist)
    7. Otherwise -> IGNORE

    Args:
        message: Discord message object.
        channel_name: Name of the channel the message was sent in.
        registry: EntityRegistry with known entities.
        replied_to_content: Content of the message being replied to (if any).

    Returns:
        RouteResult indicating where to route the message.
    """
    # Rule 1a: Bot's own non-system messages -> IGNORE
    if (
        getattr(message.author, "bot", False)
        and message.author.id == registry.bot_user_id
        and not message.content.startswith("[system]")
    ):
        return RouteResult(target=RouteTarget.IGNORE)

    # Rule 1b: Webhook messages -> IGNORE
    if message.webhook_id is not None:
        return RouteResult(target=RouteTarget.IGNORE)

    # Rule 2: Reply-based routing (D-06 rule 1)
    if (
        message.reference is not None
        and getattr(message.reference, "message_id", None) is not None
    ):
        ref_id = message.reference.message_id
        if replied_to_content is not None:
            entity = extract_entity_from_prefix(replied_to_content)
            if entity is not None:
                entity_type, entity_id = entity
                if entity_type == "pm":
                    return RouteResult(
                        target=RouteTarget.PM,
                        is_reply_to=ref_id,
                    )
                elif entity_type == "agent":
                    return RouteResult(
                        target=RouteTarget.AGENT,
                        entity_id=entity_id,
                        is_reply_to=ref_id,
                    )
            # No recognized prefix -> Strategist (speaks without prefix per D-05)
            return RouteResult(
                target=RouteTarget.STRATEGIST,
                is_reply_to=ref_id,
            )
        # No replied_to_content available -> default to Strategist for replies
        return RouteResult(
            target=RouteTarget.STRATEGIST,
            is_reply_to=ref_id,
        )

    # Rule 3: Mention-based routing (D-06 rule 2)
    # Check for @PM in content (PM is not a Discord user)
    if "@PM" in message.content:
        return RouteResult(
            target=RouteTarget.PM,
            is_mention_of="pm",
        )

    # Check for bot/@Strategist mentions
    mentions = getattr(message, "mentions", [])
    for mention in mentions:
        if mention.id in registry.strategist_user_ids or mention.id == registry.bot_user_id:
            return RouteResult(
                target=RouteTarget.STRATEGIST,
                is_mention_of="strategist",
            )

    # Rule 4: Channel-owner default (D-06 rule 3)
    if channel_name.startswith("agent-"):
        agent_id = channel_name[len("agent-"):]
        return RouteResult(
            target=RouteTarget.AGENT,
            entity_id=agent_id,
        )

    # Rule 5: Strategist default (D-06 rule 4)
    if channel_name == "strategist":
        return RouteResult(target=RouteTarget.STRATEGIST)

    # Rule 6: Unrecognized channel -> IGNORE
    return RouteResult(target=RouteTarget.IGNORE)
