---
phase: 24-discord-visibility
plan: 02
subsystem: autonomy
tags: [backlog, callback, mutation-notification, decoupling]

requires:
  - phase: none
    provides: BacklogQueue already existed with 7 mutation methods
provides:
  - BacklogQueue with injected on_mutation callback for all mutations
  - _notify helper with exception suppression and logging
affects: [24-04-wiring, communication-port, discord-visibility]

tech-stack:
  added: []
  patterns: [injected-async-callback for decoupled notification]

key-files:
  created: []
  modified: [src/vcompany/autonomy/backlog.py]

key-decisions:
  - "Used Callable[[str], Awaitable[None]] callback injection instead of importing CommunicationPort directly"
  - "Notification fires after _persist() to ensure only committed mutations are reported"
  - "_notify suppresses all exceptions to prevent notification failures from breaking backlog operations"

patterns-established:
  - "Injected callback pattern: accept optional async Callable in __init__, fire via _notify helper after state mutation"
  - "Exception-safe notification: try/except with logger.warning around callback invocation"

requirements-completed: [VIS-02]

duration: 2min
completed: 2026-03-29
---

# Phase 24 Plan 02: Backlog Mutation Notifications Summary

**Injected on_mutation async callback into BacklogQueue for Discord-visible backlog operations, fully decoupled from bot/comm layers**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-29T16:15:53Z
- **Completed:** 2026-03-29T16:17:28Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- BacklogQueue.__init__ accepts optional on_mutation: Callable[[str], Awaitable[None]]
- All 7 mutation methods (append, insert_urgent, reorder, cancel, claim_next, mark_completed, mark_pending) fire human-readable notification messages
- _notify helper suppresses exceptions so notification failures never break backlog operations
- Zero Discord/bot/comm imports -- BacklogQueue remains a pure data structure

## Task Commits

Each task was committed atomically:

1. **Task 1: Add on_mutation callback to BacklogQueue** - `92a6928` (feat)

## Files Created/Modified
- `src/vcompany/autonomy/backlog.py` - Added on_mutation callback parameter, _notify helper, and notification calls in all 7 mutation methods

## Decisions Made
- Used `Callable[[str], Awaitable[None]]` type for callback to keep BacklogQueue decoupled from any specific notification transport
- Placed notification calls after `_persist()` (post-commit pattern per D-06) so only successful mutations are reported
- claim_next notification stays inside the lock since it's inside the conditional return block -- structurally necessary
- Used `collections.abc.Awaitable` and `collections.abc.Callable` imports (via `from __future__ import annotations`) instead of `typing` module for modern Python style

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- on_mutation callback ready to be wired to CommunicationPort.send_message in Plan 04
- Existing BacklogQueue construction (without on_mutation) still works -- backward compatible

---
*Phase: 24-discord-visibility*
*Completed: 2026-03-29*
