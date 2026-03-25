"""Crash tracker with exponential backoff, circuit breaker, and classification.

Prevents runaway relaunches and API token waste by tracking crash history,
enforcing backoff delays, and opening the circuit after repeated failures.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from vcompany.models.agent_state import CrashLog, CrashRecord
from vcompany.shared.file_ops import write_atomic

# Type for circuit breaker callback: receives agent_id and crash_count
CircuitOpenCallback = Callable[[str, int], None]

# Backoff delays in seconds: 30s, 2min, 10min (per D-11)
BACKOFF_SCHEDULE: list[int] = [30, 120, 600]

# Circuit breaker threshold: max crashes per sliding 60-minute window (per D-12)
MAX_CRASHES_PER_HOUR: int = 3

# Sliding window duration
_WINDOW = timedelta(minutes=60)


class CrashClassification(str, Enum):
    """Categories for crash root cause analysis (per D-10)."""

    TRANSIENT_CONTEXT_EXHAUSTION = "transient_context_exhaustion"
    TRANSIENT_RUNTIME_ERROR = "transient_runtime_error"
    PERSISTENT_REPEATED_ERROR = "persistent_repeated_error"
    PERSISTENT_CORRUPT_STATE = "persistent_corrupt_state"
    UNCLASSIFIED = "unclassified"


class CrashTracker:
    """Tracks agent crashes and enforces recovery policies.

    Provides:
    - Exponential backoff delays (30s / 2min / 10min)
    - Circuit breaker (blocks retry after 3+ crashes in 60 minutes)
    - Crash classification (4 categories for targeted recovery)
    - Persistent state via crash_log.json
    """

    def __init__(
        self,
        crash_log_path: Path,
        *,
        on_circuit_open: CircuitOpenCallback | None = None,
    ) -> None:
        """Initialize tracker, loading existing crash log if present.

        Args:
            crash_log_path: Path to crash_log.json.
            on_circuit_open: Optional callback invoked when the circuit breaker
                trips (agent_id, crash_count). Phase 4 Discord bot injects this
                to alert #alerts when an agent exceeds MAX_CRASHES_PER_HOUR.
        """
        self._path = Path(crash_log_path)
        self._on_circuit_open = on_circuit_open
        if self._path.exists():
            self.crash_log = CrashLog.model_validate_json(self._path.read_text())
        else:
            self.crash_log = CrashLog(project="")

    def record_crash(
        self,
        agent_id: str,
        exit_code: int,
        classification: CrashClassification,
        pane_output: list[str],
        *,
        now: datetime | None = None,
    ) -> None:
        """Record a crash event and persist to disk.

        Args:
            agent_id: ID of the crashed agent.
            exit_code: Process exit code.
            classification: Crash classification category.
            pane_output: Last lines of tmux pane output for diagnosis.
            now: Override current time (for testing).
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = CrashRecord(
            agent_id=agent_id,
            timestamp=now,
            exit_code=exit_code,
            classification=classification.value,
            pane_output=pane_output,
        )
        self.crash_log.records.append(record)
        self._persist()

    def recent_crash_count(self, agent_id: str, *, now: datetime | None = None) -> int:
        """Count crashes for agent in the last 60-minute sliding window."""
        if now is None:
            now = datetime.now(timezone.utc)
        cutoff = now - _WINDOW
        return sum(
            1
            for r in self.crash_log.records
            if r.agent_id == agent_id and r.timestamp >= cutoff
        )

    def should_retry(self, agent_id: str, *, now: datetime | None = None) -> bool:
        """Return True if agent has not exceeded crash threshold in current window.

        When the circuit opens (returns False), invokes on_circuit_open callback
        if one was provided at init time.
        """
        count = self.recent_crash_count(agent_id, now=now)
        if count >= MAX_CRASHES_PER_HOUR + 1:
            if self._on_circuit_open is not None:
                self._on_circuit_open(agent_id, count)
            return False
        return True

    def get_retry_delay(self, agent_id: str, *, now: datetime | None = None) -> int:
        """Return backoff delay in seconds based on recent crash count.

        Index into BACKOFF_SCHEDULE, capping at the last value.
        """
        count = self.recent_crash_count(agent_id, now=now)
        idx = min(count, len(BACKOFF_SCHEDULE) - 1)
        return BACKOFF_SCHEDULE[idx]

    def classify_crash(
        self,
        agent_id: str,
        exit_code: int,
        clone_dir: Path,
        pane_output: list[str],
    ) -> CrashClassification:
        """Classify crash into one of 4 categories for targeted recovery.

        Classification order (per D-10):
        1. exit_code=0 + STATE.md exists -> context exhaustion (normal GSD exit)
        2. Same error in last 2 crashes -> persistent repeated error
        3. Missing STATE.md -> corrupt state
        4. Default -> transient runtime error
        """
        state_path = clone_dir / ".planning" / "STATE.md"
        state_exists = state_path.exists()

        # 1. Context exhaustion: clean exit with valid state
        if exit_code == 0 and state_exists:
            return CrashClassification.TRANSIENT_CONTEXT_EXHAUSTION

        # 2. Repeated error: same first line of pane_output in last 2 crashes
        agent_crashes = [r for r in self.crash_log.records if r.agent_id == agent_id]
        if len(agent_crashes) >= 2 and pane_output:
            current_first = pane_output[0] if pane_output else ""
            last_two = agent_crashes[-2:]
            if all(
                r.pane_output and r.pane_output[0] == current_first
                for r in last_two
            ):
                return CrashClassification.PERSISTENT_REPEATED_ERROR

        # 3. Corrupt state: missing STATE.md
        if not state_exists:
            return CrashClassification.PERSISTENT_CORRUPT_STATE

        # 4. Default: transient runtime error
        return CrashClassification.TRANSIENT_RUNTIME_ERROR

    def reset_circuit(self, agent_id: str) -> None:
        """Remove all crash records for agent (manual relaunch override)."""
        self.crash_log.records = [
            r for r in self.crash_log.records if r.agent_id != agent_id
        ]
        self._persist()

    def _persist(self) -> None:
        """Write crash log to disk atomically."""
        write_atomic(self._path, self.crash_log.model_dump_json(indent=2))
