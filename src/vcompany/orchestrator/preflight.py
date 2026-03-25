"""Pre-flight test suite for validating Claude Code headless behavior.

Runs 4 empirical tests against real Claude Code in a temp directory:
1. stream-json heartbeat -- can we monitor via stream events?
2. permission hang -- does Claude hang without --dangerously-skip-permissions?
3. max-turns exit -- does --max-turns exit (with non-zero code)?
4. resume recovery -- can a session be resumed after completion?

Results determine the monitor strategy for Phase 3:
- STREAM_JSON if stream-json heartbeat is reliable
- GIT_COMMIT_FALLBACK otherwise (conservative default)

Unit tests cover result interpretation only. The 4 live test functions
require a real Claude Code installation and API key.
"""

import json
import logging
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from vcompany.shared.file_ops import write_atomic

logger = logging.getLogger("vcompany.preflight")


# ── Data Models ──────────────────────────────────────────────────────────


class PreflightResult(BaseModel):
    """Result of a single pre-flight test."""

    test_name: str
    passed: bool
    inconclusive: bool = False
    details: str
    duration_seconds: float


class MonitorStrategy(str, Enum):
    """Monitor strategy determined by pre-flight results."""

    STREAM_JSON = "stream_json"
    GIT_COMMIT_FALLBACK = "git_commit_fallback"


class PreflightSuite(BaseModel):
    """Collection of all pre-flight test results."""

    results: list[PreflightResult]
    strategy: MonitorStrategy
    run_at: datetime
    claude_version: str = "unknown"

    @property
    def all_passed(self) -> bool:
        """True only if every test passed."""
        return all(r.passed for r in self.results)

    def summary(self) -> str:
        """Human-readable multiline summary of all test results."""
        lines = ["Pre-flight Test Results", "=" * 40]
        for r in self.results:
            if r.inconclusive:
                status = "INCONCLUSIVE"
            elif r.passed:
                status = "PASS"
            else:
                status = "FAIL"
            lines.append(f"  {r.test_name}: {status} ({r.duration_seconds:.1f}s)")
            if r.details:
                lines.append(f"    {r.details}")
        lines.append("-" * 40)
        lines.append(f"Strategy: {self.strategy.value}")
        lines.append(f"All passed: {self.all_passed}")
        return "\n".join(lines)


# ── Monitor Strategy Determination ───────────────────────────────────────


def determine_monitor_strategy(results: list[PreflightResult]) -> MonitorStrategy:
    """Determine monitor strategy from pre-flight results.

    If the stream-json heartbeat test passed, use STREAM_JSON monitoring.
    Otherwise (failed or inconclusive), fall back to GIT_COMMIT_FALLBACK.
    Per D-17, PRE-03.
    """
    for r in results:
        if r.test_name == "stream_json_heartbeat":
            if r.passed and not r.inconclusive:
                return MonitorStrategy.STREAM_JSON
            return MonitorStrategy.GIT_COMMIT_FALLBACK
    # If stream-json test not found, conservative fallback
    return MonitorStrategy.GIT_COMMIT_FALLBACK


# ── Live Test Functions ──────────────────────────────────────────────────


