"""CommandsCog: all operator commands for vCompany Discord bot.

Implements !new-project, !dispatch, !status, !standup, !kill, !relaunch, !integrate.
All commands gated by vco-owner role (DISC-10).
All blocking calls wrapped in asyncio.to_thread (DISC-11).

Implements DISC-03 through DISC-11.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from vcompany.bot.channel_setup import setup_project_channels
from vcompany.bot.embeds import (
    build_alert_embed,
    build_conflict_embed,
    build_integration_embed,
    build_standup_embed,
    build_status_embed,
)
from vcompany.bot.permissions import is_owner
from vcompany.bot.views.confirm import ConfirmView
from vcompany.bot.views.standup_release import ReleaseView
from vcompany.communication.checkin import gather_checkin_data
from vcompany.communication.standup import StandupSession
from vcompany.integration.pipeline import IntegrationPipeline
from vcompany.monitor.status_generator import generate_project_status

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot

logger = logging.getLogger("vcompany.bot.cogs.commands")


class CommandsCog(commands.Cog):
    """Operator commands for vCompany project orchestration.

    Every command requires vco-owner role. All AgentManager / filesystem
    operations use asyncio.to_thread to avoid blocking the event loop.
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot: VcoBot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Global check: reject commands if bot is not ready (Pitfall 6)."""
        if not self.bot.is_bot_ready:
            await ctx.send("Bot is starting up, please wait...")
            return False
        return True

    # ── !new-project ──────────────────────────────────────────────────

    @commands.command(name="new-project")
    @is_owner()
    async def new_project(self, ctx: commands.Context, *, name: str | None = None) -> None:
        """Create project channels and discussion thread (DISC-03)."""
        if name is None:
            await ctx.send("Please provide a project name: `!new-project <name>`")
            return

        try:
            guild = ctx.guild
            if guild is None:
                await ctx.send("This command can only be used in a server.")
                return

            owner_role = discord.utils.get(guild.roles, name="vco-owner")
            if owner_role is None:
                await ctx.send("Error: vco-owner role not found. Bot may not have initialized properly.")
                return

            await setup_project_channels(
                guild, name, owner_role, self.bot.project_config.agents
            )

            await ctx.channel.create_thread(
                name=f"Project: {name}",
                message=ctx.message,
            )

            await ctx.send(
                f"Project **{name}** created! Category and channels ready. "
                "Use the thread above to describe your product."
            )
        except Exception as exc:
            logger.exception("Error in !new-project")
            embed = build_alert_embed("new-project error", str(exc), "error")
            await ctx.send(embed=embed)

    # ── !dispatch ─────────────────────────────────────────────────────

    @commands.command(name="dispatch")
    @is_owner()
    async def dispatch_cmd(self, ctx: commands.Context, agent_id: str | None = None) -> None:
        """Dispatch an agent or all agents (DISC-04)."""
        try:
            if self.bot.agent_manager is None:
                await ctx.send("Agent manager is not initialized.")
                return

            if agent_id is None:
                await ctx.send("Please specify an agent ID or `all`: `!dispatch <agent_id|all>`")
                return

            if agent_id == "all":
                results = await asyncio.to_thread(self.bot.agent_manager.dispatch_all)
                succeeded = sum(1 for r in results if r.success)
                failed = sum(1 for r in results if not r.success)
                await ctx.send(f"Dispatched all agents: {succeeded} succeeded, {failed} failed.")
            else:
                # Validate agent exists in config
                valid_ids = [a.id for a in self.bot.project_config.agents]
                if agent_id not in valid_ids:
                    await ctx.send(f"Unknown agent `{agent_id}`. Valid: {', '.join(valid_ids)}")
                    return

                result = await asyncio.to_thread(self.bot.agent_manager.dispatch, agent_id)
                if result.success:
                    await ctx.send(f"Agent **{agent_id}** dispatched successfully.")
                else:
                    await ctx.send(f"Failed to dispatch **{agent_id}**: {result.error}")
        except Exception as exc:
            logger.exception("Error in !dispatch")
            embed = build_alert_embed("dispatch error", str(exc), "error")
            await ctx.send(embed=embed)

    # ── !status ───────────────────────────────────────────────────────

    @commands.command(name="status")
    @is_owner()
    async def status_cmd(self, ctx: commands.Context) -> None:
        """Show project status as rich embed (DISC-05)."""
        try:
            status_text = await asyncio.to_thread(
                generate_project_status,
                self.bot.project_dir,
                self.bot.project_config,
            )
            embed = build_status_embed(status_text)
            await ctx.send(embed=embed)
        except Exception as exc:
            logger.exception("Error in !status")
            embed = build_alert_embed("status error", str(exc), "error")
            await ctx.send(embed=embed)

    # ── !kill ─────────────────────────────────────────────────────────

    @commands.command(name="kill")
    @is_owner()
    async def kill_cmd(self, ctx: commands.Context, agent_id: str | None = None) -> None:
        """Kill an agent with confirmation (DISC-07)."""
        try:
            if self.bot.agent_manager is None:
                await ctx.send("Agent manager is not initialized.")
                return

            if agent_id is None:
                await ctx.send("Please specify an agent ID: `!kill <agent_id>`")
                return

            view = ConfirmView()
            view.interaction_user_id = ctx.author.id
            await ctx.send(
                f"Kill agent **{agent_id}**? This will terminate the session.",
                view=view,
            )
            await view.wait()

            if view.value is True:
                success = await asyncio.to_thread(self.bot.agent_manager.kill, agent_id)
                if success:
                    await ctx.send(f"Agent **{agent_id}** killed.")
                else:
                    await ctx.send(f"Agent **{agent_id}** not found or already stopped.")
            else:
                await ctx.send("Kill cancelled.")
        except Exception as exc:
            logger.exception("Error in !kill")
            embed = build_alert_embed("kill error", str(exc), "error")
            await ctx.send(embed=embed)

    # ── !relaunch ─────────────────────────────────────────────────────

    @commands.command(name="relaunch")
    @is_owner()
    async def relaunch_cmd(self, ctx: commands.Context, agent_id: str | None = None) -> None:
        """Relaunch an agent (DISC-08)."""
        try:
            if self.bot.agent_manager is None:
                await ctx.send("Agent manager is not initialized.")
                return

            if agent_id is None:
                await ctx.send("Please specify an agent ID: `!relaunch <agent_id>`")
                return

            # Validate agent exists in config
            valid_ids = [a.id for a in self.bot.project_config.agents]
            if agent_id not in valid_ids:
                await ctx.send(f"Unknown agent `{agent_id}`. Valid: {', '.join(valid_ids)}")
                return

            result = await asyncio.to_thread(self.bot.agent_manager.relaunch, agent_id)
            if result.success:
                await ctx.send(f"Agent **{agent_id}** relaunched successfully.")
            else:
                await ctx.send(f"Failed to relaunch **{agent_id}**: {result.error}")
        except Exception as exc:
            logger.exception("Error in !relaunch")
            embed = build_alert_embed("relaunch error", str(exc), "error")
            await ctx.send(embed=embed)

    # ── !standup ──────────────────────────────────────────────────────

    @commands.command(name="standup")
    @is_owner()
    async def standup_cmd(self, ctx: commands.Context) -> None:
        """Trigger group standup per D-11 blocking interlock model (DISC-06, COMM-03).

        1. Creates a standup message in #standup
        2. Creates a thread per agent with status embed and Release button
        3. Agents are blocked until owner clicks Release per thread
        4. Owner messages in threads are routed to agent tmux panes (COMM-05)
        5. No timeout per D-11
        """
        try:
            # Find #standup channel
            if ctx.guild is None:
                await ctx.send("This command can only be used in a server.")
                return

            standup_channel = discord.utils.get(ctx.guild.text_channels, name="standup")
            if not standup_channel:
                await ctx.send("Error: #standup channel not found.")
                return

            # Create standup session
            tmux = getattr(self.bot, "_tmux", None)
            session = StandupSession(tmux=tmux)
            self.bot._standup_session = session  # type: ignore[attr-defined]  # Store on bot for on_message access

            registry = getattr(self.bot, "_registry", None)
            if not registry:
                await ctx.send("Error: No agent registry loaded.")
                return

            await standup_channel.send("**Standup Session Started**")

            # Create per-agent threads per COMM-03
            for agent in registry.agents:
                # Gather brief status for this agent
                clone_dir = self.bot.project_dir / "clones" / agent.id
                checkin_data = gather_checkin_data(agent.id, clone_dir) if clone_dir.exists() else None

                embed = build_standup_embed(
                    agent_id=agent.id,
                    phase=checkin_data.next_phase if checkin_data else "unknown",
                    status="active",
                    summary=checkin_data.summary if checkin_data else "No data",
                )

                # Create thread for this agent
                thread = await standup_channel.create_thread(
                    name=f"standup-{agent.id}",
                    type=discord.ChannelType.public_thread,
                )
                release_view = ReleaseView(agent_id=agent.id)
                release_view.set_release_callback(session.release_agent)
                await thread.send(embed=embed, view=release_view)
                session.register_thread(agent.id, thread.id)

            await ctx.send(
                f"Standup threads created for {len(registry.agents)} agents. "
                "Release each when ready."
            )

        except Exception as exc:
            logger.exception("Error in !standup")
            embed = build_alert_embed("standup error", str(exc), "error")
            await ctx.send(embed=embed)

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
        # Get pane_id from registry or agent manager
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

    # ── !integrate ────────────────────────────────────────────────────

    @commands.command(name="integrate")
    @is_owner()
    async def integrate_cmd(self, ctx: commands.Context) -> None:
        """Trigger integration pipeline per D-01 interlock model (DISC-09).

        If agents are still working, sets integration_pending on monitor.
        If all agents are already idle, runs pipeline immediately.
        Reports results with embeds. On test failure, dispatches fixes.
        On merge conflict, attempts PM resolution before escalating.
        """
        try:
            view = ConfirmView()
            view.interaction_user_id = ctx.author.id
            await ctx.send("Trigger integration pipeline?", view=view)
            await view.wait()

            if view.value is not True:
                await ctx.send("Integration cancelled.")
                return

            # Check if monitor is available and set pending
            monitor = self.bot.monitor_loop
            if monitor:
                # Use public all_agents_idle() -- do NOT access monitor._agent_states
                if not monitor.all_agents_idle():
                    monitor.set_integration_pending(True)
                    await ctx.send(
                        "Integration pending -- will trigger when all agents "
                        "complete their current phase."
                    )
                    return

            # Run pipeline immediately
            await ctx.send("Starting integration pipeline...")
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
            await ctx.send(embed=embed)

            if result.status == "test_failure" and result.attribution:
                # Auto-dispatch fixes per D-07/INTG-05
                agent_mgr = self.bot.agent_manager
                if agent_mgr:
                    for agent_id, tests in result.attribution.items():
                        if agent_id.startswith("_"):
                            continue  # Skip _interaction, _flaky
                        agent_mgr.dispatch_fix(agent_id, tests)
                    await ctx.send("Fix tasks dispatched to responsible agents.")

            if result.status == "merge_conflict":
                # Post conflict details per INTG-07
                conflict_embed = build_conflict_embed(
                    agent_branches=[f"agent/{aid}" for aid in agent_ids],
                    conflict_files=result.conflict_files,
                    resolved=[],
                    unresolved=result.conflict_files,
                )
                if ctx.guild:
                    alerts_channel = discord.utils.get(
                        ctx.guild.text_channels, name="alerts"
                    )
                    if alerts_channel:
                        await alerts_channel.send(embed=conflict_embed)

        except Exception as exc:
            logger.exception("Error in !integrate")
            embed = build_alert_embed("integrate error", str(exc), "error")
            await ctx.send(embed=embed)

    # ── Checkin callback wiring (D-09) ─────────────────────────────

    async def _on_checkin(self, agent_id: str) -> None:
        """Auto-post checkin after phase completion per D-09."""
        from vcompany.communication.checkin import gather_checkin_data, post_checkin

        project_dir = self.bot.project_dir
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
