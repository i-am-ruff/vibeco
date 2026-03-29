"""Tests for CommandsCog operator slash commands (DISC-03 through DISC-11, MIGR-01)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from vcompany.bot.cogs.commands import CommandsCog
from vcompany.models.config import AgentConfig, ProjectConfig


def _make_config() -> ProjectConfig:
    """Create a minimal ProjectConfig for testing."""
    return ProjectConfig(
        project="testproject",
        repo="https://github.com/test/repo",
        agents=[
            AgentConfig(
                id="agent-1",
                role="backend",
                owns=["src/backend/"],
                consumes="INTERFACES.md",
                gsd_mode="full",
                system_prompt="You are a backend agent.",
            ),
            AgentConfig(
                id="agent-2",
                role="frontend",
                owns=["src/frontend/"],
                consumes="INTERFACES.md",
                gsd_mode="full",
                system_prompt="You are a frontend agent.",
            ),
        ],
    )


def _make_bot(*, ready: bool = True) -> MagicMock:
    """Create a mock VcoBot with standard attributes (Phase 22: RuntimeAPI via daemon)."""
    bot = MagicMock()
    bot.project_dir = Path("/tmp/testproject")
    bot.project_config = _make_config()
    bot._ready_flag = ready
    bot.is_bot_ready = ready
    bot._daemon = MagicMock()
    bot._daemon.runtime_api = AsyncMock()
    return bot


def _make_interaction(*, guild: bool = True) -> MagicMock:
    """Create a mock discord.Interaction for slash commands."""
    interaction = MagicMock(spec=discord.Interaction)

    # response mock
    response = MagicMock()
    response.send_message = AsyncMock()
    response.defer = AsyncMock()
    response.is_done = MagicMock(return_value=False)
    interaction.response = response

    # followup mock
    followup = MagicMock()
    followup.send = AsyncMock()
    interaction.followup = followup

    # user mock (as Member with vco-owner role)
    user = MagicMock(spec=discord.Member)
    user.id = 12345
    mock_role = MagicMock(spec=discord.Role)
    mock_role.name = "vco-owner"
    user.roles = [mock_role]
    interaction.user = user

    if guild:
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.roles = [mock_role]
        mock_guild.text_channels = []
        interaction.guild = mock_guild
    else:
        interaction.guild = None

    return interaction


class TestInteractionCheck:
    """interaction_check rejects commands when bot is not ready (Pitfall 6)."""

    @pytest.mark.asyncio
    async def test_rejects_when_not_ready(self):
        """interaction_check returns False and sends ephemeral when bot not ready."""
        bot = _make_bot(ready=False)
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        result = await cog.interaction_check(interaction)

        assert result is False
        interaction.response.send_message.assert_called_once_with(
            "Bot is starting up, please wait...", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_allows_when_ready(self):
        """interaction_check returns True when bot is ready."""
        bot = _make_bot(ready=True)
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        result = await cog.interaction_check(interaction)

        assert result is True


class TestNewProject:
    """/new-project runs full project pipeline (DISC-03)."""

    @pytest.mark.asyncio
    async def test_new_project_no_guild(self):
        """Rejects when used outside a server."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction(guild=False)

        await cog.new_project.callback(cog, interaction, name="myapp")

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "server" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_new_project_no_agents_yaml(self):
        """Reports error when RuntimeAPI raises for missing agents.yaml."""
        bot = _make_bot()
        bot._daemon.runtime_api.new_project_from_name = AsyncMock(
            side_effect=FileNotFoundError("agents.yaml not found")
        )
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.new_project.callback(cog, interaction, name="myapp")

        interaction.response.defer.assert_called_once()
        # Error reported via embed (send_message since is_done returns False in mock)
        assert interaction.response.send_message.called or interaction.followup.send.called


