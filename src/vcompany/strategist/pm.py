"""PM tier: stateless question answering with confidence-based escalation.

Implements D-01 (stateless per call), D-05 (three-tier escalation chain),
D-06/D-09 (confidence thresholds), D-08 (heuristic confidence scoring).

The PM evaluates agent questions by:
1. Loading project context docs fresh each call (stateless per D-01).
2. Scoring confidence via heuristic ConfidenceScorer (D-08).
3. HIGH confidence: answers directly via Claude CLI.
4. MEDIUM confidence: answers with "@Owner can override" note (STRAT-04).
5. LOW confidence: escalates to Strategist without calling Claude (STRAT-05/D-05).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from vcompany.strategist.confidence import ConfidenceScorer
from vcompany.strategist.context_builder import build_pm_context
from vcompany.strategist.models import ConfidenceResult, DecisionLogEntry, PMDecision

logger = logging.getLogger("vcompany.strategist.pm")

# Context files loaded from project_dir/context/ for confidence scoring.
CONTEXT_FILES = [
    "PROJECT-BLUEPRINT.md",
    "INTERFACES.md",
    "MILESTONE-SCOPE.md",
    "PROJECT-STATUS.md",
]


class PMTier:
    """Stateless PM tier for agent question evaluation.

    Each call loads context fresh (D-01). Confidence scoring is heuristic-based
    (D-08), not AI self-assessed. Escalation follows D-05 chain.
    Uses Claude CLI (claude -p) for single-shot answers instead of Anthropic SDK.
    """

    def __init__(self, project_dir: Path, model: str = "sonnet") -> None:
        self._project_dir = project_dir
        self._model = model
        self._scorer = self._get_scorer()

    @staticmethod
    def _get_scorer() -> ConfidenceScorer:
        """Create a ConfidenceScorer instance. Overridable for testing."""
        return ConfidenceScorer()

    async def evaluate_question(
        self, question: str, agent_id: str
    ) -> PMDecision:
        """Evaluate an agent question with confidence-based escalation.

        Args:
            question: The agent's question text.
            agent_id: Identifier of the asking agent.

        Returns:
            PMDecision with answer (HIGH/MEDIUM) or escalation (LOW).
        """
        context_docs = self._load_context_docs()
        decision_log = self._load_decision_log()

        confidence = self._scorer.score(question, context_docs, decision_log)

        if confidence.level == "LOW":
            return PMDecision(
                answer=None,
                confidence=confidence,
                decided_by="PM",
                escalate_to="strategist",
            )

        # HIGH or MEDIUM: call Claude CLI for answer
        answer = await self._answer_directly(question, context_docs)

        note = ""
        if confidence.level == "MEDIUM":
            note = "PM confidence: medium -- @Owner can override"

        return PMDecision(
            answer=answer,
            confidence=confidence,
            decided_by="PM",
            note=note,
        )

    async def _answer_directly(
        self, question: str, context_docs: dict[str, str]
    ) -> str:
        """Make a fresh Claude CLI call to answer the question.

        Uses `claude -p` with --output-format json for single-shot answers.
        Tools are disabled (PM should only answer, not run code).

        Args:
            question: The agent's question.
            context_docs: Project context documents for prompt assembly.

        Returns:
            Answer text, or fallback message on failure.
        """
        try:
            system_prompt = build_pm_context(self._project_dir)

            cmd = [
                "claude",
                "-p",
                "--model", self._model,
                "--output-format", "json",
                "--system-prompt", system_prompt,
                "--tools", "",
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await proc.communicate(input=question.encode())

            if proc.returncode != 0:
                logger.error("Claude CLI exited with code %d for PM question", proc.returncode)
                return "PM was unable to generate an answer. Escalating."

            data = json.loads(stdout.decode())
            return data.get("result", "PM was unable to generate an answer. Escalating.")

        except Exception:
            logger.exception("Claude CLI call failed for PM question")
            return "PM was unable to generate an answer. Escalating."

    def _load_context_docs(self) -> dict[str, str]:
        """Load context documents from project_dir/context/.

        Returns:
            Dict mapping filename to content. Missing files are skipped.
        """
        context_dir = self._project_dir / "context"
        docs: dict[str, str] = {}
        for filename in CONTEXT_FILES:
            path = context_dir / filename
            if path.exists():
                docs[filename] = path.read_text()
        return docs

    def _load_decision_log(self) -> list[DecisionLogEntry]:
        """Load decision log entries from state/decisions.jsonl.

        Returns:
            List of validated DecisionLogEntry objects. Invalid lines skipped.
        """
        decisions_path = self._project_dir / "state" / "decisions.jsonl"
        if not decisions_path.exists():
            return []

        entries: list[DecisionLogEntry] = []
        for line in decisions_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entries.append(DecisionLogEntry(**data))
            except (json.JSONDecodeError, Exception):
                logger.debug("Skipping invalid decision log entry: %s", line[:80])
                continue

        return entries
