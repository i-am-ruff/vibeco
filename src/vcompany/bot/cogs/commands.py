"""CommandsCog: all operator slash commands for vCompany Discord bot.

Implements /new-project, /dispatch, /status, /standup, /kill, /relaunch, /integrate.
All commands gated by vco-owner role via app_commands checks (DISC-10).
All blocking calls wrapped in asyncio.to_thread (DISC-11).

Implements DISC-03 through DISC-11.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from vcompany.bot.channel_setup import setup_project_channels
from vcompany.bot.embeds import (
    build_alert_embed,
    build_conflict_embed,
    build_integration_embed,
    build_standup_embed,
    build_status_embed,
)
from vcompany.bot.permissions import is_owner_app_check
from vcompany.bot.views.confirm import ConfirmView
from vcompany.bot.views.standup_release import ReleaseView
from vcompany.communication.checkin import gather_checkin_data
from vcompany.communication.standup import StandupSession
from vcompany.integration.pipeline import IntegrationPipeline
from vcompany.monitor.status_generator import generate_project_status

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot

logger = logging.getLogger("vcompany.bot.cogs.commands")


def _no_project_msg() -> str:
    """Guidance message when no project is loaded."""
    return "No project loaded. Ask the Strategist in #strategist to help you set one up."


class CommandsCog(commands.Cog):
    """Operator slash commands for vCompany project orchestration.

    Every command requires vco-owner role. All AgentManager / filesystem
    operations use asyncio.to_thread to avoid blocking the event loop.
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot: VcoBot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Global check: reject commands if bot is not ready (Pitfall 6)."""
        if not self.bot.is_bot_ready:
            await interaction.response.send_message(
                "Bot is starting up, please wait...", ephemeral=True
            )
            return False
        return True

    # ── /new-project ──────────────────────────────────────────────────

    @app_commands.command(name="new-project", description="Create project channels and discussion thread")
    @app_commands.describe(name="Project name")
    @is_owner_app_check()
    async def new_project(self, interaction: discord.Interaction, name: str) -> None:
        """Create project channels and discussion thread (DISC-03)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message(
                    "This command can only be used in a server.", ephemeral=True
                )
                return

            # Defer since channel setup may be slow
            await interaction.response.defer()

            owner_role = discord.utils.get(guild.roles, name="vco-owner")
            if owner_role is None:
                await interaction.followup.send(
                    "Error: vco-owner role not found. Bot may not have initialized properly."
                )
                return

            await setup_project_channels(
                guild, name, owner_role, self.bot.project_config.agents
            )

            await interaction.followup.send(
                f"Project **{name}** created! Category and channels ready. "
                "Describe your product in #strategist."
            )
        except Exception as exc:
            logger.exception("Error in /new-project")
            embed = build_alert_embed("new-project error", str(exc), "error")
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)

    # ── /dispatch ─────────────────────────────────────────────────────

    @app_commands.command(name="dispatch", description="Dispatch an agent or all agents")
    @app_commands.describe(agent_id="Agent ID to dispatch, or 'all' for all agents")
    @is_owner_app_check()
    async def dispatch_cmd(self, interaction: discord.Interaction, agent_id: str) -> None:
        """Dispatch an agent or all agents (DISC-04)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            if self.bot.agent_manager is None:
                await interaction.response.send_message(
                    "Agent manager is not initialized.", ephemeral=True
                )
                return

            await interaction.response.defer()

            if agent_id == "all":
                results = await asyncio.to_thread(self.bot.agent_manager.dispatch_all)
                succeeded = sum(1 for r in results if r.success)
                failed = sum(1 for r in results if not r.success)
                await interaction.followup.send(
                    f"Dispatched all agents: {succeeded} succeeded, {failed} failed."
                )
            else:
                # Validate agent exists in config
                valid_ids = [a.id for a in self.bot.project_config.agents]
                if agent_id not in valid_ids:
                    await interaction.followup.send(
                        f"Unknown agent `{agent_id}`. Valid: {', '.join(valid_ids)}"
                    )
                    return

                result = await asyncio.to_thread(self.bot.agent_manager.dispatch, agent_id)
                if result.success:
                    await interaction.followup.send(
                        f"Agent **{agent_id}** dispatched successfully."
                    )
                else:
                    await interaction.followup.send(
                        f"Failed to dispatch **{agent_id}**: {result.error}"
                    )
        except Exception as exc:
            logger.exception("Error in /dispatch")
            embed = build_alert_embed("dispatch error", str(exc), "error")
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)

    # ── /status ───────────────────────────────────────────────────────

    @app_commands.command(name="status", description="Show project status")
    @is_owner_app_check()
    async def status_cmd(self, interaction: discord.Interaction) -> None:
        """Show project status as rich embed (DISC-05)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            await interaction.response.defer()
            status_text = await asyncio.to_thread(
                generate_project_status,
                self.bot.project_dir,
                self.bot.project_config,
            )
            embed = build_status_embed(status_text)
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            logger.exception("Error in /status")
            embed = build_alert_embed("status error", str(exc), "error")
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)

    # ── /kill ─────────────────────────────────────────────────────────

    @app_commands.command(name="kill", description="Kill an agent with confirmation")
    @app_commands.describe(agent_id="Agent ID to kill")
    @is_owner_app_check()
    async def kill_cmd(self, interaction: discord.Interaction, agent_id: str) -> None:
        """Kill an agent with confirmation (DISC-07)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            if self.bot.agent_manager is None:
                await interaction.response.send_message(
                    "Agent manager is not initialized.", ephemeral=True
                )
                return

            view = ConfirmView()
            view.interaction_user_id = interaction.user.id
            await interaction.response.send_message(
                f"Kill agent **{agent_id}**? This will terminate the session.",
                view=view,
            )
            await view.wait()

            if view.value is True:
                success = await asyncio.to_thread(self.bot.agent_manager.kill, agent_id)
                if success:
                    await interaction.followup.send(f"Agent **{agent_id}** killed.")
                else:
                    await interaction.followup.send(
                        f"Agent **{agent_id}** not found or already stopped."
                    )
            else:
                await interaction.followup.send("Kill cancelled.")
        except Exception as exc:
            logger.exception("Error in /kill")
            embed = build_alert_embed("kill error", str(exc), "error")
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)

    # ── /relaunch ─────────────────────────────────────────────────────

    @app_commands.command(name="relaunch", description="Relaunch an agent")
    @app_commands.describe(agent_id="Agent ID to relaunch")
    @is_owner_app_check()
    async def relaunch_cmd(self, interaction: discord.Interaction, agent_id: str) -> None:
        """Relaunch an agent (DISC-08)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            if self.bot.agent_manager is None:
                await interaction.response.send_message(
                    "Agent manager is not initialized.", ephemeral=True
                )
                return

            # Validate agent exists in config
            valid_ids = [a.id for a in self.bot.project_config.agents]
            if agent_id not in valid_ids:
                await interaction.response.send_message(
                    f"Unknown agent `{agent_id}`. Valid: {', '.join(valid_ids)}",
                    ephemeral=True,
                )
                return

            await interaction.response.defer()
            result = await asyncio.to_thread(self.bot.agent_manager.relaunch, agent_id)
            if result.success:
                await interaction.followup.send(
                    f"Agent **{agent_id}** relaunched successfully."
                )
            else:
                await interaction.followup.send(
                    f"Failed to relaunch **{agent_id}**: {result.error}"
                )
        except Exception as exc:
            logger.exception("Error in /relaunch")
            embed = build_alert_embed("relaunch error", str(exc), "error")
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)

    # ── /standup ──────────────────────────────────────────────────────

    @app_commands.command(name="standup", description="Trigger group standup")
    @is_owner_app_check()
    async def standup_cmd(self, interaction: discord.Interaction) -> None:
        """Trigger group standup per D-11 blocking interlock model (DISC-06, COMM-03)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "This command can only be used in a server.", ephemeral=True
                )
                return

            standup_channel = discord.utils.get(
                interaction.guild.text_channels, name="standup"
            )
            if not standup_channel:
                await interaction.response.send_message(
                    "Error: #standup channel not found.", ephemeral=True
                )
                return

            await interaction.response.defer()

            # Create standup session
            tmux = getattr(self.bot, "_tmux", None)
            session = StandupSession(tmux=tmux)
            self.bot._standup_session = session  # type: ignore[attr-defined]

            registry = getattr(self.bot, "_registry", None)
            if not registry:
                await interaction.followup.send("Error: No agent registry loaded.")
                return

            await standup_channel.send("**Standup Session Started**")

            # Create per-agent threads per COMM-03
            for agent in registry.agents:
                clone_dir = self.bot.project_dir / "clones" / agent.id
                checkin_data = (
                    gather_checkin_data(agent.id, clone_dir) if clone_dir.exists() else None
                )

                embed = build_standup_embed(
                    agent_id=agent.id,
                    phase=checkin_data.next_phase if checkin_data else "unknown",
                    status="active",
                    summary=checkin_data.summary if checkin_data else "No data",
                )

                thread = await standup_channel.create_thread(
                    name=f"standup-{agent.id}",
                    type=discord.ChannelType.public_thread,
                )
                release_view = ReleaseView(agent_id=agent.id)
                release_view.set_release_callback(session.release_agent)
                await thread.send(embed=embed, view=release_view)
                session.register_thread(agent.id, thread.id)

            await interaction.followup.send(
                f"Standup threads created for {len(registry.agents)} agents. "
                "Release each when ready."
            )

        except Exception as exc:
            logger.exception("Error in /standup")
            embed = build_alert_embed("standup error", str(exc), "error")
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Route owner messages in standup threads to agent tmux panes per COMM-04/COMM-05."""
        if message.author.bot:
            return

        session: StandupSession | None = getattr(self.bot, "_standup_session", None)
        if session is None or not session.is_active:
            return

        # Check if message is in a standup thread
        if not isinstance(message.channel, discord.Thread):
            return

        agent_id = session.get_agent_for_thread(message.channel.id)
        if agent_id is None:
            return

        # Route message to agent tmux pane per COMM-05/D-12
        registry = getattr(self.bot, "_registry", None)
        if registry:
            agent = next((a for a in registry.agents if a.id == agent_id), None)
            if agent and hasattr(agent, "pane_id") and agent.pane_id:
                success = await session.route_message_to_agent(
                    agent_id,
                    message.content,
                    agent.pane_id,
                )
                if success:
                    await message.add_reaction("\u2705")  # checkmark
                else:
                    await message.add_reaction("\u274c")  # cross

    # ── /integrate ────────────────────────────────────────────────────

    @app_commands.command(name="integrate", description="Trigger integration pipeline")
    @is_owner_app_check()
    async def integrate_cmd(self, interaction: discord.Interaction) -> None:
        """Trigger integration pipeline per D-01 interlock model (DISC-09)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            view = ConfirmView()
            view.interaction_user_id = interaction.user.id
            await interaction.response.send_message(
                "Trigger integration pipeline?", view=view
            )
            await view.wait()

            if view.value is not True:
                await interaction.followup.send("Integration cancelled.")
                return

            # Check if monitor is available and set pending
            monitor = self.bot.monitor_loop
            if monitor:
                if not monitor.all_agents_idle():
                    monitor.set_integration_pending(True)
                    await interaction.followup.send(
                        "Integration pending -- will trigger when all agents "
                        "complete their current phase."
                    )
                    return

            # Run pipeline immediately
            await interaction.followup.send("Starting integration pipeline...")
            project_dir = self.bot.project_dir
            agent_ids = [a.id for a in self.bot.project_config.agents]

            pipeline = IntegrationPipeline(
                project_dir=project_dir,
                agent_ids=agent_ids,
                pm=getattr(self.bot, "_pm", None),
            )
            result = await pipeline.run()

            # Handle result
            embed = build_integration_embed(result)
            await interaction.followup.send(embed=embed)

            if result.status == "test_failure" and result.attribution:
                agent_mgr = self.bot.agent_manager
                if agent_mgr:
                    for aid, tests in result.attribution.items():
                        if aid.startswith("_"):
                            continue
                        agent_mgr.dispatch_fix(aid, tests)
                    await interaction.followup.send(
                        "Fix tasks dispatched to responsible agents."
                    )

            if result.status == "merge_conflict":
                conflict_embed = build_conflict_embed(
                    agent_branches=[f"agent/{aid}" for aid in agent_ids],
                    conflict_files=result.conflict_files,
                    resolved=[],
                    unresolved=result.conflict_files,
                )
                if interaction.guild:
                    alerts_channel = discord.utils.get(
                        interaction.guild.text_channels, name="alerts"
                    )
                    if alerts_channel:
                        await alerts_channel.send(embed=conflict_embed)

        except Exception as exc:
            logger.exception("Error in /integrate")
            embed = build_alert_embed("integrate error", str(exc), "error")
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)

    # ── Checkin callback wiring (D-09) ─────────────────────────────

    async def _on_checkin(self, agent_id: str) -> None:
        """Auto-post checkin after phase completion per D-09."""
        from vcompany.communication.checkin import gather_checkin_data, post_checkin

        project_dir = self.bot.project_dir
        if project_dir is None:
            return
        clone_dir = project_dir / "clones" / agent_id
        if clone_dir.exists():
            checkin_data = gather_checkin_data(agent_id, clone_dir)
            guild = self.bot.guilds[0] if self.bot.guilds else None
            if guild:
                channel = discord.utils.get(
                    guild.text_channels, name=f"agent-{agent_id}"
                )
                if channel:
                    await post_checkin(checkin_data, channel)

    async def cog_load(self) -> None:
        """Wire checkin callback into monitor when cog loads."""
        # Defer wiring to on_ready since monitor may not exist yet
        pass

    def wire_monitor_callbacks(self) -> None:
        """Wire _on_checkin into monitor loop. Called from on_ready after monitor init."""
        monitor = self.bot.monitor_loop
        if monitor:
            monitor._on_checkin = self._on_checkin


async def setup(bot: commands.Bot) -> None:
    """Module-level setup function for discord.py Cog loading."""
    await bot.add_cog(CommandsCog(bot))
