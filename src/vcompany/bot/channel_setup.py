"""Channel setup: creates system and project channels with permissions.

System channels (created on bot startup, always present):
  vco-system category: #strategist, #alerts, #readme

Project channels (created per-project via /new-project):
  vco-{project} category: #plan-review, #standup, #decisions, #agent-{id}...

Implements D-16, D-17, D-18, D-19 (DISC-02).
"""

from __future__ import annotations

import logging

import discord

from vcompany.models.config import AgentConfig

logger = logging.getLogger("vcompany.bot.channel_setup")

# System channels: always present, not tied to any project
_SYSTEM_CATEGORY = "vco-system"
_SYSTEM_CHANNELS: list[str] = [
    "strategist",
    "alerts",
    "readme",
    "workflow-master",
]

_README_CONTENT = """# Welcome to vCompany

**vCompany** is an autonomous multi-agent development system. This Discord server is your control center.

## How to use

1. **Talk to the Strategist** in #strategist — your AI CEO-friend who knows the project, the plan, and how vCompany works
2. **Create a project** with `/new-project <name>` — sets up agent channels and deploys agents
3. **Monitor progress** with `/status` — see what all agents are doing
4. **Run standups** with `/standup` — interactive review with agent threads

## Channels

- **#strategist** — Chat with the Strategist AI (always available)
- **#alerts** — System alerts (crashes, stuck agents, timeouts)
- **#readme** — This channel (system info)
- **#workflow-master** — Self-improvement dev agent (always available)

When you create a project, additional channels appear:
- **#plan-review** — Agent plans posted for approval
- **#standup** — Group standup threads
- **#decisions** — PM/Strategist decision log
- **#agent-{id}** — Per-agent checkin logs

## Commands

- `/new-project <name>` — Create a new project
- `/dispatch <agent|all>` — Launch agent sessions
- `/status` — Show agent fleet status
- `/kill <agent>` — Stop an agent
- `/relaunch <agent>` — Restart an agent
- `/standup` — Interactive group standup
- `/integrate` — Merge agent branches and run tests
"""

# Project-specific channels (created per project)
_PROJECT_CHANNELS: list[str] = [
    "plan-review",
    "standup",
    "decisions",
    "backlog",
]


async def setup_system_channels(
    guild: discord.Guild,
    owner_role: discord.Role,
) -> dict[str, discord.TextChannel]:
    """Create the global vco-system category and channels on bot startup.

    Idempotent — skips channels that already exist.

    Args:
        guild: Discord guild.
        owner_role: The vco-owner role for permission overwrites.

    Returns:
        Dict of channel_name -> TextChannel for the system channels.
    """
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

    # Find or create category
    category = discord.utils.get(guild.categories, name=_SYSTEM_CATEGORY)
    if category is None:
        category = await guild.create_category_channel(
            _SYSTEM_CATEGORY,
            overwrites=overwrites,
        )
        logger.info("Created system category: %s", _SYSTEM_CATEGORY)
    else:
        logger.info("System category already exists: %s", _SYSTEM_CATEGORY)

    # Create system channels (idempotent)
    channels: dict[str, discord.TextChannel] = {}
    for channel_name in _SYSTEM_CHANNELS:
        existing = discord.utils.get(category.channels, name=channel_name)
        if existing is None:
            ch = await category.create_text_channel(channel_name)
            logger.info("Created system channel: #%s", channel_name)

            # Post readme content to #readme on creation
            if channel_name == "readme":
                await ch.send(_README_CONTENT)
                logger.info("Posted readme content to #readme")

            channels[channel_name] = ch
        else:
            logger.info("System channel already exists: #%s", channel_name)
            channels[channel_name] = existing

    return channels


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

    # Create project-specific channels (D-17)
    for channel_name in _PROJECT_CHANNELS:
        await category.create_text_channel(channel_name)
        logger.info("Created channel: #%s", channel_name)

    # Create per-agent channels (D-17)
    for agent in agents:
        agent_channel_name = f"agent-{agent.id}"
        await category.create_text_channel(agent_channel_name)
        logger.info("Created agent channel: #%s", agent_channel_name)

    return category


# Category for Strategist-dispatched task agents
_TASKS_CATEGORY = "vco-tasks"


async def setup_task_channel(
    guild: discord.Guild,
    task_id: str,
) -> discord.TextChannel | None:
    """Create a #task-{id} channel under the vco-tasks category.

    Creates the vco-tasks category if it doesn't exist. Idempotent — returns
    existing channel if already present.

    Args:
        guild: Discord guild.
        task_id: Task agent identifier.

    Returns:
        The created (or existing) TextChannel, or None on failure.
    """
    # Find or create category
    category = discord.utils.get(guild.categories, name=_TASKS_CATEGORY)
    if category is None:
        owner_role = discord.utils.get(guild.roles, name="vco-owner")
        overwrites = {}
        if owner_role:
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
        category = await guild.create_category_channel(
            _TASKS_CATEGORY, overwrites=overwrites
        )
        logger.info("Created tasks category: %s", _TASKS_CATEGORY)

    # Find or create channel
    channel_name = f"task-{task_id}"
    existing = discord.utils.get(category.channels, name=channel_name)
    if existing is not None:
        logger.info("Task channel already exists: #%s", channel_name)
        return existing

    channel = await category.create_text_channel(channel_name)
    logger.info("Created task channel: #%s", channel_name)
    return channel
