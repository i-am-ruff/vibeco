---
phase: 06-resilience
plan: 02
subsystem: resilience
tags: [bulk-failure, outage-detection, backoff, supervisor, sliding-window]

# Dependency graph
requires:
  - phase: 02-supervision
    provides: Supervisor with _handle_child_failure and RestartTracker
provides:
  - BulkFailureDetector with per-child temporal correlation
  - Supervisor upstream outage detection with global backoff
  - Resilience module (src/vcompany/resilience/)
affects: [06-resilience, 07-lifecycle, 08-migration]

# Tech tracking
tech-stack:
  added: []
  patterns: [per-child-dedup-failure-tracking, is_in_backoff-before-record_failure, injectable-clock-testing]

key-files:
  created:
    - src/vcompany/resilience/__init__.py
    - src/vcompany/resilience/bulk_failure.py
    - tests/test_bulk_failure.py
  modified:
    - src/vcompany/supervisor/supervisor.py

key-decisions:
  - "Check is_in_backoff before record_failure to prevent duplicate escalations during active backoff"
  - "Bulk detector only created for supervisors with 2+ children (meaningless with 1)"

patterns-established:
  - "Per-child failure dedup: dict[str, datetime] not deque[datetime] prevents same-child false positives"
  - "Backoff-first check: test is_in_backoff before record_failure to avoid re-triggering global backoff"

requirements-completed: [RESL-02]

# Metrics
duration: 8min
completed: 2026-03-27
---

# Phase 06 Plan 02: Bulk Failure Detection Summary

**BulkFailureDetector with per-child sliding window correlation and Supervisor global backoff for upstream outage suppression**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-27T23:38:22Z
- **Completed:** 2026-03-27T23:46:40Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- BulkFailureDetector tracks per-child failure timestamps in a sliding window, detecting when 50%+ distinct children fail within 30s
- Supervisor._handle_child_failure checks for bulk failure before per-agent restart logic, entering global backoff on outage detection
- Global backoff suppresses per-agent restarts and notifies owner via escalation callback
- 11 tests passing (8 unit + 3 integration) covering detection, false positives, dedup, expiry, backoff state, and supervisor integration

## Task Commits

Each task was committed atomically:

1. **Task 1: BulkFailureDetector with temporal correlation** - `2e990a7` (feat, TDD)
2. **Task 2: Integrate BulkFailureDetector into Supervisor._handle_child_failure** - `bde182d` (feat)

## Files Created/Modified
- `src/vcompany/resilience/__init__.py` - Resilience package with BulkFailureDetector export
- `src/vcompany/resilience/bulk_failure.py` - BulkFailureDetector class with sliding window correlation
- `src/vcompany/supervisor/supervisor.py` - Extended with bulk failure check and _enter_global_backoff
- `tests/test_bulk_failure.py` - 11 tests for detector unit + supervisor integration

## Decisions Made
- Check `is_in_backoff` before `record_failure` in _handle_child_failure to prevent duplicate escalation notifications during active backoff
- Bulk detector only instantiated for supervisors with 2+ children (bulk detection is meaningless with 1 child)
- Used `dict[str, datetime]` (not deque) for per-child dedup -- threshold requires N distinct children, not N total failures

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed backoff check ordering in _handle_child_failure**
- **Found during:** Task 2 (integration)
- **Issue:** Plan specified record_failure before is_in_backoff check, causing duplicate escalation when already in backoff (record_failure returns True when count still >= threshold)
- **Fix:** Moved is_in_backoff check before record_failure call
- **Files modified:** src/vcompany/supervisor/supervisor.py
- **Verification:** Integration test test_supervisor_global_backoff passes with exactly 1 escalation message
- **Committed in:** bde182d (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix for correct backoff behavior. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Resilience module established, ready for RESL-01 (rate limiting) and RESL-03 (degraded mode)
- Supervisor now has bulk failure detection integrated alongside existing restart intensity tracking

## Self-Check: PASSED

- All 5 files verified present on disk
- Both task commits (2e990a7, bde182d) verified in git log
- 11/11 tests passing

---
*Phase: 06-resilience*
*Completed: 2026-03-27*
