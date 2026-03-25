"""Channel setup: creates project category and channels with permissions.

Implements D-16, D-17, D-18, D-19 (DISC-02).
"""

from __future__ import annotations

import logging

import discord

from vcompany.models.config import AgentConfig

logger = logging.getLogger("vcompany.bot.channel_setup")

# Standard channels created in every project category (D-17)
_STANDARD_CHANNELS: list[str] = [
    "strategist",
    "plan-review",
    "standup",
    "alerts",
    "decisions",
]


async def setup_project_channels(
    guild: discord.Guild,
    project_name: str,
    owner_role: discord.Role,
    agents: list[AgentConfig],
) -> discord.CategoryChannel:
    """Create a project category with standard and per-agent channels.

    Creates category vco-{project_name} with permission overwrites:
    - default_role (everyone): view_channel=True, send_messages=False (D-19 Viewer)
    - owner_role: view_channel=True, send_messages=True, manage_messages=True (D-19 Owner)

    Creates 5 standard channels plus one agent-{id} channel per agent.

    Args:
        guild: Discord guild to create channels in.
        project_name: Project name (used in category name).
        owner_role: The vco-owner role for permission overwrites.
        agents: List of AgentConfig for per-agent channel creation.

    Returns:
        The created CategoryChannel.
    """
    # Permission overwrites (D-19)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
        ),
        owner_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_messages=True,
        ),
    }

    # Create category (D-16)
    category_name = f"vco-{project_name}"
    category = await guild.create_category_channel(
        category_name,
        overwrites=overwrites,
    )
    logger.info("Created category: %s", category_name)

    # Create standard channels (D-17)
    for channel_name in _STANDARD_CHANNELS:
        await category.create_text_channel(channel_name)
        logger.info("Created channel: #%s", channel_name)

    # Create per-agent channels (D-17)
    for agent in agents:
        agent_channel_name = f"agent-{agent.id}"
        await category.create_text_channel(agent_channel_name)
        logger.info("Created agent channel: #%s", agent_channel_name)

    return category
