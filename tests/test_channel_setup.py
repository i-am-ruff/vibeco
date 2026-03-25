"""Tests for channel setup logic (DISC-02)."""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from vcompany.bot.channel_setup import setup_project_channels, _STANDARD_CHANNELS
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


class TestSetupProjectChannels:
    """setup_project_channels creates category and channels with permissions."""

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
    async def test_creates_all_standard_channels(self):
        """Creates all 5 standard channels (D-17)."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_guild.create_category_channel = AsyncMock(return_value=mock_category)
        mock_category.create_text_channel = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        await setup_project_channels(
            mock_guild, "myproject", mock_role, _make_agents()
        )

        # Extract all channel names created
        created_names = [
            call.args[0]
            for call in mock_category.create_text_channel.call_args_list
        ]

        for ch in _STANDARD_CHANNELS:
            assert ch in created_names, f"Missing standard channel: {ch}"

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
        """Total channels = 5 standard + 2 agent = 7."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_guild.create_category_channel = AsyncMock(return_value=mock_category)
        mock_category.create_text_channel = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        await setup_project_channels(
            mock_guild, "myproject", mock_role, _make_agents()
        )

        assert mock_category.create_text_channel.call_count == 7

    @pytest.mark.asyncio
    async def test_permission_overwrites(self):
        """Category has correct permission overwrites (D-19)."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role = mock_default_role

        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_guild.create_category_channel = AsyncMock(return_value=mock_category)
        mock_category.create_text_channel = AsyncMock()

        mock_owner_role = MagicMock(spec=discord.Role)

        await setup_project_channels(
            mock_guild, "myproject", mock_owner_role, _make_agents()
        )

        # Get the overwrites kwarg from category creation
        call_kwargs = mock_guild.create_category_channel.call_args.kwargs
        overwrites = call_kwargs["overwrites"]

        # Default role: view=True, send=False
        default_overwrite = overwrites[mock_default_role]
        assert default_overwrite.view_channel is True
        assert default_overwrite.send_messages is False

        # Owner role: view=True, send=True, manage=True
        owner_overwrite = overwrites[mock_owner_role]
        assert owner_overwrite.view_channel is True
        assert owner_overwrite.send_messages is True
        assert owner_overwrite.manage_messages is True

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
