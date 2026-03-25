---
phase: 05-hooks-and-plan-gate
plan: 04
subsystem: discord-bot
tags: [discord.py, webhook, ipc, atomic-write, plan-gate]

# Dependency graph
requires:
  - phase: 05-01
    provides: ask_discord.py hook posting webhook embeds with request_id
  - phase: 05-03
    provides: PlanReviewCog with make_sync_callback() for plan gate routing
provides:
  - QuestionHandlerCog bridging webhook questions to interactive Discord answer UI
  - Atomic answer file delivery at /tmp/vco-answers/{request_id}.json
  - PlanReviewCog callback wired into MonitorLoop for plan detection routing
  - AlertsCog alert_hook_timeout method for HOOK-04 timeout notifications
affects: [06-strategist, 07-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [dynamic-button-view, atomic-file-ipc, cog-callback-priority]

key-files:
  created:
    - src/vcompany/bot/cogs/question_handler.py
    - tests/test_question_handler.py
  modified:
    - src/vcompany/bot/client.py
    - src/vcompany/bot/cogs/alerts.py
    - tests/test_bot_client.py
    - tests/test_bot_startup.py

key-decisions:
  - "PlanReviewCog on_plan_detected preferred over AlertsCog with fallback"
  - "Dynamic button creation from embed fields with max 20 options"
  - "OtherAnswerModal for free-text answers when predefined options insufficient"

patterns-established:
  - "Cog callback priority: specialized Cog preferred over generic AlertsCog with fallback"
  - "File-based IPC: atomic tmp+rename for hook<->bot answer delivery"

requirements-completed: [HOOK-02, HOOK-03, HOOK-04, HOOK-05, GATE-01, GATE-02, GATE-03]

# Metrics
duration: 4min
completed: 2026-03-25
---

# Phase 05 Plan 04: Answer Delivery and Bot Wiring Summary

**QuestionHandlerCog with dynamic answer buttons, atomic file IPC for hook polling, and PlanReviewCog callback wired into MonitorLoop**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-25T18:21:51Z
- **Completed:** 2026-03-25T18:26:18Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- QuestionHandlerCog listens for webhook questions in #strategist and creates interactive answer UIs with dynamic buttons
- Answer files written atomically (tmp+rename) to /tmp/vco-answers/{request_id}.json for hook polling
- PlanReviewCog callback replaces AlertsCog for plan detection routing in MonitorLoop
- AlertsCog extended with alert_hook_timeout for HOOK-04 timeout notifications
- Full test suite: 317 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Create QuestionHandlerCog for answer delivery** - `0a411fd` (test: RED) + `e9539b0` (feat: GREEN)
2. **Task 2: Wire PlanReviewCog callback and QuestionHandlerCog into bot startup** - `0c0dcd6` (feat)

_Note: Task 1 used TDD with separate RED and GREEN commits_

## Files Created/Modified
- `src/vcompany/bot/cogs/question_handler.py` - QuestionHandlerCog, AnswerView, OtherAnswerModal, atomic answer file write
- `src/vcompany/bot/client.py` - Added question_handler to _COG_EXTENSIONS, wired PlanReviewCog callback
- `src/vcompany/bot/cogs/alerts.py` - Added alert_hook_timeout method
- `tests/test_question_handler.py` - 11 tests for webhook detection, button creation, atomic file write
- `tests/test_bot_client.py` - Updated extension count to 5, added question_handler assertion
- `tests/test_bot_startup.py` - Added PlanReviewCog callback priority test and fallback test

## Decisions Made
- PlanReviewCog's on_plan_detected callback preferred over AlertsCog's when available, with graceful fallback
- Dynamic button creation from embed fields supports up to 20 options plus an "Other" free-text button
- OtherAnswerModal provides discord.ui.Modal for free-text answers when predefined options are insufficient
- 600s timeout on AnswerView (10 minutes matching hook polling timeout)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Full hook-to-bot IPC flow complete: hook posts question -> bot shows buttons -> user clicks -> bot writes file -> hook reads answer
- Plan gate workflow fully wired: monitor detects plan -> PlanReviewCog handles review flow
- Phase 05 complete, ready for Phase 06 (Strategist)

---
*Phase: 05-hooks-and-plan-gate*
*Completed: 2026-03-25*
