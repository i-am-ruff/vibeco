"""Git operations wrapper using subprocess.

All git operations go through this module. Returns structured GitResult objects
instead of raising exceptions, so callers can handle failures gracefully.

Never uses check=True -- callers inspect GitResult.success instead.
Never uses GitPython -- subprocess.run() is more reliable and always available.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from vcompany.shared.logging import get_logger

logger = get_logger("git")


@dataclass
class GitResult:
    """Structured result from a git operation."""

    success: bool
    stdout: str
    stderr: str
    returncode: int


def _run_git(*args: str, cwd: Path | None = None, timeout: int = 60) -> GitResult:
    """Run a git command and return a structured result.

    Args:
        *args: Git subcommand and arguments (e.g., "status", "--porcelain").
        cwd: Working directory for the git command.
        timeout: Maximum seconds to wait (default 60).

    Returns:
        GitResult with success, stdout, stderr, and returncode.
    """
    cmd = ["git"] + list(args)
    logger.debug("git %s (cwd=%s)", " ".join(args), cwd)
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return GitResult(
            success=result.returncode == 0,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired:
        logger.error("git %s timed out after %ds", " ".join(args), timeout)
        return GitResult(success=False, stdout="", stderr="Timeout", returncode=-1)


def clone(repo_url: str, target: Path, branch: str | None = None) -> GitResult:
    """Clone a git repository to target directory.

    Args:
        repo_url: Repository URL or local path.
        target: Directory to clone into.
        branch: Optional branch to checkout after clone.
    """
    args = ["clone", repo_url, str(target)]
    if branch:
        args.extend(["-b", branch])
    return _run_git(*args)


def checkout_new_branch(branch_name: str, cwd: Path) -> GitResult:
    """Create and checkout a new branch.

    Args:
        branch_name: Name of the new branch.
        cwd: Repository working directory.
    """
    return _run_git("checkout", "-b", branch_name, cwd=cwd)


def status(cwd: Path) -> GitResult:
    """Get porcelain status of a repository.

    Args:
        cwd: Repository working directory.
    """
    return _run_git("status", "--porcelain", cwd=cwd)


def log(cwd: Path, args: list[str] | None = None) -> GitResult:
    """Get git log output.

    Args:
        cwd: Repository working directory.
        args: Additional arguments for git log (e.g., ["--oneline", "-5"]).
    """
    extra = args or []
    return _run_git("log", *extra, cwd=cwd)


def add(cwd: Path, paths: list[str] | None = None) -> GitResult:
    """Stage files for commit.

    Args:
        cwd: Repository working directory.
        paths: Files to add. Defaults to "." (all).
    """
    targets = paths or ["."]
    return _run_git("add", *targets, cwd=cwd)


def commit(message: str, cwd: Path) -> GitResult:
    """Create a commit with the given message.

    Args:
        message: Commit message.
        cwd: Repository working directory.
    """
    return _run_git("commit", "-m", message, cwd=cwd)


def branch(cwd: Path) -> GitResult:
    """List branches in the repository.

    Args:
        cwd: Repository working directory.
    """
    return _run_git("branch", cwd=cwd)


def merge(branch: str, cwd: Path, no_ff: bool = False) -> GitResult:
    """Merge a branch into the current branch.

    Args:
        branch: Branch name to merge.
        cwd: Repository working directory.
        no_ff: If True, create a merge commit even for fast-forward merges.
    """
    args: list[str] = ["merge"]
    if no_ff:
        args.append("--no-ff")
    args.append(branch)
    return _run_git(*args, cwd=cwd, timeout=120)


def fetch(cwd: Path, remote: str = "origin") -> GitResult:
    """Fetch from a remote.

    Args:
        cwd: Repository working directory.
        remote: Remote name (default "origin").
    """
    return _run_git("fetch", remote, cwd=cwd, timeout=120)


def push(cwd: Path, remote: str = "origin", branch: str | None = None) -> GitResult:
    """Push to a remote.

    Args:
        cwd: Repository working directory.
        remote: Remote name (default "origin").
        branch: Optional branch to push.
    """
    args: list[str] = ["push", remote]
    if branch:
        args.append(branch)
    return _run_git(*args, cwd=cwd, timeout=120)


def diff(cwd: Path, args: list[str] | None = None) -> GitResult:
    """Show diff output.

    Args:
        cwd: Repository working directory.
        args: Additional arguments for git diff.
    """
    extra = args or []
    return _run_git("diff", *extra, cwd=cwd)


def merge_abort(cwd: Path) -> GitResult:
    """Abort a merge in progress.

    Args:
        cwd: Repository working directory.
    """
    return _run_git("merge", "--abort", cwd=cwd)


def checkout(branch: str, cwd: Path) -> GitResult:
    """Checkout an existing branch.

    Args:
        branch: Branch name to checkout.
        cwd: Repository working directory.
    """
    return _run_git("checkout", branch, cwd=cwd)
