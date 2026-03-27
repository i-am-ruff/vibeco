---
phase: 09-askuser-hook-sends-questions-to-agent-discord-channel-mentioning-pm-for-autonomous-q-a-forwarding
plan: 03
subsystem: discord
tags: [discord, routing, cogs, question-handler, strategist, pm, escalation]

# Dependency graph
requires:
  - phase: 09-01
    provides: "Routing framework (route_message, is_question_embed, EntityRegistry)"
provides:
  - "QuestionHandlerCog with agent-channel question detection and Discord reply-based answers"
  - "StrategistCog with routing framework integration and agent-channel escalation"
  - "No file-based IPC in any bot Cog"
affects: [discord-bot, agent-channels, pm-evaluation, escalation-chain]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "is_question_embed() for bot-posted question detection in agent channels"
    - "route_message() for StrategistCog message filtering with replied-to content fetch"
    - "Non-reply Pattern B for escalation mentions (D-10)"
    - "Optional channel parameter on post_owner_escalation for agent-channel escalation (D-03)"

key-files:
  created: []
  modified:
    - "src/vcompany/bot/cogs/question_handler.py"
    - "src/vcompany/bot/cogs/strategist.py"
    - "tests/test_question_handler.py"
    - "tests/test_strategist_cog.py"

key-decisions:
  - "Removed all file-based IPC (AnswerView, OtherAnswerModal, _write_answer_file_sync, ANSWER_DIR) from QuestionHandlerCog"
  - "HIGH-confidence PM answers not logged to #decisions per D-19 (only escalated decisions logged)"
  - "StrategistCog fetches replied-to message content via fetch_message for correct routing per D-07"
  - "Owner escalation supports agent-channel posting via optional channel parameter per D-03"

patterns-established:
  - "Bot-posted question detection via is_question_embed in on_message listener"
  - "PM auto-answer delivery via message.reply() with [PM] prefix"
  - "Routing framework adoption pattern for Cog message filtering"

requirements-completed: [D-04, D-07, D-09, D-10, D-11, D-19]

# Metrics
duration: 4min
completed: 2026-03-27
---

# Phase 09 Plan 03: Rework QuestionHandlerCog and StrategistCog Summary

**Discord reply-based PM answers in agent channels with routing framework filtering and file-IPC removal**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-27T01:20:43Z
- **Completed:** 2026-03-27T01:25:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- QuestionHandlerCog detects question embeds in #agent-{id} channels via is_question_embed()
- PM auto-answers via Discord reply with [PM] prefix (HIGH/MEDIUM/LOW confidence handling)
- All file-based IPC removed (ANSWER_DIR, AnswerView, OtherAnswerModal, _write_answer_file_sync)
- StrategistCog uses routing framework for D-07 message filtering with replied-to content fetch
- Owner escalation supports agent channels via optional channel parameter (D-03)
- 42 tests pass across question_handler, strategist_cog, and routing modules

## Task Commits

Each task was committed atomically:

1. **Task 1: Rework QuestionHandlerCog for agent-channel flow** - `b2189e7` (feat)
2. **Task 2: Adapt StrategistCog for routing framework and agent-channel escalation** - `2c0e74e` (feat)

## Files Created/Modified
- `src/vcompany/bot/cogs/question_handler.py` - Reworked: detects question embeds in agent channels, PM replies via Discord, no file IPC
- `src/vcompany/bot/cogs/strategist.py` - Modified: routing framework for message filtering, agent-channel escalation support
- `tests/test_question_handler.py` - Rewritten: 10 tests covering detection, PM reply behavior, graceful degradation
- `tests/test_strategist_cog.py` - Rewritten: 15 tests covering routing integration, escalation, PM-reply filtering

## Decisions Made
- Removed all file-based IPC from QuestionHandlerCog (no ANSWER_DIR, no AnswerView, no OtherAnswerModal)
- HIGH-confidence PM answers are not logged to #decisions per D-19 (only MEDIUM/LOW/OWNER)
- StrategistCog fetches replied-to message content via channel.fetch_message for correct entity routing
- discord.NotFound handled gracefully when replied-to message is deleted
- Owner escalation uses optional channel parameter defaulting to #strategist for backward compat

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing test failures in test_bot_client.py and test_bot_startup.py (unrelated to this plan, not caused by changes)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All bot Cogs now use Discord-native communication (no file-based IPC)
- Routing framework fully integrated into StrategistCog and QuestionHandlerCog
- Ready for Phase 10 (autonomous operation rework)

---
*Phase: 09-askuser-hook-sends-questions-to-agent-discord-channel-mentioning-pm-for-autonomous-q-a-forwarding*
*Completed: 2026-03-27*