class TestDispatch:
    """/dispatch routes through RuntimeAPI (DISC-04, EXTRACT-04)."""

    @pytest.mark.asyncio
    async def test_dispatch_single_agent_via_runtime_api(self):
        """Dispatching a single agent calls runtime_api.dispatch()."""
        bot = _make_bot()
        bot._daemon.runtime_api.dispatch = AsyncMock()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.dispatch_cmd.callback(cog, interaction, agent_id="agent-1")

        bot._daemon.runtime_api.dispatch.assert_called_once_with("agent-1")
        msg = interaction.followup.send.call_args[0][0]
        assert "agent-1" in msg.lower()
        assert "dispatched" in msg.lower()

    @pytest.mark.asyncio
    async def test_dispatch_all_shows_agent_states(self):
        """Dispatching all agents reports states via runtime_api.get_agent_states()."""
        bot = _make_bot()
        bot._daemon.runtime_api.get_agent_states = AsyncMock(return_value=[
            {"agent_id": "agent-1", "state": "running", "agent_type": "gsd"},
        ])
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.dispatch_cmd.callback(cog, interaction, agent_id="all")

        msg = interaction.followup.send.call_args[0][0]
        assert "agent-1" in msg.lower()
        assert "running" in msg.lower()

    @pytest.mark.asyncio
    async def test_dispatch_no_daemon(self):
        """Reports error when daemon runtime_api is None."""
        bot = _make_bot()
        bot._daemon = None
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.dispatch_cmd.callback(cog, interaction, agent_id="agent-1")

        call_args = interaction.response.send_message.call_args
        assert "not ready" in call_args[0][0].lower() or "daemon" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_dispatch_unknown_agent(self):
        """Reports error for unknown agent ID."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.dispatch_cmd.callback(cog, interaction, agent_id="nonexistent")

        assert "unknown agent" in interaction.followup.send.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_dispatch_no_project_config(self):
        """Reports no-project message when config is None."""
        bot = _make_bot()
        bot.project_config = None
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.dispatch_cmd.callback(cog, interaction, agent_id="agent-1")

        call_args = interaction.response.send_message.call_args
        assert "no project" in call_args[0][0].lower()


class TestKill:
    """/kill routes through RuntimeAPI (DISC-07, EXTRACT-04)."""

    @pytest.mark.asyncio
    @patch("vcompany.bot.cogs.commands.ConfirmView")
    async def test_kill_confirmed(self, MockConfirmView):
        """Kills agent via runtime_api.kill() after confirmation."""
        bot = _make_bot()
        bot._daemon.runtime_api.kill = AsyncMock()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        mock_view = MagicMock()
        mock_view.wait = AsyncMock()
        mock_view.value = True
        MockConfirmView.return_value = mock_view

        await cog.kill_cmd.callback(cog, interaction, agent_id="agent-1")

        # Verify confirmation was sent via response.send_message
        first_send = interaction.response.send_message.call_args
        assert "kill" in first_send[0][0].lower()
        assert first_send[1]["view"] is mock_view

        # Verify runtime_api.kill() was called
        bot._daemon.runtime_api.kill.assert_called_once_with("agent-1")

        # Verify success message via followup
        last_followup = interaction.followup.send.call_args
        assert "stopped" in last_followup[0][0].lower()

    @pytest.mark.asyncio
    @patch("vcompany.bot.cogs.commands.ConfirmView")
    async def test_kill_cancelled(self, MockConfirmView):
        """Does not kill agent when cancelled."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        mock_view = MagicMock()
        mock_view.wait = AsyncMock()
        mock_view.value = False
        MockConfirmView.return_value = mock_view

        await cog.kill_cmd.callback(cog, interaction, agent_id="agent-1")

        # Verify "cancelled" message via followup
        last_followup = interaction.followup.send.call_args
        assert "cancelled" in last_followup[0][0].lower()

    @pytest.mark.asyncio
    @patch("vcompany.bot.cogs.commands.ConfirmView")
    async def test_kill_timeout(self, MockConfirmView):
        """Treats timeout as cancellation."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        mock_view = MagicMock()
        mock_view.wait = AsyncMock()
        mock_view.value = None  # timeout
        MockConfirmView.return_value = mock_view

        await cog.kill_cmd.callback(cog, interaction, agent_id="agent-1")

        last_followup = interaction.followup.send.call_args
        assert "cancelled" in last_followup[0][0].lower()

    @pytest.mark.asyncio
    async def test_kill_no_daemon(self):
        """Reports error when daemon is None."""
        bot = _make_bot()
        bot._daemon = None
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.kill_cmd.callback(cog, interaction, agent_id="agent-1")

        call_args = interaction.response.send_message.call_args
        assert "not ready" in call_args[0][0].lower() or "daemon" in call_args[0][0].lower()


class TestRelaunch:
    """/relaunch routes through RuntimeAPI (DISC-08, EXTRACT-04)."""

    @pytest.mark.asyncio
    async def test_relaunch(self):
        """Relaunches agent via runtime_api.relaunch()."""
        bot = _make_bot()
        bot._daemon.runtime_api.relaunch = AsyncMock()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.relaunch_cmd.callback(cog, interaction, agent_id="agent-1")

        bot._daemon.runtime_api.relaunch.assert_called_once_with("agent-1")
        msg = interaction.followup.send.call_args[0][0].lower()
        assert "stopped" in msg
        assert "supervisor restart policy" in msg

    @pytest.mark.asyncio
    async def test_relaunch_unknown_agent(self):
        """Reports error for unknown agent ID."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.relaunch_cmd.callback(cog, interaction, agent_id="nonexistent")

        call_args = interaction.response.send_message.call_args
        assert "unknown agent" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_relaunch_no_daemon(self):
        """Reports error when daemon is None."""
        bot = _make_bot()
        bot._daemon = None
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.relaunch_cmd.callback(cog, interaction, agent_id="agent-1")

        call_args = interaction.response.send_message.call_args
        assert "not ready" in call_args[0][0].lower() or "daemon" in call_args[0][0].lower()


