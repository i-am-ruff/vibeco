---
phase: 04-remaining-agent-types-and-scheduler
plan: 03
subsystem: agent-types
tags: [event-driven, asyncio-queue, fsm, statemachine, compound-state, history-state]

requires:
  - phase: 01-container-base
    provides: AgentContainer base class, ContainerContext, MemoryStore, HealthReport
  - phase: 03-gsdagent
    provides: GsdAgent subclass pattern, OrderedSet state decomposition, compound FSM pattern

provides:
  - EventDrivenLifecycle FSM with listening/processing compound states and HistoryState
  - FulltimeAgent (PM) event-driven container with asyncio.Queue
  - CompanyAgent (Strategist) event-driven container with cross-project state

affects: [05-health-tree, 07-delegation-protocol, 08-migration]

tech-stack:
  added: []
  patterns:
    - "Event-driven agents use asyncio.Queue for non-blocking event intake"
    - "Cross-project state uses xp: key prefix in memory_store"
    - "EventDrivenLifecycle HistoryState preserves listening/processing across sleep/wake"

key-files:
  created:
    - src/vcompany/agent/event_driven_lifecycle.py
    - src/vcompany/agent/fulltime_agent.py
    - src/vcompany/agent/company_agent.py
    - tests/test_event_driven_lifecycle.py
    - tests/test_fulltime_agent.py
    - tests/test_company_agent.py
  modified:
    - src/vcompany/agent/__init__.py

key-decisions:
  - "EventDrivenLifecycle is a standalone StateMachine (not subclass) following GsdLifecycle pattern"
  - "Cross-project state keys use xp: prefix to avoid collision with per-agent keys"
  - "Both agent types share identical event processing pattern (asyncio.Queue + process_next_event)"

patterns-established:
  - "Event-driven agent pattern: post_event() -> queue -> process_next_event() -> _handle_event()"
  - "Cross-project state: xp: prefix in memory_store for company-scoped data"

requirements-completed: [TYPE-04, TYPE-05]

duration: 3min
completed: 2026-03-27
---

# Phase 04 Plan 03: Event-Driven Agents Summary

**EventDrivenLifecycle FSM with listening/processing compound states, FulltimeAgent (PM) and CompanyAgent (Strategist) with asyncio.Queue event processing and crash recovery**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-27T22:44:00Z
- **Completed:** 2026-03-27T22:47:07Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- EventDrivenLifecycle FSM with listening/processing compound running state and HistoryState for sleep/wake preservation
- FulltimeAgent processes events via asyncio.Queue, project-scoped, persists event count for crash recovery
- CompanyAgent processes events the same way but company-scoped with cross-project state helpers (xp: prefix)
- 36 total tests passing across all three test files

## Task Commits

Each task was committed atomically:

1. **Task 1: EventDrivenLifecycle FSM and tests** - `6f8b5ab` (feat)
2. **Task 2: FulltimeAgent and CompanyAgent with event queue and persistence** - `691853f` (feat)

_Note: TDD tasks had RED/GREEN phases within each commit._

## Files Created/Modified
- `src/vcompany/agent/event_driven_lifecycle.py` - EventDrivenLifecycle compound FSM shared by both agents
- `src/vcompany/agent/fulltime_agent.py` - FulltimeAgent (PM) event-driven container
- `src/vcompany/agent/company_agent.py` - CompanyAgent (Strategist) event-driven container
- `src/vcompany/agent/__init__.py` - Updated exports for new types
- `tests/test_event_driven_lifecycle.py` - 22 tests for FSM transitions, history, callbacks
- `tests/test_fulltime_agent.py` - 6 tests for event processing, persistence, from_spec
- `tests/test_company_agent.py` - 8 tests for event processing, cross-project state, crash recovery

## Decisions Made
- EventDrivenLifecycle is a standalone StateMachine (not subclass of ContainerLifecycle) -- compound states require fresh class definition, consistent with GsdLifecycle pattern
- Cross-project state uses xp: prefix in memory_store to namespace company-scoped keys separately from per-agent keys
- Both FulltimeAgent and CompanyAgent share identical event processing pattern (could be extracted to mixin later but kept explicit for clarity now)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All four agent types now implemented (GsdAgent, ContinuousAgent, FulltimeAgent, CompanyAgent)
- Ready for Scheduler (Plan 04) which triggers WAKE on sleeping containers
- Ready for Phase 05 health tree aggregation across all agent types

## Self-Check: PASSED

- All 6 created files verified present
- Commit `6f8b5ab` (Task 1) verified in git log
- Commit `691853f` (Task 2) verified in git log
- 36 tests passing across 3 test files

---
*Phase: 04-remaining-agent-types-and-scheduler*
*Completed: 2026-03-27*
