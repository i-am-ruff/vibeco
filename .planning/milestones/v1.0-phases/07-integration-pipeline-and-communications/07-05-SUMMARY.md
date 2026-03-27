---
phase: 07-integration-pipeline-and-communications
plan: 05
subsystem: communication
tags: [discord, standup, asyncio, threads, blocking-interlock, tmux]

# Dependency graph
requires:
  - phase: 07-03
    provides: "Checkin ritual and gather_checkin_data function"
  - phase: 07-04
    provides: "Integration interlock and bot command wiring patterns"
provides:
  - "StandupSession with per-agent blocking via asyncio.Future"
  - "ReleaseView with no-timeout Release button per D-11"
  - "build_standup_embed for per-agent standup thread embeds"
  - "Full !standup command with thread creation and message routing"
  - "on_message listener for routing owner thread messages to agent tmux panes"
affects: [07-06, bot-commands, agent-communication]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "asyncio.Future for blocking interlock (block_agent/release_agent)"
    - "discord.Thread per-agent standup with ReleaseView button"
    - "on_message Cog listener for thread message routing"
    - "/gsd:quick routing for owner-to-agent communication via tmux"

key-files:
  created:
    - src/vcompany/communication/standup.py
    - src/vcompany/bot/views/standup_release.py
    - tests/test_standup.py
  modified:
    - src/vcompany/bot/embeds.py
    - src/vcompany/bot/cogs/commands.py

key-decisions:
  - "asyncio.Future for per-agent blocking -- lightweight, no timeout per D-11"
  - "on_message Cog listener pattern for thread message routing (not separate Cog)"
  - "route_message_to_agent sends /gsd:quick so agent processes owner feedback as task"

patterns-established:
  - "StandupSession stored on bot instance (bot._standup_session) for cross-event access"
  - "ReleaseView with set_release_callback for decoupled button->session interaction"

requirements-completed: [COMM-03, COMM-04, COMM-05, COMM-06]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 07 Plan 05: Standup Ritual Summary

**Standup blocking interlock with per-agent Discord threads, asyncio.Future-based release, and /gsd:quick message routing to agent tmux panes**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T22:24:14Z
- **Completed:** 2026-03-25T22:27:42Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- StandupSession blocks agents via asyncio.Future until owner explicitly releases (no timeout per D-11)
- ReleaseView with Release button that disables after click and calls release callback
- Full !standup command creates per-agent threads in #standup with status embeds
- on_message listener routes owner thread messages to agent tmux panes via /gsd:quick per COMM-05
- 13 tests covering blocking, release, routing, embed creation, and view behavior

## Task Commits

Each task was committed atomically:

1. **Task 1: StandupSession + ReleaseView + standup embed (RED)** - `aef9964` (test)
2. **Task 1: StandupSession + ReleaseView + standup embed (GREEN)** - `4f9603b` (feat)
3. **Task 2: Full !standup command with thread creation and message listening** - `abd57a6` (feat)

_Note: Task 1 used TDD with RED/GREEN commits_

## Files Created/Modified
- `src/vcompany/communication/standup.py` - StandupSession with block/release/route_message per D-11
- `src/vcompany/bot/views/standup_release.py` - ReleaseView with no-timeout Release button
- `src/vcompany/bot/embeds.py` - Added build_standup_embed for per-agent thread embeds
- `src/vcompany/bot/cogs/commands.py` - Full !standup command and on_message thread routing
- `tests/test_standup.py` - 13 tests for standup session, release view, and embed

## Decisions Made
- asyncio.Future for per-agent blocking -- lightweight, no timeout per D-11
- on_message Cog listener pattern for thread message routing (not a separate Cog)
- route_message_to_agent sends /gsd:quick so agent processes owner feedback as a task
- discord.py button callbacks tested via callback(interaction) per Phase 04 convention

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ReleaseView test to use discord.py callback convention**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Tests passed button as second arg to callback, but discord.py bound method callbacks take only interaction
- **Fix:** Updated tests to call view.release.callback(interaction) per Phase 04 decision
- **Files modified:** tests/test_standup.py
- **Verification:** All 13 tests pass
- **Committed in:** 4f9603b (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test fix only, no implementation change needed. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Standup ritual complete, ready for Phase 07 Plan 06 (final integration plan)
- StandupSession can be wired into monitor loop for automated standup triggers
- on_message listener active for thread-based owner-agent communication

---
*Phase: 07-integration-pipeline-and-communications*
*Completed: 2026-03-25*
