---
phase: 15-pm-actions-auto-distribution
plan: 01
subsystem: agent
tags: [fulltime-agent, project-supervisor, pm-actions, stuck-detector, callbacks, backlog]

requires:
  - phase: 14-pm-review-gates
    provides: FulltimeAgent with _on_gsd_review callback slot and event routing foundation
  - phase: 13-pm-event-routing
    provides: PM event sink wiring and _handle_event dispatch skeleton

provides:
  - FulltimeAgent with 6 PM action methods and 6 callback slots
  - Stuck detector background loop with configurable threshold and suppression
  - ProjectSupervisor public add_child_spec/remove_child API for PM-initiated agent lifecycle
  - _handle_event routing: task_completed -> _auto_assign_next, escalation -> escalate_to_strategist, gsd_transition updates stuck timestamps

affects: [16-agent-completeness, vcobot-wiring, discord-bot-integration]

tech-stack:
  added: []
  patterns:
    - "Callback-slot pattern extended: all PM actions use optional Callable slots wired post-construction"
    - "Stuck detector: background asyncio.Task with suppression set to avoid repeated alerts per agent"
    - "Public supervisor API: thin wrappers over parent Supervisor internals for PM-driven agent lifecycle"

key-files:
  created: []
  modified:
    - src/vcompany/agent/fulltime_agent.py
    - src/vcompany/supervisor/project_supervisor.py

key-decisions:
  - "Stuck detector uses asyncio.get_event_loop().time() for monotonic timestamps, not wall clock"
  - "Stuck detection suppression set cleared on gsd_transition so agent is re-checked after each state change"
  - "escalate_to_strategist called directly from _handle_event escalation branch (replaces log-only behavior from Phase 13)"
  - "ChildSpec imported under TYPE_CHECKING only -- not needed at runtime in agent layer"
  - "stop() override added to FulltimeAgent to cleanly cancel stuck detector task before delegating to parent"

patterns-established:
  - "PM action methods: async, log intent first, check callback not None, warn if missing"
  - "Event handler updates: side effects (timestamps, auto-assign) added to existing branches without restructuring"

requirements-completed: [PMAC-01, PMAC-02, PMAC-03, PMAC-04, PMAC-05, WORK-03]

duration: 12min
completed: 2026-03-28
---

# Phase 15 Plan 01: PM Actions and Auto-Distribution Summary

**FulltimeAgent gains 6 PM action methods (auto-assign, integration review, backlog inject, recruit/remove agent, Strategist escalation) and a stuck-agent background detector; ProjectSupervisor gains public add_child_spec/remove_child lifecycle helpers**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-28T17:05:51Z
- **Completed:** 2026-03-28T17:17:02Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- FulltimeAgent transformed from passive event logger to proactive PM: all 6 action methods and 6 callback slots wired, event dispatch updated
- Stuck agent detector runs as background asyncio.Task, fires intervention callback with suppression to avoid alert flooding
- ProjectSupervisor now exposes public `add_child_spec` and `remove_child` for PM-initiated agent recruitment and removal

## Task Commits

1. **Task 1: Add PM action methods, callback slots, and stuck detector to FulltimeAgent** - `b9ff1be` (feat)
2. **Task 2: Add public agent lifecycle helpers to ProjectSupervisor** - `d57fd27` (feat)

## Files Created/Modified

- `src/vcompany/agent/fulltime_agent.py` - Added 6 callback slots, 6 PM action methods, stuck detector loop, stop() override, updated _handle_event routing
- `src/vcompany/supervisor/project_supervisor.py` - Added add_child_spec() and remove_child() public methods, added module-level logger

## Decisions Made

- Stuck detector uses `asyncio.get_event_loop().time()` for monotonic timestamps -- immune to wall clock changes
- Suppression set (`_stuck_detected_agents`) is cleared on each `gsd_transition` event so the agent gets a fresh window after every state change
- `escalate_to_strategist` replaces the log-only escalation handling from Phase 13 -- now fires the callback if wired
- `ChildSpec` imported under `TYPE_CHECKING` only since it only appears in type hints for `_on_recruit_agent`
- `stop()` override cleanly cancels the stuck detector task before calling `super().stop()` to avoid dangling asyncio tasks

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- FulltimeAgent PM action surface is complete; VcoBot wiring needed to connect callbacks to Discord handlers
- ProjectSupervisor lifecycle helpers ready for PM-initiated recruitment flows
- Stuck detector will fire `_on_send_intervention` when wired in VcoBot (Phase 16 / bot wiring phase)

---
*Phase: 15-pm-actions-auto-distribution*
*Completed: 2026-03-28*
