---
phase: 02-agent-lifecycle-and-pre-flight
plan: 03
subsystem: orchestration
tags: [preflight, claude-code, stream-json, monitor-strategy, pydantic, subprocess]

# Dependency graph
requires:
  - phase: 02-agent-lifecycle-and-pre-flight
    provides: "crash_tracker.py patterns, file_ops.write_atomic, CLI command registration"
provides:
  - "PreflightResult, PreflightSuite, MonitorStrategy models"
  - "4 empirical test functions for Claude Code headless validation"
  - "determine_monitor_strategy: stream-json vs git-commit fallback"
  - "vco preflight CLI command"
affects: [03-monitor-loop, 03-liveness-checks]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Pydantic models for test result serialization", "subprocess.Popen for stream-json event reading", "exit code convention: 0=pass, 1=fail, 2=inconclusive"]

key-files:
  created:
    - src/vcompany/orchestrator/preflight.py
    - src/vcompany/cli/preflight_cmd.py
    - tests/test_preflight.py
  modified:
    - src/vcompany/cli/main.py

key-decisions:
  - "Pydantic BaseModel for PreflightResult/PreflightSuite for JSON serialization consistency with crash_tracker pattern"
  - "Conservative fallback: any non-pass stream-json result defaults to GIT_COMMIT_FALLBACK"
  - "permission_hang test always passes (documents behavior, not correctness) since either outcome is informative"

patterns-established:
  - "Pre-flight test pattern: subprocess in TemporaryDirectory with generous timeouts"
  - "CLI exit codes: 0=all pass, 1=any fail, 2=any inconclusive"

requirements-completed: [PRE-01, PRE-02, PRE-03]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 2 Plan 3: Pre-flight Test Suite Summary

**Pre-flight runner with 4 empirical Claude Code tests (stream-json, permission-hang, max-turns, resume) determining STREAM_JSON or GIT_COMMIT_FALLBACK monitor strategy**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T02:52:31Z
- **Completed:** 2026-03-25T02:55:31Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Pre-flight test runner with 4 empirical tests covering all PRE-02 behaviors
- MonitorStrategy correctly determined from stream-json heartbeat result (STREAM_JSON if passed, GIT_COMMIT_FALLBACK otherwise)
- 15 unit tests for result interpretation with no live Claude dependency
- CLI command `vco preflight <project>` registered and functional with exit code semantics

## Task Commits

Each task was committed atomically:

1. **Task 1: Pre-flight test runner and result interpretation** - `ef55f2c` (test: RED), `d145535` (feat: GREEN)
2. **Task 2: Pre-flight CLI command** - `47f5600` (feat)

## Files Created/Modified
- `src/vcompany/orchestrator/preflight.py` - PreflightResult, MonitorStrategy, PreflightSuite models + 4 live test functions + run_preflight orchestrator
- `src/vcompany/cli/preflight_cmd.py` - vco preflight CLI command with --output-dir option
- `src/vcompany/cli/main.py` - Registered preflight command in CLI group
- `tests/test_preflight.py` - 15 unit tests for result interpretation and monitor strategy determination

## Decisions Made
- Used Pydantic BaseModel (not dataclass) for PreflightResult/PreflightSuite to match crash_tracker serialization pattern
- Conservative monitor strategy: any non-pass stream-json result (failed or inconclusive) defaults to GIT_COMMIT_FALLBACK
- permission_hang test always returns passed=True since it documents behavior rather than testing correctness

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Pre-flight runner ready for live execution with `vco preflight <project>`
- MonitorStrategy enum consumed by Phase 3 monitor loop to select liveness check approach
- preflight_results.json written atomically to project state directory for monitor to read

---
*Phase: 02-agent-lifecycle-and-pre-flight*
*Completed: 2026-03-25*
