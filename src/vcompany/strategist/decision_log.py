"""Decision logging to #decisions channel and local JSONL file.

All PM and Strategist decisions are logged as append-only records per D-18/STRAT-09.
Each entry includes timestamp, question/plan, decision, confidence level, and who decided.

Dual storage:
  1. Discord #decisions channel as compact embeds
  2. Local state/decisions.jsonl as append-only JSON lines for PM lookback
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import discord

from vcompany.strategist.models import DecisionLogEntry

logger = logging.getLogger(__name__)

# Confidence level to embed color mapping
_CONFIDENCE_COLORS: dict[str, discord.Colour] = {
    "HIGH": discord.Colour.green(),
    "MEDIUM": discord.Colour.yellow(),
    "LOW": discord.Colour.red(),
}

_DECISION_TRUNCATE_LEN = 200


class DecisionLogger:
    """Logs decisions to #decisions channel and local JSONL file.

    Append-only storage pattern: each log_decision call appends one JSON line
    to decisions.jsonl and posts a compact embed to the #decisions channel.

    Attributes:
        _decisions_path: Path to decisions.jsonl file.
        _decisions_channel: Discord #decisions channel (None if unavailable).
    """

    def __init__(
        self,
        decisions_path: Path,
        decisions_channel: discord.TextChannel | None = None,
    ) -> None:
        self._decisions_path = decisions_path
        self._decisions_channel = decisions_channel

    async def log_decision(self, entry: DecisionLogEntry) -> None:
        """Log a decision to both JSONL file and #decisions channel.

        File write is performed via asyncio.to_thread to avoid blocking.
        Channel errors are caught and logged, never raised.

        Args:
            entry: The decision log entry to record.
        """
        await asyncio.to_thread(self._append_to_file, entry)
        await self._post_to_channel(entry)

    def _append_to_file(self, entry: DecisionLogEntry) -> None:
        """Append entry as JSON line to decisions.jsonl (append mode)."""
        self._decisions_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._decisions_path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    async def _post_to_channel(self, entry: DecisionLogEntry) -> None:
        """Post compact embed to #decisions channel if available."""
        if self._decisions_channel is None:
            return

        color = _CONFIDENCE_COLORS.get(entry.confidence_level, discord.Colour.greyple())

        # Truncate decision text for embed
        decision_text = entry.decision
        if len(decision_text) > _DECISION_TRUNCATE_LEN:
            decision_text = decision_text[:_DECISION_TRUNCATE_LEN] + "..."

        embed = discord.Embed(
            title=f"{entry.decided_by} Decision",
            colour=color,
        )
        embed.add_field(name="Agent", value=entry.agent_id, inline=True)
        embed.add_field(name="Confidence", value=entry.confidence_level, inline=True)
        embed.add_field(name="Decision", value=decision_text, inline=False)
        embed.set_footer(text=entry.timestamp.isoformat())

        try:
            await self._decisions_channel.send(embed=embed)
        except Exception:
            logger.exception("Failed to post decision embed to #decisions")

    def load_decisions(self) -> list[DecisionLogEntry]:
        """Read all entries from decisions.jsonl.

        Skips malformed lines with a warning log.

        Returns:
            List of DecisionLogEntry objects.
        """
        if not self._decisions_path.exists():
            return []

        entries: list[DecisionLogEntry] = []
        for line_num, line in enumerate(
            self._decisions_path.read_text(encoding="utf-8").strip().split("\n"), 1
        ):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entries.append(DecisionLogEntry.model_validate(data))
            except (json.JSONDecodeError, Exception):
                logger.warning(
                    "Skipping malformed line %d in %s", line_num, self._decisions_path
                )
        return entries
