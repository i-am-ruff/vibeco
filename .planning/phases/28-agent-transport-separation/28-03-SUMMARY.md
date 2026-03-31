---
phase: 28-agent-transport-separation
plan: 03
subsystem: container
tags: [handler, factory, agent-types, config, registry]

# Dependency graph
requires:
  - phase: 28-01
    provides: "AgentContainer with _handler slot and _channel_id"
  - phase: 28-02
    provides: "GsdSessionHandler, StrategistConversationHandler, PMTransientHandler implementations"
provides:
  - "AgentTypeConfig with handler field for config-driven handler selection"
  - "agent-types.yaml with handler field on all entries"
  - "_HANDLER_REGISTRY in factory mapping handler names to classes"
  - "Handler injection in create_container from agent type config"
affects: [28-04]

# Tech tracking
tech-stack:
  added: []
  patterns: ["handler registry pattern parallel to transport registry", "config-driven handler injection"]

key-files:
  created: []
  modified:
    - "src/vcompany/models/agent_types.py"
    - "agent-types.yaml"
    - "src/vcompany/container/factory.py"

key-decisions:
  - "handler field defaults to None for backward compatibility with legacy subclass routing"
  - "_HANDLER_REGISTRY parallels _TRANSPORT_REGISTRY pattern for consistency"

patterns-established:
  - "Handler registry: string name maps to handler class, same as transport registry"
  - "Config-driven composition: agent-types.yaml handler field drives factory injection"

requirements-completed: [HSEP-04, HSEP-05]

# Metrics
duration: 2min
completed: 2026-03-31
---

# Phase 28 Plan 03: Config-Driven Handler Composition Summary

**Handler field in AgentTypeConfig and agent-types.yaml, _HANDLER_REGISTRY in factory with config-driven injection into container._handler**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T04:45:13Z
- **Completed:** 2026-03-31T04:46:37Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added handler field to AgentTypeConfig model with None default for backward compat
- Updated all _BUILTIN_DEFAULTS and agent-types.yaml entries with correct handler values
- Added _HANDLER_REGISTRY to factory with 3 handler class mappings
- Factory create_container now injects handler from config into container._handler

## Task Commits

Each task was committed atomically:

1. **Task 1: Add handler field to AgentTypeConfig and agent-types.yaml** - `faff325` (feat)
2. **Task 2: Add handler registry and injection to factory** - `29465d6` (feat)

## Files Created/Modified
- `src/vcompany/models/agent_types.py` - Added handler: str | None = None field, updated _BUILTIN_DEFAULTS
- `agent-types.yaml` - Added handler field to all 6 agent type entries
- `src/vcompany/container/factory.py` - Added _HANDLER_REGISTRY, handler injection in create_container, get_handler_registry()

## Decisions Made
- handler defaults to None (not "session") for backward compatibility -- configs without handler still work via legacy subclass routing
- _HANDLER_REGISTRY follows exact same dict[str, type] pattern as _TRANSPORT_REGISTRY for consistency

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Handler x transport matrix is fully composable from configuration
- Plan 04 can now implement end-to-end wiring tests or additional handler types
- Adding a new handler requires: 1 handler class + 1 registry line + 1 yaml entry

---
*Phase: 28-agent-transport-separation*
*Completed: 2026-03-31*
