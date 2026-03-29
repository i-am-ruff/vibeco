"""PlanReviewCog: Plan gate workflow for agent plan review.

When a new PLAN.md is detected, this Cog:
1. Reads the plan content and validates safety table (SAFE-01/D-16)
2. Posts rich embed summary to #plan-review with Approve/Reject buttons (D-07/D-08)
3. Attaches full PLAN.md as a file (D-07)
4. Waits for reviewer response (GATE-03)
5. On approve: notifies WorkflowOrchestratorCog, triggers execution via RuntimeAPI (D-11/D-12)
6. On reject: sends feedback to agent via RuntimeAPI (D-09/GATE-04)

All business logic delegated to RuntimeAPI -- this cog is a pure Discord I/O adapter.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands

from vcompany.bot.embeds import build_plan_review_embed
from vcompany.bot.views.plan_review import PlanReviewView
from vcompany.shared.safety_validator import validate_safety_table

logger = logging.getLogger("vcompany.bot.cogs.plan_review")

# GATE-05: Maximum 1 review request per agent per this many seconds
_REVIEW_THROTTLE_SECS = 30.0

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot
    from vcompany.bot.cogs.workflow_orchestrator_cog import WorkflowOrchestratorCog


def _get_runtime_api(bot: VcoBot):
    """Get RuntimeAPI from daemon, or None if not available."""
    daemon = getattr(bot, "_daemon", None)
    if daemon is not None:
        return getattr(daemon, "runtime_api", None)
    return None


class PlanReviewCog(commands.Cog):
    """Plan gate: reviews agent plans before allowing execution."""

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._plan_review_channel: discord.TextChannel | None = None
        self._alerts_channel: discord.TextChannel | None = None
        self._plan_reviewer = None  # Set via set_plan_reviewer
        self._workflow_cog: WorkflowOrchestratorCog | None = None
        # GATE-05: Per-agent throttle tracker (agent_id -> last post monotonic time)
        self._last_review_time: dict[str, float] = {}

    def set_plan_reviewer(self, reviewer) -> None:
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
        """Watch agent channels for @PM mentions and PM review responses.

        When an agent posts "@PM plan ready" in #agent-{id}, this triggers
        the PM review flow. Discord is the bus -- no file watching needed.

        Also handles PM review responses (bot-posted [PM] ... messages) to
        resolve GsdAgent gate Futures via RuntimeAPI.
        """
        # Only respond to messages in agent-* channels
        if not message.channel.name.startswith("agent-"):
            return

        agent_id = message.channel.name.removeprefix("agent-")

        # Handle bot's own [PM] review responses (from automated PM review dispatch).
        # Must check BEFORE the bot-author guard below -- otherwise these are skipped.
        if message.author.id == self.bot.user.id:
            if message.content.startswith("[PM]"):
                await self._handle_review_response(agent_id, message.content)
            return

        # Only process messages containing @PM (from non-bot authors)
        if "@PM" not in message.content:
            return

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
        """PM reviews agent's plan using accumulated knowledge doc."""
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
                review_prompt = (
                    f"You are reviewing a plan from agent '{agent_id}'.\n\n"
                    f"## Your accumulated project knowledge\n{pm_knowledge or '(first review -- no prior knowledge)'}\n\n"
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
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                knowledge_entry = (
                    f"---\n"
                    f"## {agent_id} -- {latest_plan.name} (reviewed {ts})\n"
                    f"Decision: {'APPROVED' if review.confidence.level == 'HIGH' else 'NEEDS REVISION'}\n"
                    f"Note: {review.note}\n"
                )
                await asyncio.to_thread(self._append_pm_context, knowledge_entry)

                if review.confidence.level == "HIGH":
                    await channel.send(
                        f"[PM] Plan approved for {agent_id}. {review.note}\n"
                        f"Sending execute command."
                    )
                    # Route through RuntimeAPI
                    runtime_api = _get_runtime_api(self.bot)
                    if runtime_api is not None:
                        await runtime_api.relay_channel_message(agent_id, "/gsd:execute-phase 1")
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
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        knowledge_entry = (
            f"---\n"
            f"## {agent_id} -- {latest_plan.name} (auto-approved {ts})\n"
            f"Plan file: {latest_plan}\n"
        )
        await asyncio.to_thread(self._append_pm_context, knowledge_entry)

        # Route through RuntimeAPI
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is not None:
            await runtime_api.relay_channel_message(agent_id, "/gsd:execute-phase 1")

    async def _verify_agent_execution(self, agent_id: str, channel: discord.TextChannel) -> None:
        """PM verifies that execution completed successfully via RuntimeAPI."""
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is None:
            await channel.send("[PM] Daemon not available for verification.")
            return

        result = await runtime_api.verify_agent_execution(agent_id)

        if result["success"] and result["stdout"]:
            await channel.send(
                f"[PM] Execution verified for {agent_id}. Recent commits:\n"
                f"```\n{result['stdout']}\n```"
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

        # Validate safety table (SAFE-01/D-16) -- pure utility, no container deps
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
                    # Post review decision as Discord message (D-13, VIS-03)
                    try:
                        await self._plan_review_channel.send(
                            f"[Review] Plan for {agent_id}: APPROVED (confidence: HIGH). {review_decision.note or 'Auto-approved by PM'}"
                        )
                    except Exception:
                        logger.exception("Failed to post review decision for %s", agent_id)
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
        """Process plan approval -- route through RuntimeAPI (COMM-05 receive path)."""
        self._update_gate_state(agent_id, plan_path, status="approved")

        # Route through RuntimeAPI (COMM-05 receive path, EXTRACT-04)
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is not None:
            await runtime_api.handle_plan_approval(agent_id, plan_path)

        # Notify WorkflowOrchestratorCog (stays local -- Discord UI concern)
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
        """Process plan rejection -- route through RuntimeAPI (COMM-05 receive path)."""
        self._update_gate_state(agent_id, plan_path, status="rejected")

        # Route through RuntimeAPI (COMM-05 receive path, EXTRACT-04)
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is not None:
            await runtime_api.handle_plan_rejection(agent_id, plan_path, feedback)

        # Notify WorkflowOrchestratorCog (stays local -- Discord UI concern)
        if self._workflow_cog is not None:
            await self._workflow_cog.notify_plan_rejected(agent_id)

        # Send rejection feedback to agent via RuntimeAPI (D-09)
        if runtime_api is None:
            # Fallback only if RuntimeAPI unavailable
            feedback_cmd = (
                f"Your plan {Path(plan_path).name} was rejected. "
                f"Feedback: {feedback}. Please revise the plan."
            )
            logger.warning("RuntimeAPI unavailable, cannot send rejection feedback to %s", agent_id)

        if self._plan_review_channel:
            await self._plan_review_channel.send(
                f"Plan **rejected** for `{agent_id}`: `{Path(plan_path).name}`\n"
                f"Feedback: {feedback}"
            )

    async def _trigger_execution(self, agent_id: str, state: object) -> None:
        """Send /gsd:execute-phase command to agent via RuntimeAPI per D-11/D-12."""
        phase = getattr(state, "current_phase", "unknown")
        execute_cmd = f"/gsd:execute-phase {phase}"

        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is not None:
            await runtime_api.relay_channel_message(agent_id, execute_cmd)

        # Reset gate state to idle after triggering
        if hasattr(state, "plan_gate_status"):
            state.plan_gate_status = "idle"
            state.approved_plans = []

        if self._alerts_channel:
            await self._alerts_channel.send(
                f"All plans approved for `{agent_id}`. Execution triggered."
            )

    def _get_agent_state(self, agent_id: str):
        """Get AgentMonitorState if available via bot attribute."""
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

    # --- Review Request Infrastructure (GATE-01, GATE-05) ---

    async def _post_throttled(
        self,
        agent_id: str,
        channel: discord.TextChannel,
        content: str,
        files: list[discord.File] | None = None,
    ) -> None:
        """Post review message respecting 1-per-30s throttle per agent (GATE-05)."""
        now = time.monotonic()
        last = self._last_review_time.get(agent_id, 0.0)
        wait = _REVIEW_THROTTLE_SECS - (now - last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_review_time[agent_id] = time.monotonic()
        kwargs: dict = {"content": content}
        if files:
            kwargs["files"] = files
        await channel.send(**kwargs)

    async def _build_review_attachments(
        self, agent_id: str, stage: str
    ) -> list[discord.File]:
        """Collect relevant files for a stage review request (GATE-01)."""
        if not self.bot.project_dir:
            return []
        clone_dir = self.bot.project_dir / "clones" / agent_id
        phases_dir = clone_dir / ".planning" / "phases"
        if not phases_dir.exists():
            return []
        stage_globs = {
            "discuss": ["*/*-CONTEXT.md"],
            "plan": ["*/*-PLAN.md"],
            "execute": ["*/*-SUMMARY.md"],
            "uat": ["*/*-SUMMARY.md"],
            "ship": ["*/*-SUMMARY.md"],
        }
        patterns = stage_globs.get(stage, [])
        files = []
        for pattern in patterns:
            matches = sorted(phases_dir.glob(pattern))
            if matches:
                latest = matches[-1]
                if latest.stat().st_size < 1_000_000:  # 1MB guard
                    files.append(discord.File(fp=str(latest), filename=latest.name))
        return files

    async def post_review_request(self, agent_id: str, stage: str) -> None:
        """Post a review request to the agent's Discord channel with file attachments."""
        guild = self.bot.get_guild(self.bot._guild_id)
        if not guild:
            return
        channel = discord.utils.get(guild.text_channels, name=f"agent-{agent_id}")
        if not channel:
            logger.warning("Channel agent-%s not found for review request", agent_id)
            return
        attachments = await self._build_review_attachments(agent_id, stage)
        content = f"[{agent_id}] @PM, finished {stage}, need your review"
        await self._post_throttled(agent_id, channel, content, attachments or None)

    async def _handle_review_response(self, agent_id: str, content: str) -> None:
        """Parse a [PM] review response and resolve the agent's gate Future via RuntimeAPI."""
        content_lower = content.lower()
        if "approved" in content_lower or "approve" in content_lower:
            decision = "approve"
        elif "needs changes" in content_lower or "modify" in content_lower:
            decision = "modify"
        elif "clarify" in content_lower:
            decision = "clarify"
        else:
            decision = "clarify"  # safe fallback

        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is None:
            return

        resolved = await runtime_api.resolve_review(agent_id, decision)
        if resolved:
            logger.info("Resolved review gate for %s: %s", agent_id, decision)
            if decision == "modify":
                # Extract feedback after the first colon
                feedback = content.split(":", 1)[1].strip() if ":" in content else content
                await runtime_api.relay_channel_message(agent_id, f"PM feedback: {feedback}")
        else:
            logger.warning("No pending review to resolve for %s", agent_id)

    async def dispatch_pm_review(self, agent_id: str, stage: str) -> None:
        """Have PM evaluate the agent's stage artifacts and post a review response."""
        guild = self.bot.get_guild(self.bot._guild_id)
        if not guild:
            return
        channel = discord.utils.get(guild.text_channels, name=f"agent-{agent_id}")
        if not channel:
            logger.warning("Channel agent-%s not found for PM review dispatch", agent_id)
            return

        # Read stage artifacts for PM evaluation
        if not self.bot.project_dir:
            await self._post_throttled(agent_id, channel, f"[PM] APPROVED (no project context)")
            return

        clone_dir = self.bot.project_dir / "clones" / agent_id
        phases_dir = clone_dir / ".planning" / "phases"
        artifact_content = ""
        if phases_dir.exists():
            stage_globs: dict[str, str] = {
                "discuss": "*/*-CONTEXT.md",
                "plan": "*/*-PLAN.md",
                "execute": "*/*-SUMMARY.md",
                "uat": "*/*-SUMMARY.md",
                "ship": "*/*-SUMMARY.md",
            }
            pattern = stage_globs.get(stage, "")
            if pattern:
                matches = sorted(phases_dir.glob(pattern))
                if matches:
                    artifact_content = await asyncio.to_thread(matches[-1].read_text)
                    artifact_content = artifact_content[:3000]  # cap for LLM context

        await asyncio.to_thread(self._read_pm_context)

        # Use PlanReviewer for ALL stages (not just plan)
        if self._plan_reviewer and artifact_content:
            try:
                review = await asyncio.to_thread(
                    self._plan_reviewer.review_plan, agent_id, artifact_content
                )
                if review.confidence.level == "HIGH":
                    response = f"[PM] APPROVED: {review.note or f'{stage} stage approved'}"
                else:
                    response = f"[PM] NEEDS CHANGES: {review.note}"
                self._append_pm_context(
                    f"## {agent_id} {stage} review: {review.note[:200] if review.note else 'approved'}"
                )
                await self._post_throttled(agent_id, channel, response)
                return
            except Exception:
                logger.exception("PlanReviewer failed for %s %s", agent_id, stage)

        # Fallback: auto-approve if no reviewer or no artifacts
        response = f"[PM] APPROVED: {stage} stage looks good for {agent_id}"
        self._append_pm_context(f"## {agent_id} {stage} auto-approved")
        await self._post_throttled(agent_id, channel, response)

    def make_sync_callback(self) -> dict:
        """Create sync callback for on_plan_detected routing."""
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
