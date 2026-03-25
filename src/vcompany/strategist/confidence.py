"""Heuristic confidence scorer for the PM tier (D-08).

Deterministic scoring based on two signals:
1. Context coverage -- keyword matches in project documents.
2. Prior decision match -- Jaccard similarity with previous decisions.

Weighted combination: 60% coverage + 40% prior match (Research Pattern 4).
Thresholds per D-06/D-09: >0.9 HIGH, >=0.6 MEDIUM, <0.6 LOW.
"""

from vcompany.strategist.models import ConfidenceResult, DecisionLogEntry

# Common English stopwords to filter from keyword extraction.
STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "because", "but", "and", "or", "if", "while", "about", "against",
    "up", "down", "it", "its", "this", "that", "these", "those", "i",
    "me", "my", "we", "our", "you", "your", "he", "him", "his", "she",
    "her", "they", "them", "their", "what", "which", "who", "whom",
})


class ConfidenceScorer:
    """Deterministic heuristic confidence scorer for PM tier decisions.

    Implements D-08: PM confidence is heuristic-based, not AI self-assessed.
    """

    def score(
        self,
        question: str,
        context_docs: dict[str, str],
        decision_log: list[DecisionLogEntry],
    ) -> ConfidenceResult:
        """Score confidence for a question given project context and decision history.

        Args:
            question: The agent's question text.
            context_docs: Project documents keyed by name
                (e.g., "blueprint", "interfaces", "scope", "status").
            decision_log: Previous decision log entries for prior match.

        Returns:
            ConfidenceResult with score, level, coverage, and prior_match.
        """
        coverage = self._check_context_coverage(question, context_docs)
        prior_match = self._check_prior_decisions(question, decision_log)

        # Weighted combination per Research Pattern 4: 60% coverage + 40% prior match
        raw_score = coverage * 0.6 + prior_match * 0.4

        # Thresholds per D-06/D-09
        if raw_score > 0.9:
            level = "HIGH"
        elif raw_score >= 0.6:
            level = "MEDIUM"
        else:
            level = "LOW"

        return ConfidenceResult(
            score=raw_score,
            level=level,
            coverage=coverage,
            prior_match=prior_match,
        )

    def _check_context_coverage(
        self, question: str, context_docs: dict[str, str]
    ) -> float:
        """Check how many question keywords appear in context documents.

        Tokenizes the question into keywords (lowercase, filter stopwords),
        then counts how many appear in any context document.

        Returns:
            Fraction of keywords found (0.0 to 1.0).
        """
        keywords = self._extract_keywords(question)
        if not keywords:
            return 0.0

        # Combine all context docs into a single lowercase text for matching
        all_context = " ".join(context_docs.values()).lower()

        found = sum(1 for kw in keywords if kw in all_context)
        return found / len(keywords)

    def _check_prior_decisions(
        self, question: str, decision_log: list[DecisionLogEntry]
    ) -> float:
        """Check for similar prior decisions using Jaccard similarity.

        For each decision log entry, compares question word sets.
        Returns the maximum similarity found.

        Returns:
            Max Jaccard similarity (1.0 for exact match, 0.0 for no overlap).
        """
        if not decision_log:
            return 0.0

        question_words = set(self._extract_keywords(question))
        if not question_words:
            return 0.0

        max_similarity = 0.0
        for entry in decision_log:
            entry_words = set(self._extract_keywords(entry.question_or_plan))
            if not entry_words:
                continue
            intersection = question_words & entry_words
            union = question_words | entry_words
            similarity = len(intersection) / len(union) if union else 0.0
            max_similarity = max(max_similarity, similarity)

        return max_similarity

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from text.

        Splits on whitespace, lowercases, filters stopwords and short words.

        Returns:
            List of keyword strings.
        """
        words = text.lower().split()
        return [w for w in words if w not in STOPWORDS and len(w) > 1]
