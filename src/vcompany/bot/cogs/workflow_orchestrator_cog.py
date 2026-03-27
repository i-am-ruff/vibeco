"""WorkflowOrchestratorCog: Bridges Discord events to the WorkflowOrchestrator state machine.

Listens for vco report messages in agent channels, triggers PM artifact reviews
at gates (CONTEXT.md at discussion gate, VERIFICATION.md at verify gate per D-07),
and advances the state machine. PlanReviewCog notifies this Cog on plan
approval/rejection via notify_plan_approved/notify_plan_rejected.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from vcompany.orchestrator.workflow_orchestrator import (
    WorkflowStage,
    detect_stage_signal,
)

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot
    from vcompany.orchestrator.workflow_orchestrator import WorkflowOrchestrator
    from vcompany.strategist.pm import PMTier

logger = logging.getLogger("vcompany.bot.cogs.workflow_orchestrator_cog")


class WorkflowOrchestratorCog(commands.Cog):
    """Discord Cog that listens for vco report signals and drives gate reviews.

    Bridges Discord events (vco report messages in agent channels) to the
    WorkflowOrchestrator state machine. PM reviews artifacts at each gate:
    - CONTEXT.md at discussion gate
    - PLAN.md at plan gate (via existing PlanReviewCog)
    - VERIFICATION.md at verify gate (D-07)
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._orchestrator: WorkflowOrchestrator | None = None
        self._pm: PMTier | None = None
        self._project_dir: Path | None = None

    def set_orchestrator(
        self,
        orchestrator: WorkflowOrchestrator,
        pm: PMTier | None,
        project_dir: Path,
    ) -> None:
        """Store references to orchestrator, PM, and project directory.

        Called from bot on_ready after all components are initialized.
        """
        self._orchestrator = orchestrator
        self._pm = pm
        self._project_dir = project_dir
        logger.info("WorkflowOrchestratorCog wired with orchestrator and PM")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Detect vco report stage completion signals in agent channels.

        When a signal is detected, transitions the agent's state machine
        and triggers the appropriate gate review.
        """
        if self._orchestrator is None:
            return

        # Only process messages in agent channels
        if not hasattr(message.channel, "name"):
            return
        if not message.channel.name.startswith("agent-"):
            return

        # Skip bot's own messages
        if message.author.id == self.bot.user.id:
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

        # Transition the state machine
        new_stage = await asyncio.to_thread(
            self._orchestrator.on_stage_complete, agent_id, stage
        )

        logger.info(
            "Agent %s stage signal '%s' -> %s", agent_id, stage, new_stage.value
        )

        # Handle gate reviews based on new stage
        if new_stage == WorkflowStage.DISCUSSION_GATE:
            await self._review_discussion_gate(agent_id)
        elif new_stage == WorkflowStage.PM_PLAN_REVIEW_GATE:
            # PlanReviewCog handles plan review. Orchestrator waits for
            # notify_plan_approved/rejected callback.
            logger.info(
                "Agent %s at PM_PLAN_REVIEW_GATE, waiting for PlanReviewCog",
                agent_id,
            )
        elif new_stage == WorkflowStage.VERIFY:
            await self._review_verify_gate(agent_id)
        elif new_stage == WorkflowStage.PHASE_COMPLETE:
            await self._handle_phase_complete(agent_id)

    async def _review_discussion_gate(self, agent_id: str) -> None:
        """Review CONTEXT.md at the discussion gate via PM evaluation.

        Reads the agent's CONTEXT.md from their clone directory and asks
        the PM to evaluate completeness and alignment. HIGH/MEDIUM confidence
        advances the gate; LOW confidence blocks for owner review.
        """
        if self._orchestrator is None or self._project_dir is None:
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
            # No CONTEXT.md found -- auto-advance (agent may not produce one)
            logger.warning(
                "No CONTEXT.md found for %s, auto-advancing discussion gate",
                agent_id,
            )
            await asyncio.to_thread(
                self._orchestrator.advance_from_gate, agent_id, True
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
                    await asyncio.to_thread(
                        self._orchestrator.advance_from_gate, agent_id, True
                    )
                else:
                    # LOW confidence -- block and notify
                    logger.warning(
                        "PM LOW confidence for %s discussion gate, blocking",
                        agent_id,
                    )
                    self._orchestrator.handle_unknown_prompt(
                        agent_id,
                        f"Discussion gate: PM confidence LOW on CONTEXT.md review",
                    )
                    # Post to agent channel for owner visibility
                    guild = self.bot.get_guild(self.bot._guild_id)
                    if guild:
                        channel = discord.utils.get(
                            guild.text_channels, name=f"agent-{agent_id}"
                        )
                        if channel:
                            await channel.send(
                                f"[PM] CONTEXT.md review for {agent_id}: LOW confidence. "
                                f"@Owner please review and approve/reject."
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
        await asyncio.to_thread(
            self._orchestrator.advance_from_gate, agent_id, True
        )

    async def _review_verify_gate(self, agent_id: str) -> None:
        """Review VERIFICATION.md at the verify gate (D-07).

        PM reviews VERIFICATION.md before advancing to PHASE_COMPLETE.
        If all checks pass, advances. If failures found, PM evaluates
        whether to re-execute or block.
        """
        if self._orchestrator is None or self._project_dir is None:
            return

        # Find VERIFICATION.md in agent's clone
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

        # Transition to VERIFY_GATE first (execute -> verify was already done)
        state = self._orchestrator.get_agent_state(agent_id)
        if state and state.stage == WorkflowStage.VERIFY:
            state.stage = WorkflowStage.VERIFY_GATE

        if not verification_content:
            # No VERIFICATION.md -- auto-advance
            logger.warning(
                "No VERIFICATION.md found for %s, auto-advancing verify gate",
                agent_id,
            )
            await asyncio.to_thread(
                self._orchestrator.advance_from_gate, agent_id, True
            )
            return

        # Check for pass/fail patterns
        content_upper = verification_content.upper()
        has_fail = "FAIL" in content_upper
        has_pass = "PASS" in content_upper

        if has_pass and not has_fail:
            # All checks passed -- advance to PHASE_COMPLETE
            logger.info(
                "VERIFICATION.md for %s shows all PASS, advancing to PHASE_COMPLETE",
                agent_id,
            )
            await asyncio.to_thread(
                self._orchestrator.advance_from_gate, agent_id, True
            )
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
                    # PM suggests re-execute
                    logger.info(
                        "PM recommends re-execute for %s (confidence=%s)",
                        agent_id,
                        decision.confidence.level,
                    )
                    await asyncio.to_thread(
                        self._orchestrator.advance_from_gate, agent_id, False
                    )
                else:
                    # LOW confidence -- block for owner
                    logger.warning(
                        "PM LOW confidence on verify gate for %s, blocking",
                        agent_id,
                    )
                    self._orchestrator.handle_unknown_prompt(
                        agent_id,
                        "Verify gate: PM confidence LOW on VERIFICATION.md review",
                    )
                    guild = self.bot.get_guild(self.bot._guild_id)
                    if guild:
                        channel = discord.utils.get(
                            guild.text_channels, name=f"agent-{agent_id}"
                        )
                        if channel:
                            await channel.send(
                                f"[PM] VERIFICATION.md for {agent_id} has failures. "
                                f"LOW confidence on resolution. @Owner please review."
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
        await asyncio.to_thread(
            self._orchestrator.advance_from_gate, agent_id, False
        )

    async def _handle_phase_complete(self, agent_id: str) -> None:
        """Handle phase completion for an agent.

        Logs completion and checks if there's a next phase to start.
        """
        if self._orchestrator is None:
            return

        state = self._orchestrator.get_agent_state(agent_id)
        phase = state.current_phase if state else "unknown"

        logger.info(
            "Agent %s completed phase %s", agent_id, phase
        )

        # Post completion message to agent channel
        guild = self.bot.get_guild(self.bot._guild_id)
        if guild:
            channel = discord.utils.get(
                guild.text_channels, name=f"agent-{agent_id}"
            )
            if channel:
                await channel.send(
                    f"[Orchestrator] Agent {agent_id} completed phase {phase}."
                )

        # Check if there's a next phase (simple increment)
        if state and isinstance(phase, int):
            next_phase = phase + 1
            # Check if roadmap has this phase
            roadmap_path = self._project_dir / ".planning" / "ROADMAP.md" if self._project_dir else None
            if roadmap_path and roadmap_path.exists():
                try:
                    roadmap = await asyncio.to_thread(roadmap_path.read_text)
                    if f"Phase {next_phase}" in roadmap or f"phase-{next_phase}" in roadmap.lower():
                        logger.info(
                            "Starting next phase %d for agent %s",
                            next_phase,
                            agent_id,
                        )
                        await asyncio.to_thread(
                            self._orchestrator.start_agent, agent_id, next_phase
                        )
                        return
                except Exception:
                    logger.exception("Failed to check roadmap for next phase")

            # No next phase found -- set to IDLE
            if state:
                state.stage = WorkflowStage.IDLE
                logger.info(
                    "No next phase found for %s, setting to IDLE", agent_id
                )

    async def notify_plan_approved(self, agent_id: str) -> None:
        """Called by PlanReviewCog after plan approval.

        Advances the agent from PM_PLAN_REVIEW_GATE if that's the current stage.
        """
        if self._orchestrator is None:
            return

        state = self._orchestrator.get_agent_state(agent_id)
        if state and state.stage == WorkflowStage.PM_PLAN_REVIEW_GATE:
            await asyncio.to_thread(
                self._orchestrator.advance_from_gate, agent_id, True
            )
            logger.info(
                "Plan approved for %s, advanced from PM_PLAN_REVIEW_GATE",
                agent_id,
            )

    async def notify_plan_rejected(self, agent_id: str) -> None:
        """Called by PlanReviewCog after plan rejection.

        Sends agent back to PLAN stage for replanning.
        """
        if self._orchestrator is None:
            return

        state = self._orchestrator.get_agent_state(agent_id)
        if state and state.stage == WorkflowStage.PM_PLAN_REVIEW_GATE:
            await asyncio.to_thread(
                self._orchestrator.advance_from_gate, agent_id, False
            )
            logger.info(
                "Plan rejected for %s, sent back to PLAN stage", agent_id
            )

    async def start_workflow(self, agent_id: str, phase: int) -> bool:
        """Kick off an agent's workflow for a phase.

        Public method wrapping orchestrator.start_agent in asyncio.to_thread.

        Args:
            agent_id: Agent to start.
            phase: Phase number.

        Returns:
            True if the command was sent successfully.
        """
        if self._orchestrator is None:
            logger.error("Cannot start workflow: orchestrator not initialized")
            return False

        result = await asyncio.to_thread(
            self._orchestrator.start_agent, agent_id, phase
        )
        return result


async def setup(bot: VcoBot) -> None:
    """Load WorkflowOrchestratorCog into the bot."""
    await bot.add_cog(WorkflowOrchestratorCog(bot))
