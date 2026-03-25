"""Tests for git/ops.py extensions and IntegrationPipeline.

TDD RED: These tests define the expected behavior for merge, fetch, push,
diff, merge_abort, checkout operations, and the IntegrationPipeline class.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vcompany.git.ops import GitResult


# ---------------------------------------------------------------------------
# Git ops extension tests
# ---------------------------------------------------------------------------


class TestMerge:
    """Tests for git merge wrapper."""

    @patch("vcompany.git.ops._run_git")
    def test_merge_clean(self, mock_run: MagicMock) -> None:
        mock_run.return_value = GitResult(
            success=True, stdout="Merge made by the 'ort' strategy.", stderr="", returncode=0
        )
        from vcompany.git.ops import merge

        result = merge("feature-branch", cwd=Path("/repo"))
        assert result.success is True
        mock_run.assert_called_once_with("merge", "feature-branch", cwd=Path("/repo"), timeout=120)

    @patch("vcompany.git.ops._run_git")
    def test_merge_conflict(self, mock_run: MagicMock) -> None:
        mock_run.return_value = GitResult(
            success=False,
            stdout="",
            stderr="CONFLICT (content): Merge conflict in src/app.py\nAutomatic merge failed",
            returncode=1,
        )
        from vcompany.git.ops import merge

        result = merge("conflicting-branch", cwd=Path("/repo"))
        assert result.success is False
        assert "CONFLICT" in result.stderr

    @patch("vcompany.git.ops._run_git")
    def test_merge_no_ff(self, mock_run: MagicMock) -> None:
        mock_run.return_value = GitResult(success=True, stdout="", stderr="", returncode=0)
        from vcompany.git.ops import merge

        merge("feature", cwd=Path("/repo"), no_ff=True)
        mock_run.assert_called_once_with("merge", "--no-ff", "feature", cwd=Path("/repo"), timeout=120)


class TestFetch:
    @patch("vcompany.git.ops._run_git")
    def test_fetch_default(self, mock_run: MagicMock) -> None:
        mock_run.return_value = GitResult(success=True, stdout="", stderr="", returncode=0)
        from vcompany.git.ops import fetch

        result = fetch(cwd=Path("/repo"))
        assert result.success is True
        mock_run.assert_called_once_with("fetch", "origin", cwd=Path("/repo"), timeout=120)

    @patch("vcompany.git.ops._run_git")
    def test_fetch_custom_remote(self, mock_run: MagicMock) -> None:
        mock_run.return_value = GitResult(success=True, stdout="", stderr="", returncode=0)
        from vcompany.git.ops import fetch

        fetch(cwd=Path("/repo"), remote="upstream")
        mock_run.assert_called_once_with("fetch", "upstream", cwd=Path("/repo"), timeout=120)


class TestPush:
    @patch("vcompany.git.ops._run_git")
    def test_push_default(self, mock_run: MagicMock) -> None:
        mock_run.return_value = GitResult(success=True, stdout="", stderr="", returncode=0)
        from vcompany.git.ops import push

        result = push(cwd=Path("/repo"))
        assert result.success is True
        mock_run.assert_called_once_with("push", "origin", cwd=Path("/repo"), timeout=120)

    @patch("vcompany.git.ops._run_git")
    def test_push_with_branch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = GitResult(success=True, stdout="", stderr="", returncode=0)
        from vcompany.git.ops import push

        push(cwd=Path("/repo"), branch="integrate/123")
        mock_run.assert_called_once_with("push", "origin", "integrate/123", cwd=Path("/repo"), timeout=120)


class TestDiff:
    @patch("vcompany.git.ops._run_git")
    def test_diff_passthrough(self, mock_run: MagicMock) -> None:
        mock_run.return_value = GitResult(success=True, stdout="diff output", stderr="", returncode=0)
        from vcompany.git.ops import diff

        result = diff(cwd=Path("/repo"), args=["--stat", "HEAD~1"])
        assert result.success is True
        mock_run.assert_called_once_with("diff", "--stat", "HEAD~1", cwd=Path("/repo"))

    @patch("vcompany.git.ops._run_git")
    def test_diff_no_args(self, mock_run: MagicMock) -> None:
        mock_run.return_value = GitResult(success=True, stdout="", stderr="", returncode=0)
        from vcompany.git.ops import diff

        diff(cwd=Path("/repo"))
        mock_run.assert_called_once_with("diff", cwd=Path("/repo"))


class TestMergeAbort:
    @patch("vcompany.git.ops._run_git")
    def test_merge_abort(self, mock_run: MagicMock) -> None:
        mock_run.return_value = GitResult(success=True, stdout="", stderr="", returncode=0)
        from vcompany.git.ops import merge_abort

        result = merge_abort(cwd=Path("/repo"))
        assert result.success is True
        mock_run.assert_called_once_with("merge", "--abort", cwd=Path("/repo"))


class TestCheckout:
    @patch("vcompany.git.ops._run_git")
    def test_checkout_existing(self, mock_run: MagicMock) -> None:
        mock_run.return_value = GitResult(success=True, stdout="", stderr="", returncode=0)
        from vcompany.git.ops import checkout

        result = checkout("main", cwd=Path("/repo"))
        assert result.success is True
        mock_run.assert_called_once_with("checkout", "main", cwd=Path("/repo"))


# ---------------------------------------------------------------------------
# Integration models tests
# ---------------------------------------------------------------------------


class TestIntegrationModels:
    def test_integration_result_success(self) -> None:
        from vcompany.integration.models import IntegrationResult, TestRunResult

        tr = TestRunResult(passed=True, total=10, failed=0)
        result = IntegrationResult(
            status="success",
            branch_name="integrate/123",
            merged_agents=["agent-a", "agent-b"],
            test_results=tr,
            pr_url="https://github.com/org/repo/pull/1",
        )
        assert result.status == "success"
        assert result.pr_url is not None
        assert len(result.merged_agents) == 2

    def test_integration_result_merge_conflict(self) -> None:
        from vcompany.integration.models import IntegrationResult

        result = IntegrationResult(
            status="merge_conflict",
            branch_name="integrate/456",
            conflict_files=["src/app.py", "src/utils.py"],
        )
        assert result.status == "merge_conflict"
        assert len(result.conflict_files) == 2

    def test_integration_result_test_failure(self) -> None:
        from vcompany.integration.models import IntegrationResult, TestRunResult

        tr = TestRunResult(passed=False, total=10, failed=2, failed_tests=["test_a", "test_b"])
        result = IntegrationResult(
            status="test_failure",
            branch_name="integrate/789",
            test_results=tr,
            attribution={"agent-a": ["test_a"], "agent-b": ["test_b"]},
        )
        assert result.status == "test_failure"
        assert result.attribution["agent-a"] == ["test_a"]

    def test_integration_result_error(self) -> None:
        from vcompany.integration.models import IntegrationResult

        result = IntegrationResult(
            status="error",
            branch_name="integrate/000",
            error="Something went wrong",
        )
        assert result.status == "error"
        assert result.error == "Something went wrong"

    def test_test_run_result_defaults(self) -> None:
        from vcompany.integration.models import TestRunResult

        tr = TestRunResult(passed=True)
        assert tr.total == 0
        assert tr.failed == 0
        assert tr.failed_tests == []
        assert tr.output == ""


# ---------------------------------------------------------------------------
# IntegrationPipeline tests
# ---------------------------------------------------------------------------


class TestIntegrationPipeline:
    """Tests for the IntegrationPipeline.run() method."""

    @pytest.mark.asyncio
    async def test_run_success_creates_pr(self) -> None:
        """All merges clean, tests pass -> creates PR, returns success."""
        from vcompany.integration.pipeline import IntegrationPipeline

        pipeline = IntegrationPipeline(
            project_dir=Path("/projects/myapp"),
            agent_ids=["agent-a", "agent-b"],
        )

        ok = GitResult(success=True, stdout="", stderr="", returncode=0)

        with (
            patch("vcompany.integration.pipeline.git_ops") as mock_git,
            patch.object(pipeline, "_run_tests") as mock_tests,
            patch.object(pipeline, "_create_pr") as mock_pr,
            patch("vcompany.integration.pipeline.time") as mock_time,
        ):
            mock_time.time.return_value = 1700000.0
            mock_git.fetch.return_value = ok
            mock_git.checkout.return_value = ok
            mock_git.checkout_new_branch.return_value = ok
            mock_git.merge.return_value = ok
            mock_git.push.return_value = ok

            from vcompany.integration.models import TestRunResult

            mock_tests.return_value = TestRunResult(passed=True, total=5, failed=0)
            mock_pr.return_value = "https://github.com/org/repo/pull/42"

            result = await pipeline.run()

        assert result.status == "success"
        assert result.pr_url == "https://github.com/org/repo/pull/42"
        assert "agent-a" in result.merged_agents
        assert "agent-b" in result.merged_agents
        assert result.branch_name.startswith("integrate/")

    @pytest.mark.asyncio
    async def test_run_merge_conflict(self) -> None:
        """Merge conflict returns status=merge_conflict with files."""
        from vcompany.integration.pipeline import IntegrationPipeline

        pipeline = IntegrationPipeline(
            project_dir=Path("/projects/myapp"),
            agent_ids=["agent-a", "agent-b"],
        )

        ok = GitResult(success=True, stdout="", stderr="", returncode=0)
        conflict = GitResult(
            success=False,
            stdout="",
            stderr="CONFLICT (content): Merge conflict in src/app.py\nAutomatic merge failed",
            returncode=1,
        )

        with (
            patch("vcompany.integration.pipeline.git_ops") as mock_git,
            patch("vcompany.integration.pipeline.time") as mock_time,
        ):
            mock_time.time.return_value = 1700000.0
            mock_git.fetch.return_value = ok
            mock_git.checkout.return_value = ok
            mock_git.checkout_new_branch.return_value = ok
            mock_git.merge.side_effect = [ok, conflict]  # agent-a ok, agent-b conflict
            mock_git.merge_abort.return_value = ok

            result = await pipeline.run()

        assert result.status == "merge_conflict"
        assert "src/app.py" in result.conflict_files

    @pytest.mark.asyncio
    async def test_run_test_failure_with_attribution(self) -> None:
        """Test failures trigger attribution and return test_failure status."""
        from vcompany.integration.pipeline import IntegrationPipeline

        pipeline = IntegrationPipeline(
            project_dir=Path("/projects/myapp"),
            agent_ids=["agent-a", "agent-b"],
        )

        ok = GitResult(success=True, stdout="", stderr="", returncode=0)

        with (
            patch("vcompany.integration.pipeline.git_ops") as mock_git,
            patch.object(pipeline, "_run_tests") as mock_tests,
            patch("vcompany.integration.pipeline.attribute_failures") as mock_attr,
            patch("vcompany.integration.pipeline.time") as mock_time,
        ):
            mock_time.time.return_value = 1700000.0
            mock_git.fetch.return_value = ok
            mock_git.checkout.return_value = ok
            mock_git.checkout_new_branch.return_value = ok
            mock_git.merge.return_value = ok

            from vcompany.integration.models import TestRunResult

            mock_tests.return_value = TestRunResult(
                passed=False, total=5, failed=2, failed_tests=["test_a", "test_b"]
            )
            mock_attr.return_value = {"agent-a": ["test_a", "test_b"]}

            result = await pipeline.run()

        assert result.status == "test_failure"
        assert result.attribution == {"agent-a": ["test_a", "test_b"]}

    @pytest.mark.asyncio
    async def test_branch_naming(self) -> None:
        """Integration branch uses integrate/{timestamp} format."""
        from vcompany.integration.pipeline import IntegrationPipeline

        pipeline = IntegrationPipeline(
            project_dir=Path("/projects/myapp"),
            agent_ids=["agent-a"],
        )

        ok = GitResult(success=True, stdout="", stderr="", returncode=0)

        with (
            patch("vcompany.integration.pipeline.git_ops") as mock_git,
            patch.object(pipeline, "_run_tests") as mock_tests,
            patch.object(pipeline, "_create_pr") as mock_pr,
            patch("vcompany.integration.pipeline.time") as mock_time,
        ):
            mock_time.time.return_value = 1700001.5
            mock_git.fetch.return_value = ok
            mock_git.checkout.return_value = ok
            mock_git.checkout_new_branch.return_value = ok
            mock_git.merge.return_value = ok
            mock_git.push.return_value = ok

            from vcompany.integration.models import TestRunResult

            mock_tests.return_value = TestRunResult(passed=True, total=1, failed=0)
            mock_pr.return_value = "https://github.com/org/repo/pull/1"

            result = await pipeline.run()

        assert result.branch_name == "integrate/1700001500"

    @pytest.mark.asyncio
    async def test_pr_creation_uses_gh(self) -> None:
        """PR creation calls gh pr create with correct flags."""
        from vcompany.integration.pipeline import IntegrationPipeline

        pipeline = IntegrationPipeline(
            project_dir=Path("/projects/myapp"),
            agent_ids=["agent-a"],
        )

        with patch("vcompany.integration.pipeline.asyncio") as mock_asyncio:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "https://github.com/org/repo/pull/99"

            async def mock_to_thread(fn, *args, **kwargs):
                return fn(*args, **kwargs)

            mock_asyncio.to_thread = mock_to_thread

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="https://github.com/org/repo/pull/99\n",
                    stderr="",
                )
                pr_url = await pipeline._create_pr("integrate/123")

            assert pr_url == "https://github.com/org/repo/pull/99"
            call_args = mock_run.call_args
            cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
            assert "gh" in cmd
            assert "pr" in cmd
            assert "create" in cmd
            assert "--base" in cmd
            assert "main" in cmd

    def test_parse_conflict_files(self) -> None:
        """Conflict file parsing extracts paths from git merge stderr."""
        from vcompany.integration.pipeline import IntegrationPipeline

        pipeline = IntegrationPipeline(
            project_dir=Path("/projects/myapp"),
            agent_ids=[],
        )
        stderr = (
            "Auto-merging src/utils.py\n"
            "CONFLICT (content): Merge conflict in src/app.py\n"
            "CONFLICT (content): Merge conflict in src/models.py\n"
            "Automatic merge failed; fix conflicts and then commit the result."
        )
        files = pipeline._parse_conflict_files(stderr)
        assert sorted(files) == ["src/app.py", "src/models.py"]
