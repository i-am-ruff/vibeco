---
phase: 09-agent-type-routing-and-pm-event-dispatch
plan: 01
subsystem: config
tags: [pydantic, agent-types, factory-routing, config-validation]

# Dependency graph
requires:
  - phase: 04-agent-type-specializations
    provides: ContainerFactory with register_defaults(), FulltimeAgent, CompanyAgent classes
provides:
  - AgentConfig.type field with Literal validation and "gsd" default
  - Direct attribute access on AgentConfig in client.py and commands.py (no hasattr guards)
  - Config-driven agent type routing via ContainerFactory
affects: [09-02-pm-event-dispatch]

# Tech tracking
tech-stack:
  added: []
  patterns: [pydantic-literal-validation-for-agent-type-routing]

key-files:
  created: []
  modified:
    - src/vcompany/models/config.py
    - src/vcompany/bot/client.py
    - src/vcompany/bot/cogs/commands.py
    - tests/test_config.py
    - tests/test_container_factory.py

key-decisions:
  - "type field placed after system_prompt in AgentConfig for logical grouping"
  - "Default 'gsd' ensures full backward compatibility with existing agents.yaml files"

patterns-established:
  - "Pydantic Literal type for agent type validation: all valid types enumerated in one place"

requirements-completed: [TYPE-04, TYPE-05]

# Metrics
duration: 3min
completed: 2026-03-28
---

# Phase 09 Plan 01: Agent Type Routing Summary

**AgentConfig.type field with Literal["gsd","continuous","fulltime","company"] default "gsd" enabling config-driven factory routing and clean direct attribute access**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-28T04:34:06Z
- **Completed:** 2026-03-28T04:37:04Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Added validated type field to AgentConfig with backward-compatible "gsd" default
- Factory routing tested: fulltime -> FulltimeAgent, company -> CompanyAgent
- Removed all hasattr fallback guards from client.py and commands.py
- 83 tests pass across all modified file test suites

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for type field** - `e97da48` (test)
2. **Task 1 GREEN: Add type field to AgentConfig** - `9c2aea5` (feat)
3. **Task 2: Remove hasattr guards** - `a606960` (fix)

## Files Created/Modified
- `src/vcompany/models/config.py` - Added type: Literal["gsd", "continuous", "fulltime", "company"] = "gsd" to AgentConfig
- `src/vcompany/bot/client.py` - Replaced hasattr guards with direct attribute access on AgentConfig
- `src/vcompany/bot/cogs/commands.py` - Replaced hasattr guards with direct attribute access on AgentConfig
- `tests/test_config.py` - Added 6 tests for type field validation (default, all 4 valid values, invalid rejection, fixture compat)
- `tests/test_container_factory.py` - Added 2 tests for factory routing (fulltime, company)

## Decisions Made
- type field placed after system_prompt in AgentConfig for logical grouping with other agent metadata
- Default "gsd" ensures backward compatibility -- existing agents.yaml files without type key parse without changes

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Pre-existing test failure in tests/test_pm_integration.py (unrelated to this plan -- _write_answer_file_sync attribute missing from question_handler module). Logged as out-of-scope.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- AgentConfig.type field ready for consumption by PM event dispatch (plan 09-02)
- All 4 agent types route correctly through ContainerFactory from config
- No blockers

---
*Phase: 09-agent-type-routing-and-pm-event-dispatch*
*Completed: 2026-03-28*
