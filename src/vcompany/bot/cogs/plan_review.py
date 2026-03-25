"""PlanReviewCog: Plan gate workflow for agent plan review.

When monitor detects a new PLAN.md, this Cog:
1. Reads the plan content and validates safety table (SAFE-01/D-16)
2. Posts rich embed summary to #plan-review with Approve/Reject buttons (D-07/D-08)
3. Attaches full PLAN.md as a file (D-07)
4. Waits for reviewer response (GATE-03)
5. On approve: updates plan_gate_status, checks if all plans approved -> triggers execution (D-11/D-12)
6. On reject: sends feedback to agent tmux pane for replanning (D-09/GATE-04)
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import discord
from discord.ext import commands

from vcompany.bot.embeds import build_plan_review_embed
from vcompany.bot.views.plan_review import PlanReviewView
from vcompany.monitor.safety_validator import validate_safety_table

logger = logging.getLogger("vcompany.bot.cogs.plan_review")

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot


class PlanReviewCog(commands.Cog):
    """Plan gate: reviews agent plans before allowing execution."""

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._plan_review_channel: discord.TextChannel | None = None
        self._alerts_channel: discord.TextChannel | None = None

    async def _resolve_channels(self) -> None:
        """Find #plan-review and #alerts channels in the guild."""
        guild = self.bot.get_guild(self.bot._guild_id)
        if guild:
            for channel in guild.text_channels:
                if channel.name == "plan-review":
                    self._plan_review_channel = channel
                elif channel.name == "alerts":
                    self._alerts_channel = channel

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Resolve channels on ready."""
        await self._resolve_channels()

    async def handle_new_plan(self, agent_id: str, plan_path: Path) -> None:
        """Process a newly detected plan file per D-07 through D-12.

        Called by the monitor via callback injection.

        Args:
            agent_id: Agent that created the plan.
            plan_path: Absolute path to the PLAN.md file.
        """
        if not self._plan_review_channel:
            await self._resolve_channels()
        if not self._plan_review_channel:
            logger.error("Cannot post plan review: #plan-review channel not found")
            return

        # Read plan content
        try:
            plan_content = await asyncio.to_thread(plan_path.read_text)
        except Exception:
            logger.exception("Failed to read plan file: %s", plan_path)
            return

        # Parse plan metadata from frontmatter and content
        phase = _extract_frontmatter_field(plan_content, "phase") or "unknown"
        plan_number = _extract_frontmatter_field(plan_content, "plan") or "?"
        task_count = len(re.findall(r'<task\s+type=', plan_content))
        goal = _extract_objective(plan_content)

        # Validate safety table (SAFE-01/D-16)
        safety_valid, safety_message = validate_safety_table(plan_content)

        # Build embed (D-07)
        embed = build_plan_review_embed(
            agent_id=agent_id,
            phase=phase,
            plan_number=plan_number,
            task_count=task_count,
            goal=goal,
            plan_path=str(plan_path),
            safety_valid=safety_valid,
            safety_message=safety_message,
        )

        # Create view with Approve/Reject buttons (D-08)
        view = PlanReviewView(agent_id=agent_id, plan_path=str(plan_path))

        # Post embed + file attachment (D-07)
        try:
            file_attachment = discord.File(fp=str(plan_path), filename=plan_path.name)
            await self._plan_review_channel.send(
                embed=embed, view=view, file=file_attachment,
            )
        except Exception:
            logger.exception("Failed to post plan review for %s", agent_id)
            return

        # Update plan gate state to awaiting_review (D-13)
        self._update_gate_state(agent_id, str(plan_path), status="awaiting_review")

        # Wait for reviewer response (GATE-03)
        timed_out = await view.wait()

        if timed_out or view.result is None:
            logger.warning("Plan review timed out for %s: %s", agent_id, plan_path)
            return

        if view.result == "approved":
            await self._handle_approval(agent_id, str(plan_path))
        elif view.result == "rejected":
            await self._handle_rejection(agent_id, str(plan_path), view.feedback)

    async def _handle_approval(self, agent_id: str, plan_path: str) -> None:
        """Process plan approval per D-11/D-12.

        Updates state, checks if all plans for the phase are approved,
        and triggers execution if so.
        """
        self._update_gate_state(agent_id, plan_path, status="approved")

        # Check if ALL pending plans are now approved (D-12)
        state = self._get_agent_state(agent_id)
        if state and not state.pending_plans:
            # All plans approved -> trigger execution
            await self._trigger_execution(agent_id, state)

        if self._plan_review_channel:
            await self._plan_review_channel.send(
                f"Plan **approved** for `{agent_id}`: `{Path(plan_path).name}`"
            )

    async def _handle_rejection(self, agent_id: str, plan_path: str, feedback: str) -> None:
        """Process plan rejection per D-09/GATE-04.

        Sends feedback to agent tmux pane for replanning.
        """
        self._update_gate_state(agent_id, plan_path, status="rejected")

        # Send rejection feedback to agent tmux pane (D-09)
        if self.bot.agent_manager:
            try:
                tmux = self.bot.agent_manager._tmux
                # Load agent registry to get pane reference
                from vcompany.models.agent_state import AgentsRegistry
                registry_path = self.bot.project_dir / "state" / "agents.json"
                if registry_path.exists():
                    registry = AgentsRegistry.model_validate_json(
                        await asyncio.to_thread(registry_path.read_text)
                    )
                    entry = registry.agents.get(agent_id)
                    if entry and entry.pane_id:
                        feedback_cmd = (
                            f"Your plan {Path(plan_path).name} was rejected. "
                            f"Feedback: {feedback}. Please revise the plan."
                        )
                        await asyncio.to_thread(
                            tmux.send_command, entry.pane_id, feedback_cmd
                        )
            except Exception:
                logger.exception("Failed to send rejection feedback to %s", agent_id)

        if self._plan_review_channel:
            await self._plan_review_channel.send(
                f"Plan **rejected** for `{agent_id}`: `{Path(plan_path).name}`\n"
                f"Feedback: {feedback}"
            )

    async def _trigger_execution(self, agent_id: str, state: object) -> None:
        """Send /gsd:execute-phase command to agent tmux pane per D-11/D-12.

        Only called when ALL plans for a phase are approved.
        """
        if not self.bot.agent_manager:
            logger.error("Cannot trigger execution: agent_manager not available")
            return

        try:
            tmux = self.bot.agent_manager._tmux
            from vcompany.models.agent_state import AgentsRegistry
            registry_path = self.bot.project_dir / "state" / "agents.json"
            if registry_path.exists():
                registry = AgentsRegistry.model_validate_json(
                    await asyncio.to_thread(registry_path.read_text)
                )
                entry = registry.agents.get(agent_id)
                if entry and entry.pane_id:
                    # Extract phase number from state
                    phase = getattr(state, 'current_phase', 'unknown')
                    execute_cmd = f"/gsd:execute-phase {phase}"
                    await asyncio.to_thread(
                        tmux.send_command, entry.pane_id, execute_cmd
                    )
                    logger.info("Triggered execution for %s: %s", agent_id, execute_cmd)

                    # Reset gate state to idle after triggering
                    if hasattr(state, 'plan_gate_status'):
                        state.plan_gate_status = "idle"
                        state.approved_plans = []

        except Exception:
            logger.exception("Failed to trigger execution for %s", agent_id)

        if self._alerts_channel:
            await self._alerts_channel.send(
                f"All plans approved for `{agent_id}`. Execution triggered."
            )

    def _get_agent_state(self, agent_id: str):
        """Get AgentMonitorState from MonitorLoop."""
        if self.bot.monitor_loop:
            return self.bot.monitor_loop._agent_states.get(agent_id)
        return None

    def _update_gate_state(self, agent_id: str, plan_path: str, *, status: str) -> None:
        """Update plan_gate_status in AgentMonitorState per D-13/D-14."""
        state = self._get_agent_state(agent_id)
        if not state:
            return

        if status == "awaiting_review":
            state.plan_gate_status = "awaiting_review"
            if plan_path not in state.pending_plans:
                state.pending_plans.append(plan_path)

        elif status == "approved":
            state.plan_gate_status = "approved"
            if plan_path in state.pending_plans:
                state.pending_plans.remove(plan_path)
            if plan_path not in state.approved_plans:
                state.approved_plans.append(plan_path)

        elif status == "rejected":
            state.plan_gate_status = "rejected"
            if plan_path in state.pending_plans:
                state.pending_plans.remove(plan_path)

    def make_sync_callback(self) -> dict:
        """Create sync callback for on_plan_detected routing.

        Returns dict with on_plan_detected key that schedules
        handle_new_plan via run_coroutine_threadsafe.
        """
        loop = self.bot.loop

        def on_plan_detected(agent_id: str, plan_path: Path) -> None:
            asyncio.run_coroutine_threadsafe(
                self.handle_new_plan(agent_id, plan_path), loop
            )

        return {"on_plan_detected": on_plan_detected}


def _extract_frontmatter_field(content: str, field: str) -> str | None:
    """Extract a field value from YAML frontmatter."""
    match = re.search(rf'^{field}:\s*(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return None


def _extract_objective(content: str) -> str:
    """Extract objective text from <objective> tags."""
    match = re.search(r'<objective>\s*(.*?)\s*</objective>', content, re.DOTALL)
    if match:
        text = match.group(1).strip()
        return text[:500] if len(text) > 500 else text
    return "No objective found"


async def setup(bot: commands.Bot) -> None:
    """Load PlanReviewCog into the bot."""
    await bot.add_cog(PlanReviewCog(bot))
