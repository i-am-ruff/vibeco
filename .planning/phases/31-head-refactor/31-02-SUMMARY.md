---
phase: 31-head-refactor
plan: 02
subsystem: daemon
tags: [agent-handle, transport-channel, routing-state, worker-subprocess, ndjson]

# Dependency graph
requires:
  - phase: 31-01
    provides: "AgentHandle, RoutingState, channel protocol messages"
  - phase: 30
    provides: "vco-worker package with WorkerContainer, channel framing"
  - phase: 29
    provides: "Transport channel protocol messages and NDJSON framing"
provides:
  - "CompanyRoot using AgentHandle instead of AgentContainer for company agents"
  - "RuntimeAPI sending channel messages instead of calling container methods"
  - "Routing state persistence on hire/dismiss"
  - "Background channel reader task per agent for worker message dispatch"
affects: [33-docker-channel, 34-dead-code-removal]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "AgentHandle + channel messages for company-level agent lifecycle"
    - "Duck-typing for backward compat with project-level AgentContainer"
    - "channel_id passed to hire() to ensure routing persistence correctness"

key-files:
  created: []
  modified:
    - "src/vcompany/supervisor/company_root.py"
    - "src/vcompany/daemon/runtime_api.py"

key-decisions:
  - "add_company_agent() kept on container path for Strategist backward compat"
  - "channel_id passed as parameter to hire() not set after return"
  - "_find_handle() returns both AgentHandle and AgentContainer via duck-typing"

patterns-established:
  - "Company agents: AgentHandle + channel protocol; Project agents: AgentContainer (until Phase 34)"
  - "Duck-typed isinstance checks for graceful Handle/Container coexistence"

requirements-completed: [HEAD-01, HEAD-02, HEAD-03, HEAD-05]

# Metrics
duration: 5min
completed: 2026-03-31
---

# Phase 31 Plan 02: Head Refactor - CompanyRoot and RuntimeAPI Summary

**CompanyRoot and RuntimeAPI refactored to use AgentHandle + transport channel messages for company-level agents, with routing state persistence and background channel readers**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-31T15:56:23Z
- **Completed:** 2026-03-31T16:01:23Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- CompanyRoot.hire() spawns vco-worker subprocess, sends StartMessage, creates background channel reader
- RuntimeAPI lifecycle methods (hire, give_task, dispatch, kill, dismiss, relay, resolve_review) all communicate through typed channel messages for company agents
- Routing state persisted on hire/dismiss with channel_id correctly populated before save
- Full backward compatibility with project-level AgentContainer agents via duck-typing

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor CompanyRoot to use AgentHandle and channel messages** - `07a5404` (feat)
2. **Task 2: Refactor RuntimeAPI lifecycle methods to use channel messages** - `4462978` (feat)

## Files Created/Modified
- `src/vcompany/supervisor/company_root.py` - CompanyRoot using AgentHandle, channel reader, routing persistence
- `src/vcompany/daemon/runtime_api.py` - RuntimeAPI sending channel messages, isinstance-based Handle/Container dispatch

## Decisions Made
- add_company_agent() remains on the container creation path for Strategist -- conversation handler not yet ported to vco-worker
- channel_id is passed as a parameter to CompanyRoot.hire() rather than set on the handle after return, ensuring routing.json always has channel_id populated
- _find_handle() returns both AgentHandle (company) and AgentContainer (project) via duck-typing to avoid breaking project-level code paths
- stop() uses isinstance check to handle both AgentHandle.stop_process() and AgentContainer.stop()

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all methods are fully wired to real implementations.

## Next Phase Readiness
- CompanyRoot and RuntimeAPI are ready for Phase 33 (Docker channel integration)
- Phase 34 (dead code removal) can safely remove container imports once ProjectSupervisor is also refactored
- Strategist still uses add_company_agent() container path -- needs worker port before full removal

---
*Phase: 31-head-refactor*
*Completed: 2026-03-31*
