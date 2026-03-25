"""Pydantic v2 models for the PM/Strategist decision system.

Defines data models for confidence scoring (D-08/D-09), PM decisions (D-06),
decision logging (D-18), and knowledge transfer documents (D-12).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ConfidenceResult(BaseModel):
    """Result of heuristic confidence scoring per D-08.

    Attributes:
        score: Raw weighted score (0.0 to 1.0).
        level: Threshold-based level per D-06/D-09: >0.9 HIGH, >=0.6 MEDIUM, <0.6 LOW.
        coverage: Context coverage sub-score (0.0 to 1.0).
        prior_match: Prior decision match sub-score (0.0 to 1.0).
    """

    score: float
    level: Literal["HIGH", "MEDIUM", "LOW"]
    coverage: float
    prior_match: float


class PMDecision(BaseModel):
    """Result of a PM tier evaluation for an agent question or plan.

    Attributes:
        answer: The PM's answer, or None if escalating.
        confidence: Heuristic confidence result.
        decided_by: Who made the decision (PM, Strategist, or Owner).
        note: Optional annotation (e.g., "PM confidence: medium -- @Owner can override").
        escalate_to: If set, indicates escalation target ("strategist" or "owner").
    """

    answer: str | None
    confidence: ConfidenceResult
    decided_by: Literal["PM", "Strategist", "Owner"]
    note: str = ""
    escalate_to: str | None = None


class DecisionLogEntry(BaseModel):
    """Single decision record for #decisions channel and local log (D-18).

    Attributes:
        timestamp: When the decision was made.
        question_or_plan: The agent's question or plan identifier.
        decision: The decision text.
        confidence_level: HIGH, MEDIUM, or LOW.
        decided_by: Who decided (PM, Strategist, Owner).
        agent_id: Which agent asked the question.
    """

    timestamp: datetime
    question_or_plan: str
    decision: str
    confidence_level: str
    decided_by: str
    agent_id: str


class KnowledgeTransferDoc(BaseModel):
    """Knowledge transfer document for Strategist context handoff (D-12).

    Generated when the persistent conversation approaches ~800K tokens.
    Used to seed a fresh Strategist session with accumulated context.

    Attributes:
        generated_at: When the KT document was generated.
        token_count: Token count at time of generation.
        decisions_summary: Summary of key decisions made.
        personality_notes: Calibration notes for maintaining Strategist personality.
        project_state: Current project state summary.
        open_threads: List of unresolved topics/questions.
    """

    generated_at: datetime
    token_count: int
    decisions_summary: str
    personality_notes: str
    project_state: str
    open_threads: list[str]
