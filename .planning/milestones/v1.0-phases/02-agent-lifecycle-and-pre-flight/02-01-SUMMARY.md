---
phase: 02-agent-lifecycle-and-pre-flight
plan: 01
subsystem: orchestrator
tags: [pydantic, crash-recovery, circuit-breaker, backoff, agent-state]

# Dependency graph
requires:
  - phase: 01-foundation-and-scaffolding
    provides: "write_atomic file_ops, AgentConfig/ProjectConfig models, GitResult dataclass"
provides:
  - "AgentEntry and AgentsRegistry Pydantic models for agents.json runtime state"
  - "CrashRecord and CrashLog models for crash_log.json persistence"
  - "CrashTracker with exponential backoff, circuit breaker, and crash classification"
affects: [02-agent-lifecycle-and-pre-flight, 03-monitor-loop-and-coordination]

# Tech tracking
tech-stack:
  added: []
  patterns: [pydantic-v2-models, sliding-window-circuit-breaker, testable-time-injection]

key-files:
  created:
    - src/vcompany/models/agent_state.py
    - src/vcompany/orchestrator/__init__.py
    - src/vcompany/orchestrator/crash_tracker.py
    - tests/test_agent_state.py
    - tests/test_crash_tracker.py
  modified: []

key-decisions:
  - "Used now parameter injection instead of freezegun for time-dependent tests"
  - "Circuit breaker threshold check uses < MAX+1 (allows exactly MAX crashes, blocks on MAX+1)"
  - "CrashClassification uses str+Enum for JSON serialization compatibility"

patterns-established:
  - "Time injection: methods accept optional now parameter for deterministic testing"
  - "Persistent state: Pydantic model_dump_json + write_atomic for crash-safe JSON persistence"
  - "Classification priority: check conditions in order of specificity (context exhaustion > repeated > corrupt > default)"

requirements-completed: [LIFE-05, LIFE-06, LIFE-07]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 2 Plan 1: State Models and Crash Tracker Summary

**Pydantic v2 agent state models and CrashTracker with 30s/2min/10min backoff, 3-crash/hour circuit breaker, and 4-category classification**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T02:42:01Z
- **Completed:** 2026-03-25T02:44:47Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 5

## Accomplishments
- AgentEntry/AgentsRegistry models for agents.json runtime state with typed Literal status field
- CrashRecord/CrashLog models for persistent crash history
- CrashTracker with exponential backoff schedule [30, 120, 600] seconds
- Circuit breaker blocks retry after 3+ crashes in sliding 60-minute window
- 4-category crash classification: context exhaustion, runtime error, repeated error, corrupt state
- 28 tests covering all backoff, circuit breaker, classification, and persistence behaviors

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests** - `0717c1c` (test)
2. **Task 1 (GREEN): Implementation** - `fd4b6fb` (feat)

_TDD task with RED/GREEN commits._

## Files Created/Modified
- `src/vcompany/models/agent_state.py` - AgentEntry, AgentsRegistry, CrashRecord, CrashLog Pydantic models
- `src/vcompany/orchestrator/__init__.py` - Orchestrator package init
- `src/vcompany/orchestrator/crash_tracker.py` - CrashTracker with backoff, circuit breaker, classification
- `tests/test_agent_state.py` - 12 tests for state models
- `tests/test_crash_tracker.py` - 16 tests for crash tracker

## Decisions Made
- Used `now` parameter injection for time-dependent methods instead of freezegun -- simpler, no extra dependency
- Circuit breaker allows exactly MAX_CRASHES_PER_HOUR (3) then blocks on the 4th -- matches D-12 spec
- CrashClassification inherits from both str and Enum for transparent JSON serialization

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Agent state models ready for dispatch (Plan 02-02) to use for tracking launched agents
- CrashTracker ready for monitor loop (Phase 3) to call on agent crashes
- All models serialize/deserialize cleanly for file-based persistence

## Self-Check: PASSED

All 5 files found. Both commit hashes verified. All 14 acceptance criteria satisfied (MAX_CRASHES_PER_HOUR has type annotation `int = 3` which is correct). 28/28 tests pass. Full suite 81/81 pass.

---
*Phase: 02-agent-lifecycle-and-pre-flight*
*Completed: 2026-03-25*
