---
phase: 28-agent-transport-separation
plan: 04
subsystem: agent
tags: [refactor, handler-composition, thin-wrappers, dead-code-removal]

# Dependency graph
requires:
  - phase: 28-02
    provides: Handler types and registry (SessionHandler, TransientHandler, ConversationHandler)
  - phase: 28-03
    provides: Handler implementations (GsdSessionHandler, PMTransientHandler, StrategistConversationHandler)
provides:
  - Thinned agent subclasses with no duplicated _send_discord/state/inner_state/receive_discord_message
  - Correct handler lifecycle hook ordering in base container (on_start before transport launch)
  - _channel_id wired at agent registration time in MentionRouterCog (D-05)
  - Dead _tmux/_launch_tmux_session code eliminated from GsdAgent and TaskAgent
affects: [agent-types, container, runtime-api, supervisor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin subclass pattern: lifecycle FSM override + domain-specific methods only"
    - "Handler lifecycle hooks called between memory.open() and transport launch"
    - "D-05 _channel_id set at registration time, cleared at unregistration"

key-files:
  created: []
  modified:
    - src/vcompany/container/container.py
    - src/vcompany/bot/cogs/mention_router.py
    - src/vcompany/agent/gsd_agent.py
    - src/vcompany/agent/task_agent.py
    - src/vcompany/agent/company_agent.py
    - src/vcompany/agent/fulltime_agent.py
    - src/vcompany/agent/continuous_agent.py

key-decisions:
  - "GsdAgent keeps checkpoint/phase methods locally (advance_phase calls _checkpoint_phase) rather than delegating to handler"
  - "Handler on_start runs between memory.open() and transport launch for correct GSD checkpoint-restore ordering"
  - "TaskAgent inner_state override kept (reads .phase marker file) while all other state/inner_state overrides removed"

patterns-established:
  - "Thin subclass: lifecycle FSM override + domain methods for hasattr compat, no message handling"
  - "Base container owns _send_discord, state, inner_state, receive_discord_message"

requirements-completed: [HSEP-06, HSEP-07]

# Metrics
duration: 5min
completed: 2026-03-31
---

# Phase 28 Plan 04: Agent Subclass Thinning Summary

**Thinned 5 agent subclasses to lifecycle FSM + domain methods, removed 339 lines of duplicated code, fixed handler hook ordering, wired _channel_id at registration**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-31T04:48:15Z
- **Completed:** 2026-03-31T04:53:38Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- All 5 agent subclasses thinned: no duplicated _send_discord, state, inner_state, or receive_discord_message
- Base container start() now calls handler.on_start() before transport launch (correct ordering for GSD checkpoint restore)
- MentionRouterCog.register_agent() sets container._channel_id at registration time (D-05 fully wired)
- Dead _tmux/_launch_tmux_session code eliminated from GsdAgent and TaskAgent (HSEP-07)
- Net reduction of ~320 lines of duplicated/dead code across agent subclasses

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix container.start() handler hook ordering, wire _channel_id, thin GsdAgent + TaskAgent** - `977c42c` (feat)
2. **Task 2: Thin CompanyAgent, FulltimeAgent, and ContinuousAgent** - `c1ebb2c` (feat)

## Files Created/Modified
- `src/vcompany/container/container.py` - Fixed handler hook ordering: on_start before transport launch
- `src/vcompany/bot/cogs/mention_router.py` - register_agent sets container._channel_id, unregister clears it
- `src/vcompany/agent/gsd_agent.py` - Removed _send_discord, state, inner_state, receive_discord_message; fixed start() to use transport
- `src/vcompany/agent/task_agent.py` - Removed dead _tmux code from start(), delegates to super()
- `src/vcompany/agent/company_agent.py` - Removed _send_discord, state, inner_state, receive_discord_message, trivial lifecycle overrides
- `src/vcompany/agent/fulltime_agent.py` - Removed _send_discord, state, inner_state, receive_discord_message, _run_stuck_detector, _auto_assign_next, start/stop overrides, _extract_field
- `src/vcompany/agent/continuous_agent.py` - Removed state, inner_state property overrides

## Decisions Made
- GsdAgent retains its own checkpoint/phase methods (advance_phase, _checkpoint_phase, _restore_from_checkpoint) since advance_phase directly calls _checkpoint_phase. Handler's on_start is a simpler hook.
- TaskAgent.inner_state override kept because it reads from a .phase marker file (different mechanism than OrderedSet-based compound states)
- Handler on_start placed between memory.open() and _launch_agent() in base container for correct GSD checkpoint-restore ordering

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all code paths are fully wired.

## Next Phase Readiness
- Phase 28 (agent-transport-separation) is now complete
- All agent subclasses are thin wrappers: lifecycle FSM + domain methods
- Handler composition is fully operational: handlers injected via registry, lifecycle hooks in correct order
- _channel_id wiring enables outbound Discord messages from handlers

---
*Phase: 28-agent-transport-separation*
*Completed: 2026-03-31*
