---
phase: 06-resilience
plan: 01
subsystem: resilience
tags: [asyncio, priority-queue, rate-limiting, debounce, backoff]

# Dependency graph
requires:
  - phase: 05-health
    provides: HealthReport model and HealthCog notification delivery
provides:
  - MessageQueue with priority ordering for outbound Discord messages
  - Health report debounce within configurable window
  - Exponential backoff on 429 rate-limit responses
  - RateLimited exception for Discord-agnostic error signaling
affects: [08-wiring, 06-resilience]

# Tech tracking
tech-stack:
  added: []
  patterns: [injectable send_func for testability, RateLimited exception for decoupling]

key-files:
  created:
    - src/vcompany/resilience/__init__.py
    - src/vcompany/resilience/message_queue.py
    - tests/test_message_queue.py
  modified: []

key-decisions:
  - "RateLimited custom exception instead of catching discord.HTTPException -- keeps MessageQueue Discord-agnostic"
  - "Injectable send_func callable instead of bot reference -- makes testing trivial without Discord mocks"

patterns-established:
  - "Injectable async callable pattern: pass send_func to queue instead of coupling to discord.py"
  - "Custom exception bridging: caller translates library exceptions into domain exceptions (RateLimited)"

requirements-completed: [RESL-01]

# Metrics
duration: 3min
completed: 2026-03-28
---

# Phase 06 Plan 01: Message Queue Summary

**Discord-agnostic priority message queue with health debounce and exponential backoff on rate limits using asyncio.PriorityQueue**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-27T23:38:22Z
- **Completed:** 2026-03-27T23:42:00Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- MessagePriority IntEnum with 4 levels (ESCALATION > SUPERVISOR > STATUS > HEALTH_DEBOUNCED)
- QueuedMessage ordered dataclass for priority queue comparison
- MessageQueue with async drain loop, injectable send_func, health debounce, and exponential backoff
- RateLimited exception for Discord-agnostic 429 error signaling
- 7 passing tests covering all specified behaviors

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests** - `5dd962f` (test)
2. **Task 1 (GREEN): MessageQueue implementation** - `f34e1b7` (feat)

_TDD task with RED/GREEN commits._

## Files Created/Modified
- `src/vcompany/resilience/__init__.py` - Package init exporting MessageQueue, MessagePriority, QueuedMessage, RateLimited
- `src/vcompany/resilience/message_queue.py` - Priority message queue with rate limiting and debounce (196 lines)
- `tests/test_message_queue.py` - 7 tests for priority ordering, debounce, backoff, reset, drain, start/stop (219 lines)

## Decisions Made
- Used RateLimited custom exception instead of catching discord.HTTPException directly. This keeps the module completely Discord-agnostic and testable without discord.py imports.
- Injectable send_func (Callable[[QueuedMessage], Awaitable[None]]) instead of a bot reference. Production callers wrap channel.send() into a send_func; tests pass a simple mock.
- Backoff starts at 1.0s on first RateLimited, doubles each time, capped at 60.0s. Resets to 0.0 on first successful send.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Test test_backoff_reset initially failed because it set _backoff=4.0 and only waited 0.1s for the drain loop (which sleeps the backoff duration before sending). Fixed by using a smaller backoff value (0.01) in the test.

## Known Stubs

None - all functionality is fully implemented.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- MessageQueue is ready for integration in Phase 8 (CompanyRoot wiring) where HealthCog._notify_state_change will route through the queue
- Plans 06-02 and 06-03 can proceed independently (outage detection and degraded mode)

---
*Phase: 06-resilience*
*Completed: 2026-03-28*
