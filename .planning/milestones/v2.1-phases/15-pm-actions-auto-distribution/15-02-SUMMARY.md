---
phase: 15-pm-actions-auto-distribution
plan: 02
subsystem: bot
tags: [discord-bot, pm-callbacks, tmux, message-queue, strategist, supervisor]

requires:
  - phase: 15-pm-actions-auto-distribution
    plan: 01
    provides: FulltimeAgent with 6 PM action methods and 6 callback slots, ProjectSupervisor add_child_spec/remove_child
  - phase: 14-pm-review-gates
    provides: PlanReviewCog._send_tmux_command, VcoBot callback wiring patterns
  - phase: 13-pm-event-routing
    provides: VcoBot.on_ready PM wiring scaffold, factory closure pattern, pm_event_sink

provides:
  - VcoBot.on_ready wires all 6 Phase 15 PM action callbacks on FulltimeAgent
  - _on_assign_task: GsdAgent.set_assignment + tmux GSD command delivery
  - _on_trigger_integration_review: MessageQueue post to #alerts channel
  - _on_recruit_agent: ProjectSupervisor.add_child_spec + event callback wiring on new agent
  - _on_remove_agent: ProjectSupervisor.remove_child
  - _on_escalate_to_strategist: StrategistCog.handle_pm_escalation delegation
  - _on_send_intervention: MessageQueue post to agent channel with #alerts fallback
  - set_pm_event_sink moved to after all callback wiring (race condition fix)

affects: [16-agent-completeness, pm-integration-testing, stuck-detector-e2e]

tech-stack:
  added: []
  patterns:
    - "Phase 15 callbacks all wired before set_pm_event_sink() to prevent race condition (Research Pitfall 3)"
    - "_make_gsd_cb/_make_briefing_cb factory closures hoisted above Phase 15 block for reuse in _on_recruit_agent"
    - "_on_recruit_agent wires new agent callbacks same as initial wiring -- no duplication via factory reuse"

key-files:
  created: []
  modified:
    - src/vcompany/bot/client.py

key-decisions:
  - "set_pm_event_sink moved to after all Phase 15 callback wiring -- ensures no events arrive before handlers are set"
  - "_make_gsd_cb and _make_briefing_cb hoisted out of the for-loop block so _on_recruit_agent can reuse them"
  - "_on_assign_task iterates project_sup.children twice (set_assignment + gsd_command lookup) -- acceptable for small agent counts"
  - "_on_trigger_integration_review uses self.project_config.project for message context (always available inside project-only block)"

patterns-established:
  - "All Phase 15 PM action callbacks follow: define async closure -> assign to pm_container attribute"
  - "Recruitment callback wires same event callbacks as initial startup loop -- factory closures make this zero-duplication"

requirements-completed: [PMAC-01, PMAC-03, PMAC-04, PMAC-05, WORK-03]

duration: 3min
completed: 2026-03-28
---

# Phase 15 Plan 02: PM Action Callback Wiring Summary

**VcoBot.on_ready wires all 6 Phase 15 PM action callbacks connecting FulltimeAgent to Discord MessageQueue, tmux GSD commands, StrategistCog, and ProjectSupervisor, with set_pm_event_sink deferred to last to prevent race conditions**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-28T17:18:00Z
- **Completed:** 2026-03-28T17:21:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- All 6 Phase 15 PM action callbacks fully wired in VcoBot.on_ready
- WORK-03 path complete: task_completed -> _auto_assign_next -> _on_assign_task -> GsdAgent.set_assignment + tmux GSD command
- Stuck detector's `_on_send_intervention` now wired to post to agent's Discord channel with #alerts fallback
- _on_recruit_agent wires event callbacks on newly recruited agents using hoisted factory closures (zero duplication)
- Race condition fix: set_pm_event_sink moved to after all callback wiring

## Task Commits

1. **Task 1: Wire Phase 15 PM action callbacks in VcoBot.on_ready** - `8f82cb3` (feat)

## Files Created/Modified

- `src/vcompany/bot/client.py` - Added Phase 15 PM action callback wiring block (117 line net addition), hoisted factory closures, moved set_pm_event_sink to after all wiring

## Decisions Made

- `set_pm_event_sink` moved to the very end of all callback wiring to prevent race condition where supervisor emits health_change events before _on_send_intervention is wired
- `_make_gsd_cb` and `_make_briefing_cb` factory closures hoisted from inside the for-loop to be available for `_on_recruit_agent` reuse in the Phase 15 block
- `_on_assign_task` iterates `project_sup.children` twice (once for set_assignment, once for gsd_command lookup) -- intentional; agent count is small and the loop is O(n) bounded

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Refactor] Hoisted factory closures out of for-loop**
- **Found during:** Task 1
- **Issue:** `_make_gsd_cb` was defined inside the `for child in project_sup.children.values():` loop body -- defined-but-not-called repeatedly and not accessible outside loop scope for Phase 15 `_on_recruit_agent` reuse
- **Fix:** Hoisted `_make_gsd_cb` and `_make_briefing_cb` to top of the `if pm_container is not None:` block, then simplified the loop to just call them
- **Files modified:** src/vcompany/bot/client.py
- **Verification:** python3 -c "import ast; ast.parse(...)" passes, VcoBot importable
- **Committed in:** 8f82cb3 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (code quality / correctness)
**Impact on plan:** Required for _on_recruit_agent to reuse factory closures. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All Phase 15 PM action callbacks are wired; FulltimeAgent's PM action surface is now fully connected to Discord, tmux, Strategist, and supervisor
- Stuck detector will fire _on_send_intervention which posts to agent channels -- ready for end-to-end testing
- Phase 16 (agent completeness) can proceed -- the integration loop is complete for the PM subsystem

---
*Phase: 15-pm-actions-auto-distribution*
*Completed: 2026-03-28*
