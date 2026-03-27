---
phase: 04-remaining-agent-types-and-scheduler
plan: 04
subsystem: supervisor
tags: [scheduler, asyncio, pydantic, memory-store, agent-types, factory]

# Dependency graph
requires:
  - phase: 04-remaining-agent-types-and-scheduler (plans 01-03)
    provides: "AgentContainer factory, ContinuousAgent, FulltimeAgent, CompanyAgent, GsdAgent"
provides:
  - "Scheduler with persistent MemoryStore-backed schedule and 60s wake loop"
  - "register_defaults() for all four agent types in factory"
  - "CompanyRoot manages scheduler lifecycle (start/stop)"
  - "CompanyRoot._find_container() for cross-project agent lookup"
affects: [05-health-tree-and-delegation, 06-resilience]

# Tech tracking
tech-stack:
  added: []
  patterns: [scheduler-as-asyncio-task, register-defaults-lazy-imports, pass-through-methods]

key-files:
  created:
    - src/vcompany/supervisor/scheduler.py
    - tests/test_scheduler.py
  modified:
    - src/vcompany/supervisor/company_root.py
    - src/vcompany/container/factory.py

key-decisions:
  - "Scheduler uses MemoryStore KV (not checkpoints) for schedule persistence -- single 'schedules' key with JSON array"
  - "register_defaults() uses lazy imports to avoid circular dependencies between factory and agent modules"
  - "CompanyRoot._find_container searches all ProjectSupervisors' children dict by agent_id"

patterns-established:
  - "Scheduler-as-task: asyncio.create_task(scheduler.run()) owned by CompanyRoot lifecycle"
  - "register_defaults with lazy imports: factory registration function uses local imports to break circular deps"

requirements-completed: [AUTO-06, TYPE-03, TYPE-04, TYPE-05]

# Metrics
duration: 4min
completed: 2026-03-27
---

# Phase 4 Plan 4: Scheduler and Factory Registration Summary

**Scheduler waking sleeping ContinuousAgents on persistent schedule with all four agent types registered in factory via register_defaults()**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-27T22:50:01Z
- **Completed:** 2026-03-27T22:54:18Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Scheduler module with ScheduleEntry pydantic model, persistent MemoryStore storage, 60s check loop, and graceful missing-agent handling
- All four agent types (gsd, continuous, fulltime, company) registered in factory via register_defaults()
- CompanyRoot owns scheduler lifecycle: start opens MemoryStore + loads schedules + creates task, stop cancels task + closes store
- 10 dedicated scheduler tests covering add/remove/get, wake logic, persistence, missing agents, and run loop

## Task Commits

Each task was committed atomically:

1. **Task 1: Scheduler module with persistent schedule and wake logic** - `58208f6` (test) + `e79a3f7` (feat) [TDD]
2. **Task 2: Wire scheduler into CompanyRoot and register all agent types** - `060468d` (feat)

_Note: Task 1 used TDD -- test commit followed by implementation commit_

## Files Created/Modified
- `src/vcompany/supervisor/scheduler.py` - Scheduler and ScheduleEntry: persistent wake scheduling for ContinuousAgents
- `tests/test_scheduler.py` - 10 tests covering scheduler add/remove/wake/persistence/loop
- `src/vcompany/supervisor/company_root.py` - Scheduler integration: start/stop lifecycle, _find_container, pass-through methods
- `src/vcompany/container/factory.py` - register_defaults() registering all four agent types

## Decisions Made
- Scheduler stores schedules as JSON array under single MemoryStore key "schedules" (simple, sufficient for expected scale)
- register_defaults() uses lazy local imports to avoid circular dependency between factory module and agent modules
- _find_container searches ProjectSupervisor.children dicts linearly -- sufficient for expected number of agents per company

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- pytest-asyncio strict mode rejects async fixtures without explicit @pytest_asyncio.fixture decorator -- resolved by using inline async helper functions instead of async fixtures

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 4 complete: all agent types implemented, factory populated, scheduler operational
- Ready for Phase 5 (health tree and delegation) -- all container/supervisor/agent infrastructure in place
- Pre-existing test_bot_startup.py failure is unrelated to this plan

## Self-Check: PASSED

All files exist, all commit hashes verified.

---
*Phase: 04-remaining-agent-types-and-scheduler*
*Completed: 2026-03-27*
