"""Data models for integration pipeline results.

IntegrationResult captures the outcome of a full integration run.
TestRunResult captures the outcome of a test suite execution.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TestRunResult(BaseModel):
    """Result of running the test suite."""

    passed: bool
    total: int = 0
    failed: int = 0
    failed_tests: list[str] = []
    output: str = ""


class IntegrationResult(BaseModel):
    """Result of an integration pipeline run."""

    status: Literal["success", "test_failure", "merge_conflict", "error"]
    branch_name: str
    merged_agents: list[str] = []
    test_results: TestRunResult | None = None
    attribution: dict[str, list[str]] = {}  # agent_id -> [failing_test_names]
    pr_url: str | None = None
    conflict_files: list[str] = []
    error: str = ""
