---
phase: 09-agent-type-routing-and-pm-event-dispatch
plan: 02
subsystem: bot
tags: [discord, event-dispatch, pm, backlog, dead-code-removal]

requires:
  - phase: 09-01
    provides: AgentConfig type field and factory routing
  - phase: 08
    provides: WorkflowOrchestratorCog, CompanyRoot wiring, /new-project command
  - phase: 07
    provides: BacklogQueue, ProjectStateManager, FulltimeAgent.post_event
provides:
  - GsdAgent completion event routing to PM via WorkflowOrchestratorCog
  - PM backlog wiring in /new-project (parity with on_ready)
  - Dead code removal (setup_notifications, build_status_embed)
  - Event dispatch test coverage (3 scenarios)
affects: [pm-event-handling, agent-lifecycle, bot-cogs]

tech-stack:
  added: []
  patterns:
    - "Duck-type check hasattr(container, 'make_completion_event') for GsdAgent detection"
    - "Local imports inside command body to avoid circular import at cog load time"

key-files:
  created:
    - tests/test_event_dispatch.py
  modified:
    - src/vcompany/bot/cogs/workflow_orchestrator_cog.py
    - src/vcompany/bot/cogs/commands.py
    - src/vcompany/bot/cogs/health.py
    - src/vcompany/bot/embeds.py
    - tests/test_pm_integration.py
    - tests/test_workflow_orchestrator_cog.py

key-decisions:
  - "Use getattr for _pm_container access to safely handle missing attribute"
  - "Local imports in /new-project to match on_ready pattern and avoid circular imports"

patterns-established:
  - "Event dispatch: GsdAgent -> WorkflowOrchestratorCog -> PM via post_event"
  - "PM wiring: BacklogQueue + ProjectStateManager injected after add_project()"

requirements-completed: [AUTO-05]

duration: 8min
completed: 2026-03-28
---

# Phase 09 Plan 02: PM Event Dispatch and Dead Code Removal Summary

**GsdAgent completion events routed to PM via WorkflowOrchestratorCog, /new-project PM backlog wired, dead code purged**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-28T04:39:18Z
- **Completed:** 2026-03-28T04:47:32Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- _handle_phase_complete now dispatches task_completed events to PM container (AUTO-05)
- /new-project wires BacklogQueue and ProjectStateManager to FulltimeAgent (parity with on_ready)
- Deleted HealthCog.setup_notifications() no-op and build_status_embed deprecated function
- 3 event dispatch tests covering PM present, PM absent, and no-assignment scenarios
- Fixed pre-existing test_pm_integration failures (stale _write_answer_file_sync patches)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire PM event dispatch and /new-project backlog** - `399114d` (feat)
2. **Task 2: Event dispatch tests** - `7c1b48b` (test)
3. **Task 2: Remove dead code** - `5583c1d` (refactor)

_Note: Task 2 was TDD — test commit then refactor commit._

## Files Created/Modified
- `src/vcompany/bot/cogs/workflow_orchestrator_cog.py` - Added PM event routing in _handle_phase_complete
- `src/vcompany/bot/cogs/commands.py` - Added PM backlog wiring after add_project() in /new-project
- `src/vcompany/bot/cogs/health.py` - Removed setup_notifications no-op method
- `src/vcompany/bot/embeds.py` - Removed deprecated build_status_embed function
- `tests/test_event_dispatch.py` - New: 3 tests for PM event dispatch scenarios
- `tests/test_pm_integration.py` - Fixed stale patches and assertion text
- `tests/test_workflow_orchestrator_cog.py` - Added _pm_container=None to mock_bot fixture

## Decisions Made
- Used getattr(self.bot, "_pm_container", None) for safe access in _handle_phase_complete
- Used hasattr(container, "make_completion_event") for duck-type GsdAgent check (not isinstance) because only GsdAgent has this method
- Local imports in /new-project command body to avoid circular imports at cog load time (matches on_ready pattern)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pre-existing test_pm_integration test failures**
- **Found during:** Task 1
- **Issue:** Tests patched non-existent _write_answer_file_sync (removed in Phase 9 refactor), used stale assertion text ("PM auto-answered" vs "[PM]"), and mock_bot.user.id didn't match message.author.id
- **Fix:** Removed stale patches, updated assertion text to match current implementation, set author.id=42 matching bot.user.id=42
- **Files modified:** tests/test_pm_integration.py
- **Verification:** All 9 PM integration tests pass
- **Committed in:** 399114d (Task 1 commit)

**2. [Rule 1 - Bug] Fixed mock_bot fixture missing _pm_container**
- **Found during:** Task 1
- **Issue:** MagicMock auto-creates attributes, so getattr(bot, "_pm_container", None) returned a MagicMock instead of None, causing "can't await MagicMock" when calling container.get_assignment()
- **Fix:** Explicitly set bot._pm_container = None in mock_bot fixture
- **Files modified:** tests/test_workflow_orchestrator_cog.py
- **Verification:** All 24 workflow orchestrator cog tests pass
- **Committed in:** 399114d (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs in test fixtures)
**Impact on plan:** Both fixes were necessary to get test suite green. No scope creep.

## Issues Encountered
- 2 pre-existing test failures (test_pm_tier, test_report_cmd) are unrelated to this plan's changes -- they fail on main as well. Logged to deferred items.

## Known Stubs
None -- all wiring is functional.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- AUTO-05 is complete: GsdAgent completion events flow to PM
- /new-project has full parity with on_ready for PM wiring
- Dead code from v1-to-v2 migration removed
- Test suite green (927 pass, 2 pre-existing failures in unrelated tests)

---
*Phase: 09-agent-type-routing-and-pm-event-dispatch*
*Completed: 2026-03-28*
