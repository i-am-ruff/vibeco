---
phase: 03-monitor-loop-and-coordination
plan: 03
subsystem: monitoring
tags: [asyncio, monitor-loop, parallel-checks, callbacks, cli]

# Dependency graph
requires:
  - phase: 03-monitor-loop-and-coordination plan 01
    provides: "check_liveness, check_stuck, check_plan_gate functions and CheckResult model"
  - phase: 03-monitor-loop-and-coordination plan 02
    provides: "generate_project_status, distribute_project_status, write_heartbeat"
  - phase: 01-foundation
    provides: "TmuxManager, AgentEntry model with pid field"
provides:
  - "MonitorLoop class with async 60s cycle orchestration"
  - "Parallel agent checks via asyncio.gather with error isolation"
  - "Callbacks for dead/stuck/plan-detected events"
  - "vco monitor CLI command"
affects: [04-discord-bot, 05-hooks-and-agent-communication]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "asyncio.gather with return_exceptions=True for parallel error-isolated checks"
    - "asyncio.to_thread for blocking git operations in async context"
    - "Callback injection pattern (on_agent_dead, on_agent_stuck, on_plan_detected)"

key-files:
  created:
    - src/vcompany/monitor/loop.py
    - src/vcompany/cli/monitor_cmd.py
    - tests/test_monitor_loop.py
  modified:
    - src/vcompany/cli/main.py

key-decisions:
  - "asyncio.gather with return_exceptions=True for parallel agent checks ensuring one failure never crashes others"
  - "asyncio.to_thread wraps blocking check functions for async compatibility"
  - "Agent PID passed from AgentEntry.pid to check_liveness for full D-02 PID validation"

patterns-established:
  - "MonitorLoop composes check functions rather than duplicating logic"
  - "CLI callbacks are logging placeholders for Phase 4 Discord integration"
  - "Plan gate mtimes persisted in AgentMonitorState between cycles"

requirements-completed: [MON-01, MON-05, MON-06, MON-07]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 03 Plan 03: Monitor Loop and CLI Summary

**Async MonitorLoop composing liveness/stuck/plan-gate checks in parallel 60s cycles with heartbeat-first ordering, callback hooks, and vco monitor CLI command**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T04:11:18Z
- **Completed:** 2026-03-25T04:14:29Z
- **Tasks:** 2 (Task 1 TDD: RED + GREEN)
- **Files modified:** 4

## Accomplishments
- MonitorLoop class with async 60s cycle orchestration checking all agents in parallel via asyncio.gather
- Error isolation per D-01: one agent's check failure logged but never crashes the loop or affects other agents
- Heartbeat written at cycle START per Pitfall 6, before any checks
- Callbacks (on_agent_dead, on_agent_stuck, on_plan_detected) follow CrashTracker pattern from Phase 2
- Plan gate mtimes persist between cycles via AgentMonitorState
- Agent PID from agents.json registry passed to check_liveness for full PID validation per D-02
- vco monitor CLI command registered with --interval flag and Ctrl+C graceful shutdown
- All 10 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for MonitorLoop** - `5a75b8e` (test)
2. **Task 1 GREEN: Implement MonitorLoop** - `6cce410` (feat)
3. **Task 2: vco monitor CLI command and wiring** - `3ac8310` (feat)

_Note: Task 1 is TDD with RED (failing tests) then GREEN (implementation) commits._

## Files Created/Modified
- `src/vcompany/monitor/loop.py` - MonitorLoop class with async run/stop lifecycle and parallel agent checks
- `src/vcompany/cli/monitor_cmd.py` - vco monitor Click command with default logging callbacks
- `src/vcompany/cli/main.py` - Added monitor command registration
- `tests/test_monitor_loop.py` - 10 tests covering parallel checks, error isolation, callbacks, heartbeat order, graceful stop, mtime persistence

## Decisions Made
- Used asyncio.gather with return_exceptions=True to ensure parallel execution and error isolation simultaneously
- Wrapped blocking check functions with asyncio.to_thread per Pitfall 2 (blocking operations in async context)
- Agent PID loaded from AgentEntry.pid in agents.json and passed to check_liveness for full D-02 PID validation
- CLI callbacks log warnings as placeholders; Phase 4 Discord bot will inject real callbacks

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all functions are fully implemented with real logic. CLI callbacks log warnings as designed placeholders for Phase 4 Discord integration.

## Next Phase Readiness
- MonitorLoop ready for Discord bot integration (Phase 4) via callback injection
- vco monitor command available for running the supervision loop
- All check functions, status generation, heartbeat, and loop orchestration tested and working
- Complete monitor subsystem: checks (Plan 01) + status/heartbeat (Plan 02) + loop/CLI (Plan 03)

---
*Phase: 03-monitor-loop-and-coordination*
*Completed: 2026-03-25*
