---
phase: 08-companyroot-wiring-and-migration
plan: 02
subsystem: bot
tags: [discord, supervision-tree, company-root, migration, cogs]

# Dependency graph
requires:
  - phase: 02-supervision-tree
    provides: CompanyRoot, Supervisor, ProjectSupervisor
  - phase: 01-container-base
    provides: AgentContainer, ChildSpec, ContainerContext
provides:
  - VcoBot with CompanyRoot-based initialization replacing v1 flat components
  - CommandsCog routing all operations through CompanyRoot
  - WorkflowOrchestratorCog adapted for GsdAgent containers
affects: [08-03-cleanup, bot-startup, agent-lifecycle]

# Tech tracking
tech-stack:
  added: []
  patterns: [supervision-tree-wiring, container-lookup-via-company-root, cog-bridge-pattern]

key-files:
  created: []
  modified:
    - src/vcompany/bot/client.py
    - src/vcompany/bot/cogs/commands.py
    - src/vcompany/bot/cogs/workflow_orchestrator_cog.py
    - tests/test_bot_client.py
    - tests/test_commands_cog.py
    - tests/test_workflow_orchestrator_cog.py

key-decisions:
  - "WorkflowOrchestratorCog keeps importing WorkflowStage and detect_stage_signal from v1 module -- plan 03 will extract to shared utility"
  - "Gate reviews simplified to post Discord events rather than calling orchestrator methods -- container FSM handles transitions"
  - "set_company_root() replaces set_orchestrator() -- PM and project_dir passed directly, CompanyRoot accessed via bot attribute"

patterns-established:
  - "Container lookup pattern: bot.company_root._find_container(agent_id) for all agent operations"
  - "Supervision tree wiring: on_escalation and on_health_change callbacks from cogs to CompanyRoot"

requirements-completed: [MIGR-01]

# Metrics
duration: 10min
completed: 2026-03-28
---

# Phase 08 Plan 02: CompanyRoot Bot Wiring Summary

**CompanyRoot supervision tree replaces v1 flat initialization in VcoBot.on_ready(), CommandsCog, and WorkflowOrchestratorCog**

## Performance

- **Duration:** 10 min
- **Started:** 2026-03-28T00:30:59Z
- **Completed:** 2026-03-28T00:41:33Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- VcoBot.on_ready() creates CompanyRoot, starts supervision tree, builds ChildSpec list from agents.yaml
- CommandsCog routes /new-project, /dispatch, /kill, /relaunch, /remove-project through CompanyRoot
- WorkflowOrchestratorCog adapted to use bot.company_root instead of v1 WorkflowOrchestrator
- All v1 component initialization (AgentManager, MonitorLoop, CrashTracker) removed from bot startup path
- 61 tests pass across all 3 test files

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite VcoBot.on_ready() to use CompanyRoot** - `67f6319` (feat)
2. **Task 2: Adapt CommandsCog and WorkflowOrchestratorCog for CompanyRoot** - `35228a1` (feat)

## Files Created/Modified
- `src/vcompany/bot/client.py` - VcoBot with CompanyRoot supervision tree replacing v1 flat init
- `src/vcompany/bot/cogs/commands.py` - CommandsCog routing through CompanyRoot for all agent ops
- `src/vcompany/bot/cogs/workflow_orchestrator_cog.py` - WorkflowOrchestratorCog bridging to GsdAgent containers
- `tests/test_bot_client.py` - Updated tests for CompanyRoot attributes and v1 removal
- `tests/test_commands_cog.py` - Updated mocks to use company_root instead of agent_manager
- `tests/test_workflow_orchestrator_cog.py` - Updated to mock CompanyRoot and container lookups

## Decisions Made
- WorkflowOrchestratorCog still imports WorkflowStage and detect_stage_signal from v1 workflow_orchestrator module. Plan 03 handles extracting these to a shared utility. This avoids premature deletion of the v1 module.
- Gate reviews simplified from calling orchestrator.advance_from_gate() to posting Discord events. The GsdAgent container FSM handles actual state transitions -- the cog is purely a Discord bridge.
- set_company_root(pm, project_dir) replaces set_orchestrator(orchestrator, pm, project_dir). CompanyRoot is accessed via self.bot.company_root directly, reducing coupling.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_on_ready_without_project auto-detecting real project**
- **Found during:** Task 1 (test verification)
- **Issue:** Test expected company_root=None but _detect_active_project found real project on disk
- **Fix:** Patched _detect_active_project to return None in test
- **Files modified:** tests/test_bot_client.py
- **Verification:** All 16 bot client tests pass
- **Committed in:** 67f6319 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test fix necessary for correct test isolation. No scope creep.

## Issues Encountered
None

## Known Stubs
None -- all wiring is functional. Gate review methods post real Discord events.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CompanyRoot is now the single entry point for agent lifecycle in the bot
- Plan 03 can safely remove v1 modules (AgentManager, MonitorLoop, CrashTracker, WorkflowOrchestrator)
- WorkflowStage and detect_stage_signal need extraction from v1 module before deletion

## Self-Check: PASSED

All 6 files verified present. Both commit hashes (67f6319, 35228a1) verified in git log.

---
*Phase: 08-companyroot-wiring-and-migration*
*Completed: 2026-03-28*
