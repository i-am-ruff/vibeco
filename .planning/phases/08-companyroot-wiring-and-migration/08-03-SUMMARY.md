---
phase: 08-companyroot-wiring-and-migration
plan: 03
subsystem: migration
tags: [v1-removal, tmux, cli, supervision-tree, workflow-types]

# Dependency graph
requires:
  - phase: 08-companyroot-wiring-and-migration plan 01
    provides: CompanyRoot bot wiring, DiscordCommunicationPort
  - phase: 08-companyroot-wiring-and-migration plan 02
    provides: VcoBot.on_ready with CompanyRoot, adapted CommandsCog and WorkflowOrchestratorCog
provides:
  - 4 v1 source modules deleted (MonitorLoop, CrashTracker, WorkflowOrchestrator, AgentManager)
  - 6 v1 test files deleted
  - CLI commands using TmuxManager directly
  - Shared workflow types module (WorkflowStage, detect_stage_signal)
  - PlanReviewCog using TmuxManager instead of AgentManager
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CLI commands use TmuxManager directly for operator-only use"
    - "Shared workflow_types.py for cross-module enums and signal detection"
    - "PlanReviewCog._send_tmux_command helper for decoupled tmux operations"

key-files:
  created:
    - src/vcompany/shared/workflow_types.py
  modified:
    - src/vcompany/cli/dispatch_cmd.py
    - src/vcompany/cli/kill_cmd.py
    - src/vcompany/cli/relaunch_cmd.py
    - src/vcompany/cli/monitor_cmd.py
    - src/vcompany/bot/cogs/alerts.py
    - src/vcompany/bot/cogs/plan_review.py
    - src/vcompany/bot/cogs/workflow_orchestrator_cog.py
    - tests/test_bot_startup.py
    - tests/test_conflict_resolver.py
    - tests/test_pm_integration.py
    - tests/test_integration_interlock.py
    - tests/test_workflow_orchestrator_cog.py
    - tests/test_plan_review_cog.py

key-decisions:
  - "Extracted WorkflowStage and detect_stage_signal to shared/workflow_types.py instead of duplicating or inlining"
  - "CLI commands use TmuxManager directly (not CompanyRoot) for independence from running bot"
  - "monitor command kept as deprecation notice rather than deleted for backward compatibility"
  - "PlanReviewCog uses TmuxManager via agents.json registry lookup instead of AgentManager._panes"

patterns-established:
  - "CLI dispatch pattern: TmuxManager for operator-only manual dispatch"
  - "Cog tmux pattern: agents.json registry -> TmuxManager.send_command for pane operations"

requirements-completed: [MIGR-03]

# Metrics
duration: 46min
completed: 2026-03-28
---

# Phase 08 Plan 03: Remove v1 Modules and Update All Imports Summary

**Deleted 4 v1 source modules and 6 test files, updated 14+ import sites across CLI/cogs/tests to use TmuxManager and shared workflow types**

## Performance

- **Duration:** 46 min
- **Started:** 2026-03-28T00:46:40Z
- **Completed:** 2026-03-28T01:32:40Z
- **Tasks:** 2
- **Files modified:** 25 (4 deleted source + 6 deleted tests + 1 created + 14 modified)

## Accomplishments
- Deleted all 4 v1 source modules: monitor/loop.py, orchestrator/crash_tracker.py, orchestrator/workflow_orchestrator.py, orchestrator/agent_manager.py
- Deleted 6 v1-only test files: test_monitor_loop, test_crash_tracker, test_workflow_orchestrator, test_dispatch, test_kill, test_relaunch
- Extracted WorkflowStage enum and detect_stage_signal to shared/workflow_types.py
- Rewrote 4 CLI commands to use TmuxManager directly
- Updated PlanReviewCog to use TmuxManager instead of AgentManager
- Rewrote test_bot_startup.py from v1 to v2 CompanyRoot assertions
- 906 tests collected, 896 pass (7 pre-existing failures unrelated to changes)

## Task Commits

Each task was committed atomically:

1. **Task 1: Delete v1 source modules and their dedicated tests** - `dbb9f58` (feat)
2. **Task 2: Update CLI commands and remaining cogs** - `fb13fbc` (feat)

