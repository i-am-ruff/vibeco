---
phase: 24-discord-visibility
plan: 04
subsystem: daemon
tags: [runtime-api, supervisor, discord-routing, cleanup]

# Dependency graph
requires:
  - phase: 24-01
    provides: MentionRouterCog with register_agent/unregister_agent
  - phase: 24-02
    provides: BacklogQueue on_mutation callback parameter
  - phase: 24-03
    provides: Agent receive_discord_message() replacing post_event()
provides:
  - Clean RuntimeAPI with only infrastructure operations (no agent-routing methods)
  - Supervisor without pm_event_sink (health visible through Discord)
  - PlanReviewCog posting decisions as Discord messages
  - Agent handles registered with MentionRouterCog in new_project()
  - BacklogQueue wired with on_mutation callback to #backlog channel
affects: [strategist-cog, workflow-orchestrator-cog, question-handler-cog]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "MentionRouterCog registration in new_project() for handle-based routing"
    - "BacklogQueue on_mutation callback wired to Discord channel via CommunicationPort"

key-files:
  created: []
  modified:
    - src/vcompany/daemon/runtime_api.py
    - src/vcompany/supervisor/supervisor.py
    - src/vcompany/bot/cogs/plan_review.py

key-decisions:
  - "Strategist container accessed via company_root._company_agents instead of stored ref"
  - "PM handle registered as PM{project_name} for project-scoped routing"
  - "Backlog notification uses CommunicationPort (platform-agnostic) not discord.py"

patterns-established:
  - "Agent registration: new_project() registers handles, remove_project() unregisters them"
  - "No internal event sinks: all agent communication flows through Discord channels"

requirements-completed: [VIS-01, VIS-03, VIS-04, VIS-05, VIS-06]

# Metrics
duration: 6min
completed: 2026-03-29
---

# Phase 24 Plan 04: RuntimeAPI Cleanup and Discord Routing Wiring Summary

**Removed 16 agent-routing methods from RuntimeAPI, eliminated pm_event_sink from Supervisor, wired MentionRouterCog registration and BacklogQueue on_mutation in new_project()**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-29T16:25:21Z
- **Completed:** 2026-03-29T16:31:25Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Removed all 16 internal agent-routing methods from RuntimeAPI (376 lines deleted) per D-10/D-11/D-14
- Eliminated pm_event_sink from Supervisor -- health changes visible through Discord health tree
- Rewired new_project() to register agent handles with MentionRouterCog and wire BacklogQueue on_mutation to #backlog channel
- PlanReviewCog now posts review decisions as plain text Discord messages instead of internal log_plan_decision

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove agent-routing methods from RuntimeAPI and rewire new_project()** - `fdc7d60` (feat)
2. **Task 2: Remove pm_event_sink from Supervisor and update PlanReviewCog** - `ccbd68b` (feat)

## Files Created/Modified
- `src/vcompany/daemon/runtime_api.py` - Removed 16 routing methods, added set_mention_router(), rewrote new_project() with MentionRouterCog registration and BacklogQueue on_mutation
- `src/vcompany/supervisor/supervisor.py` - Removed pm_event_sink parameter, set_pm_event_sink(), and PMRT-01/04 event posting
- `src/vcompany/bot/cogs/plan_review.py` - Replaced log_plan_decision() call with Discord message post

## Decisions Made
- Removed _strategist_container stored reference; log_decision() now finds strategist via company_root._company_agents.get("strategist") -- avoids stale ref
- PM registered with handle "PM{project_name}" for project-scoped routing (e.g., "PMmyproject")
- BacklogQueue on_mutation wired through CommunicationPort.send_message (platform-agnostic, not discord.py direct)
- Strategist handle registration happens in new_project() after conversation initialization

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed log_decision() referencing removed _strategist_container**
- **Found during:** Task 1 (RuntimeAPI cleanup)
- **Issue:** log_decision() method used self._strategist_container which was being removed
- **Fix:** Changed to find strategist via self._root._company_agents.get("strategist")
- **Files modified:** src/vcompany/daemon/runtime_api.py
- **Verification:** Import succeeds, no references to _strategist_container remain
- **Committed in:** fdc7d60 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential fix -- log_decision() would have crashed without it. No scope creep.

## Issues Encountered
- External callers in strategist.py, workflow_orchestrator_cog.py, and question_handler.py reference removed RuntimeAPI methods. These are outside Plan 04's scope and documented in deferred-items.md. They are dead code paths that were superseded by Discord-based routing in Plans 01-03.

## Known Stubs
None -- all wiring is functional with real callbacks.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 24 is complete: all inter-agent communication now flows through Discord
- External cog callers (strategist.py, workflow_orchestrator_cog.py) reference removed methods and need cleanup in a follow-up
- Ready for Phase 25+ container runtime abstraction work

---
*Phase: 24-discord-visibility*
*Completed: 2026-03-29*
