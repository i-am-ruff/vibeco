"""Integration pipeline: merge agent branches, run tests, create PR.

The IntegrationPipeline orchestrates the full integration cycle:
1. Fetch latest, create integration branch from main
2. Merge each agent's branch (agent/{id.lower()})
3. Run the test suite
4. On pass: push branch and create PR via gh
5. On fail: run N+1 attribution to identify responsible agents
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from vcompany.git import ops as git_ops
from vcompany.integration.attribution import attribute_failures
from vcompany.integration.models import IntegrationResult, TestRunResult
from vcompany.shared.logging import get_logger

logger = get_logger("integration.pipeline")


class IntegrationPipeline:
    """Merges agent branches, runs tests, creates PR on success."""

    def __init__(
        self,
        project_dir: Path,
        agent_ids: list[str],
        pm: Any | None = None,
    ) -> None:
        self._project_dir = project_dir
        self._integration_dir = project_dir / "integration"
        self._agent_ids = agent_ids
        self._pm = pm

    async def run(self) -> IntegrationResult:
        """Execute the full integration pipeline.

        Returns:
            IntegrationResult with status, merged agents, test results, etc.
        """
        branch_name = f"integrate/{int(time.time() * 1000)}"
        merged_agents: list[str] = []

        try:
            # 1. Fetch and create integration branch
            git_ops.fetch(cwd=self._integration_dir)
            git_ops.checkout("main", cwd=self._integration_dir)
            git_ops.checkout_new_branch(branch_name, cwd=self._integration_dir)

            # 2. Merge each agent's branch
            for agent_id in self._agent_ids:
                agent_branch = f"agent/{agent_id.lower()}"
                result = git_ops.merge(agent_branch, cwd=self._integration_dir)
                if not result.success:
                    conflict_files = self._parse_conflict_files(result.stderr)
                    git_ops.merge_abort(cwd=self._integration_dir)
                    return IntegrationResult(
                        status="merge_conflict",
                        branch_name=branch_name,
                        merged_agents=merged_agents,
                        conflict_files=conflict_files,
                        error=f"Merge conflict with {agent_branch}",
                    )
                merged_agents.append(agent_id)

            # 3. Run tests
            test_results = await self._run_tests()

            if test_results.passed:
                # 4. Push and create PR
                git_ops.push(
                    cwd=self._integration_dir,
                    branch=branch_name,
                )
                pr_url = await self._create_pr(branch_name)
                return IntegrationResult(
                    status="success",
                    branch_name=branch_name,
                    merged_agents=merged_agents,
                    test_results=test_results,
                    pr_url=pr_url,
                )

            # 5. Test failure -- attribute to agents
            attribution = await attribute_failures(
                integration_dir=self._integration_dir,
                failed_tests=test_results.failed_tests,
                agent_ids=self._agent_ids,
            )
            return IntegrationResult(
                status="test_failure",
                branch_name=branch_name,
                merged_agents=merged_agents,
                test_results=test_results,
                attribution=attribution,
            )

        except Exception as exc:
            logger.error("Integration pipeline error: %s", exc)
            return IntegrationResult(
                status="error",
                branch_name=branch_name,
                merged_agents=merged_agents,
                error=str(exc),
            )

    async def _run_tests(self) -> TestRunResult:
        """Run the test suite in the integration directory.

        Returns:
            TestRunResult with pass/fail status and details.
        """
        result = await asyncio.to_thread(
            subprocess.run,
            ["uv", "run", "pytest", "tests/", "-x", "-q", "--tb=line"],
            cwd=self._integration_dir,
            capture_output=True,
            text=True,
            timeout=600,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        # Parse failed test names from pytest output
        failed_tests: list[str] = []
        if not passed:
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("FAILED "):
                    # Format: FAILED tests/test_foo.py::test_bar - reason
                    test_name = line.split(" ")[1].split(" - ")[0] if " " in line else line
                    failed_tests.append(test_name)

        # Parse totals from pytest summary line
        total = 0
        failed = 0
        for line in output.splitlines():
            if "passed" in line or "failed" in line:
                # e.g., "3 failed, 7 passed in 1.23s"
                import re as _re

                m_failed = _re.search(r"(\d+) failed", line)
                m_passed = _re.search(r"(\d+) passed", line)
                if m_failed:
                    failed = int(m_failed.group(1))
                if m_passed:
                    total = int(m_passed.group(1)) + failed
                elif m_failed:
                    total = failed

        return TestRunResult(
            passed=passed,
            total=total,
            failed=failed,
            failed_tests=failed_tests,
            output=output,
        )

    async def _create_pr(self, branch_name: str) -> str:
        """Create a pull request via gh CLI.

        Args:
            branch_name: The integration branch name.

        Returns:
            PR URL string.
        """
        agents_str = ", ".join(self._agent_ids)
        title = f"Integration: {branch_name}"
        body = f"Merged agents: {agents_str}"

        result = await asyncio.to_thread(
            subprocess.run,
            [
                "gh", "pr", "create",
                "--title", title,
                "--body", body,
                "--base", "main",
                "--head", branch_name,
            ],
            cwd=self._integration_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        return result.stdout.strip()

    def _parse_conflict_files(self, stderr: str) -> list[str]:
        """Extract conflicting file paths from git merge stderr.

        Args:
            stderr: The stderr output from a failed git merge.

        Returns:
            List of file paths with conflicts.
        """
        files: list[str] = []
        for line in stderr.splitlines():
            match = re.match(r"CONFLICT \(.*?\): Merge conflict in (.+)", line)
            if match:
                files.append(match.group(1).strip())
        return files
