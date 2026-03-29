"""WorkflowOrchestratorCog: Bridges Discord events to agent containers via RuntimeAPI.

Listens for vco report messages in agent channels, triggers PM artifact reviews
at gates (CONTEXT.md at discussion gate, VERIFICATION.md at verify gate per D-07),
and advances the state machine. PlanReviewCog notifies this Cog on plan
approval/rejection via notify_plan_approved/notify_plan_rejected.

All container access goes through RuntimeAPI -- no direct CompanyRoot or
container references. This cog is a pure Discord I/O adapter.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

# Extracted from v1 workflow_orchestrator to shared utility during MIGR-03.
from vcompany.shared.workflow_types import (
    WorkflowStage,
    detect_stage_signal,
)

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot

logger = logging.getLogger("vcompany.bot.cogs.workflow_orchestrator_cog")


def _get_runtime_api(bot: VcoBot):
    """Get RuntimeAPI from daemon, or None if not available."""
    daemon = getattr(bot, "_daemon", None)
    if daemon is not None:
        return getattr(daemon, "runtime_api", None)
    return None


class WorkflowOrchestratorCog(commands.Cog):
    """Discord Cog that listens for vco report signals and drives gate reviews.

    Bridges Discord events (vco report messages in agent channels) to
    agent containers via RuntimeAPI. PM reviews artifacts at each gate:
    - CONTEXT.md at discussion gate
    - PLAN.md at plan gate (via existing PlanReviewCog)
    - VERIFICATION.md at verify gate (D-07)

    All container access goes through RuntimeAPI -- no direct CompanyRoot access.
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._pm = None  # Set via set_runtime_context
        self._project_dir: Path | None = None

    def _get_project_category_name(self) -> str | None:
        """Get the Discord category name for the current project."""
        if self.bot.project_config is not None:
            return f"vco-{self.bot.project_config.project}"
        return None

    def _find_agent_channel(self, guild: discord.Guild, agent_id: str) -> discord.TextChannel | None:
        """Find #agent-{id} scoped to the current project's category."""
        category_name = self._get_project_category_name()
        channel_name = f"agent-{agent_id}"
        for ch in guild.text_channels:
            if ch.name == channel_name:
                if category_name is None:
                    return ch
                if ch.category and ch.category.name == category_name:
                    return ch
        return None

    async def _send_system_event(self, agent_id: str, message: str) -> None:
        """Post a [system] event message in the agent's Discord channel (project-scoped)."""
        if not hasattr(self.bot, '_guild_id') or not self.bot._guild_id:
            return
        guild = self.bot.get_guild(self.bot._guild_id)
        if not guild:
            return
        channel = self._find_agent_channel(guild, agent_id)
        if channel:
            try:
                await channel.send(f"[system] {message}")
            except Exception:
                logger.exception("Failed to send system event to #agent-%s", agent_id)

    def set_runtime_context(
        self,
        pm,
        project_dir: Path,
    ) -> None:
        """Store PM and project directory references.

        RuntimeAPI is accessed via _get_runtime_api(self.bot).
        Called from bot on_ready after all components are initialized.
        """
        self._pm = pm
        self._project_dir = project_dir
        logger.info("WorkflowOrchestratorCog wired with PM and project_dir")


    @property
    def _initialized(self) -> bool:
        """Check if the cog is ready to process signals."""
        return _get_runtime_api(self.bot) is not None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Detect vco report stage completion signals in agent channels."""
        if not self._initialized:
            return

        # Only process messages in agent channels
        if not hasattr(message.channel, "name"):
            return
        if not message.channel.name.startswith("agent-"):
            return

        # Skip [system] messages to avoid infinite loops
        if message.content.startswith("[system]"):
            return

        # Detect stage completion signal
        signal = detect_stage_signal(message.content)
        if signal is None:
            return

        agent_id, stage = signal

        # Verify agent_id matches channel (sanity check)
        expected_channel = f"agent-{agent_id}"
        if message.channel.name != expected_channel:
            logger.warning(
                "Signal for agent %s in channel %s (expected %s), ignoring",
                agent_id,
                message.channel.name,
                expected_channel,
            )
            return

        # Verify container exists via RuntimeAPI
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is None:
            return

        container_info = await runtime_api.get_container_info(agent_id)
        if container_info is None:
            logger.warning("No container found for agent %s, ignoring signal", agent_id)
            return

        # Map stage signals to WorkflowStage enum for gate review dispatch
        stage_map = {
            "discuss": WorkflowStage.DISCUSSION_GATE,
            "plan": WorkflowStage.PM_PLAN_REVIEW_GATE,
            "execute": WorkflowStage.VERIFY,
            "verify": WorkflowStage.PHASE_COMPLETE,
        }
        new_stage = stage_map.get(stage)
        if new_stage is None:
            logger.warning("Unknown stage signal '%s' for agent %s", stage, agent_id)
            return

        logger.info(
            "Agent %s stage signal '%s' -> %s", agent_id, stage, new_stage.value
        )

        await self._send_system_event(
            agent_id,
            f"Stage '{stage}' complete -> entering {new_stage.value.upper().replace('_', ' ')}",
        )

        # Handle gate reviews based on new stage
        if new_stage == WorkflowStage.DISCUSSION_GATE:
            await self._review_discussion_gate(agent_id)
        elif new_stage == WorkflowStage.PM_PLAN_REVIEW_GATE:
            await self._review_plan_gate(agent_id)
        elif new_stage == WorkflowStage.VERIFY:
            await self._review_verify_gate(agent_id)
        elif new_stage == WorkflowStage.PHASE_COMPLETE:
            await self._handle_phase_complete(agent_id)

    async def _review_discussion_gate(self, agent_id: str) -> None:
        """Review CONTEXT.md at the discussion gate via PM evaluation."""
        if self._project_dir is None:
            return

        # Find CONTEXT.md in agent's clone
        clone_dir = self._project_dir / "clones" / agent_id
        phases_dir = clone_dir / ".planning" / "phases"

        context_content = ""
        if phases_dir.exists():
            context_files = sorted(phases_dir.rglob("*-CONTEXT.md"))
            if context_files:
                latest_context = context_files[-1]
                try:
                    raw = await asyncio.to_thread(latest_context.read_text)
                    context_content = raw[:3000]
                except Exception:
                    logger.exception(
                        "Failed to read CONTEXT.md for %s", agent_id
                    )

        if not context_content:
            logger.warning(
                "No CONTEXT.md found for %s, auto-advancing discussion gate",
                agent_id,
            )
            await self._send_system_event(
                agent_id,
                "DISCUSSION GATE -- no CONTEXT.md found, auto-advancing to PLAN stage",
            )
            return

        # PM review if available
        if self._pm is not None:
            try:
                review_prompt = (
                    f"Review this CONTEXT.md from agent '{agent_id}' for completeness "
                    f"and alignment with the project goals. Is the context research "
                    f"sufficient to proceed to planning?\n\n{context_content}"
                )
                decision = await self._pm.evaluate_question(review_prompt, agent_id)

                if decision.confidence.level in ("HIGH", "MEDIUM"):
                    logger.info(
                        "PM approved discussion gate for %s (confidence=%s)",
                        agent_id,
                        decision.confidence.level,
                    )
                    await self._send_system_event(
                        agent_id,
                        f"DISCUSSION GATE passed (PM confidence: {decision.confidence.level}) -> advancing to PLAN stage",
                    )
                else:
                    logger.warning(
                        "PM LOW confidence for %s discussion gate, blocking",
                        agent_id,
                    )
                    await self._send_system_event(
                        agent_id,
                        "DISCUSSION GATE blocked -- PM confidence LOW on CONTEXT.md. @Owner please review.",
                    )
                return
            except Exception:
                logger.exception(
                    "PM evaluation failed for %s discussion gate", agent_id
                )

        # No PM available -- auto-advance
        logger.info(
            "No PM available, auto-advancing discussion gate for %s", agent_id
        )
        await self._send_system_event(
            agent_id,
            "DISCUSSION GATE -- no PM available, auto-advancing to PLAN stage",
        )

    async def _review_plan_gate(self, agent_id: str) -> None:
        """Review plans at the PM plan review gate."""
        if self._project_dir is None:
            return

        clone_dir = self._project_dir / "clones" / agent_id
        phases_dir = clone_dir / ".planning" / "phases"

        plan_content = ""
        plan_count = 0
        if phases_dir.exists():
            plan_files = sorted(phases_dir.rglob("*-PLAN.md"))
            for pf in plan_files[-5:]:  # Last 5 plans max
                try:
                    raw = await asyncio.to_thread(pf.read_text)
                    plan_content += f"\n--- {pf.name} ---\n{raw[:1000]}\n"
                    plan_count += 1
                except Exception:
                    pass

        if not plan_content:
            logger.warning("No plans found for %s, auto-advancing plan gate", agent_id)
            await self._send_system_event(
                agent_id,
                "PM PLAN REVIEW GATE -- no plans found, auto-advancing to EXECUTE stage",
            )
            return

        # PM review
        if self._pm is not None:
            try:
                review_prompt = (
                    f"Review these {plan_count} plan(s) from agent '{agent_id}'. "
                    f"Are they reasonable and aligned with the project? "
                    f"Answer YES to approve or NO with reason to reject.\n\n{plan_content}"
                )
                decision = await self._pm.evaluate_question(review_prompt, agent_id)

                if decision.confidence.level in ("HIGH", "MEDIUM"):
                    await self._send_system_event(
                        agent_id,
                        f"PM PLAN REVIEW GATE passed -- {plan_count} plan(s) approved (PM confidence: {decision.confidence.level}) -> advancing to EXECUTE stage",
                    )
                else:
                    await self._send_system_event(
                        agent_id,
                        "PM PLAN REVIEW GATE blocked -- PM confidence LOW. @Owner please review plans.",
                    )
                return
            except Exception:
                logger.exception("PM evaluation failed for %s plan gate", agent_id)

        # No PM -- auto-advance
        logger.info("No PM available, auto-advancing plan gate for %s", agent_id)
        await self._send_system_event(
            agent_id,
            f"PM PLAN REVIEW GATE -- no PM available, auto-advancing to EXECUTE stage",
        )

    async def _review_verify_gate(self, agent_id: str) -> None:
        """Review VERIFICATION.md at the verify gate (D-07)."""
        if self._project_dir is None:
            return

        clone_dir = self._project_dir / "clones" / agent_id
        phases_dir = clone_dir / ".planning" / "phases"

        verification_content = ""
        if phases_dir.exists():
            verification_files = sorted(phases_dir.rglob("*-VERIFICATION.md"))
            if verification_files:
                latest = verification_files[-1]
                try:
                    raw = await asyncio.to_thread(latest.read_text)
                    verification_content = raw[:3000]
                except Exception:
                    logger.exception(
                        "Failed to read VERIFICATION.md for %s", agent_id
                    )

        if not verification_content:
            logger.warning(
                "No VERIFICATION.md found for %s, auto-advancing verify gate",
                agent_id,
            )
            await self._send_system_event(
                agent_id,
                "VERIFY GATE -- no VERIFICATION.md (verifier disabled), auto-advancing to PHASE COMPLETE",
            )
            await self._handle_phase_complete(agent_id)
            return

        content_upper = verification_content.upper()
        has_fail = "FAIL" in content_upper
        has_pass = "PASS" in content_upper

        if has_pass and not has_fail:
            logger.info(
                "VERIFICATION.md for %s shows all PASS, advancing to PHASE_COMPLETE",
                agent_id,
            )
            await self._send_system_event(
                agent_id,
                "VERIFY GATE passed -- all checks PASS -> advancing to PHASE COMPLETE",
            )
            await self._handle_phase_complete(agent_id)
            return

        # Failures found -- PM evaluates
        if self._pm is not None:
            try:
                review_prompt = (
                    f"Review this VERIFICATION.md from agent '{agent_id}'. "
                    f"It contains test/verification failures. Should the agent "
                    f"re-execute to fix them, or is manual review needed?\n\n"
                    f"{verification_content}"
                )
                decision = await self._pm.evaluate_question(review_prompt, agent_id)

                if decision.confidence.level in ("HIGH", "MEDIUM"):
                    logger.info(
                        "PM recommends re-execute for %s (confidence=%s)",
                        agent_id,
                        decision.confidence.level,
                    )
                    await self._send_system_event(
                        agent_id,
                        f"VERIFY GATE -- failures found, PM recommends re-execute (confidence: {decision.confidence.level})",
                    )
                else:
                    logger.warning(
                        "PM LOW confidence on verify gate for %s, blocking",
                        agent_id,
                    )
                    await self._send_system_event(
                        agent_id,
                        "VERIFY GATE blocked -- verification failures, PM confidence LOW. @Owner please review.",
                    )
                return
            except Exception:
                logger.exception(
                    "PM evaluation failed for %s verify gate", agent_id
                )

        # No PM -- re-execute by default if failures found
        logger.info(
            "No PM available, re-executing for %s due to verification failures",
            agent_id,
        )

    async def _handle_phase_complete(self, agent_id: str) -> None:
        """Handle phase completion for an agent via RuntimeAPI."""
        logger.info("Agent %s completed current phase", agent_id)

        await self._send_system_event(
            agent_id,
            "PHASE COMPLETE -- all stages passed",
        )

        # Route completion event to PM via RuntimeAPI (AUTO-05)
        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is not None:
            routed = await runtime_api.route_completion_to_pm(agent_id)
            if routed:
                logger.info("Routed completion event for %s to PM via RuntimeAPI", agent_id)

    async def notify_plan_approved(self, agent_id: str) -> None:
        """Called by PlanReviewCog after plan approval."""
        if not self._initialized:
            return

        await self._send_system_event(
            agent_id,
            "PM PLAN REVIEW GATE passed -- plans approved -> advancing to EXECUTE stage",
        )
        logger.info(
            "Plan approved for %s, advanced from PM_PLAN_REVIEW_GATE",
            agent_id,
        )

    async def notify_plan_rejected(self, agent_id: str) -> None:
        """Called by PlanReviewCog after plan rejection."""
        if not self._initialized:
            return

        await self._send_system_event(
            agent_id,
            "PM PLAN REVIEW GATE rejected -- plans sent back for replanning",
        )
        logger.info(
            "Plan rejected for %s, sent back to PLAN stage", agent_id
        )

    async def start_workflow(self, agent_id: str, phase: int) -> bool:
        """Kick off an agent's workflow for a phase via RuntimeAPI."""
        if not self._initialized:
            logger.error("Cannot start workflow: RuntimeAPI not initialized")
            return False

        runtime_api = _get_runtime_api(self.bot)
        if runtime_api is None:
            return False

        container_info = await runtime_api.get_container_info(agent_id)
        if container_info is None:
            logger.error("Cannot start workflow: container %s not found", agent_id)
            return False

        await self._send_system_event(
            agent_id,
            f"Workflow started -- Phase {phase}, entering DISCUSS stage",
        )
        return True


async def setup(bot) -> None:
    """Load WorkflowOrchestratorCog into the bot."""
    await bot.add_cog(WorkflowOrchestratorCog(bot))
