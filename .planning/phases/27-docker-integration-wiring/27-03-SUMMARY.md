---
phase: 27-docker-integration-wiring
plan: 03
subsystem: runtime
tags: [duck-typing, config-driven, agent-types, factory, capabilities]

# Dependency graph
requires:
  - phase: 27-01
    provides: AgentTypesConfig model, agent-types.yaml, get_agent_types_config(), _REGISTRY
provides:
  - Config-driven ChildSpec building in runtime_api.py (gsd_command, uses_tmux, transport from agent-types config)
  - Duck-typed method guards replacing isinstance checks (hasattr for resolve_review, initialize_conversation, backlog)
  - container_class lookup in factory from agent-types config (D-13)
  - Dual registry (by type string AND class name) for flexible container resolution
affects: [27-04, docker-agent-e2e]

# Tech tracking
tech-stack:
  added: []
  patterns: [hasattr duck typing for method guards, config-driven capability checks, dual-key registry]

key-files:
  created: []
  modified:
    - src/vcompany/daemon/runtime_api.py
    - src/vcompany/supervisor/supervisor.py
    - src/vcompany/container/factory.py

key-decisions:
  - "hasattr duck typing over isinstance for method guards (resolve_review, initialize_conversation, backlog)"
  - "Plan approval/rejection sends to all containers (receive_discord_message is on base class)"
  - "Dual registry by type string and class name enables docker-gsd -> GsdAgent mapping"

patterns-established:
  - "Config-driven capabilities: check 'uses_tmux' in type_config.capabilities, not type string matching"
  - "Duck-typed method guards: hasattr(container, 'method_name') instead of isinstance(container, SubClass)"
  - "Dual registry pattern: register_agent_type('gsd', GsdAgent) AND register_agent_type('GsdAgent', GsdAgent)"

requirements-completed: [WIRE-05, WIRE-07]

# Metrics
duration: 3min
completed: 2026-03-29
---

# Phase 27 Plan 03: Remove Hardcoded Type Checks Summary

**Config-driven capability lookups and hasattr duck typing replace all isinstance/type-string checks in runtime_api.py and supervisor.py**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-29T23:16:24Z
- **Completed:** 2026-03-29T23:19:33Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Eliminated all hardcoded agent-type string checks from runtime_api.py (gsd_command, uses_tmux now from config)
- Replaced 7 isinstance checks across runtime_api.py with hasattr duck typing
- Added container_class config lookup in factory.py (D-13) enabling docker-gsd type to resolve to GsdAgent
- Updated register_defaults to register by both type string and class name (11 entries)
- Eliminated hardcoded type check in supervisor.py delegation context

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace type checks in runtime_api.py** - `05112c6` (feat)
2. **Task 2: Replace type checks in supervisor.py and update factory** - `d9ed8b2` (feat)

## Files Created/Modified
- `src/vcompany/daemon/runtime_api.py` - Config-driven ChildSpec building, duck-typed method guards replacing 7 isinstance checks
- `src/vcompany/supervisor/supervisor.py` - Config-driven delegation context (uses_tmux, gsd_command, transport)
- `src/vcompany/container/factory.py` - container_class lookup from agent-types config, dual-key registry

## Decisions Made
- Used hasattr duck typing for method guards (resolve_review, initialize_conversation, backlog) -- true structural subtyping
- Plan approval/rejection simplified to check `container is not None` (receive_discord_message exists on base AgentContainer)
- Factory tries container_class name from config first, falls back to agent_type string lookup -- backward compatible
- Dual registry registers by both type string ("gsd") and class name ("GsdAgent") so config container_class field works

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All hardcoded type checks eliminated from runtime code
- Adding a new agent type now requires only a config entry in agent-types.yaml + optional subclass registration
- Ready for Plan 04 (e2e Docker agent via Discord) -- factory resolves container_class from config

---
*Phase: 27-docker-integration-wiring*
*Completed: 2026-03-29*
