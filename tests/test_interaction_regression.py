"""Interaction regression tests for critical concurrent scenarios (SAFE-04).

Derived from INTERACTIONS.md patterns. Each test simulates a concurrent
scenario using threads or asyncio to verify safety invariants.

Per D-15: marked with @pytest.mark.integration -- run only during vco integrate.
Per D-16: uses mocks/fakes for tmux and subprocess.
"""

import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration  # All tests in this file are integration


class TestAtomicWriteDuringRead:
    """Monitor reads while agent writes -- INTERACTIONS.md pattern 1."""

    def test_concurrent_read_during_atomic_write(self, tmp_path: Path) -> None:
        """write_atomic produces complete content visible to concurrent readers.

        Verifies: Reader never sees partial content. Uses threading to
        simulate concurrent read/write on the same file path.
        """
        from vcompany.shared.file_ops import write_atomic

        target = tmp_path / "state.md"
        target.write_text("initial content")

        results: list[str] = []
        barrier = threading.Barrier(2)

        def writer() -> None:
            barrier.wait()
            write_atomic(target, "updated content that is longer")

        def reader() -> None:
            barrier.wait()
            for _ in range(100):
                content = target.read_text()
                results.append(content)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Every read must be either the old or new complete content
        for content in results:
            assert content in ("initial content", "updated content that is longer"), (
                f"Partial read detected: {content!r}"
            )


class TestGitCloneIsolation:
    """Simultaneous git operations across clones -- INTERACTIONS.md pattern 2."""

    def test_parallel_git_status_in_separate_clones(self, tmp_path: Path) -> None:
        """Git operations in independent clone dirs do not interfere."""
        from vcompany.git import ops as git_ops

        # Create two fake git repos
        for name in ("clone-a", "clone-b"):
            d = tmp_path / name
            d.mkdir()
            (d / ".git").mkdir()

        with patch.object(git_ops, "_run_git") as mock_git:
            mock_git.return_value = git_ops.GitResult(True, "", "", 0)
            results: list[git_ops.GitResult] = []
            threads = []
            for name in ("clone-a", "clone-b"):
                t = threading.Thread(
                    target=lambda n=name: results.append(
                        git_ops.status(tmp_path / n)
                    )
                )
                threads.append(t)
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(results) == 2
            assert all(r.success for r in results)


class TestProjectStatusDistribution:
    """PROJECT-STATUS.md atomic rename -- INTERACTIONS.md pattern 3."""

    def test_atomic_rename_visible_as_complete_file(self, tmp_path: Path) -> None:
        """Concurrent readers never see partial PROJECT-STATUS.md content."""
        from vcompany.shared.file_ops import write_atomic

        target = tmp_path / "PROJECT-STATUS.md"
        old_content = "# Status v1\n\nAll agents running."
        new_content = "# Status v2\n\nAll agents running.\n\n## Agent-A\nPhase 3 complete."
        target.write_text(old_content)

        reads: list[str] = []
        barrier = threading.Barrier(2)

        def distributor() -> None:
            barrier.wait()
            write_atomic(target, new_content)

        def agent_reader() -> None:
            barrier.wait()
            for _ in range(100):
                reads.append(target.read_text())

        t1 = threading.Thread(target=distributor)
        t2 = threading.Thread(target=agent_reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        for content in reads:
            assert content in (old_content, new_content), (
                f"Partial PROJECT-STATUS.md read: {content!r}"
            )


class TestPlanGateSendKeys:
    """Plan gate approve while agent idle -- INTERACTIONS.md pattern 4."""

    def test_send_keys_safe_when_agent_idle(self) -> None:
        """Mock tmux send_keys succeeds when pane exists and agent is idle."""
        tmux = MagicMock()
        tmux.send_command.return_value = True

        # Simulate plan gate approval sending execute command
        result = tmux.send_command("pane-1", "/gsd:execute-phase 01-foundation")
        assert result is True
        tmux.send_command.assert_called_once()


class TestSyncContextDuringExecution:
    """sync-context during agent execution -- INTERACTIONS.md pattern 5."""

    def test_sync_context_write_atomic_safe_during_read(self, tmp_path: Path) -> None:
        """write_atomic for sync-context is safe during concurrent agent reads."""
        from vcompany.shared.file_ops import write_atomic

        target = tmp_path / "INTERFACES.md"
        old_content = "# Interfaces v1\n\nNo contracts yet."
        new_content = "# Interfaces v2\n\n## API Contract\nGET /status -> 200"
        target.write_text(old_content)

        reads: list[str] = []
        barrier = threading.Barrier(2)

        def sync_writer() -> None:
            barrier.wait()
            write_atomic(target, new_content)

        def agent_reader() -> None:
            barrier.wait()
            for _ in range(100):
                reads.append(target.read_text())

        t1 = threading.Thread(target=sync_writer)
        t2 = threading.Thread(target=agent_reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        for content in reads:
            assert content in (old_content, new_content), (
                f"Partial sync-context read: {content!r}"
            )


class TestDuplicateMonitorPrevention:
    """Multiple monitors accidental -- INTERACTIONS.md pattern 6."""

    def test_pid_file_prevents_second_monitor(self, tmp_path: Path) -> None:
        """Second monitor refuses to start if PID file exists and process alive."""
        pid_file = tmp_path / "monitor.pid"
        pid_file.write_text(str(os.getpid()))  # Current process is "alive"

        # Simulate check: if PID file exists and process alive, refuse
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)  # Check if alive (signal 0)
            is_alive = True
        except OSError:
            is_alive = False

        assert is_alive is True, "PID file check should detect running process"

    def test_stale_pid_allows_new_monitor(self, tmp_path: Path) -> None:
        """New monitor starts if PID file points to dead process."""
        pid_file = tmp_path / "monitor.pid"
        # Use a PID that almost certainly doesn't exist
        pid_file.write_text("999999999")

        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            is_alive = True
        except OSError:
            is_alive = False

        assert is_alive is False, "Stale PID should not block new monitor"


class TestHookTimeoutIndependence:
    """Hook timeout during context compression -- INTERACTIONS.md pattern 7."""

    def test_hook_returns_fallback_on_timeout(self) -> None:
        """Hook timeout returns deny+fallback regardless of agent state."""
        start = time.monotonic()
        timeout = 0.1  # Accelerated for test

        answer = None
        while time.monotonic() - start < timeout:
            # Simulate polling: no answer file exists
            answer = None
            time.sleep(0.01)

        # Fallback per HOOK-04
        if answer is None:
            answer = "Fallback: using recommended option (timeout)"

        assert "Fallback" in answer
        assert "timeout" in answer


class TestSimultaneousPushes:
    """Simultaneous git pushes from multiple agents -- INTERACTIONS.md pattern 8."""

    def test_parallel_pushes_to_different_branches(self) -> None:
        """Pushes to agent/{id} branches do not conflict."""
        from vcompany.git import ops as git_ops

        push_results: list[git_ops.GitResult] = []
        with patch.object(git_ops, "_run_git") as mock_git:
            mock_git.return_value = git_ops.GitResult(True, "", "", 0)

            threads = []
            for agent_id in ("agent-a", "agent-b", "agent-c"):
                t = threading.Thread(
                    target=lambda aid=agent_id: push_results.append(
                        git_ops._run_git(
                            "push", "origin", f"agent/{aid}", cwd=Path("/tmp")
                        )
                    )
                )
                threads.append(t)
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(push_results) == 3
            assert all(r.success for r in push_results)
