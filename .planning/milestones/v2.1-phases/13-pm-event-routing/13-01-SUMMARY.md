---
phase: 13-pm-event-routing
plan: 01
subsystem: agent-orchestration
tags: [pm-events, supervisor, callback-hooks, event-routing, fulltime-agent]

# Dependency graph
requires:
  - phase: 12-work-initiation
    provides: GsdAgent and ContinuousAgent operational with lifecycle FSMs

provides:
  - Supervisor pm_event_sink parameter and set_pm_event_sink() method
  - Supervisor._make_state_change_callback posts health_change + escalation events to PM sink
  - GsdAgent._on_phase_transition callback wired in advance_phase()
  - ContinuousAgent._on_briefing callback wired in advance_cycle("report")
  - FulltimeAgent._handle_event handles health_change, gsd_transition, briefing, escalation
  - VcoBot.on_ready wires all PM event routing callbacks after PM container identified

affects: [14-pm-review-gates, 15-pm-outbound-actions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PM event sink: Supervisor accepts Callable[[dict], Awaitable[None]] injectable post-construction via set_pm_event_sink()"
    - "Callback hook pattern: agent stores _on_phase_transition/_on_briefing = None; wired externally by VcoBot"
    - "Factory closures: _make_gsd_cb/_make_briefing_cb prevent Python closure-over-loop-variable bug"
    - "try/except RuntimeError around asyncio.get_running_loop() for all event dispatch"

key-files:
  created: []
  modified:
    - src/vcompany/supervisor/supervisor.py
    - src/vcompany/agent/gsd_agent.py
    - src/vcompany/agent/continuous_agent.py
    - src/vcompany/agent/fulltime_agent.py
    - src/vcompany/bot/client.py

key-decisions:
  - "pm_event_sink uses set_pm_event_sink() post-construction method because PM container identity is not known at Supervisor creation time"
  - "health_change events cover errored/running/blocked/stopped (not stopping) -- stopping is transient, PM doesn't need it"
  - "escalation events are additional (not replacing) health_change for blocked state -- PM gets both signals"
  - "advance_cycle briefing_content is keyword-only arg (after *) to avoid positional arg confusion in callers"
  - "FulltimeAgent handlers are log-only in Phase 13; real PM action logic added in Phases 14-15"

patterns-established:
  - "Event sink injection: injectable callable stored as _pm_event_sink, None by default, safe to call in sync callback context via loop.create_task()"
  - "Agent callback hooks: set to None in __init__, wired by orchestrator (VcoBot) after supervision tree starts"

requirements-completed: [PMRT-01, PMRT-02, PMRT-03, PMRT-04]

# Metrics
duration: 9min
completed: 2026-03-28
---

# Phase 13 Plan 01: PM Event Routing -- Source Hooks Summary

**Full PM event pipeline wired: Supervisor posts health_change/escalation, GsdAgent fires phase transitions, ContinuousAgent fires briefings, FulltimeAgent handles all four new event types, VcoBot connects them all on startup**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-03-28T16:21:13Z
- **Completed:** 2026-03-28T16:29:22Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Supervisor now accepts a PM event sink callable and posts `health_change` events for all significant state transitions (errored, running, blocked, stopped) plus `escalation` events specifically when an agent enters the blocked state
- GsdAgent and ContinuousAgent have optional callback hooks (`_on_phase_transition`, `_on_briefing`) that are None by default and fired from their respective advance methods after checkpointing
- FulltimeAgent._handle_event no longer warns on the four new event types -- all four route to info-level logging ready for Phase 14 action logic
- VcoBot.on_ready wires the complete event pipeline in a single block: defines `pm_event_sink` closure, calls `project_sup.set_pm_event_sink()`, then iterates children to assign agent-specific callbacks using factory functions

## Task Commits

1. **Task 1: Add PM event sink to Supervisor and callback hooks to GsdAgent + ContinuousAgent** - `a9d500b` (feat)
2. **Task 2: Add PM event handlers in FulltimeAgent and wire callbacks in VcoBot.on_ready()** - `3ba99d6` (feat)

## Files Created/Modified

- `src/vcompany/supervisor/supervisor.py` - Added `pm_event_sink` constructor param, `set_pm_event_sink()` method, and event posting logic in `_make_state_change_callback`
- `src/vcompany/agent/gsd_agent.py` - Added `Awaitable` import, `_on_phase_transition` attribute, `from_phase` capture + callback fire in `advance_phase`
- `src/vcompany/agent/continuous_agent.py` - Added `Awaitable` import, `_on_briefing` attribute, `briefing_content` keyword-only param + callback fire in `advance_cycle`
- `src/vcompany/agent/fulltime_agent.py` - Extended `_handle_event` with elif branches for health_change, gsd_transition, briefing, escalation (info logging)
- `src/vcompany/bot/client.py` - Added imports for GsdAgent, ContinuousAgent, Any, Callable; added PM event routing wiring block in `on_ready`

## Decisions Made

- `set_pm_event_sink()` as post-construction setter: PM container identity is not known until `project_sup.children` is inspected after `add_project()`, so the sink cannot be passed to the Supervisor constructor. The setter pattern solves this cleanly.
- `health_change` skips the "stopping" state: "stopping" is a transient pass-through; PM only needs the terminal states (errored, running, blocked, stopped).
- Dual events for blocked: PM receives both a `health_change{state=blocked}` and a separate `escalation` event -- they carry different information (health context vs. blocked reason) and Phase 14 may handle them with different urgency.
- Keyword-only `briefing_content`: placed after `*` in `advance_cycle` signature to make it impossible to pass positionally and confuse with `phase`.
- Factory closures (`_make_gsd_cb`, `_make_briefing_cb`): prevents the classic Python for-loop closure bug where all iterations would share the same binding.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

One pre-existing test failure unrelated to these changes: `tests/test_pm_tier.py::test_low_confidence_escalates_to_strategist` was already failing on the pre-change codebase due to a subprocess communicate bug in `pm.py`. Confirmed pre-existing by running against the stashed state.

## Next Phase Readiness

- Phase 13 Plan 02 (VcoBot.on_ready wiring) is already complete as part of this plan -- the plan description says "Wiring to VcoBot.on_ready() happens in Plan 02" but the research and plan document explicitly include it in Plan 01 Task 2. All wiring is done.
- Phase 14 (PM review gates) can now receive health_change, gsd_transition, briefing, and escalation events from the full agent fleet
- FulltimeAgent._handle_event is ready to have real action logic added to the four new elif branches

## Self-Check: PASSED

- All 5 modified files exist on disk
- Commit a9d500b (Task 1) verified in git log
- Commit 3ba99d6 (Task 2) verified in git log
- SUMMARY.md created at expected path
- 43 targeted tests pass (test_supervisor, test_gsd_agent, test_continuous_agent, test_fulltime_agent)
- 717 of 718 tests pass; 1 pre-existing failure (test_pm_tier.py::test_low_confidence_escalates_to_strategist) confirmed pre-existing

---
*Phase: 13-pm-event-routing*
*Completed: 2026-03-28*
