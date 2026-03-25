"""Tests for strategist confidence scoring and Pydantic models."""

from datetime import datetime, timezone

import pytest

from vcompany.strategist.confidence import ConfidenceScorer
from vcompany.strategist.models import (
    ConfidenceResult,
    DecisionLogEntry,
    KnowledgeTransferDoc,
    PMDecision,
)


# --- ConfidenceResult model tests ---


class TestConfidenceResult:
    def test_has_required_fields(self):
        result = ConfidenceResult(
            score=0.85, level="MEDIUM", coverage=0.9, prior_match=0.7
        )
        assert result.score == 0.85
        assert result.level == "MEDIUM"
        assert result.coverage == 0.9
        assert result.prior_match == 0.7


# --- PMDecision model tests ---


class TestPMDecision:
    def test_serializes_to_json(self):
        confidence = ConfidenceResult(
            score=0.95, level="HIGH", coverage=1.0, prior_match=0.9
        )
        decision = PMDecision(
            answer="Use JWT tokens",
            confidence=confidence,
            decided_by="PM",
        )
        json_str = decision.model_dump_json()
        assert "Use JWT tokens" in json_str
        assert "HIGH" in json_str

    def test_optional_fields(self):
        confidence = ConfidenceResult(
            score=0.5, level="LOW", coverage=0.3, prior_match=0.2
        )
        decision = PMDecision(
            answer=None,
            confidence=confidence,
            decided_by="Strategist",
            note="needs review",
            escalate_to="Owner",
        )
        assert decision.answer is None
        assert decision.note == "needs review"
        assert decision.escalate_to == "Owner"


# --- DecisionLogEntry model tests ---


class TestDecisionLogEntry:
    def test_has_required_fields(self):
        entry = DecisionLogEntry(
            timestamp=datetime(2026, 3, 25, tzinfo=timezone.utc),
            question_or_plan="Should we use REST or GraphQL?",
            decision="Use REST for v1",
            confidence_level="HIGH",
            decided_by="PM",
            agent_id="backend-01",
        )
        assert entry.question_or_plan == "Should we use REST or GraphQL?"
        assert entry.decided_by == "PM"
        assert entry.agent_id == "backend-01"


# --- KnowledgeTransferDoc model tests ---


class TestKnowledgeTransferDoc:
    def test_has_required_fields(self):
        doc = KnowledgeTransferDoc(
            generated_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
            token_count=500000,
            decisions_summary="Key decisions made...",
            personality_notes="Friendly CEO-friend tone",
            project_state="Phase 6 in progress",
            open_threads=["Auth design", "API versioning"],
        )
        assert doc.token_count == 500000
        assert len(doc.open_threads) == 2


# --- ConfidenceScorer tests ---


class TestConfidenceScorerThresholds:
    def test_high_confidence_when_score_above_90(self):
        scorer = ConfidenceScorer()
        # Full coverage + exact prior match = 1.0 * 0.6 + 1.0 * 0.4 = 1.0 > 0.9
        result = scorer.score(
            question="authentication tokens jwt",
            context_docs={
                "blueprint": "authentication tokens jwt secure login",
                "interfaces": "authentication tokens jwt api endpoints",
                "scope": "authentication tokens jwt milestone",
                "status": "authentication tokens jwt completed",
            },
            decision_log=[
                DecisionLogEntry(
                    timestamp=datetime(2026, 3, 25, tzinfo=timezone.utc),
                    question_or_plan="authentication tokens jwt",
                    decision="Use JWT",
                    confidence_level="HIGH",
                    decided_by="PM",
                    agent_id="backend-01",
                ),
            ],
        )
        assert result.level == "HIGH"
        assert result.score > 0.9

    def test_medium_confidence_when_score_between_60_and_90(self):
        scorer = ConfidenceScorer()
        # Moderate coverage, no prior match
        # coverage ~1.0 * 0.6 + 0.0 * 0.4 = 0.6 -> MEDIUM
        result = scorer.score(
            question="database migration strategy",
            context_docs={
                "blueprint": "database migration strategy schema updates",
                "interfaces": "database migration endpoints",
                "scope": "database migration milestone",
                "status": "database migration pending",
            },
            decision_log=[],
        )
        assert result.level == "MEDIUM"
        assert 0.6 <= result.score <= 0.9

    def test_low_confidence_when_score_below_60(self):
        scorer = ConfidenceScorer()
        # Low coverage, no prior match
        result = scorer.score(
            question="should we pivot to microservices architecture",
            context_docs={
                "blueprint": "monolith application",
            },
            decision_log=[],
        )
        assert result.level == "LOW"
        assert result.score < 0.6


class TestContextCoverage:
    def test_finds_keyword_matches_in_docs(self):
        scorer = ConfidenceScorer()
        result = scorer.score(
            question="authentication login security",
            context_docs={
                "blueprint": "authentication is required for login with security",
            },
            decision_log=[],
        )
        assert result.coverage > 0.5

    def test_zero_coverage_when_no_matches(self):
        scorer = ConfidenceScorer()
        result = scorer.score(
            question="quantum computing blockchain",
            context_docs={
                "blueprint": "simple web application with forms",
            },
            decision_log=[],
        )
        assert result.coverage == 0.0


class TestPriorDecisionMatch:
    def test_exact_question_match_returns_high(self):
        scorer = ConfidenceScorer()
        result = scorer.score(
            question="should we use REST or GraphQL",
            context_docs={"blueprint": "api design rest graphql"},
            decision_log=[
                DecisionLogEntry(
                    timestamp=datetime(2026, 3, 25, tzinfo=timezone.utc),
                    question_or_plan="should we use REST or GraphQL",
                    decision="Use REST",
                    confidence_level="HIGH",
                    decided_by="PM",
                    agent_id="backend-01",
                ),
            ],
        )
        assert result.prior_match == 1.0

    def test_partial_match_returns_moderate(self):
        scorer = ConfidenceScorer()
        result = scorer.score(
            question="REST API design patterns",
            context_docs={"blueprint": "rest api"},
            decision_log=[
                DecisionLogEntry(
                    timestamp=datetime(2026, 3, 25, tzinfo=timezone.utc),
                    question_or_plan="should we use REST or GraphQL for the API",
                    decision="Use REST",
                    confidence_level="HIGH",
                    decided_by="PM",
                    agent_id="backend-01",
                ),
            ],
        )
        assert 0.0 < result.prior_match < 1.0

    def test_no_match_returns_zero(self):
        scorer = ConfidenceScorer()
        result = scorer.score(
            question="database migration strategy",
            context_docs={"blueprint": "database"},
            decision_log=[
                DecisionLogEntry(
                    timestamp=datetime(2026, 3, 25, tzinfo=timezone.utc),
                    question_or_plan="authentication tokens jwt",
                    decision="Use JWT",
                    confidence_level="HIGH",
                    decided_by="PM",
                    agent_id="backend-01",
                ),
            ],
        )
        assert result.prior_match == 0.0


class TestWeightedCombination:
    def test_60_coverage_40_prior_match_weighting(self):
        scorer = ConfidenceScorer()
        # Create scenario where we can verify weighting
        # Full coverage (1.0) + no prior match (0.0) = 1.0 * 0.6 + 0.0 * 0.4 = 0.6
        result = scorer.score(
            question="simple test",
            context_docs={
                "blueprint": "simple test words here",
            },
            decision_log=[],
        )
        # With full coverage and no prior match, score should be ~0.6
        expected = result.coverage * 0.6 + result.prior_match * 0.4
        assert abs(result.score - expected) < 0.001
