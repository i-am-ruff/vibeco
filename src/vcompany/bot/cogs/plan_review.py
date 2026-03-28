"""PlanReviewCog: Plan gate workflow for agent plan review.

When a new PLAN.md is detected, this Cog:
1. Reads the plan content and validates safety table (SAFE-01/D-16)
2. Posts rich embed summary to #plan-review with Approve/Reject buttons (D-07/D-08)
3. Attaches full PLAN.md as a file (D-07)
4. Waits for reviewer response (GATE-03)
5. On approve: notifies WorkflowOrchestratorCog, triggers execution via TmuxManager (D-11/D-12)
6. On reject: sends feedback to agent tmux pane for replanning (D-09/GATE-04)
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
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
    from vcompany.bot.cogs.workflow_orchestrator_cog import WorkflowOrchestratorCog
    from vcompany.strategist.plan_reviewer import PlanReviewer


class PlanReviewCog(commands.Cog):
    """Plan gate: reviews agent plans before allowing execution."""

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._plan_review_channel: discord.TextChannel | None = None
        self._alerts_channel: discord.TextChannel | None = None
        self._plan_reviewer: PlanReviewer | None = None
        self._workflow_cog: WorkflowOrchestratorCog | None = None

    def set_plan_reviewer(self, reviewer: PlanReviewer) -> None:
        """Inject PlanReviewer for PM review. Called from bot startup."""
        self._plan_reviewer = reviewer

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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Watch agent channels for @PM mentions to trigger plan review.

        When an agent posts "@PM plan ready" in #agent-{id}, this triggers
        the PM review flow. Discord is the bus — no file watching needed.
        """
        # Only respond to messages in agent-* channels
        if not message.channel.name.startswith("agent-"):
            return
        # Only process messages containing @PM
        if "@PM" not in message.content:
            return
        # Skip bot's own messages (PM responses)
        if message.author.id == self.bot.user.id:
            return

        agent_id = message.channel.name.removeprefix("agent-")
        content_lower = message.content.lower()

        # Detect plan completion
        if "plan" in content_lower and ("complete" in content_lower or "ready" in content_lower or "review" in content_lower):
            await message.channel.send(f"[PM] Reviewing {agent_id}'s plan...")
            await self._review_agent_plans(agent_id, message.channel)

        # Detect phase/execution completion
        elif "execute" in content_lower and "complete" in content_lower:
            await message.channel.send(f"[PM] Verifying {agent_id}'s execution...")
            await self._verify_agent_execution(agent_id, message.channel)

    def _pm_context_path(self) -> Path:
        """Path to PM's persistent knowledge doc."""
        return self.bot.project_dir / "state" / "pm-context.md"

    def _read_pm_context(self) -> str:
        """Read PM's accumulated knowledge, or empty string if none."""
        path = self._pm_context_path()
        if path.exists():
            return path.read_text()
        return ""

    def _append_pm_context(self, entry: str) -> None:
        """Append a condensed entry to PM's knowledge doc."""
        path = self._pm_context_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(f"\n{entry}\n")

    async def _review_agent_plans(self, agent_id: str, channel: discord.TextChannel) -> None:
        """PM reviews agent's plan using accumulated knowledge doc.

        PM reads its own condensed notes (not raw plan files from other agents),
        reviews the new plan, checks for conflicts, then appends what matters
        to its knowledge doc. Like a real PM keeping running notes.
        """
        if not self.bot.project_dir or not self.bot.project_config:
            await channel.send("[PM] No project loaded, cannot review.")
            return

        clone_dir = self.bot.project_dir / "clones" / agent_id
        phases_dir = clone_dir / ".planning" / "phases"

        # Find latest plan files
        plan_files = sorted(phases_dir.rglob("*-PLAN.md")) if phases_dir.exists() else []
        if not plan_files:
            await channel.send(f"[PM] No PLAN.md files found for {agent_id}.")
            return

        latest_plan = plan_files[-1]
        plan_content = await asyncio.to_thread(latest_plan.read_text)

        # Read PM's accumulated knowledge
        pm_knowledge = await asyncio.to_thread(self._read_pm_context)

        # Also read project roadmap for overall context
        roadmap_path = clone_dir / ".planning" / "ROADMAP.md"
        roadmap = ""
        if roadmap_path.exists():
            roadmap = await asyncio.to_thread(roadmap_path.read_text)

        # Use PlanReviewer (PM) if available
        if self._plan_reviewer:
            try:
                # Build PM review prompt with knowledge doc, not raw plans
                review_prompt = (
                    f"You are reviewing a plan from agent '{agent_id}'.\n\n"
                    f"## Your accumulated project knowledge\n{pm_knowledge or '(first review — no prior knowledge)'}\n\n"
                    f"## Project roadmap\n{roadmap[:1500]}\n\n"
                    f"## New plan to review\n{plan_content}\n\n"
                    f"Review this plan for:\n"
                    f"1. Does it conflict with any approved work from other agents?\n"
                    f"2. Are the file paths within this agent's owned directories?\n"
                    f"3. Is the scope appropriate for the phase?\n"
                    f"4. Any interface/dependency risks?\n\n"
                    f"After your review, provide a CONDENSED SUMMARY (3-5 lines) of what this agent "
                    f"plans to do, which directories/files it touches, and any interfaces it creates. "
                    f"This summary will be saved to your knowledge doc for future reviews."
                )

                review = await asyncio.to_thread(
                    self._plan_reviewer.review_plan, agent_id, review_prompt
                )

                # Save condensed knowledge from this review
                from datetime import datetime, timezone
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                knowledge_entry = (
                    f"---\n"
                    f"## {agent_id} — {latest_plan.name} (reviewed {ts})\n"
                    f"Decision: {'APPROVED' if review.confidence.level == 'HIGH' else 'NEEDS REVISION'}\n"
                    f"Note: {review.note}\n"
                )
                await asyncio.to_thread(self._append_pm_context, knowledge_entry)

                if review.confidence.level == "HIGH":
                    await channel.send(
                        f"[PM] Plan approved for {agent_id}. {review.note}\n"
                        f"Sending execute command."
                    )
                    await self._send_tmux_command(agent_id, "/gsd:execute-phase 1")
                else:
                    await channel.send(
                        f"[PM] Plan needs revision for {agent_id}: {review.note}"
                    )
                return
            except Exception:
                logger.exception("PM review failed for %s", agent_id)

        # Fallback: auto-approve if no PM configured, still save knowledge
        await channel.send(
            f"[PM] Auto-approving plan for {agent_id} (no PM tier configured). Sending execute command."
        )
        # Save basic knowledge even without PM
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        knowledge_entry = (
            f"---\n"
            f"## {agent_id} — {latest_plan.name} (auto-approved {ts})\n"
            f"Plan file: {latest_plan}\n"
        )
        await asyncio.to_thread(self._append_pm_context, knowledge_entry)

        await self._send_tmux_command(agent_id, "/gsd:execute-phase 1")

    async def _verify_agent_execution(self, agent_id: str, channel: discord.TextChannel) -> None:
        """PM verifies that execution completed successfully."""
        if not self.bot.project_dir:
            await channel.send("[PM] No project loaded.")
            return

        clone_dir = self.bot.project_dir / "clones" / agent_id

        # Check git log for recent commits
        from vcompany.git import ops as git_ops
        result = await asyncio.to_thread(
            git_ops.log, clone_dir, args=["--oneline", "-5"]
        )

        if result.success and result.stdout.strip():
            await channel.send(
                f"[PM] Execution verified for {agent_id}. Recent commits:\n"
                f"```\n{result.stdout.strip()}\n```"
            )
        else:
            await channel.send(f"[PM] Warning: No commits found for {agent_id} after execution.")

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

        # Phase 6: PM review intercept before posting to #plan-review
        if self._plan_reviewer:
            try:
                review_decision = await asyncio.to_thread(
                    self._plan_reviewer.review_plan, agent_id, plan_content
                )
                if review_decision.confidence.level == "HIGH":
                    # Auto-approve per D-15
                    self._update_gate_state(agent_id, str(plan_path), status="approved")
                    await self._handle_approval(agent_id, str(plan_path))
                    # Still post notification to #plan-review for owner visibility
                    embed.add_field(
                        name="PM Review", value="Auto-approved (HIGH confidence)", inline=False
                    )
                    try:
                        await self._plan_review_channel.send(embed=embed)
                    except Exception:
                        logger.exception("Failed to post auto-approval notice for %s", agent_id)
                    # Log decision
                    await self._log_plan_decision(
                        agent_id, str(plan_path), "Plan approved by PM", "HIGH"
                    )
                    return
                else:
                    # LOW confidence or check failures -- add PM notes to embed, let human review
                    embed.add_field(
                        name="PM Review",
                        value=f"Needs review: {review_decision.note}",
                        inline=False,
                    )
                    # Fall through to normal review flow with buttons
            except Exception:
                logger.exception("PM plan review failed for %s, falling through to manual review", agent_id)

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
        and triggers execution if so. Notifies WorkflowOrchestratorCog.
        """
        self._update_gate_state(agent_id, plan_path, status="approved")

        # Notify WorkflowOrchestratorCog of plan approval
        if self._workflow_cog is not None:
            await self._workflow_cog.notify_plan_approved(agent_id)

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

        Sends feedback to agent tmux pane for replanning. Notifies WorkflowOrchestratorCog.
        """
        self._update_gate_state(agent_id, plan_path, status="rejected")

        # Notify WorkflowOrchestratorCog of plan rejection
        if self._workflow_cog is not None:
            await self._workflow_cog.notify_plan_rejected(agent_id)

        # Send rejection feedback to agent tmux pane (D-09)
        feedback_cmd = (
            f"Your plan {Path(plan_path).name} was rejected. "
            f"Feedback: {feedback}. Please revise the plan."
        )
        await self._send_tmux_command(agent_id, feedback_cmd)

        if self._plan_review_channel:
            await self._plan_review_channel.send(
                f"Plan **rejected** for `{agent_id}`: `{Path(plan_path).name}`\n"
                f"Feedback: {feedback}"
            )

    async def _trigger_execution(self, agent_id: str, state: object) -> None:
        """Send /gsd:execute-phase command to agent tmux pane per D-11/D-12.

        Only called when ALL plans for a phase are approved.
        """
        phase = getattr(state, "current_phase", "unknown")
        execute_cmd = f"/gsd:execute-phase {phase}"
        await self._send_tmux_command(agent_id, execute_cmd)

        # Reset gate state to idle after triggering
        if hasattr(state, "plan_gate_status"):
            state.plan_gate_status = "idle"
            state.approved_plans = []

        if self._alerts_channel:
            await self._alerts_channel.send(
                f"All plans approved for `{agent_id}`. Execution triggered."
            )

    def _get_agent_state(self, agent_id: str):
        """Get AgentMonitorState if available via bot attribute.

        Returns None if no monitor state tracking is active (supervision tree
        handles health monitoring via event-driven callbacks instead).
        """
        monitor = getattr(self.bot, "monitor_loop", None)
        if monitor is not None:
            return getattr(monitor, "_agent_states", {}).get(agent_id)
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

    async def _send_tmux_command(self, agent_id: str, command: str) -> bool:
        """Send a command to an agent's tmux pane via TmuxManager.

        Looks up the agent's pane_id from agents.json registry, then uses
        TmuxManager to send the command. Returns True on success.
        """
        if not self.bot.project_dir:
            logger.error("Cannot send tmux command: no project_dir")
            return False

        try:
            from vcompany.models.agent_state import AgentsRegistry
            from vcompany.tmux.session import TmuxManager

            registry_path = self.bot.project_dir / "state" / "agents.json"
            if not registry_path.exists():
                logger.warning("agents.json not found, cannot send command to %s", agent_id)
                return False

            registry = AgentsRegistry.model_validate_json(
                await asyncio.to_thread(registry_path.read_text)
            )
            entry = registry.agents.get(agent_id)
            if not entry or not entry.pane_id:
                logger.warning("No pane_id for agent %s in registry", agent_id)
                return False

            tmux = TmuxManager()
            sent = await asyncio.to_thread(tmux.send_command, entry.pane_id, command)
            if sent:
                logger.info("Sent command to %s (pane %s): %s", agent_id, entry.pane_id, command[:80])
            else:
                logger.error("Failed to send command to %s (pane %s)", agent_id, entry.pane_id)
            return sent
        except Exception:
            logger.exception("Failed to send tmux command to %s", agent_id)
            return False

    async def _log_plan_decision(
        self, agent_id: str, plan_path: str, decision: str, confidence_level: str
    ) -> None:
        """Log a plan review decision via StrategistCog's DecisionLogger if available."""
        strategist_cog = self.bot.get_cog("StrategistCog")
        if strategist_cog and strategist_cog.decision_logger:
            from vcompany.strategist.models import DecisionLogEntry

            await strategist_cog.decision_logger.log_decision(
                DecisionLogEntry(
                    timestamp=datetime.now(timezone.utc),
                    question_or_plan=f"Plan review: {plan_path}",
                    decision=decision,
                    confidence_level=confidence_level,
                    decided_by="PM",
                    agent_id=agent_id,
                )
            )

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
