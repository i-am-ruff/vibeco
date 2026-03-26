"""Tests for channel setup logic (DISC-02)."""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from vcompany.bot.channel_setup import (
    setup_project_channels,
    setup_system_channels,
    _PROJECT_CHANNELS,
    _SYSTEM_CHANNELS,
)
from vcompany.models.config import AgentConfig


def _make_agents() -> list[AgentConfig]:
    """Create test agents."""
    return [
        AgentConfig(
            id="frontend",
            role="frontend",
            owns=["src/frontend/"],
            consumes="INTERFACES.md",
            gsd_mode="full",
            system_prompt="Frontend agent.",
        ),
        AgentConfig(
            id="backend",
            role="backend",
            owns=["src/backend/"],
            consumes="INTERFACES.md",
            gsd_mode="full",
            system_prompt="Backend agent.",
        ),
    ]


class TestSetupSystemChannels:
    """setup_system_channels creates vco-system category on startup."""

    @pytest.mark.asyncio
    async def test_creates_system_category(self):
        """Creates vco-system category when it doesn't exist."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.categories = []  # No existing categories
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_category.channels = []
        mock_guild.create_category_channel = AsyncMock(return_value=mock_category)
        mock_category.create_text_channel = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        await setup_system_channels(mock_guild, mock_role)

        mock_guild.create_category_channel.assert_called_once()
        assert mock_guild.create_category_channel.call_args.args[0] == "vco-system"

    @pytest.mark.asyncio
    async def test_skips_existing_category(self):
        """Reuses existing vco-system category."""
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_category.name = "vco-system"
        mock_category.channels = []
        mock_category.create_text_channel = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.categories = [mock_category]
        mock_guild.create_category_channel = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        # Patch discord.utils.get to find the category
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "vcompany.bot.channel_setup.discord.utils.get",
            side_effect=lambda seq, **kw: mock_category if kw.get("name") == "vco-system" else None,
        ):
            await setup_system_channels(mock_guild, mock_role)

        mock_guild.create_category_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_all_system_channels(self):
        """Creates strategist, alerts, readme channels."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.categories = []
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_category.channels = []
        mock_guild.create_category_channel = AsyncMock(return_value=mock_category)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_category.create_text_channel = AsyncMock(return_value=mock_channel)

        mock_role = MagicMock(spec=discord.Role)

        result = await setup_system_channels(mock_guild, mock_role)

        assert mock_category.create_text_channel.call_count == len(_SYSTEM_CHANNELS)
        created_names = [
            call.args[0] for call in mock_category.create_text_channel.call_args_list
        ]
        for ch in _SYSTEM_CHANNELS:
            assert ch in created_names

    @pytest.mark.asyncio
    async def test_returns_channel_dict(self):
        """Returns dict mapping channel names to TextChannel objects."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.categories = []
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_category.channels = []
        mock_guild.create_category_channel = AsyncMock(return_value=mock_category)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_category.create_text_channel = AsyncMock(return_value=mock_channel)

        mock_role = MagicMock(spec=discord.Role)

        result = await setup_system_channels(mock_guild, mock_role)

        assert isinstance(result, dict)
        for ch in _SYSTEM_CHANNELS:
            assert ch in result


class TestSetupProjectChannels:
    """setup_project_channels creates project category and channels."""

    @pytest.mark.asyncio
    async def test_creates_category_with_project_name(self):
        """Category is named vco-{project_name} (D-16)."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_guild.create_category_channel = AsyncMock(return_value=mock_category)
        mock_category.create_text_channel = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        await setup_project_channels(
            mock_guild, "myproject", mock_role, _make_agents()
        )

        mock_guild.create_category_channel.assert_called_once()
        call_args = mock_guild.create_category_channel.call_args
        assert call_args.args[0] == "vco-myproject"

    @pytest.mark.asyncio
    async def test_creates_project_channels(self):
        """Creates project-specific channels (plan-review, standup, decisions)."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_guild.create_category_channel = AsyncMock(return_value=mock_category)
        mock_category.create_text_channel = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        await setup_project_channels(
            mock_guild, "myproject", mock_role, _make_agents()
        )

        created_names = [
            call.args[0]
            for call in mock_category.create_text_channel.call_args_list
        ]

        for ch in _PROJECT_CHANNELS:
            assert ch in created_names, f"Missing project channel: {ch}"

    @pytest.mark.asyncio
    async def test_creates_per_agent_channels(self):
        """Creates agent-{id} channels for each agent (D-17)."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_guild.create_category_channel = AsyncMock(return_value=mock_category)
        mock_category.create_text_channel = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)
        agents = _make_agents()

        await setup_project_channels(mock_guild, "myproject", mock_role, agents)

        created_names = [
            call.args[0]
            for call in mock_category.create_text_channel.call_args_list
        ]

        assert "agent-frontend" in created_names
        assert "agent-backend" in created_names

    @pytest.mark.asyncio
    async def test_total_channel_count(self):
        """Total channels = 3 project + 2 agent = 5."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_guild.create_category_channel = AsyncMock(return_value=mock_category)
        mock_category.create_text_channel = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        await setup_project_channels(
            mock_guild, "myproject", mock_role, _make_agents()
        )

        # 3 project channels + 2 agent channels = 5
        assert mock_category.create_text_channel.call_count == 5

    @pytest.mark.asyncio
    async def test_returns_category(self):
        """Function returns the created CategoryChannel."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_guild.create_category_channel = AsyncMock(return_value=mock_category)
        mock_category.create_text_channel = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        result = await setup_project_channels(
            mock_guild, "myproject", mock_role, _make_agents()
        )

        assert result is mock_category