## Files Created/Modified
- `src/vcompany/shared/workflow_types.py` - Extracted WorkflowStage enum and detect_stage_signal from v1 module
- `src/vcompany/cli/dispatch_cmd.py` - Rewritten to use TmuxManager directly
- `src/vcompany/cli/kill_cmd.py` - Rewritten to use TmuxManager (kill window/session)
- `src/vcompany/cli/relaunch_cmd.py` - Rewritten to use TmuxManager (kill + re-dispatch)
- `src/vcompany/cli/monitor_cmd.py` - Replaced with deprecation notice
- `src/vcompany/bot/cogs/alerts.py` - Updated docstrings to reference supervision tree
- `src/vcompany/bot/cogs/plan_review.py` - Replaced bot.agent_manager with _send_tmux_command helper
- `src/vcompany/bot/cogs/workflow_orchestrator_cog.py` - Import from shared/workflow_types.py
- `tests/test_bot_startup.py` - Rewritten for v2 CompanyRoot wiring
- `tests/test_conflict_resolver.py` - Removed AgentManager.dispatch_fix tests
- `tests/test_pm_integration.py` - Removed MonitorLoop status digest test
- `tests/test_integration_interlock.py` - Kept only AgentMonitorState field tests
- `tests/test_workflow_orchestrator_cog.py` - Import from shared/workflow_types.py
- `tests/test_plan_review_cog.py` - Fixed approval flow assertion for v2 behavior

## Decisions Made
- Extracted WorkflowStage and detect_stage_signal to shared/workflow_types.py rather than duplicating or inlining -- these are needed by WorkflowOrchestratorCog and its tests
- CLI commands use TmuxManager directly (not through CompanyRoot) so they work independently when the Discord bot is not running
- monitor command kept as a deprecation notice rather than deleted, so `vco monitor` doesn't error but explains the replacement
- PlanReviewCog uses a new _send_tmux_command helper that looks up pane_id from agents.json registry, creating a TmuxManager instance as needed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Extracted shared workflow types before deletion**
- **Found during:** Task 1 (Delete v1 source modules)
- **Issue:** WorkflowOrchestratorCog (adapted in plan 02) still imported WorkflowStage and detect_stage_signal from v1 workflow_orchestrator.py. Deleting the file without extraction would break the cog.
- **Fix:** Created src/vcompany/shared/workflow_types.py with the stage enum and signal detection function, updated imports in cog and tests.
- **Files modified:** src/vcompany/shared/workflow_types.py (created), src/vcompany/bot/cogs/workflow_orchestrator_cog.py, tests/test_workflow_orchestrator_cog.py
- **Verification:** pytest --co collects all tests, no import errors
- **Committed in:** dbb9f58 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed test_bot_startup.py testing stale v1 behavior**
- **Found during:** Task 2 (Update CLI commands and remaining cogs)
- **Issue:** test_bot_startup.py patched vcompany.bot.client.AgentManager which no longer exists after plan 02 rewired on_ready() to use CompanyRoot.
- **Fix:** Rewrote test_bot_startup.py to test v2 CompanyRoot initialization instead.
- **Files modified:** tests/test_bot_startup.py
- **Verification:** All new tests pass
- **Committed in:** fb13fbc (Task 2 commit)

**3. [Rule 1 - Bug] Fixed test_plan_review_cog assertion for v2 flow**
- **Found during:** Task 2 (Update CLI commands and remaining cogs)
- **Issue:** test_handle_approval_updates_state expected plan_gate_status=="approved" but v2 _trigger_execution now runs (doesn't early-return on missing agent_manager) and resets state to "idle". This is correct v2 behavior.
- **Fix:** Updated test assertion to expect "idle" which matches the full approve->trigger->reset flow.
- **Files modified:** tests/test_plan_review_cog.py
- **Verification:** Test passes
- **Committed in:** fb13fbc (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 bugs from stale v1 tests, 1 blocking extraction)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
None beyond the deviations above.

## Known Stubs
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 08 is complete: CompanyRoot wired into bot startup (plan 01), commands/cogs adapted (plan 02), v1 modules removed (plan 03)
- The codebase is now fully v2: supervision tree, health monitoring, and container lifecycle replace all v1 equivalents
- 7 pre-existing test failures in test_pm_integration.py, test_pm_tier.py, and test_report_cmd.py remain unrelated to this migration

## Self-Check: PASSED

- All created files exist
- All deleted files confirmed absent
- Both task commits found in git log (dbb9f58, fb13fbc)

---
*Phase: 08-companyroot-wiring-and-migration*
*Completed: 2026-03-28*
