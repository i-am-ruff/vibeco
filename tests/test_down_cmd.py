"""Tests for vco down command."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from vcompany.cli.down_cmd import down


def test_down_no_pid_file(tmp_path: Path) -> None:
    """vco down with no PID file exits 1 with 'not running'."""
    fake_pid = tmp_path / "vco-daemon.pid"
    runner = CliRunner()
    with patch("vcompany.cli.down_cmd.VCO_PID_PATH", fake_pid):
        result = runner.invoke(down, catch_exceptions=False)
    assert result.exit_code == 1
    assert "not running" in result.output.lower()


def test_down_stale_pid(tmp_path: Path) -> None:
    """vco down with stale PID cleans up and reports."""
    fake_pid = tmp_path / "vco-daemon.pid"
    # Use a PID that almost certainly doesn't exist
    fake_pid.write_text("999999999")
    runner = CliRunner()
    with patch("vcompany.cli.down_cmd.VCO_PID_PATH", fake_pid):
        result = runner.invoke(down, catch_exceptions=False)
    assert result.exit_code == 0
    assert "stale" in result.output.lower()
    assert not fake_pid.exists()


def test_down_sends_sigterm(tmp_path: Path) -> None:
    """vco down sends SIGTERM to a real process and waits for exit."""
    fake_pid = tmp_path / "vco-daemon.pid"
    # Start a real subprocess in its own session so it's not a zombie of ours.
    # In real usage the daemon is an independent process, not a child.
    proc = subprocess.Popen(["sleep", "60"], start_new_session=True)
    fake_pid.write_text(str(proc.pid))

    # Reap the child from a background thread so the zombie is cleaned up
    # and os.kill(pid, 0) correctly raises ProcessLookupError.
    reaper = threading.Thread(target=proc.wait, daemon=True)
    reaper.start()

    runner = CliRunner()
    try:
        with patch("vcompany.cli.down_cmd.VCO_PID_PATH", fake_pid):
            result = runner.invoke(down, catch_exceptions=False)
        assert result.exit_code == 0
        assert "sigterm" in result.output.lower()
        assert "stopped" in result.output.lower()
    finally:
        # Ensure cleanup even if test fails
        try:
            proc.kill()
            proc.wait(timeout=2)
        except (ProcessLookupError, OSError):
            pass


def test_down_invalid_pid_file(tmp_path: Path) -> None:
    """vco down with garbage PID file exits 1 with 'Invalid PID'."""
    fake_pid = tmp_path / "vco-daemon.pid"
    fake_pid.write_text("garbage")
    runner = CliRunner()
    with patch("vcompany.cli.down_cmd.VCO_PID_PATH", fake_pid):
        result = runner.invoke(down, catch_exceptions=False)
    assert result.exit_code == 1
    assert "invalid pid" in result.output.lower()
    # PID file should be cleaned up
    assert not fake_pid.exists()
