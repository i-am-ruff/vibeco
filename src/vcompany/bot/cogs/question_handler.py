"""QuestionHandlerCog: Detects agent questions in #agent-{id} channels and delivers answers via Discord reply.

Listens for bot-posted question embeds in agent channels (posted by ask_discord.py hook
using the bot token). PM auto-answers via Discord reply (D-09/D-11). Escalation uses
non-reply Pattern B mentions (D-10). Owner escalation happens in agent channel (D-03).

No file-based IPC -- all answer delivery is via Discord replies (D-04, D-13).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from vcompany.bot.routing import is_question_embed

logger = logging.getLogger("vcompany.bot.cogs.question_handler")

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot
    from vcompany.strategist.pm import PMTier


class QuestionHandlerCog(commands.Cog):
    """Detects question embeds in #agent-{id} channels and delivers answers via Discord reply.

    Phase 9: Uses routing framework's is_question_embed() to detect questions posted by
    the hook. PM evaluates and replies directly. Escalation uses non-reply Pattern B.
    No file-based IPC remains.
    """

    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot
        self._pm: PMTier | None = None
        self._entity_prefixes = {"pm": "[PM]"}

    def set_pm(self, pm: PMTier) -> None:
        """Inject PMTier for question evaluation. Called from bot startup."""
        self._pm = pm

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Detect question embeds in agent channels and auto-answer via PM.

        1. Bot's own messages: check for question embed pattern.
        2. Non-bot messages: check if it's an owner reply to a pending escalation.
        """
        # Question embeds are posted by the hook using the bot token,
        # so message.author.id == bot.user.id
        if message.author.id != self.bot.user.id:
            # Not a bot message -- nothing for us to detect here.
            # Owner replies to escalations are handled by StrategistCog's
            # pending_escalations mechanism.
            return

        # Check if this is a question embed from the hook
        result = is_question_embed(message)
        if result is None:
            return

        agent_id, request_id = result

        # Extract question text from embed description
        embed = message.embeds[0]
        question_text = embed.description or ""

        # Extract options from embed fields
        options = [
            {"name": field.name, "value": field.value or ""}
            for field in embed.fields
        ]

        # PM intercept: evaluate question and reply
        if self._pm is not None and question_text:
            try:
                await self._handle_pm_evaluation(
                    message, agent_id, request_id, question_text, options
                )
            except Exception:
                logger.exception(
                    "PM evaluation failed for %s, question will sit for manual reply",
                    agent_id,
                )
                # Graceful degradation: question sits in channel for manual reply
            return

        # PM not injected: question sits in channel for manual human reply
        # (graceful degradation when ANTHROPIC_API_KEY is not set)

    async def _handle_pm_evaluation(
        self,
        message: discord.Message,
        agent_id: str,
        request_id: str,
        question_text: str,
        options: list[dict[str, str]],
    ) -> None:
        """Evaluate question via PM and deliver answer by Discord reply."""
        decision = await self._pm.evaluate_question(question_text, agent_id)

        if decision.confidence.level == "HIGH":
            # Auto-answer: reply to the question message
            await message.reply(f"[PM] {decision.answer}")
            # D-19: Do NOT log routine HIGH-confidence PM answers
            return

        elif decision.confidence.level == "MEDIUM":
            # Answer with note, reply to the question message
            await message.reply(f"[PM] {decision.answer}\n*{decision.note}*")
            # D-19: Log escalation-worthy event
            await self._log_decision(
                agent_id, question_text, decision.answer or "", "MEDIUM", "PM"
            )
            return

        else:  # LOW
            # Escalate to Strategist -- non-reply Pattern B (D-10)
            await message.channel.send(
                f"[PM] Escalating to @Strategist -- confidence too low for: {question_text[:200]}"
            )

            strategist_cog = self.bot.get_cog("StrategistCog")
            if strategist_cog is not None:
                strat_answer = await strategist_cog.handle_pm_escalation(
                    agent_id, question_text, decision.confidence.score
                )
                if strat_answer:
                    # Strategist answered -- reply to original question
                    # Strategist speaks without prefix per D-05
                    await message.reply(strat_answer)
                    await self._log_decision(
                        agent_id, question_text, strat_answer, "MEDIUM", "Strategist"
                    )
                    return
                else:
                    # Strategist also unsure -- escalate to Owner in agent channel (D-03)
                    await message.channel.send(
                        f"[PM] @Owner -- strategic decision needed for {agent_id}: {question_text[:200]}"
                    )
                    owner_answer = await strategist_cog.post_owner_escalation(
                        agent_id,
                        question_text,
                        decision.confidence.score,
                        channel=message.channel,
                    )
                    # Reply to original question with owner's decision
                    await message.reply(f"Owner decided: {owner_answer}")
                    await self._log_decision(
                        agent_id, question_text, owner_answer, "OWNER", "Owner"
                    )
                    return

            # StrategistCog not available -- question sits for manual reply

    async def _log_decision(
        self,
        agent_id: str,
        question: str,
        decision: str,
        confidence_level: str,
        decided_by: str,
    ) -> None:
        """Log a decision via StrategistCog's DecisionLogger if available.

        Only called for escalated decisions per D-19 (not routine HIGH-confidence).
        """
        strategist_cog = self.bot.get_cog("StrategistCog")
        if strategist_cog and strategist_cog.decision_logger:
            from vcompany.strategist.models import DecisionLogEntry

            await strategist_cog.decision_logger.log_decision(
                DecisionLogEntry(
                    timestamp=datetime.now(timezone.utc),
                    question_or_plan=question,
                    decision=decision,
                    confidence_level=confidence_level,
                    decided_by=decided_by,
                    agent_id=agent_id,
                )
            )


async def setup(bot: commands.Bot) -> None:
    """Load QuestionHandlerCog into the bot."""
    await bot.add_cog(QuestionHandlerCog(bot))