class TestStandup:
    """/standup triggers standup session (DISC-06, COMM-03)."""

    @pytest.mark.asyncio
    async def test_standup_calls_send(self):
        """Standup command sends a response."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.standup_cmd.callback(cog, interaction)

        # Should have sent some response (either response.send_message or followup.send)
        assert (
            interaction.response.send_message.called
            or interaction.followup.send.called
        )


class TestIntegrate:
    """/integrate triggers integration pipeline (DISC-09, INTG-02)."""

    @pytest.mark.asyncio
    @patch("vcompany.bot.cogs.commands.ConfirmView")
    async def test_integrate_sends_response(self, MockConfirmView):
        """Integrate command sends a response after confirmation."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        mock_view = MagicMock()
        mock_view.wait = AsyncMock()
        mock_view.value = True
        MockConfirmView.return_value = mock_view

        await cog.integrate_cmd.callback(cog, interaction)

        assert (
            interaction.response.send_message.called
            or interaction.followup.send.called
        )

    @pytest.mark.asyncio
    @patch("vcompany.bot.cogs.commands.ConfirmView")
    async def test_integrate_cancelled(self, MockConfirmView):
        """Returns cancellation message when cancelled."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        mock_view = MagicMock()
        mock_view.wait = AsyncMock()
        mock_view.value = False
        MockConfirmView.return_value = mock_view

        await cog.integrate_cmd.callback(cog, interaction)

        last_followup = interaction.followup.send.call_args
        assert "cancelled" in last_followup[0][0].lower()


class TestRoleCheckUnauthorized:
    """Verify is_owner_app_check decorator is applied to all slash commands."""

    def test_all_commands_have_checks(self):
        """Every app command has at least one check (is_owner_app_check)."""
        bot = _make_bot()
        cog = CommandsCog(bot)

        command_names = [
            "new-project", "dispatch", "kill",
            "relaunch", "standup", "integrate",
        ]

        # For app_commands, iterate the cog's app_commands
        app_cmds = {cmd.name: cmd for cmd in cog.__cog_app_commands__}

        for cmd_name in command_names:
            cmd = app_cmds.get(cmd_name)
            assert cmd is not None, f"App command {cmd_name} not found"
            assert len(cmd.checks) > 0, (
                f"App command {cmd_name} has no checks (missing @is_owner_app_check)"
            )
