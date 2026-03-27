---
phase: 06-resilience
plan: 03
subsystem: resilience
tags: [degraded-mode, health-check, auto-recovery, circuit-breaker]

# Dependency graph
requires:
  - phase: 02-supervision
    provides: CompanyRoot supervisor with add_project lifecycle
provides:
  - DegradedModeManager with active probing and passive operational detection
  - CompanyRoot dispatch gating when Claude API unreachable
  - Auto-recovery after consecutive successful health checks
affects: [08-migration]

# Tech tracking
tech-stack:
  added: []
  patterns: [injectable-health-check, callback-on-state-transition, passive-operational-detection]

key-files:
  created:
    - src/vcompany/resilience/__init__.py
    - src/vcompany/resilience/degraded_mode.py
    - tests/test_degraded_mode.py
  modified:
    - src/vcompany/supervisor/company_root.py

key-decisions:
  - "Injectable health_check callable decouples DegradedModeManager from anthropic SDK"
  - "Both active probing (background loop) and passive detection (record_operational_failure/success) supported"
  - "DegradedModeManager is optional in CompanyRoot -- graceful no-op when health_check not provided"

patterns-established:
  - "Injectable async callable for health checks -- caller provides the check function"
  - "Dual detection: active background probing + passive inline API call reporting"

requirements-completed: [RESL-03]

# Metrics
duration: 3min
completed: 2026-03-28
---

# Phase 6 Plan 3: Degraded Mode Summary

**DegradedModeManager with 3-failure threshold, 2-success auto-recovery, injectable health checks, and CompanyRoot dispatch gating**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-27T23:38:27Z
- **Completed:** 2026-03-27T23:41:48Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- DegradedModeManager transitions between normal/degraded based on consecutive health check results
- CompanyRoot gates add_project() with degraded mode check -- existing containers stay alive
- Owner notified via callbacks on state entry and recovery
- Both active probing (background loop) and passive operational detection supported
- 19 tests covering state transitions, callbacks, loop behavior, and CompanyRoot integration

## Task Commits

Each task was committed atomically:

1. **Task 1: DegradedModeManager with health checking and auto-recovery** - `c7cb785` (test) + `5c67308` (feat)
2. **Task 2: Integrate DegradedModeManager into CompanyRoot** - `4bd44f8` (feat)

_Note: Task 1 used TDD with separate RED/GREEN commits_

## Files Created/Modified
- `src/vcompany/resilience/__init__.py` - Resilience package with DegradedModeManager export
- `src/vcompany/resilience/degraded_mode.py` - DegradedModeManager with health checking, state transitions, callbacks
- `src/vcompany/supervisor/company_root.py` - Added degraded mode integration (dispatch gating, lifecycle, is_degraded property)
- `tests/test_degraded_mode.py` - 19 tests for DegradedModeManager and CompanyRoot integration

## Decisions Made
- Injectable health_check callable decouples DegradedModeManager from anthropic SDK -- caller provides the check function
- Both active probing (background loop) and passive detection (record_operational_failure/success) supported
- DegradedModeManager is optional in CompanyRoot -- graceful no-op when health_check not provided

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Resilience subsystem complete with rate limiting (06-01), restart backoff (06-02), and degraded mode (06-03)
- Ready for Phase 07 (agent-types) or Phase 08 (migration)

## Self-Check: PASSED

---
*Phase: 06-resilience*
*Completed: 2026-03-28*
