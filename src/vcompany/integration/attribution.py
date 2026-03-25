"""N+1 test failure attribution algorithm.

Given a list of failed tests and agent IDs, determines which agent's branch
is responsible for each test failure by isolating merges against main.

Algorithm (D-06):
1. For each agent: checkout main, merge only that agent's branch
2. Re-run ONLY the failing tests (not full suite)
3. If tests fail with just agent-A -> agent-A owns those tests
4. If tests pass with every individual branch -> interaction failure ("_interaction")
5. If a test passes on re-run against full merge -> flaky ("_flaky")
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from vcompany.git import ops as git_ops
from vcompany.shared.logging import get_logger

logger = get_logger("integration.attribution")


async def attribute_failures(
    integration_dir: Path,
    failed_tests: list[str],
    agent_ids: list[str],
) -> dict[str, list[str]]:
    """Map test failures to responsible agent branches.

    Args:
        integration_dir: Path to the integration clone directory.
        failed_tests: List of failing test identifiers (e.g. tests/test_foo.py::test_bar).
        agent_ids: List of agent IDs whose branches were merged.

    Returns:
        Mapping of agent_id to list of test names they are responsible for.
        Special keys: "_interaction" for cross-agent issues, "_flaky" for flaky tests.
    """
    if not failed_tests:
        return {}

    attribution: dict[str, list[str]] = {}
    # Track which tests have been attributed to at least one agent
    attributed_tests: set[str] = set()

    # For each agent, isolate their branch against main and re-run failing tests
    for agent_id in agent_ids:
        temp_branch = f"_attr_{agent_id}"
        agent_branch = f"agent/{agent_id.lower()}"

        try:
            # Checkout main and create temp branch
            git_ops.checkout("main", cwd=integration_dir)
            git_ops.checkout_new_branch(temp_branch, cwd=integration_dir)

            # Merge only this agent's branch
            merge_result = git_ops.merge(agent_branch, cwd=integration_dir)
            if not merge_result.success:
                # If merge itself fails, attribute all tests to this agent
                attribution[agent_id] = list(failed_tests)
                attributed_tests.update(failed_tests)
                continue

            # Re-run ONLY the failing tests
            test_result = await asyncio.to_thread(
                subprocess.run,
                ["uv", "run", "pytest"] + list(failed_tests) + ["--tb=line", "-q"],
                cwd=integration_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if test_result.returncode != 0:
                # Parse which specific tests failed
                agent_failures = _parse_failed_tests(test_result.stdout, failed_tests)
                if agent_failures:
                    attribution[agent_id] = agent_failures
                    attributed_tests.update(agent_failures)

        finally:
            # Clean up: go back to main
            git_ops.checkout("main", cwd=integration_dir)

    # Tests that no individual agent caused
    unattributed = [t for t in failed_tests if t not in attributed_tests]

    if unattributed:
        if len(agent_ids) > 1:
            # Multiple agents but no single agent causes the failure -> interaction
            attribution["_interaction"] = unattributed
        else:
            # Single agent but test passes on individual merge -> flaky
            attribution["_flaky"] = unattributed

    return attribution


def _parse_failed_tests(
    output: str,
    candidate_tests: list[str],
) -> list[str]:
    """Parse pytest output for failed tests from the candidate list.

    Args:
        output: pytest stdout output.
        candidate_tests: The tests we re-ran (to match against).

    Returns:
        List of tests from candidate_tests that failed.
    """
    failed: list[str] = []

    # Look for FAILED lines in pytest output
    failed_in_output: set[str] = set()
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("FAILED "):
            # Format: FAILED tests/test_foo.py::test_bar - reason
            test_id = line.split(" ")[1].split(" - ")[0] if " " in line else line
            failed_in_output.add(test_id)

    # Match candidates against failures
    for test in candidate_tests:
        if test in failed_in_output:
            failed.append(test)

    # If pytest failed but no FAILED lines parsed, all candidates likely failed
    if not failed and failed_in_output:
        return list(candidate_tests)

    return failed
