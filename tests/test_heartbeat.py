"""Tests for heartbeat file writing and watchdog checking.

Covers:
- write_heartbeat creates file with ISO timestamp
- write_heartbeat uses write_atomic
- write_heartbeat writes to correct path
- check_heartbeat fresh/stale/missing/corrupt
- Heartbeat written at START of cycle (Pitfall 6)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from vcompany.monitor.heartbeat import check_heartbeat, write_heartbeat


class TestWriteHeartbeat:
    def test_write_heartbeat_creates_file(self, tmp_path: Path) -> None:
        now = datetime(2026, 3, 25, 8, 30, 0, tzinfo=timezone.utc)
        write_heartbeat(tmp_path, now=now)

        heartbeat_path = tmp_path / "state" / "monitor_heartbeat"
        assert heartbeat_path.exists()
        content = heartbeat_path.read_text().strip()
        # Should be a valid ISO timestamp
        parsed = datetime.fromisoformat(content)
        assert parsed == now

    def test_write_heartbeat_uses_write_atomic(self, tmp_path: Path) -> None:
        now = datetime(2026, 3, 25, 8, 30, 0, tzinfo=timezone.utc)
        with patch("vcompany.monitor.heartbeat.write_atomic") as mock_wa:
            write_heartbeat(tmp_path, now=now)

        mock_wa.assert_called_once()
        call_args = mock_wa.call_args
        assert str(call_args[0][0]).endswith("monitor_heartbeat")

    def test_write_heartbeat_correct_path(self, tmp_path: Path) -> None:
        now = datetime(2026, 3, 25, 8, 30, 0, tzinfo=timezone.utc)
        write_heartbeat(tmp_path, now=now)

        expected_path = tmp_path / "state" / "monitor_heartbeat"
        assert expected_path.exists()

    def test_write_heartbeat_at_cycle_start(self, tmp_path: Path) -> None:
        """Per Pitfall 6: heartbeat written at START of cycle.

        This test verifies the timestamp matches the provided 'now',
        confirming the heartbeat captures the time it was called
        (cycle start) rather than computing some other time.
        """
        now = datetime(2026, 3, 25, 8, 30, 0, tzinfo=timezone.utc)
        write_heartbeat(tmp_path, now=now)

        content = (tmp_path / "state" / "monitor_heartbeat").read_text().strip()
        parsed = datetime.fromisoformat(content)
        assert parsed == now


class TestCheckHeartbeat:
    def test_check_heartbeat_fresh(self, tmp_path: Path) -> None:
        # Write heartbeat 60 seconds ago
        heartbeat_time = datetime(2026, 3, 25, 8, 29, 0, tzinfo=timezone.utc)
        write_heartbeat(tmp_path, now=heartbeat_time)

        now = datetime(2026, 3, 25, 8, 30, 0, tzinfo=timezone.utc)
        assert check_heartbeat(tmp_path, now=now) is True

    def test_check_heartbeat_stale(self, tmp_path: Path) -> None:
        # Write heartbeat 200 seconds ago (> 180s threshold)
        heartbeat_time = datetime(2026, 3, 25, 8, 26, 40, tzinfo=timezone.utc)
        write_heartbeat(tmp_path, now=heartbeat_time)

        now = datetime(2026, 3, 25, 8, 30, 0, tzinfo=timezone.utc)
        assert check_heartbeat(tmp_path, now=now) is False

    def test_check_heartbeat_missing(self, tmp_path: Path) -> None:
        # No heartbeat file at all
        assert check_heartbeat(tmp_path) is False

    def test_check_heartbeat_corrupt(self, tmp_path: Path) -> None:
        # Write garbage to heartbeat file
        heartbeat_path = tmp_path / "state" / "monitor_heartbeat"
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        heartbeat_path.write_text("not a valid timestamp at all")

        assert check_heartbeat(tmp_path) is False

    def test_check_heartbeat_custom_max_age(self, tmp_path: Path) -> None:
        # Write heartbeat 100 seconds ago, but max_age is 60
        heartbeat_time = datetime(2026, 3, 25, 8, 28, 20, tzinfo=timezone.utc)
        write_heartbeat(tmp_path, now=heartbeat_time)

        now = datetime(2026, 3, 25, 8, 30, 0, tzinfo=timezone.utc)
        assert check_heartbeat(tmp_path, max_age_seconds=60, now=now) is False
        assert check_heartbeat(tmp_path, max_age_seconds=180, now=now) is True

    def test_check_heartbeat_default_max_age_is_180(self, tmp_path: Path) -> None:
        # Write heartbeat exactly 180 seconds ago - should be fresh (<=)
        heartbeat_time = datetime(2026, 3, 25, 8, 27, 0, tzinfo=timezone.utc)
        write_heartbeat(tmp_path, now=heartbeat_time)

        now = datetime(2026, 3, 25, 8, 30, 0, tzinfo=timezone.utc)
        assert check_heartbeat(tmp_path, now=now) is True
