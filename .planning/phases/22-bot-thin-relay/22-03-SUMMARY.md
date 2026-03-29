---
phase: 22-bot-thin-relay
plan: 03
subsystem: bot-cogs
tags: [import-boundary, runtime-api, bot-relay, refactoring, cog-rewrite, pure-io-adapter]

requires:
  - phase: 22-bot-thin-relay
    plan: 01
    provides: RuntimeAPI gateway methods for bot cog delegation
  - phase: 22-bot-thin-relay
    plan: 02
    provides: Three heaviest cog files rewritten as pure RuntimeAPI delegates
provides:
  - All 9 cog files + client.py are pure I/O adapters with zero prohibited imports
  - Import boundary tests pass strict (no xfail markers)
  - RuntimeAPI methods for PM escalation, decision logging, workflow-master conversation
  - alerts.py daemon event formatting verified (BOT-03)
affects: [phase-23-state-persistence, bot-layer-maintenance]

tech-stack:
  added: []
  patterns: [cog-as-pure-io-adapter, runtime-api-for-all-business-logic]

key-files:
  created: []
  modified:
    - src/vcompany/bot/cogs/strategist.py
    - src/vcompany/bot/cogs/health.py
    - src/vcompany/bot/cogs/task_relay.py
    - src/vcompany/bot/cogs/workflow_master.py
    - src/vcompany/bot/cogs/question_handler.py
    - src/vcompany/bot/client.py
    - src/vcompany/daemon/runtime_api.py
    - tests/test_import_boundary.py

key-decisions:
  - "StrategistCog fully decoupled from StrategistConversation and CompanyAgent -- all routing through RuntimeAPI"
  - "HealthCog._notify_state_change accepts dict instead of HealthReport -- no container.health import needed"
  - "WorkflowMasterCog delegates conversation to RuntimeAPI.initialize_workflow_master and relay_workflow_master_message"
  - "QuestionHandlerCog._pm typed as object instead of PMTier -- avoids strategist import"
  - "client.py ProjectConfig moved to TYPE_CHECKING, _detect_active_project delegates to RuntimeAPI"

patterns-established:
  - "_get_runtime_api(bot) helper function pattern used by all cogs for daemon access"
  - "All cog files are pure Discord I/O adapters -- zero prohibited imports at any level"

requirements-completed: [BOT-02, BOT-03, BOT-04, BOT-05]

duration: 6min
completed: 2026-03-29
---

# Phase 22 Plan 03: Clean Remaining Cogs + Import Boundary Verification Summary

**5 remaining cog files (strategist, health, task_relay, workflow_master, question_handler) rewritten as pure I/O adapters with zero prohibited imports; alerts.py BOT-03 verified; all xfail markers removed from import boundary tests**

## Performance

- **Duration:** 6 min (386s)
- **Started:** 2026-03-29T12:47:45Z
- **Completed:** 2026-03-29T12:54:11Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Rewrote strategist.py: removed StrategistConversation, DecisionLogger, CompanyAgent; all routing through RuntimeAPI
- Rewrote health.py: removed MessagePriority/QueuedMessage/company_root access; uses RuntimeAPI.health_tree()
- Rewrote task_relay.py: removed TmuxManager/_find_container/container._pane_id; uses RuntimeAPI.relay_channel_message()
- Rewrote workflow_master.py: removed StrategistConversation and workflow_master_persona imports; delegates to RuntimeAPI
- Rewrote question_handler.py: removed DecisionLogEntry import; uses RuntimeAPI.log_decision()
- Fixed client.py: ProjectConfig moved to TYPE_CHECKING, _detect_active_project delegates to RuntimeAPI
- Verified alerts.py already clean with all BOT-03 event formatters (agent_dead, agent_stuck, circuit_open, etc.)
- Removed all 3 xfail markers from import boundary tests -- all 4 tests pass strict

## Task Commits

Each task was committed atomically:

1. **Task 1: Clean 5 cog files + client.py + add RuntimeAPI methods** - `21f7f87` (feat)
2. **Task 2: Remove xfail markers from import boundary tests** - `fdc350a` (test)

## Files Created/Modified

- `src/vcompany/bot/cogs/strategist.py` - Pure I/O adapter: removed StrategistConversation, DecisionLogger, CompanyAgent
- `src/vcompany/bot/cogs/health.py` - Pure I/O adapter: removed resilience imports, uses RuntimeAPI.health_tree()
- `src/vcompany/bot/cogs/task_relay.py` - Pure I/O adapter: removed TmuxManager, uses RuntimeAPI.relay_channel_message()
- `src/vcompany/bot/cogs/workflow_master.py` - Pure I/O adapter: removed StrategistConversation, delegates to RuntimeAPI
- `src/vcompany/bot/cogs/question_handler.py` - Pure I/O adapter: removed DecisionLogEntry, uses RuntimeAPI.log_decision()
- `src/vcompany/bot/client.py` - ProjectConfig to TYPE_CHECKING, _detect_active_project delegates to RuntimeAPI
- `src/vcompany/daemon/runtime_api.py` - Added handle_pm_escalation, log_decision, initialize_workflow_master, relay_workflow_master_message, detect_active_project
- `tests/test_import_boundary.py` - Removed all 3 xfail markers

## Decisions Made

- StrategistCog: removed _company_agent attribute, set_company_agent(), _send_to_channel(), decision_logger property -- all backward compat paths eliminated
- HealthCog._notify_state_change: changed from accepting HealthReport to plain dict -- avoids container.health import
- QuestionHandlerCog._pm: typed as `object` instead of `PMTier` to avoid TYPE_CHECKING import from strategist layer
- client.py: _detect_active_project now delegates entirely to RuntimeAPI.detect_active_project() -- eliminates load_config import

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed client.py prohibited imports**
- **Found during:** Task 1
- **Issue:** client.py had module-level `from vcompany.models.config import ProjectConfig` and function-level `from vcompany.models.config import load_config` -- both prohibited by import boundary tests
- **Fix:** Moved ProjectConfig to TYPE_CHECKING guard; refactored _detect_active_project to delegate to RuntimeAPI.detect_active_project()
- **Files modified:** src/vcompany/bot/client.py, src/vcompany/daemon/runtime_api.py
- **Commit:** 21f7f87

**2. [Rule 3 - Blocking] Added 5 new RuntimeAPI methods for cog delegation**
- **Found during:** Task 1
- **Issue:** Cogs needed daemon-layer methods for PM escalation, decision logging, workflow-master conversation, and project detection
- **Fix:** Added handle_pm_escalation, log_decision, initialize_workflow_master, relay_workflow_master_message, detect_active_project to RuntimeAPI
- **Files modified:** src/vcompany/daemon/runtime_api.py
- **Commit:** 21f7f87

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both auto-fixes necessary for correctness. No scope creep.

## Issues Encountered

- Full test suite cannot run in this environment due to missing packages (discord.py, aiosqlite, pytest_asyncio not installed). Import boundary tests (the scope of this plan) all pass. Pre-existing environment issue, not caused by this plan.

## Known Stubs

None -- all functionality is wired to RuntimeAPI methods.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 10 bot files (9 cogs + client.py) have zero prohibited imports at module and function level
- Import boundary tests pass strict with genuine PASSED (no xfail)
- Bot layer is a complete thin relay -- ready for Phase 23 (state persistence)
- RuntimeAPI is the sole gateway for all bot->daemon communication

---
*Phase: 22-bot-thin-relay*
*Completed: 2026-03-29*
