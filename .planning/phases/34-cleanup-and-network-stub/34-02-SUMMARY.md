---
phase: 34-cleanup-and-network-stub
plan: 02
subsystem: infra
tags: [refactor, dead-code-removal, cleanup, container-deletion]

# Dependency graph
requires:
  - phase: 34-cleanup-and-network-stub
    provides: migrated types (HealthReport, ChildSpec, MemoryStore), StrategistConversation with direct subprocess
provides:
  - "No agent/, handler/, container/ directories under src/vcompany/"
  - "No isinstance(x, AgentHandle) dispatch branches in live code"
  - "Clean transport/__init__.py with only ChannelTransport, NativeTransport, DockerChannelTransport"
  - "ContainerContext inlined into supervisor/child_spec.py"
  - "18 dead test files removed, 14 surviving test files updated"
affects: [34-03-network-stub]

# Tech tracking
tech-stack:
  added: []
  patterns: ["All agents are AgentHandle -- no container type dispatch", "ContainerContext co-located with ChildSpec in supervisor/"]

key-files:
  created: []
  modified:
    - src/vcompany/transport/__init__.py
    - src/vcompany/daemon/runtime_api.py
    - src/vcompany/daemon/daemon.py
    - src/vcompany/supervisor/company_root.py
    - src/vcompany/supervisor/supervisor.py
    - src/vcompany/supervisor/child_spec.py
    - src/vcompany/supervisor/scheduler.py
    - src/vcompany/supervisor/__init__.py
    - src/vcompany/bot/cogs/mention_router.py

key-decisions:
  - "ContainerContext moved into supervisor/child_spec.py rather than its own file -- co-located with ChildSpec which is the only type that uses it"
  - "Supervisor._start_child() raises NotImplementedError -- all new agent creation goes through CompanyRoot.hire()"
  - "supervisor/__init__.py uses lazy imports for CompanyRoot/ProjectSupervisor to break circular import with daemon.agent_handle"
  - "TASKS_DIR inlined as Path.home() / 'vco-tasks' in CompanyRoot.hire() since agent.task_agent module was deleted"

patterns-established:
  - "All agent routing assumes AgentHandle -- no isinstance dispatch needed"
  - "MentionRouter accepts Any agent with send() method -- no type-specific routing"

requirements-completed: [HEAD-04]

# Metrics
duration: 10min
completed: 2026-03-31
---

# Phase 34 Plan 02: Delete Dead Code Summary

**Deleted agent/, handler/, container/ directories and 3 transport files (7,872 lines removed), cleaned all isinstance dispatch branches to assume AgentHandle only, deleted 18 dead test files and updated 14 surviving test imports**

## Performance

- **Duration:** 10 min
- **Started:** 2026-03-31T17:24:01Z
- **Completed:** 2026-03-31T17:34:01Z
- **Tasks:** 2
- **Files modified:** 72 (38 deleted + 9 modified in Task 1, 18 deleted + 16 modified in Task 2)

## Accomplishments
- Deleted 3 entire directories (agent/, handler/, container/) and 3 dead transport files -- 7,872 lines of dead code removed
- Cleaned all isinstance(handle, AgentHandle) branches in RuntimeAPI (8 methods simplified), CompanyRoot (stop()), and MentionRouter (_deliver_to_agent())
- Removed add_company_agent(), _find_container(), register_defaults() from CompanyRoot
- Deleted 18 dead test files and updated 14 surviving test files to use new import paths
- 905 tests collect successfully after cleanup

## Task Commits

Each task was committed atomically:

1. **Task 1: Delete dead directories and files, clean isinstance branches** - `7ce8d6a` (refactor)
2. **Task 2: Delete dead tests, update surviving test imports** - `3d59a1d` (test)

## Files Created/Modified
- `src/vcompany/transport/__init__.py` - Clean exports: ChannelTransport, NativeTransport, DockerChannelTransport only
- `src/vcompany/daemon/runtime_api.py` - All isinstance branches removed, all methods assume AgentHandle
- `src/vcompany/daemon/daemon.py` - Removed dead _find_container file resolution in _handle_send_file
- `src/vcompany/supervisor/company_root.py` - Removed container imports, add_company_agent(), _find_container(), register_defaults()
- `src/vcompany/supervisor/supervisor.py` - Removed container/factory imports, _start_child raises NotImplementedError
- `src/vcompany/supervisor/child_spec.py` - ContainerContext moved here from deleted container/context.py
- `src/vcompany/supervisor/scheduler.py` - Updated TYPE_CHECKING import from container to agent_handle
- `src/vcompany/supervisor/__init__.py` - Lazy imports for CompanyRoot/ProjectSupervisor to avoid circular import
- `src/vcompany/bot/cogs/mention_router.py` - Removed legacy AgentContainer path, all routing via InboundMessage

## Decisions Made
- ContainerContext inlined into supervisor/child_spec.py since ChildSpec is the only remaining consumer
- Supervisor._start_child() made to raise NotImplementedError since container factory was deleted
- Used lazy imports in supervisor/__init__.py to resolve circular import between company_root and daemon.agent_handle

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Circular import in supervisor/__init__.py**
- **Found during:** Task 1 (verification step)
- **Issue:** supervisor/__init__.py eagerly imported CompanyRoot which imports daemon.agent_handle which imports supervisor.health which triggers supervisor/__init__.py
- **Fix:** Made CompanyRoot and ProjectSupervisor lazy imports via __getattr__ in supervisor/__init__.py
- **Files modified:** src/vcompany/supervisor/__init__.py
- **Verification:** `python -c "from vcompany.daemon.runtime_api import RuntimeAPI"` succeeds
- **Committed in:** 7ce8d6a (Task 1 commit)

**2. [Rule 3 - Blocking] TASKS_DIR import from deleted module**
- **Found during:** Task 1 (CompanyRoot.hire() cleanup)
- **Issue:** hire() imported TASKS_DIR from vcompany.agent.task_agent which was deleted
- **Fix:** Inlined as `Path.home() / "vco-tasks"` (same value the deleted constant had)
- **Files modified:** src/vcompany/supervisor/company_root.py
- **Committed in:** 7ce8d6a (Task 1 commit)

**3. [Rule 2 - Missing Critical] ContainerContext needed by ChildSpec after container/ deletion**
- **Found during:** Task 1 (planning phase)
- **Issue:** ChildSpec.context field uses ContainerContext which lived in the deleted container/context.py
- **Fix:** Moved ContainerContext class definition into supervisor/child_spec.py alongside ChildSpec
- **Files modified:** src/vcompany/supervisor/child_spec.py
- **Committed in:** 7ce8d6a (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 missing critical)
**Impact on plan:** All auto-fixes necessary for correctness after directory deletion. No scope creep.

## Issues Encountered
- test_report_cmd.py has a pre-existing collection error (imports _channel_cache which doesn't exist) -- not caused by this plan, not fixed

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All dead code removed, codebase clean for HEAD-04 requirement
- Ready for Plan 03 (network transport stub)
- 905 tests collect successfully

## Self-Check: PASSED

---
*Phase: 34-cleanup-and-network-stub*
*Completed: 2026-03-31*