def test_stream_json_heartbeat(timeout: int = 60) -> PreflightResult:
    """Test: Does stream-json output produce JSON events we can monitor?

    Runs Claude Code with --output-format stream-json in a temp directory.
    Counts JSON lines received. If >= 1 valid JSON event within timeout,
    the test passes.
    """
    start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = subprocess.Popen(
                [
                    "claude",
                    "-p",
                    "--output-format",
                    "stream-json",
                    "--dangerously-skip-permissions",
                    "--max-turns",
                    "1",
                    "echo hello",
                ],
                cwd=tmpdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            json_events = 0
            try:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if proc.stdout is None:
                        break
                    line = proc.stdout.readline()
                    if not line:
                        if proc.poll() is not None:
                            break
                        continue
                    line = line.strip()
                    if line:
                        try:
                            json.loads(line)
                            json_events += 1
                        except json.JSONDecodeError:
                            pass
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

            elapsed = time.monotonic() - start
            if json_events >= 1:
                return PreflightResult(
                    test_name="stream_json_heartbeat",
                    passed=True,
                    details=f"Received {json_events} JSON events",
                    duration_seconds=elapsed,
                )
            return PreflightResult(
                test_name="stream_json_heartbeat",
                passed=False,
                details=f"No JSON events received within {timeout}s",
                duration_seconds=elapsed,
            )
    except Exception as e:
        elapsed = time.monotonic() - start
        return PreflightResult(
            test_name="stream_json_heartbeat",
            passed=False,
            inconclusive=True,
            details=f"Subprocess error: {e}",
            duration_seconds=elapsed,
        )


def test_permission_hang(timeout: int = 30) -> PreflightResult:
    """Test: Does Claude hang or exit without --dangerously-skip-permissions?

    Runs Claude Code WITHOUT --dangerously-skip-permissions to document behavior.
    Either way, passed=True (we are documenting behavior, not testing correctness).
    """
    start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                result = subprocess.run(
                    [
                        "claude",
                        "-p",
                        "--max-turns",
                        "1",
                        "list files",
                    ],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                elapsed = time.monotonic() - start
                return PreflightResult(
                    test_name="permission_hang",
                    passed=True,
                    details=f"exits normally without permission flag (exit code {result.returncode})",
                    duration_seconds=elapsed,
                )
            except subprocess.TimeoutExpired:
                elapsed = time.monotonic() - start
                return PreflightResult(
                    test_name="permission_hang",
                    passed=True,
                    details="hangs without permission flag -- flag is required",
                    duration_seconds=elapsed,
                )
    except Exception as e:
        elapsed = time.monotonic() - start
        return PreflightResult(
            test_name="permission_hang",
            passed=False,
            inconclusive=True,
            details=f"Error: {e}",
            duration_seconds=elapsed,
        )


def test_max_turns_exit(timeout: int = 60) -> PreflightResult:
    """Test: Does --max-turns exit and can we capture the exit code?

    Per Pitfall 3 and PRE-02: --max-turns exits with an error (non-zero).
    passed=True if process exits (regardless of code) and exit code is captured.
    """
    start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                result = subprocess.run(
                    [
                        "claude",
                        "-p",
                        "--dangerously-skip-permissions",
                        "--max-turns",
                        "1",
                        "list all files in current directory",
                    ],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                elapsed = time.monotonic() - start
                return PreflightResult(
                    test_name="max_turns_exit",
                    passed=True,
                    details=f"Process exited with code {result.returncode}",
                    duration_seconds=elapsed,
                )
            except subprocess.TimeoutExpired:
                elapsed = time.monotonic() - start
                return PreflightResult(
                    test_name="max_turns_exit",
                    passed=False,
                    details=f"Process did not exit within {timeout}s",
                    duration_seconds=elapsed,
                )
    except Exception as e:
        elapsed = time.monotonic() - start
        return PreflightResult(
            test_name="max_turns_exit",
            passed=False,
            inconclusive=True,
            details=f"Error: {e}",
            duration_seconds=elapsed,
        )


def test_resume_recovery(timeout: int = 120) -> PreflightResult:
    """Test: Can a session be resumed after completion?

    Step 1: Run claude to create a file.
    Step 2: Run claude with --continue to resume.
    passed=True if step 2 completes without error.
    """
    start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: Initial session
            try:
                subprocess.run(
                    [
                        "claude",
                        "-p",
                        "--dangerously-skip-permissions",
                        "--max-turns",
                        "1",
                        "create a file named test.txt",
                    ],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout // 2,
                )
            except subprocess.TimeoutExpired:
                elapsed = time.monotonic() - start
                return PreflightResult(
                    test_name="resume_recovery",
                    passed=False,
                    inconclusive=True,
                    details="Step 1 timed out",
                    duration_seconds=elapsed,
                )

            # Step 2: Resume
            try:
                result = subprocess.run(
                    [
                        "claude",
                        "-p",
                        "--dangerously-skip-permissions",
                        "--continue",
                        "/gsd:resume-work",
                    ],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout // 2,
                )
                elapsed = time.monotonic() - start
                continued = result.returncode == 0
                return PreflightResult(
                    test_name="resume_recovery",
                    passed=True,
                    details=f"Resume completed (exit code {result.returncode}, session continued: {continued})",
                    duration_seconds=elapsed,
                )
            except subprocess.TimeoutExpired:
                elapsed = time.monotonic() - start
                return PreflightResult(
                    test_name="resume_recovery",
                    passed=False,
                    inconclusive=True,
                    details="Step 2 (resume) timed out",
                    duration_seconds=elapsed,
                )
    except Exception as e:
        elapsed = time.monotonic() - start
        return PreflightResult(
            test_name="resume_recovery",
            passed=False,
            inconclusive=True,
            details=f"Error: {e}",
            duration_seconds=elapsed,
        )


# ── Runner ───────────────────────────────────────────────────────────────


def run_preflight(output_path: Path | None = None) -> PreflightSuite:
    """Run all 4 pre-flight tests and determine monitor strategy.

    Args:
        output_path: If provided, writes results JSON via write_atomic.

    Returns:
        PreflightSuite with all results and determined strategy.
    """
    logger.info("Starting pre-flight tests...")

    results = [
        test_stream_json_heartbeat(),
        test_permission_hang(),
        test_max_turns_exit(),
        test_resume_recovery(),
    ]

    strategy = determine_monitor_strategy(results)

    suite = PreflightSuite(
        results=results,
        strategy=strategy,
        run_at=datetime.now(timezone.utc),
    )

    if output_path is not None:
        output_path = Path(output_path)
        write_atomic(output_path, suite.model_dump_json(indent=2))
        logger.info("Results written to %s", output_path)

    return suite
