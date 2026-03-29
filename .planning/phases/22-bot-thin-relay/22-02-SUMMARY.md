---
phase: 22-bot-thin-relay
plan: 02
subsystem: bot-cogs
tags: [import-boundary, runtime-api, bot-relay, refactoring, cog-rewrite]

requires:
  - phase: 22-bot-thin-relay
    plan: 01
    provides: RuntimeAPI gateway methods for bot cog delegation
provides:
  - Three heaviest cog files rewritten as pure RuntimeAPI delegates
  - validate_safety_table moved to vcompany.shared.safety_validator
  - RuntimeAPI methods for resolve_review, verify_agent_execution, log_plan_decision, get_container_info, route_completion_to_pm, new_project_from_name
affects: [22-bot-thin-relay plan 03 (remaining cogs), import-boundary-tests]

tech-stack:
  added: []
  patterns: [cog-as-pure-io-adapter, runtime-api-delegation-for-all-container-access]

key-files:
  created:
    - src/vcompany/shared/safety_validator.py
  modified:
    - src/vcompany/bot/cogs/commands.py
    - src/vcompany/bot/cogs/plan_review.py
    - src/vcompany/bot/cogs/workflow_orchestrator_cog.py
    - src/vcompany/daemon/runtime_api.py
    - tests/test_import_boundary.py

key-decisions:
  - "validate_safety_table moved to vcompany.shared -- pure stateless utility with no container deps"
  - "RuntimeAPI.new_project_from_name() handles config loading, cloning, structure creation previously inline in commands.py"
  - "WorkflowOrchestratorCog.set_company_root renamed to set_runtime_context"
  - "xfail markers narrowed to remaining violations in client.py and strategist.py for Plan 03"
  - "build_integration_embed replaced with inline Discord embed construction to avoid importing IntegrationResult"

duration: 545s
completed: 2026-03-29
---

# Phase 22 Plan 02: Rewrite Heaviest Cog Files Summary

**Three heaviest-violation cog files (commands.py, plan_review.py, workflow_orchestrator_cog.py) rewritten as pure RuntimeAPI delegates with zero prohibited imports and zero _find_container calls**

## Performance

- **Duration:** 9 min (545s)
- **Started:** 2026-03-29T12:36:30Z
- **Completed:** 2026-03-29T12:45:35Z
- **Tasks:** 2
- **Files modified:** 6 (5 modified + 1 created)

## Accomplishments

- Rewrote commands.py: removed 3 module-level prohibited imports and 7 function-level prohibited imports, removed _get_company_root helper entirely, all slash commands now delegate to RuntimeAPI
- Rewrote plan_review.py: removed 5 function-level prohibited imports (git ops, AgentsRegistry, TmuxManager, DecisionLogEntry, GsdAgent), all container access goes through RuntimeAPI
- Rewrote workflow_orchestrator_cog.py: removed all 4 _find_container calls, replaced with RuntimeAPI.get_container_info and route_completion_to_pm
- Moved validate_safety_table from vcompany.monitor to vcompany.shared (pure utility)
- Added 7 new RuntimeAPI methods for cog delegation
- Updated import boundary test xfail markers to reflect narrowed scope

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite commands.py** - `7899cac` (feat)
2. **Task 2: Rewrite plan_review.py and workflow_orchestrator_cog.py** - `c1b8fe4` (feat)

## Files Created/Modified

- `src/vcompany/bot/cogs/commands.py` - Pure RuntimeAPI delegate, all prohibited imports removed
- `src/vcompany/bot/cogs/plan_review.py` - Pure RuntimeAPI delegate, all function-level prohibited imports removed
- `src/vcompany/bot/cogs/workflow_orchestrator_cog.py` - Pure RuntimeAPI delegate, all _find_container calls removed
- `src/vcompany/daemon/runtime_api.py` - Added 7 new methods (resolve_review, verify_agent_execution, log_plan_decision, signal_workflow_stage, get_container_info, route_completion_to_pm, new_project_from_name)
- `src/vcompany/shared/safety_validator.py` - Moved from vcompany.monitor (pure stateless utility)
- `tests/test_import_boundary.py` - Updated xfail reasons (narrowed to plan 03 scope)

## Decisions Made

- validate_safety_table is a pure function (only imports re from stdlib) so moved to shared rather than wrapping in RuntimeAPI
- build_integration_embed replaced with inline Discord embed construction in commands.py to avoid importing IntegrationResult type
- WorkflowOrchestratorCog.set_company_root renamed to set_runtime_context (no external callers found)
- RuntimeAPI.new_project_from_name handles all project initialization business logic previously inline in commands.py /new-project

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added RuntimeAPI.new_project_from_name()**
- **Found during:** Task 1
- **Issue:** /new-project command had extensive inline business logic (config loading, cloning, directory structure) that couldn't simply call existing RuntimeAPI.new_project() which expects config and dir already loaded
- **Fix:** Added new_project_from_name(name) method to RuntimeAPI that handles full initialization pipeline
- **Files modified:** src/vcompany/daemon/runtime_api.py
- **Commit:** 7899cac

**2. [Rule 3 - Blocking] Added 6 new RuntimeAPI methods for plan_review/workflow_orchestrator**
- **Found during:** Task 2
- **Issue:** plan_review.py and workflow_orchestrator_cog.py accessed containers directly for review resolution, git verification, decision logging, and completion routing
- **Fix:** Added resolve_review, verify_agent_execution, log_plan_decision, signal_workflow_stage, get_container_info, route_completion_to_pm to RuntimeAPI
- **Files modified:** src/vcompany/daemon/runtime_api.py
- **Commit:** c1b8fe4

## Issues Encountered
None

## User Setup Required
None

## Known Stubs
None -- all functionality is wired to RuntimeAPI methods.

## Next Phase Readiness
- Three heaviest cog files are clean
- Remaining violations are in client.py and strategist.py (Plan 03 scope)
- Import boundary tests will pass fully once Plan 03 completes

---
*Phase: 22-bot-thin-relay*
*Completed: 2026-03-29*
