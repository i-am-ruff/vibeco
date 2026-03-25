"""Tests for CrashTracker with backoff, circuit breaker, and classification."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from vcompany.models.agent_state import CrashLog, CrashRecord
from vcompany.orchestrator.crash_tracker import (
    BACKOFF_SCHEDULE,
    MAX_CRASHES_PER_HOUR,
    CrashClassification,
    CrashTracker,
)


@pytest.fixture
def crash_log_path(tmp_path: Path) -> Path:
    """Return a path for crash_log.json in tmp directory."""
    return tmp_path / "crash_log.json"


@pytest.fixture
def tracker(crash_log_path: Path) -> CrashTracker:
    """Return a fresh CrashTracker."""
    return CrashTracker(crash_log_path)


class TestBackoff:
    """Tests for exponential backoff delay calculation."""

    def test_zero_crashes_returns_30s(self, tracker: CrashTracker) -> None:
        """recent_crash_count=0 -> delay=30s."""
        delay = tracker.get_retry_delay("BACKEND")
        assert delay == 30

    def test_one_crash_returns_120s(self, tracker: CrashTracker, crash_log_path: Path) -> None:
        """count=1 -> delay=120s."""
        now = datetime.now(timezone.utc)
        tracker.record_crash("BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR, [], now=now)
        delay = tracker.get_retry_delay("BACKEND", now=now)
        assert delay == 120

    def test_two_crashes_returns_600s(self, tracker: CrashTracker) -> None:
        """count=2 -> delay=600s."""
        now = datetime.now(timezone.utc)
        for i in range(2):
            tracker.record_crash(
                "BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR, [],
                now=now + timedelta(seconds=i),
            )
        delay = tracker.get_retry_delay("BACKEND", now=now + timedelta(seconds=2))
        assert delay == 600

    def test_three_or_more_crashes_caps_at_600s(self, tracker: CrashTracker) -> None:
        """count>=3 -> delay=600s (capped at last value)."""
        now = datetime.now(timezone.utc)
        for i in range(5):
            tracker.record_crash(
                "BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR, [],
                now=now + timedelta(seconds=i),
            )
        delay = tracker.get_retry_delay("BACKEND", now=now + timedelta(seconds=5))
        assert delay == 600

    def test_backoff_schedule_values(self) -> None:
        """BACKOFF_SCHEDULE contains [30, 120, 600]."""
        assert BACKOFF_SCHEDULE == [30, 120, 600]


class TestCircuitBreaker:
    """Tests for circuit breaker logic."""

    def test_under_threshold_allows_retry(self, tracker: CrashTracker) -> None:
        """3 crashes in 60min -> should_retry=True (at threshold, not over)."""
        now = datetime.now(timezone.utc)
        for i in range(3):
            tracker.record_crash(
                "BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR, [],
                now=now + timedelta(seconds=i),
            )
        assert tracker.should_retry("BACKEND", now=now + timedelta(seconds=3)) is True

    def test_over_threshold_blocks_retry(self, tracker: CrashTracker) -> None:
        """4th crash in same window -> should_retry=False."""
        now = datetime.now(timezone.utc)
        for i in range(4):
            tracker.record_crash(
                "BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR, [],
                now=now + timedelta(seconds=i),
            )
        assert tracker.should_retry("BACKEND", now=now + timedelta(seconds=4)) is False

    def test_sliding_window_resets_after_60min(self, tracker: CrashTracker) -> None:
        """3 crashes in 60min, then 61min passes, new crash -> should_retry=True."""
        base = datetime.now(timezone.utc)
        # 3 crashes at base time
        for i in range(3):
            tracker.record_crash(
                "BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR, [],
                now=base + timedelta(seconds=i),
            )
        # 61 minutes later, add one more crash
        later = base + timedelta(minutes=61)
        tracker.record_crash(
            "BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR, [],
            now=later,
        )
        # Should be allowed -- only 1 crash in the new window
        assert tracker.should_retry("BACKEND", now=later) is True

    def test_reset_circuit_clears_history(self, tracker: CrashTracker) -> None:
        """reset_circuit(agent_id) clears crash history and allows retry."""
        now = datetime.now(timezone.utc)
        for i in range(4):
            tracker.record_crash(
                "BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR, [],
                now=now + timedelta(seconds=i),
            )
        assert tracker.should_retry("BACKEND", now=now + timedelta(seconds=4)) is False

        tracker.reset_circuit("BACKEND")
        assert tracker.should_retry("BACKEND", now=now + timedelta(seconds=5)) is True

    def test_max_crashes_per_hour_is_3(self) -> None:
        """MAX_CRASHES_PER_HOUR = 3."""
        assert MAX_CRASHES_PER_HOUR == 3

    def test_on_circuit_open_callback_invoked(self, crash_log_path: Path) -> None:
        """on_circuit_open callback fires when circuit breaker trips."""
        calls: list[tuple[str, int]] = []
        tracker = CrashTracker(
            crash_log_path, on_circuit_open=lambda aid, cnt: calls.append((aid, cnt))
        )
        now = datetime.now(timezone.utc)
        for i in range(4):
            tracker.record_crash(
                "BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR, [],
                now=now + timedelta(seconds=i),
            )
        tracker.should_retry("BACKEND", now=now + timedelta(seconds=4))
        assert len(calls) == 1
        assert calls[0][0] == "BACKEND"
        assert calls[0][1] >= 4

    def test_no_callback_when_circuit_not_open(self, crash_log_path: Path) -> None:
        """on_circuit_open callback does not fire under threshold."""
        calls: list[tuple[str, int]] = []
        tracker = CrashTracker(
            crash_log_path, on_circuit_open=lambda aid, cnt: calls.append((aid, cnt))
        )
        now = datetime.now(timezone.utc)
        for i in range(3):
            tracker.record_crash(
                "BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR, [],
                now=now + timedelta(seconds=i),
            )
        tracker.should_retry("BACKEND", now=now + timedelta(seconds=3))
        assert len(calls) == 0


class TestClassification:
    """Tests for crash classification logic."""

    def test_transient_context_exhaustion(self, tracker: CrashTracker, tmp_path: Path) -> None:
        """exit_code=0 + checkpoint exists -> transient_context_exhaustion."""
        clone_dir = tmp_path / "clone"
        (clone_dir / ".planning").mkdir(parents=True)
        (clone_dir / ".planning" / "STATE.md").write_text("# State")

        result = tracker.classify_crash("BACKEND", 0, clone_dir, ["Normal exit"])
        assert result == CrashClassification.TRANSIENT_CONTEXT_EXHAUSTION

    def test_transient_runtime_error(self, tracker: CrashTracker, tmp_path: Path) -> None:
        """exit_code!=0 + no repeated error -> transient_runtime_error."""
        clone_dir = tmp_path / "clone"
        (clone_dir / ".planning").mkdir(parents=True)
        (clone_dir / ".planning" / "STATE.md").write_text("# State")

        result = tracker.classify_crash("BACKEND", 1, clone_dir, ["Some error"])
        assert result == CrashClassification.TRANSIENT_RUNTIME_ERROR

    def test_persistent_repeated_error(self, tracker: CrashTracker, tmp_path: Path) -> None:
        """Same error pattern in last 2 crashes -> persistent_repeated_error."""
        clone_dir = tmp_path / "clone"
        (clone_dir / ".planning").mkdir(parents=True)
        (clone_dir / ".planning" / "STATE.md").write_text("# State")

        now = datetime.now(timezone.utc)
        # Record 2 previous crashes with same first line of pane_output
        tracker.record_crash(
            "BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR,
            ["ConnectionError: failed to connect"],
            now=now,
        )
        tracker.record_crash(
            "BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR,
            ["ConnectionError: failed to connect"],
            now=now + timedelta(seconds=10),
        )

        result = tracker.classify_crash(
            "BACKEND", 1, clone_dir,
            ["ConnectionError: failed to connect"],
        )
        assert result == CrashClassification.PERSISTENT_REPEATED_ERROR

    def test_persistent_corrupt_state(self, tracker: CrashTracker, tmp_path: Path) -> None:
        """Missing STATE.md in .planning/ -> persistent_corrupt_state."""
        clone_dir = tmp_path / "clone"
        clone_dir.mkdir()
        # No .planning/STATE.md

        result = tracker.classify_crash("BACKEND", 1, clone_dir, ["Error"])
        assert result == CrashClassification.PERSISTENT_CORRUPT_STATE

    def test_record_crash_persists_to_file(self, tracker: CrashTracker, crash_log_path: Path) -> None:
        """record_crash persists to crash_log.json via write_atomic."""
        now = datetime.now(timezone.utc)
        tracker.record_crash("BACKEND", 1, CrashClassification.TRANSIENT_RUNTIME_ERROR, ["err"], now=now)

        assert crash_log_path.exists()
        loaded = CrashLog.model_validate_json(crash_log_path.read_text())
        assert len(loaded.records) == 1
        assert loaded.records[0].agent_id == "BACKEND"

    def test_crash_tracker_loads_existing_log(self, crash_log_path: Path) -> None:
        """CrashTracker loads existing crash_log.json on init (state survives restart)."""
        now = datetime.now(timezone.utc)
        record = CrashRecord(
            agent_id="BACKEND",
            timestamp=now,
            exit_code=1,
            classification="transient_runtime_error",
            pane_output=["error line"],
        )
        log = CrashLog(project="test", records=[record])
        crash_log_path.write_text(log.model_dump_json())

        tracker = CrashTracker(crash_log_path)
        assert len(tracker.crash_log.records) == 1
        assert tracker.crash_log.records[0].agent_id == "BACKEND"
