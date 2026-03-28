"""CommandsCog: all operator slash commands for vCompany Discord bot.

Implements /new-project, /dispatch, /standup, /kill, /relaunch, /integrate.
All commands gated by vco-owner role via app_commands checks (DISC-10).
All blocking calls wrapped in asyncio.to_thread (DISC-11).

Routes agent lifecycle operations through CompanyRoot supervision tree (MIGR-01).
/dispatch shows tmux liveness and restarts stopped containers via supervisor.
/kill and /relaunch kill tmux panes via container.stop().
/status removed in Phase 8.2 -- replaced by /health.

Implements DISC-03 through DISC-11, MIGR-01.
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
)
from vcompany.bot.permissions import is_owner_app_check
from vcompany.bot.views.confirm import ConfirmView
from vcompany.bot.views.standup_release import ReleaseView
from vcompany.communication.checkin import gather_checkin_data
from vcompany.communication.standup import StandupSession
from vcompany.integration.pipeline import IntegrationPipeline

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot

logger = logging.getLogger("vcompany.bot.cogs.commands")


def _no_project_msg() -> str:
    """Guidance message when no project is loaded."""
    return "No project loaded. Ask the Strategist in #strategist to help you set one up."


class CommandsCog(commands.Cog):
    """Operator slash commands for vCompany project orchestration.

    Every command requires vco-owner role. Agent lifecycle operations route
    through CompanyRoot supervision tree (MIGR-01).
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot: VcoBot = bot
        self._advisories_enabled: bool = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Global check: reject commands if bot is not ready (Pitfall 6)."""
        if not self.bot.is_bot_ready:
            await interaction.response.send_message(
                "Bot is starting up, please wait...", ephemeral=True
            )
            return False
        return True

    # ── /new-project ──────────────────────────────────────────────────

    @app_commands.command(name="new-project", description="Set up a new project (channels + agents + supervision tree)")
    @app_commands.describe(name="Project name")
    @is_owner_app_check()
    async def new_project(self, interaction: discord.Interaction, name: str) -> None:
        """Full project setup: channels + init + clone + supervision tree (DISC-03, MIGR-01).

        Expects the Strategist to have already generated project files at
        ~/vco-projects/<name>/ (agents.yaml, planning/ artifacts).
        """
        try:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message(
                    "This command can only be used in a server.", ephemeral=True
                )
                return

            await interaction.response.defer()

            # Check project files exist
            from vcompany.shared.paths import PROJECTS_BASE
            project_dir = PROJECTS_BASE / name

            if not (project_dir / "agents.yaml").exists():
                await interaction.followup.send(
                    f"No agents.yaml found at `{project_dir}/agents.yaml`.\n"
                    "Ask the Strategist to set up the project files first, then run this command."
                )
                return

            # Step 1: Load config and initialize project structure
            from vcompany.models.config import load_config
            from vcompany.shared.file_ops import write_atomic
            from vcompany.shared.templates import render_template

            config = load_config(project_dir / "agents.yaml")

            # Create project directory structure (same as vco init)
            context_dir = project_dir / "context"
            agents_dir = context_dir / "agents"
            context_dir.mkdir(parents=True, exist_ok=True)
            agents_dir.mkdir(parents=True, exist_ok=True)

            # Generate agent system prompts
            for agent in config.agents:
                prompt_content = render_template(
                    "agent_prompt.md.j2",
                    agent_id=agent.id,
                    role=agent.role,
                    project_name=config.project,
                    owned_dirs=agent.owns,
                    consumes=agent.consumes,
                    milestone_name="TBD",
                    milestone_scope="See MILESTONE-SCOPE.md",
                )
                write_atomic(agents_dir / f"{agent.id}.md", prompt_content)

            await interaction.followup.send(
                f"Setting up **{name}**... loaded {len(config.agents)} agents, project structure initialized."
            )

            # Step 2: Clone repos (if not already cloned)
            clones_dir = project_dir / "clones"
            needs_clone = not clones_dir.exists() or not any(clones_dir.iterdir())
            if needs_clone:
                from vcompany.cli.clone_cmd import _deploy_artifacts
                from vcompany.git import ops as git
                import shutil

                clones_dir.mkdir(exist_ok=True)
                for agent in config.agents:
                    clone_dir = clones_dir / agent.id
                    if clone_dir.exists():
                        continue
                    result = await asyncio.to_thread(git.clone, config.repo, clone_dir)
                    if not result.success:
                        await interaction.channel.send(f"Error cloning for {agent.id}: {result.stderr}")
                        continue
                    await asyncio.to_thread(
                        git.checkout_new_branch, f"agent/{agent.id.lower()}", clone_dir
                    )
                    await asyncio.to_thread(_deploy_artifacts, clone_dir, agent, config, project_dir)

                await interaction.channel.send(f"Cloned {len(config.agents)} agent repos.")
            else:
                await interaction.channel.send("Agent clones already exist, skipping clone step.")

            # Step 3: Create Discord channels
            owner_role = discord.utils.get(guild.roles, name="vco-owner")
            if owner_role:
                await setup_project_channels(guild, name, owner_role, config.agents)
                await interaction.channel.send(f"Discord channels created for **{name}**.")

            # Step 4: Wire bot to project and create CompanyRoot supervision tree
            self.bot.project_dir = project_dir
            self.bot.project_config = config

            from vcompany.container.child_spec import ChildSpec
            from vcompany.container.context import ContainerContext
            from vcompany.supervisor.company_root import CompanyRoot

            if not hasattr(self.bot, "company_root") or self.bot.company_root is None:
                async def on_escalation(msg: str) -> None:
                    alerts_ch = self.bot._system_channels.get("alerts")
                    if alerts_ch:
                        await alerts_ch.send(f"ESCALATION: {msg}")

                health_cog = self.bot.get_cog("HealthCog")
                on_health_change = health_cog._notify_state_change if health_cog else None

                from vcompany.tmux.session import TmuxManager
                tmux_manager = TmuxManager()
                self.bot._tmux_manager = tmux_manager

                self.bot.company_root = CompanyRoot(
                    on_escalation=on_escalation,
                    max_restarts=3,
                    window_seconds=600,
                    data_dir=project_dir / "state" / "supervision",
                    on_health_change=on_health_change,
                    tmux_manager=tmux_manager,
                    project_dir=project_dir,
                )
                await self.bot.company_root.start()

            specs = []
            for agent in config.agents:
                ctx = ContainerContext(
                    agent_id=agent.id,
                    agent_type=agent.type if hasattr(agent, "type") else "gsd",
                    parent_id="project-supervisor",
                    project_id=config.project,
                    owned_dirs=agent.owns if hasattr(agent, "owns") else [],
                )
                specs.append(ChildSpec(child_id=agent.id, agent_type=ctx.agent_type, context=ctx))

            await self.bot.company_root.add_project(
                project_id=config.project,
                child_specs=specs,
            )

            await interaction.channel.send(
                f"Supervision tree started with {len(specs)} agents. "
                "Agent containers are managed by the supervision tree."
            )

            # Step 5: Wire WorkflowOrchestratorCog with PM
            try:
                from vcompany.strategist.pm import PMTier

                pm = PMTier(project_dir=project_dir)
                wo_cog = self.bot.get_cog("WorkflowOrchestratorCog")
                if wo_cog:
                    wo_cog.set_company_root(pm, project_dir)

                    # Wire PlanReviewCog notifications
                    plan_review_cog_ref = self.bot.get_cog("PlanReviewCog")
                    if plan_review_cog_ref:
                        plan_review_cog_ref._workflow_cog = wo_cog

                    # Kick off all agents on Phase 1
                    await interaction.channel.send(
                        "Starting agent workflows via supervision tree..."
                    )
                    for agent in config.agents:
                        started = await wo_cog.start_workflow(agent.id, 1)
                        if started:
                            await interaction.channel.send(
                                f"Agent **{agent.id}** started on Phase 1 (discuss stage)."
                            )
                        else:
                            await interaction.channel.send(
                                f"Failed to start workflow for **{agent.id}**."
                            )
            except Exception:
                logger.exception("Failed to initialize WorkflowOrchestratorCog in /new-project")
                await interaction.channel.send(
                    "WorkflowOrchestratorCog initialization failed. Agents dispatched but not orchestrated."
                )

            await interaction.channel.send("All agents running. Supervision tree active.")

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
        """Dispatch an agent via supervision tree (DISC-04, MIGR-01).

        Agents are managed by the CompanyRoot supervision tree. Dispatch checks
        container state and triggers start if needed.
        """
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            if self.bot.company_root is None:
                await interaction.response.send_message(
                    "Supervision tree is not initialized.", ephemeral=True
                )
                return

            await interaction.response.defer()

            if agent_id == "all":
                # Report all agents with tmux liveness
                lines = []
                for ps in self.bot.company_root.projects.values():
                    for cid, child in ps.children.items():
                        tmux_status = "tmux alive" if child.is_tmux_alive() else "tmux dead"
                        lines.append(f"**{cid}**: {child.state} ({tmux_status})")
                if lines:
                    await interaction.followup.send(
                        "Agent states:\n" + "\n".join(lines)
                    )
                else:
                    await interaction.followup.send(
                        "No agents in supervision tree."
                    )
            else:
                # Validate agent exists in config
                valid_ids = [a.id for a in self.bot.project_config.agents]
                if agent_id not in valid_ids:
                    await interaction.followup.send(
                        f"Unknown agent `{agent_id}`. Valid: {', '.join(valid_ids)}"
                    )
                    return

                container = await self.bot.company_root._find_container(agent_id)
                if container is not None:
                    state = container.state
                    if state == "running":
                        tmux_status = "tmux alive" if container.is_tmux_alive() else "tmux dead"
                        await interaction.followup.send(
                            f"Agent **{agent_id}** is {state} ({tmux_status})."
                        )
                    elif state in ("stopped", "errored"):
                        # Find ProjectSupervisor and restart via supervision tree
                        restarted = False
                        for ps in self.bot.company_root.projects.values():
                            if agent_id in ps.children:
                                spec = ps._get_spec(agent_id)
                                if spec:
                                    await ps._start_child(spec)
                                    await interaction.followup.send(
                                        f"Agent **{agent_id}** restarted via supervision tree (new tmux session)."
                                    )
                                    restarted = True
                                break
                        if not restarted:
                            await interaction.followup.send(
                                f"Agent **{agent_id}** is {state} but not found in any project supervisor."
                            )
                    else:
                        await interaction.followup.send(
                            f"Agent **{agent_id}** container state: {state}."
                        )
                else:
                    await interaction.followup.send(
                        f"Agent **{agent_id}** not found in supervision tree."
                    )
        except Exception as exc:
            logger.exception("Error in /dispatch")
            embed = build_alert_embed("dispatch error", str(exc), "error")
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)

    # ── /kill ─────────────────────────────────────────────────────────

    @app_commands.command(name="kill", description="Kill an agent with confirmation")
    @app_commands.describe(agent_id="Agent ID to kill")
    @is_owner_app_check()
    async def kill_cmd(self, interaction: discord.Interaction, agent_id: str) -> None:
        """Kill an agent via supervision tree with confirmation (DISC-07, MIGR-01)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            if self.bot.company_root is None:
                await interaction.response.send_message(
                    "Supervision tree is not initialized.", ephemeral=True
                )
                return

            view = ConfirmView()
            view.interaction_user_id = interaction.user.id
            await interaction.response.send_message(
                f"Kill agent **{agent_id}**? This will stop the container.",
                view=view,
            )
            await view.wait()

            if view.value is True:
                container = await self.bot.company_root._find_container(agent_id)
                if container is not None:
                    await container.stop()
                    await interaction.followup.send(f"Agent **{agent_id}** stopped (tmux pane killed).")
                else:
                    await interaction.followup.send(
                        f"Agent **{agent_id}** not found in supervision tree."
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
        """Relaunch an agent via supervision tree (DISC-08, MIGR-01).

        Stops the container; the supervisor restart policy will restart it.
        """
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            if self.bot.company_root is None:
                await interaction.response.send_message(
                    "Supervision tree is not initialized.", ephemeral=True
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
            container = await self.bot.company_root._find_container(agent_id)
            if container is not None:
                # Stop triggers supervisor restart policy (kills tmux pane)
                await container.stop()
                await interaction.followup.send(
                    f"Agent **{agent_id}** stopped (tmux pane killed). Supervisor restart policy active."
                )
            else:
                await interaction.followup.send(
                    f"Agent **{agent_id}** not found in supervision tree."
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

    async def _on_advisory(self, agent_id: str, message: str) -> None:
        """Post monitor advisory to #strategist channel."""
        if not self._advisories_enabled:
            return
        guild = self.bot.get_guild(self.bot._guild_id)
        if not guild:
            return
        channel = discord.utils.get(guild.text_channels, name="strategist")
        if channel:
            try:
                await channel.send(f"[monitor-advisory] {message}")
            except Exception:
                logger.exception("Failed to post advisory")

    @app_commands.command(name="toggle-advisories", description="Enable/disable monitor advisories to Strategist")
    @is_owner_app_check()
    async def toggle_advisories(self, interaction: discord.Interaction) -> None:
        """Toggle monitor advisory posting to #strategist."""
        self._advisories_enabled = not self._advisories_enabled
        state = "enabled" if self._advisories_enabled else "disabled"
        await interaction.response.send_message(f"Monitor advisories are now **{state}**.")

    @app_commands.command(name="remove-project", description="Remove a project: stop supervision tree, delete Discord channels/category, and clean files")
    @is_owner_app_check()
    async def remove_project(self, interaction: discord.Interaction, name: str) -> None:
        """Remove a project entirely: supervision tree, Discord channels, and local files (MIGR-01)."""
        try:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("Server only.", ephemeral=True)
                return

            await interaction.response.defer()
            removed = []

            # Step 1: Remove project from supervision tree
            if self.bot.company_root is not None:
                try:
                    await self.bot.company_root.remove_project(name)
                    removed.append("project removed from supervision tree")
                except KeyError:
                    removed.append("project not found in supervision tree")
                except Exception:
                    logger.exception("Error removing project from supervision tree")

            # Step 2: Kill project tmux session
            try:
                from vcompany.tmux.session import TmuxManager
                tmux = TmuxManager()
                if tmux.kill_session(f"vco-{name}"):
                    removed.append("tmux session killed")
            except Exception:
                pass

            # Step 3: Delete Discord category and all channels under it
            category_name = f"vco-{name}"
            category = discord.utils.get(guild.categories, name=category_name)
            if category:
                for channel in category.channels:
                    await channel.delete()
                await category.delete()
                removed.append(f"Discord category '{category_name}' deleted")

            # Step 4: Delete project files
            import shutil
            from vcompany.shared.paths import PROJECTS_BASE
            project_dir = PROJECTS_BASE / name
            if project_dir.exists():
                await asyncio.to_thread(shutil.rmtree, project_dir)
                removed.append(f"files at {project_dir} deleted")

            # Step 5: Clear bot project reference
            if self.bot.project_dir and self.bot.project_dir.name == name:
                self.bot.project_dir = None
                self.bot.project_config = None
                removed.append("bot project reference cleared")

            summary = "\n".join(f"- {r}" for r in removed) if removed else "Nothing to remove."
            await interaction.followup.send(f"Project **{name}** removed:\n{summary}")

        except Exception as exc:
            logger.exception("Error in /remove-project")
            if interaction.response.is_done():
                await interaction.followup.send(f"Error: {exc}")
            else:
                await interaction.response.send_message(f"Error: {exc}")


async def setup(bot: commands.Bot) -> None:
    """Module-level setup function for discord.py Cog loading."""
    await bot.add_cog(CommandsCog(bot))
