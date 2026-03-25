"""Tests for the git operations wrapper."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from vcompany.git.ops import GitResult, clone, checkout_new_branch, status, log, add, commit


def _git_init(path: Path) -> None:
    """Helper: initialize a git repo at path."""
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(path), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(path), capture_output=True, check=True,
    )


class TestGitStatus:
    def test_status_clean_repo(self, tmp_path: Path) -> None:
        _git_init(tmp_path)
        result = status(tmp_path)
        assert isinstance(result, GitResult)
        assert result.success is True
        assert result.returncode == 0

    def test_status_returns_gitresult(self, tmp_path: Path) -> None:
        _git_init(tmp_path)
        result = status(tmp_path)
        assert hasattr(result, "success")
        assert hasattr(result, "stdout")
        assert hasattr(result, "stderr")
        assert hasattr(result, "returncode")


class TestGitCheckout:
    def test_checkout_new_branch(self, tmp_path: Path) -> None:
        _git_init(tmp_path)
        # Need at least one commit to create a branch
        (tmp_path / "README.md").write_text("init")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=str(tmp_path), capture_output=True,
        )
        result = checkout_new_branch("feature-test", tmp_path)
        assert result.success is True
        # Verify branch exists
        branch_result = subprocess.run(
            ["git", "branch"], cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert "feature-test" in branch_result.stdout


class TestGitClone:
    def test_clone_repo(self, tmp_path: Path) -> None:
        # Create a bare repo to clone from
        bare = tmp_path / "bare.git"
        subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True)

        target = tmp_path / "cloned"
        result = clone(str(bare), target)
        assert result.success is True
        assert target.exists()
        assert (target / ".git").exists()

    def test_clone_nonexistent_repo(self, tmp_path: Path) -> None:
        target = tmp_path / "cloned"
        result = clone("https://example.com/nonexistent/repo.git", target)
        assert result.success is False
        assert result.stderr  # Should have meaningful error message
        assert result.returncode != 0


class TestGitTimeout:
    def test_git_timeout(self, tmp_path: Path) -> None:
        _git_init(tmp_path)
        with patch("vcompany.git.ops.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=1)
            result = status(tmp_path)
            assert result.success is False
            assert result.returncode == -1


class TestGitCommit:
    def test_commit_with_message(self, tmp_path: Path) -> None:
        _git_init(tmp_path)
        (tmp_path / "file.txt").write_text("hello")
        add_result = add(tmp_path)
        assert add_result.success is True
        commit_result = commit("test commit", tmp_path)
        assert commit_result.success is True
        # Verify commit exists
        log_result = log(tmp_path)
        assert log_result.success is True
        assert "test commit" in log_result.stdout
