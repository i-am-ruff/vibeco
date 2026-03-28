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
    """Create a mock VcoBot with standard attributes (v2: CompanyRoot)."""
    bot = MagicMock()
    bot.project_dir = Path("/tmp/testproject")
    bot.project_config = _make_config()
    bot._ready_flag = ready
    bot.is_bot_ready = ready
    bot.company_root = MagicMock()
    bot.company_root._find_container = AsyncMock(return_value=MagicMock(state="running"))
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
    async def test_new_project_no_agents_yaml(self, tmp_path):
        """Reports error when agents.yaml not found."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        with patch("vcompany.shared.paths.PROJECTS_BASE", tmp_path):
            (tmp_path / "myapp").mkdir()  # dir exists but no agents.yaml
            await cog.new_project.callback(cog, interaction, name="myapp")

        interaction.response.defer.assert_called_once()
        sent_text = interaction.followup.send.call_args[0][0]
        assert "agents.yaml" in sent_text.lower()


class TestDispatch:
    """/dispatch routes through CompanyRoot supervision tree (DISC-04, MIGR-01)."""

    @pytest.mark.asyncio
    async def test_dispatch_single(self):
        """Dispatches a single agent by checking container state via CompanyRoot."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.dispatch_cmd.callback(cog, interaction, agent_id="agent-1")

        bot.company_root._find_container.assert_called_once_with("agent-1")
        assert "agent-1" in interaction.followup.send.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_dispatch_all(self):
        """Dispatching all agents returns supervision tree message."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.dispatch_cmd.callback(cog, interaction, agent_id="all")

        assert "supervision tree" in interaction.followup.send.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_dispatch_no_company_root(self):
        """Reports error when company_root is None."""
        bot = _make_bot()
        bot.company_root = None
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.dispatch_cmd.callback(cog, interaction, agent_id="agent-1")

        call_args = interaction.response.send_message.call_args
        assert "not initialized" in call_args[0][0].lower()

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


class TestStatus:
    """/status shows project status embed (DISC-05)."""

    @pytest.mark.asyncio
    @patch("vcompany.bot.cogs.commands.asyncio.to_thread", new_callable=AsyncMock)
    @patch("vcompany.bot.cogs.commands.build_status_embed")
    async def test_status(self, mock_build_embed, mock_to_thread):
        """Generates status via to_thread and sends embed."""
        bot = _make_bot()
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        mock_to_thread.return_value = "## Agent 1\nRunning"
        mock_embed = MagicMock(spec=discord.Embed)
        mock_build_embed.return_value = mock_embed

        await cog.status_cmd.callback(cog, interaction)

        mock_to_thread.assert_called_once()
        # Verify to_thread called with generate_project_status
        call_args = mock_to_thread.call_args[0]
        assert call_args[0].__name__ == "generate_project_status"

        mock_build_embed.assert_called_once_with("## Agent 1\nRunning")
        interaction.followup.send.assert_called_once_with(embed=mock_embed)


class TestKill:
    """/kill routes through CompanyRoot supervision tree (DISC-07, MIGR-01)."""

    @pytest.mark.asyncio
    @patch("vcompany.bot.cogs.commands.ConfirmView")
    async def test_kill_confirmed(self, MockConfirmView):
        """Kills agent by stopping container after confirmation."""
        bot = _make_bot()
        mock_container = AsyncMock()
        bot.company_root._find_container = AsyncMock(return_value=mock_container)
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        mock_view = MagicMock()
        mock_view.wait = AsyncMock()
        mock_view.value = True
        MockConfirmView.return_value = mock_view

        await cog.kill_cmd.callback(cog, interaction, agent_id="agent-1")

        # Verify confirmation was sent via response.send_message
        first_send = interaction.response.send_message.call_args
        assert "kill agent" in first_send[0][0].lower()
        assert first_send[1]["view"] is mock_view

        # Verify container.stop() was called
        mock_container.stop.assert_called_once()

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
    async def test_kill_no_company_root(self):
        """Reports error when company_root is None."""
        bot = _make_bot()
        bot.company_root = None
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.kill_cmd.callback(cog, interaction, agent_id="agent-1")

        call_args = interaction.response.send_message.call_args
        assert "not initialized" in call_args[0][0].lower()


class TestRelaunch:
    """/relaunch routes through CompanyRoot supervision tree (DISC-08, MIGR-01)."""

    @pytest.mark.asyncio
    async def test_relaunch(self):
        """Relaunches agent by stopping container (supervisor restarts)."""
        bot = _make_bot()
        mock_container = AsyncMock()
        bot.company_root._find_container = AsyncMock(return_value=mock_container)
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.relaunch_cmd.callback(cog, interaction, agent_id="agent-1")

        mock_container.stop.assert_called_once()
        assert "stopped" in interaction.followup.send.call_args[0][0].lower()

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
    async def test_relaunch_no_company_root(self):
        """Reports error when company_root is None."""
        bot = _make_bot()
        bot.company_root = None
        cog = CommandsCog(bot)
        interaction = _make_interaction()

        await cog.relaunch_cmd.callback(cog, interaction, agent_id="agent-1")

        call_args = interaction.response.send_message.call_args
        assert "not initialized" in call_args[0][0].lower()


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
            "new-project", "dispatch", "status", "kill",
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
