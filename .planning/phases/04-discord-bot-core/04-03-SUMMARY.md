---
phase: 04-discord-bot-core
plan: 03
subsystem: discord
tags: [discord.py, cogs, alerts, buffer, run_coroutine_threadsafe, callbacks]

# Dependency graph
requires:
  - phase: 04-discord-bot-core
    provides: "VcoBot client, build_alert_embed, Cog architecture"
  - phase: 03-monitor-coordination
    provides: "MonitorLoop with on_agent_dead/stuck/plan_detected callbacks"
  - phase: 02-agent-lifecycle
    provides: "CrashTracker with CircuitOpenCallback"
provides:
  - "AlertsCog with send-or-buffer, reconnect flush, and sync callback bridge"
  - "PlanReviewCog placeholder for Phase 5 plan gate"
  - "StrategistCog placeholder for Phase 6 AI PM"
affects: [04-04-bot-entry-point, 05-hooks, 06-strategist]

# Tech tracking
tech-stack:
  added: []
  patterns: [sync-to-async callback bridge via run_coroutine_threadsafe, alert buffering during disconnect with flush on reconnect]

key-files:
  created:
    - src/vcompany/bot/cogs/alerts.py
    - src/vcompany/bot/cogs/plan_review.py
    - src/vcompany/bot/cogs/strategist.py
    - tests/test_alerts_cog.py
  modified: []

key-decisions:
  - "TYPE_CHECKING import for VcoBot to avoid circular imports at runtime"

patterns-established:
  - "Sync-to-async bridge: run_coroutine_threadsafe for MonitorLoop/CrashTracker callbacks (Pitfall 4)"
  - "Alert buffer pattern: _send_or_buffer queues embeds when disconnected, on_resumed flushes (D-15)"
  - "Placeholder cog pattern: minimal class with docstring referencing target phase"

requirements-completed: [DISC-12]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 4 Plan 3: Alerts and Placeholder Cogs Summary

**AlertsCog with monitor callback bridge via run_coroutine_threadsafe, disconnect buffering with reconnect flush, plus PlanReviewCog and StrategistCog placeholders**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T15:07:22Z
- **Completed:** 2026-03-25T15:10:22Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- AlertsCog bridges sync MonitorLoop/CrashTracker callbacks to async Discord sends via run_coroutine_threadsafe
- Alerts buffered during bot disconnect and flushed on reconnect (DISC-12, D-15)
- PlanReviewCog and StrategistCog placeholders complete DISC-01 4-Cog architecture
- 17 tests covering buffer/flush, all 4 alert types, sync callback wiring, and channel resolution

## Task Commits

Each task was committed atomically:

1. **Task 1: AlertsCog with buffer, flush, and sync-to-async callback bridge** - `4b6e079` (feat)
2. **Task 2: PlanReviewCog and StrategistCog placeholders** - `7b13836` (feat)

## Files Created/Modified
- `src/vcompany/bot/cogs/alerts.py` - AlertsCog with _send_or_buffer, on_resumed flush, make_sync_callbacks
- `src/vcompany/bot/cogs/plan_review.py` - PlanReviewCog placeholder for Phase 5 plan gate
- `src/vcompany/bot/cogs/strategist.py` - StrategistCog placeholder for Phase 6 AI PM
- `tests/test_alerts_cog.py` - 17 tests for alert buffer, flush, callback wiring, all alert types

## Decisions Made
- Used TYPE_CHECKING import for VcoBot to avoid circular import at runtime (alerts.py imports from bot.embeds, client.py imports cog extensions)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 4 Cogs now exist: CommandsCog, AlertsCog, PlanReviewCog, StrategistCog
- Plan 04 (bot entry point) can wire AlertsCog.make_sync_callbacks() into MonitorLoop and CrashTracker
- Phase 5 can expand PlanReviewCog with plan gate workflow
- Phase 6 can expand StrategistCog with Anthropic SDK integration
- All 247 tests pass with no regressions

## Self-Check: PASSED

---
*Phase: 04-discord-bot-core*
*Completed: 2026-03-25*
