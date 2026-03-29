"""CommandsCog: all operator slash commands for vCompany Discord bot.

Implements /new-project, /dispatch, /standup, /kill, /relaunch, /integrate.
All commands gated by vco-owner role via app_commands checks (DISC-10).
All blocking calls wrapped in asyncio.to_thread (DISC-11).

Routes all operations through RuntimeAPI (EXTRACT-04, Phase 22).
Bot cog is a pure Discord I/O adapter -- no business logic, no prohibited imports.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from vcompany.bot.channel_setup import setup_project_channels
from vcompany.bot.embeds import build_alert_embed
from vcompany.bot.permissions import is_owner_app_check
from vcompany.bot.views.confirm import ConfirmView

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot

logger = logging.getLogger("vcompany.bot.cogs.commands")


def _no_project_msg() -> str:
    """Guidance message when no project is loaded."""
    return "No project loaded. Ask the Strategist in #strategist to help you set one up."


def _get_runtime_api(bot: VcoBot):
    """Get RuntimeAPI from daemon, or None if not available."""
    daemon = getattr(bot, "_daemon", None)
    if daemon is not None:
        return getattr(daemon, "runtime_api", None)
    return None


class CommandsCog(commands.Cog):
    """Operator slash commands for vCompany project orchestration.

    Every command requires vco-owner role. All operations delegate
    to RuntimeAPI -- this cog is a pure Discord I/O adapter.
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

    # -- /new-project ----------------------------------------------------------

    @app_commands.command(name="new-project", description="Set up a new project (channels + agents + supervision tree)")
    @app_commands.describe(name="Project name")
    @is_owner_app_check()
    async def new_project(self, interaction: discord.Interaction, name: str) -> None:
        """Full project setup via RuntimeAPI (DISC-03, EXTRACT-04).

        Expects the Strategist to have already generated project files at
        ~/vco-projects/<name>/ (agents.yaml, planning/ artifacts).
        Delegates all business logic to RuntimeAPI.new_project().
        """
        try:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message(
                    "This command can only be used in a server.", ephemeral=True
                )
                return

            await interaction.response.defer()

            runtime_api = _get_runtime_api(self.bot)
            if runtime_api is None:
                await interaction.followup.send("Daemon not ready. Cannot create project.")
                return

            # RuntimeAPI.new_project handles config loading, cloning, supervision tree
            await runtime_api.new_project_from_name(name)

            # Create Discord channels (Discord-specific concern stays in cog)
            project_config = runtime_api._project_config
            if project_config is not None:
                owner_role = discord.utils.get(guild.roles, name="vco-owner")
                if owner_role:
                    await setup_project_channels(guild, name, owner_role, project_config.agents)
                    await interaction.followup.send(
                        f"Project **{name}** created with {len(project_config.agents)} agents. "
                        "Supervision tree active. Discord channels created."
                    )
                else:
                    await interaction.followup.send(
                        f"Project **{name}** created with {len(project_config.agents)} agents. "
                        "Supervision tree active. (vco-owner role not found for channel setup)"
                    )
            else:
                await interaction.followup.send(f"Project **{name}** created.")

            # Wire WorkflowOrchestratorCog with PM (Discord-specific concern)
            try:
                wo_cog = self.bot.get_cog("WorkflowOrchestratorCog")
                if wo_cog:
                    plan_review_cog_ref = self.bot.get_cog("PlanReviewCog")
                    if plan_review_cog_ref:
                        plan_review_cog_ref._workflow_cog = wo_cog

                    if project_config is not None:
                        await interaction.channel.send(
                            "Starting agent workflows via supervision tree..."
                        )
                        for agent in project_config.agents:
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

    # -- /dispatch -------------------------------------------------------------

    @app_commands.command(name="dispatch", description="Dispatch an agent or all agents")
    @app_commands.describe(agent_id="Agent ID to dispatch, or 'all' for all agents")
    @is_owner_app_check()
    async def dispatch_cmd(self, interaction: discord.Interaction, agent_id: str) -> None:
        """Dispatch an agent via RuntimeAPI (DISC-04, EXTRACT-04)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            runtime_api = _get_runtime_api(self.bot)
            if runtime_api is None:
                await interaction.response.send_message(
                    "Daemon not ready.", ephemeral=True
                )
                return

            await interaction.response.defer()

            if agent_id == "all":
                # Report all agent states via RuntimeAPI
                states = await runtime_api.get_agent_states()
                if states:
                    lines = [
                        f"**{s['agent_id']}**: {s['state']} ({s['agent_type']})"
                        for s in states
                    ]
                    await interaction.followup.send(
                        "Agent states:\n" + "\n".join(lines)
                    )
                else:
                    await interaction.followup.send("No agents in supervision tree.")
            else:
                # Validate agent exists in config
                valid_ids = [a.id for a in self.bot.project_config.agents]
                if agent_id not in valid_ids:
                    await interaction.followup.send(
                        f"Unknown agent `{agent_id}`. Valid: {', '.join(valid_ids)}"
                    )
                    return

                try:
                    await runtime_api.dispatch(agent_id)
                    await interaction.followup.send(
                        f"Agent **{agent_id}** dispatched via RuntimeAPI."
                    )
                except KeyError:
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

    # -- /kill -----------------------------------------------------------------

    @app_commands.command(name="kill", description="Kill an agent with confirmation")
    @app_commands.describe(agent_id="Agent ID to kill")
    @is_owner_app_check()
    async def kill_cmd(self, interaction: discord.Interaction, agent_id: str) -> None:
        """Kill an agent via RuntimeAPI with confirmation (DISC-07, EXTRACT-04)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            runtime_api = _get_runtime_api(self.bot)
            if runtime_api is None:
                await interaction.response.send_message(
                    "Daemon not ready.", ephemeral=True
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
                try:
                    await runtime_api.kill(agent_id)
                    await interaction.followup.send(f"Agent **{agent_id}** stopped.")
                except KeyError:
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

    # -- /relaunch -------------------------------------------------------------

    @app_commands.command(name="relaunch", description="Relaunch an agent")
    @app_commands.describe(agent_id="Agent ID to relaunch")
    @is_owner_app_check()
    async def relaunch_cmd(self, interaction: discord.Interaction, agent_id: str) -> None:
        """Relaunch an agent via RuntimeAPI (DISC-08, EXTRACT-04)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            runtime_api = _get_runtime_api(self.bot)
            if runtime_api is None:
                await interaction.response.send_message(
                    "Daemon not ready.", ephemeral=True
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
            try:
                await runtime_api.relaunch(agent_id)
                await interaction.followup.send(
                    f"Agent **{agent_id}** stopped. Supervisor restart policy active."
                )
            except KeyError:
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

    # -- /standup --------------------------------------------------------------

    @app_commands.command(name="standup", description="Trigger group standup")
    @is_owner_app_check()
    async def standup_cmd(self, interaction: discord.Interaction) -> None:
        """Trigger group standup via RuntimeAPI (DISC-06, COMM-03)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "This command can only be used in a server.", ephemeral=True
                )
                return

            runtime_api = _get_runtime_api(self.bot)
            if runtime_api is None:
                await interaction.response.send_message(
                    "Daemon not ready.", ephemeral=True
                )
                return

            await interaction.response.defer()

            result = await runtime_api.standup()
            if "error" in result:
                await interaction.followup.send(f"Standup error: {result['error']}")
                return

            await interaction.followup.send(
                f"Standup session completed. {result.get('agent_count', 0)} agents checked in."
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
        """Route owner messages in standup threads to agent tmux panes via RuntimeAPI."""
        if message.author.bot:
            return

        # Check if message is in a standup thread
        if not isinstance(message.channel, discord.Thread):
            return

        # Route message to agent via RuntimeAPI relay_channel_message
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is None:
            return

        # Extract agent_id from thread name (format: standup-{agent_id})
        thread_name = message.channel.name
        if not thread_name.startswith("standup-"):
            return
        agent_id = thread_name.removeprefix("standup-")

        success = await runtime_api.relay_channel_message(agent_id, message.content)
        if success:
            await message.add_reaction("\u2705")  # checkmark
        else:
            await message.add_reaction("\u274c")  # cross

    # -- /integrate ------------------------------------------------------------

    @app_commands.command(name="integrate", description="Trigger integration pipeline")
    @is_owner_app_check()
    async def integrate_cmd(self, interaction: discord.Interaction) -> None:
        """Trigger integration pipeline via RuntimeAPI (DISC-09)."""
        if self.bot.project_config is None:
            await interaction.response.send_message(_no_project_msg(), ephemeral=True)
            return

        try:
            runtime_api = _get_runtime_api(self.bot)
            if runtime_api is None:
                await interaction.response.send_message(
                    "Daemon not ready.", ephemeral=True
                )
                return

            view = ConfirmView()
            view.interaction_user_id = interaction.user.id
            await interaction.response.send_message(
                "Trigger integration pipeline?", view=view
            )
            await view.wait()

            if view.value is not True:
                await interaction.followup.send("Integration cancelled.")
                return

            await interaction.followup.send("Starting integration pipeline...")
            result = await runtime_api.run_integration()

            if "error" in result:
                await interaction.followup.send(f"Integration error: {result['error']}")
            else:
                status = result.get("status", "unknown")
                embed = discord.Embed(
                    title="Integration Pipeline",
                    description=f"Status: **{status}**",
                    color=discord.Color.green() if status == "success" else discord.Color.red(),
                )
                if result.get("pr_url"):
                    embed.add_field(name="PR", value=result["pr_url"], inline=False)
                await interaction.followup.send(embed=embed)

        except Exception as exc:
            logger.exception("Error in /integrate")
            embed = build_alert_embed("integrate error", str(exc), "error")
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)

    # -- Checkin callback (D-09) -----------------------------------------------

    async def _on_checkin(self, agent_id: str) -> None:
        """Auto-post checkin after phase completion via RuntimeAPI (D-09)."""
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is None:
            return
        checkin_data = await runtime_api.checkin()
        # Post summary to agent channel if available
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if guild:
            channel = discord.utils.get(
                guild.text_channels, name=f"agent-{agent_id}"
            )
            if channel and checkin_data:
                await channel.send(f"[checkin] Agent {agent_id} checked in.")

    async def cog_load(self) -> None:
        """Wire checkin callback into monitor when cog loads."""
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
        """Remove a project entirely via RuntimeAPI (EXTRACT-04)."""
        try:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("Server only.", ephemeral=True)
                return

            await interaction.response.defer()
            removed = []

            # Step 1: Remove project from supervision tree via RuntimeAPI
            runtime_api = _get_runtime_api(self.bot)
            if runtime_api is not None:
                try:
                    await runtime_api.remove_project(name)
                    removed.append("project removed from supervision tree")
                except KeyError:
                    removed.append("project not found in supervision tree")
                except Exception:
                    logger.exception("Error removing project from supervision tree")

            # Step 2: Delete Discord category and all channels under it
            category_name = f"vco-{name}"
            category = discord.utils.get(guild.categories, name=category_name)
            if category:
                for channel in category.channels:
                    await channel.delete()
                await category.delete()
                removed.append(f"Discord category '{category_name}' deleted")

            # Step 3: Clear bot project reference
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
