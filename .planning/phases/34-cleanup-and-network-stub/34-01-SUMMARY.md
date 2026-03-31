---
phase: 34-cleanup-and-network-stub
plan: 01
subsystem: infra
tags: [refactor, import-migration, subprocess, dead-code-prep]

# Dependency graph
requires:
  - phase: 33-container-autonomy
    provides: transport channel protocol, container autonomy, daemon restart survival
provides:
  - "HealthReport/HealthNode/HealthTree/CompanyHealthTree in supervisor/health.py"
  - "ChildSpec/ChildSpecRegistry/RestartPolicy in supervisor/child_spec.py"
  - "MemoryStore in shared/memory_store.py"
  - "set/get_agent_types_config in models/agent_types.py"
  - "StrategistConversation uses direct subprocess (no AgentTransport)"
affects: [34-02-dead-code-deletion, 34-03-network-stub]

# Tech tracking
tech-stack:
  added: []
  patterns: ["direct subprocess for Strategist CLI calls", "type migration from container/ to permanent homes"]

key-files:
  created:
    - src/vcompany/supervisor/health.py
    - src/vcompany/supervisor/child_spec.py
    - src/vcompany/shared/memory_store.py
  modified:
    - src/vcompany/models/agent_types.py
    - src/vcompany/daemon/agent_handle.py
    - src/vcompany/daemon/daemon.py
    - src/vcompany/daemon/runtime_api.py
    - src/vcompany/supervisor/company_root.py
    - src/vcompany/supervisor/supervisor.py
    - src/vcompany/supervisor/project_supervisor.py
    - src/vcompany/supervisor/scheduler.py
    - src/vcompany/autonomy/backlog.py
    - src/vcompany/autonomy/project_state.py
    - src/vcompany/bot/cogs/health.py
    - src/vcompany/bot/embeds.py
    - src/vcompany/strategist/conversation.py

key-decisions:
  - "ChildSpec still imports ContainerContext from container/context.py -- ContainerContext is needed for container runtime and stays in container/"
  - "StrategistConversation no longer requires transport parameter -- uses working_dir + direct subprocess"
  - "RuntimeAPI.create_strategist() creates StrategistConversation directly, no AgentContainer/ChildSpec/ContainerContext"

patterns-established:
  - "Supervisor-owned types live in supervisor/ not container/"
  - "Shared infrastructure (MemoryStore) lives in shared/ not container/"
  - "Agent types config accessor functions live with the config models in models/"

requirements-completed: [HEAD-04]

# Metrics
duration: 5min
completed: 2026-03-31
---

# Phase 34 Plan 01: Migrate Live Types and Port Strategist Summary

**Migrated HealthReport/ChildSpec/MemoryStore to permanent homes and ported StrategistConversation to direct subprocess, eliminating all container/ imports for migrated types**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-31T17:16:28Z
- **Completed:** 2026-03-31T17:22:01Z
- **Tasks:** 2
- **Files modified:** 17

## Accomplishments
- All live types (HealthReport, ChildSpec, MemoryStore, agent_types_config) migrated from container/ to permanent locations
- All 15 files importing migrated types updated to new paths
- StrategistConversation rewritten to use asyncio.create_subprocess_exec directly
- RuntimeAPI.create_strategist() simplified to create conversation directly (no container path)

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate types from container/ to permanent locations** - `b590ea1` (refactor)
2. **Task 2: Port StrategistConversation to direct subprocess** - `0fe9431` (refactor)

## Files Created/Modified
- `src/vcompany/supervisor/health.py` - HealthReport, HealthNode, HealthTree, CompanyHealthTree (migrated from container/)
- `src/vcompany/supervisor/child_spec.py` - ChildSpec, ChildSpecRegistry, RestartPolicy (migrated from container/)
- `src/vcompany/shared/memory_store.py` - MemoryStore async SQLite wrapper (migrated from container/)
- `src/vcompany/models/agent_types.py` - Added set/get_agent_types_config functions
- `src/vcompany/daemon/agent_handle.py` - Updated HealthReport import
- `src/vcompany/daemon/daemon.py` - Updated set_agent_types_config import
- `src/vcompany/daemon/runtime_api.py` - Updated imports, rewrote create_strategist()
- `src/vcompany/supervisor/company_root.py` - Updated ChildSpec, health, MemoryStore imports
- `src/vcompany/supervisor/supervisor.py` - Updated ChildSpec, health imports
- `src/vcompany/supervisor/project_supervisor.py` - Updated ChildSpec import
- `src/vcompany/supervisor/scheduler.py` - Updated MemoryStore import
- `src/vcompany/autonomy/backlog.py` - Updated MemoryStore import
- `src/vcompany/autonomy/project_state.py` - Updated MemoryStore import
- `src/vcompany/bot/cogs/health.py` - Updated CompanyHealthTree import
- `src/vcompany/bot/embeds.py` - Updated CompanyHealthTree import
- `src/vcompany/strategist/conversation.py` - Rewritten with direct subprocess

## Decisions Made
- ChildSpec still imports ContainerContext from container/context.py since ContainerContext is still used by the container runtime (will be cleaned in Plan 02)
- StrategistConversation takes `working_dir` parameter instead of `transport` -- simpler, no transport abstraction needed for piped CLI
- create_strategist() registers StrategistConversation directly with MentionRouter instead of going through add_company_agent()

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All migrated types are in permanent locations with updated imports
- StrategistConversation has no AgentTransport dependency
- Ready for Plan 02 (dead code deletion of container/ files that are no longer imported by live code)

## Self-Check: PASSED

---
*Phase: 34-cleanup-and-network-stub*
*Completed: 2026-03-31*
