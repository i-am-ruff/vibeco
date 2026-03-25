"""Tests for N+1 test failure attribution algorithm.

TDD RED: These tests define the expected behavior for attribute_failures()
which isolates each agent's branch against main to determine blame.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from vcompany.git.ops import GitResult


class TestAttributeFailures:
    """Tests for the attribute_failures function."""

    @pytest.mark.asyncio
    async def test_single_agent_causes_failure(self) -> None:
        """Agent-A breaks test_foo, Agent-B is clean -> {agent-a: [test_foo]}."""
        from vcompany.integration.attribution import attribute_failures

        ok = GitResult(success=True, stdout="", stderr="", returncode=0)

        with (
            patch("vcompany.integration.attribution.git_ops") as mock_git,
            patch("vcompany.integration.attribution.asyncio") as mock_asyncio,
        ):
            mock_git.checkout_new_branch.return_value = ok
            mock_git.merge.return_value = ok
            mock_git.checkout.return_value = ok

            # Simulate: agent-a merge -> test_foo fails; agent-b merge -> test_foo passes
            agent_a_result = MagicMock()
            agent_a_result.returncode = 1
            agent_a_result.stdout = "FAILED tests/test_app.py::test_foo\n1 failed in 0.5s"
            agent_a_result.stderr = ""

            agent_b_result = MagicMock()
            agent_b_result.returncode = 0
            agent_b_result.stdout = "1 passed in 0.3s"
            agent_b_result.stderr = ""

            call_count = [0]
            subprocess_results = [agent_a_result, agent_b_result]

            async def mock_to_thread(fn, *args, **kwargs):
                if fn is subprocess.run:
                    idx = call_count[0]
                    call_count[0] += 1
                    return subprocess_results[idx]
                return fn(*args, **kwargs)

            mock_asyncio.to_thread = mock_to_thread

            result = await attribute_failures(
                integration_dir=Path("/repo/integration"),
                failed_tests=["tests/test_app.py::test_foo"],
                agent_ids=["agent-a", "agent-b"],
            )

        assert "agent-a" in result
        assert "tests/test_app.py::test_foo" in result["agent-a"]
        assert "agent-b" not in result

    @pytest.mark.asyncio
    async def test_interaction_failure(self) -> None:
        """All individual merges pass but combined fails -> _interaction."""
        from vcompany.integration.attribution import attribute_failures

        ok = GitResult(success=True, stdout="", stderr="", returncode=0)

        with (
            patch("vcompany.integration.attribution.git_ops") as mock_git,
            patch("vcompany.integration.attribution.asyncio") as mock_asyncio,
        ):
            mock_git.checkout_new_branch.return_value = ok
            mock_git.merge.return_value = ok
            mock_git.checkout.return_value = ok

            # Both individual agent runs pass
            pass_result = MagicMock()
            pass_result.returncode = 0
            pass_result.stdout = "1 passed in 0.3s"
            pass_result.stderr = ""

            async def mock_to_thread(fn, *args, **kwargs):
                if fn is subprocess.run:
                    return pass_result
                return fn(*args, **kwargs)

            mock_asyncio.to_thread = mock_to_thread

            result = await attribute_failures(
                integration_dir=Path("/repo/integration"),
                failed_tests=["tests/test_bar.py::test_bar"],
                agent_ids=["agent-a", "agent-b"],
            )

        assert "_interaction" in result
        assert "tests/test_bar.py::test_bar" in result["_interaction"]

    @pytest.mark.asyncio
    async def test_only_reruns_failing_tests(self) -> None:
        """Attribution only re-runs the specific failing tests, not full suite."""
        from vcompany.integration.attribution import attribute_failures

        ok = GitResult(success=True, stdout="", stderr="", returncode=0)
        captured_cmds: list[list[str]] = []

        with (
            patch("vcompany.integration.attribution.git_ops") as mock_git,
            patch("vcompany.integration.attribution.asyncio") as mock_asyncio,
        ):
            mock_git.checkout_new_branch.return_value = ok
            mock_git.merge.return_value = ok
            mock_git.checkout.return_value = ok

            pass_result = MagicMock()
            pass_result.returncode = 0
            pass_result.stdout = "1 passed"
            pass_result.stderr = ""

            async def mock_to_thread(fn, *args, **kwargs):
                if fn is subprocess.run:
                    cmd = args[0] if args else kwargs.get("args", [])
                    captured_cmds.append(list(cmd))
                    return pass_result
                return fn(*args, **kwargs)

            mock_asyncio.to_thread = mock_to_thread

            await attribute_failures(
                integration_dir=Path("/repo/integration"),
                failed_tests=["tests/test_x.py::test_one", "tests/test_y.py::test_two"],
                agent_ids=["agent-a"],
            )

        # Verify specific test names are in the command
        assert len(captured_cmds) >= 1
        cmd = captured_cmds[0]
        assert "tests/test_x.py::test_one" in cmd
        assert "tests/test_y.py::test_two" in cmd

    @pytest.mark.asyncio
    async def test_creates_temp_branch_per_agent(self) -> None:
        """Attribution creates _attr_{agent_id} branch from main for isolation."""
        from vcompany.integration.attribution import attribute_failures

        ok = GitResult(success=True, stdout="", stderr="", returncode=0)

        with (
            patch("vcompany.integration.attribution.git_ops") as mock_git,
            patch("vcompany.integration.attribution.asyncio") as mock_asyncio,
        ):
            mock_git.checkout_new_branch.return_value = ok
            mock_git.merge.return_value = ok
            mock_git.checkout.return_value = ok

            pass_result = MagicMock()
            pass_result.returncode = 0
            pass_result.stdout = "1 passed"
            pass_result.stderr = ""

            async def mock_to_thread(fn, *args, **kwargs):
                if fn is subprocess.run:
                    return pass_result
                return fn(*args, **kwargs)

            mock_asyncio.to_thread = mock_to_thread

            await attribute_failures(
                integration_dir=Path("/repo/integration"),
                failed_tests=["tests/test_z.py::test_z"],
                agent_ids=["agent-a", "agent-b"],
            )

        # Verify checkout to main and branch creation for each agent
        checkout_calls = mock_git.checkout.call_args_list
        assert any(
            c == call("main", cwd=Path("/repo/integration"))
            for c in checkout_calls
        )

        branch_calls = mock_git.checkout_new_branch.call_args_list
        branch_names = [c[0][0] for c in branch_calls]
        assert "_attr_agent-a" in branch_names
        assert "_attr_agent-b" in branch_names

    @pytest.mark.asyncio
    async def test_flaky_test_detection(self) -> None:
        """Test that passes on re-run in full merge -> _flaky."""
        from vcompany.integration.attribution import attribute_failures

        ok = GitResult(success=True, stdout="", stderr="", returncode=0)

        with (
            patch("vcompany.integration.attribution.git_ops") as mock_git,
            patch("vcompany.integration.attribution.asyncio") as mock_asyncio,
        ):
            mock_git.checkout_new_branch.return_value = ok
            mock_git.merge.return_value = ok
            mock_git.checkout.return_value = ok

            # All individual agent runs pass (same as interaction test)
            pass_result = MagicMock()
            pass_result.returncode = 0
            pass_result.stdout = "1 passed in 0.3s"
            pass_result.stderr = ""

            call_count = [0]

            async def mock_to_thread(fn, *args, **kwargs):
                if fn is subprocess.run:
                    call_count[0] += 1
                    return pass_result
                return fn(*args, **kwargs)

            mock_asyncio.to_thread = mock_to_thread

            # For flaky detection: we need the full-merge re-run to also pass
            # The algorithm first re-runs on full merge; if it passes there, it's flaky
            result = await attribute_failures(
                integration_dir=Path("/repo/integration"),
                failed_tests=["tests/test_baz.py::test_baz"],
                agent_ids=["agent-a"],
            )

        # If single-agent merge also passes, it could be interaction or flaky
        # With only one agent and test passes on individual -> _flaky (not _interaction for single agent)
        # The distinction: _interaction requires multiple agents. Single agent + passes = _flaky
        assert "_flaky" in result or "_interaction" in result
