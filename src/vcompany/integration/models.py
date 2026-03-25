"""Data models for the integration pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TestResults:
    """Test run results from integration testing."""

    passed: int = 0
    failed: int = 0
    errors: int = 0
    failing_tests: list[str] = field(default_factory=list)


@dataclass
class IntegrationResult:
    """Result of an integration pipeline run."""

    status: str  # "success", "test_failure", "merge_conflict", "error"
    branch_name: str = ""
    merged_agents: list[str] = field(default_factory=list)
    test_results: TestResults | None = None
    pr_url: str = ""
    conflict_files: list[str] = field(default_factory=list)
    attribution: dict[str, list[str]] = field(default_factory=dict)
    error_message: str = ""
