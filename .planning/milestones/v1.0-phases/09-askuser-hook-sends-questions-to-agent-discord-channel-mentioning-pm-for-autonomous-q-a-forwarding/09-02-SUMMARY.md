---
phase: 09-askuser-hook-sends-questions-to-agent-discord-channel-mentioning-pm-for-autonomous-q-a-forwarding
plan: 02
subsystem: hooks
tags: [discord-rest-api, urllib, pretooluse, polling, escalation]

# Dependency graph
requires:
  - phase: 09-01
    provides: message routing module for question/answer dispatch
provides:
  - Discord REST API hook (post + reply poll) replacing webhook + file IPC
  - Channel resolution scoped to project category
  - Escalation-aware polling with infinite extension
affects: [09-03, question_handler, bot-cogs]

# Tech tracking
tech-stack:
  added: []
  patterns: [urllib.request for Discord REST API, message_reference reply matching, escalation marker detection]

key-files:
  created: []
  modified: [tools/ask_discord.py, tests/test_ask_discord.py]

key-decisions:
  - "urllib.request for all HTTP (stdlib-only constraint per HOOK-06)"
  - "_make_request helper wraps all Discord API calls with error handling"
  - "Escalation detection via substring match in non-reply messages switches to infinite polling"
  - "Entity prefix [agent_id] in message content for consistent Discord formatting (D-05)"

patterns-established:
  - "Discord REST API pattern: _make_request with Bot token auth for channel resolution and message posting"
  - "Reply polling: message_reference.message_id match for answer detection"

requirements-completed: [D-01, D-02, D-03, D-05, D-12, D-13, D-14, D-15, D-17, D-18, D-20]

# Metrics
duration: 2min
completed: 2026-03-27
---

# Phase 09 Plan 02: Discord REST API Hook Summary

**Rewrote ask_discord.py to use Discord REST API for posting questions to #agent-{id} channels and polling for reply messages, replacing webhook + file-based IPC**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-27T01:20:24Z
- **Completed:** 2026-03-27T01:23:11Z
- **Tasks:** 1 (TDD)
- **Files modified:** 2

## Accomplishments
- Replaced webhook POST + /tmp/vco-answers file polling with Discord REST API (GET channels, POST messages, GET replies)
- Added resolve_channel with project category scoping (vco-{project_name})
- Added poll_for_reply with message_reference matching and escalation detection for extended polling
- Removed all file-based IPC references (ANSWER_DIR, /tmp/vco-answers, webhook_url)
- 15 tests passing covering all new functions

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for Discord REST API hook** - `8a47993` (test)
2. **Task 1 (GREEN): Rewrite ask_discord.py implementation** - `331e1ab` (feat)

_TDD task: test -> feat commits_

## Files Created/Modified
- `tools/ask_discord.py` - Rewritten PreToolUse hook using Discord REST API for post+poll
- `tests/test_ask_discord.py` - 15 tests covering resolve_channel, post_question, poll_for_reply, escalation, end-to-end flows

## Decisions Made
- urllib.request for all HTTP calls (stdlib-only constraint per HOOK-06)
- _make_request helper wraps all Discord API calls with consistent error handling and Bot token auth
- Escalation detection via substring match ("escalated") in non-reply messages switches to infinite polling (D-18)
- Entity prefix [agent_id] in message content for consistent Discord formatting (D-05)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Hook now uses Discord REST API for all Q&A communication
- Ready for Plan 03 (bot-side question handler updates if applicable)
- VCO_AGENT_ID, DISCORD_BOT_TOKEN, DISCORD_GUILD_ID env vars required at runtime

## Self-Check: PASSED

---
*Phase: 09-askuser-hook-sends-questions-to-agent-discord-channel-mentioning-pm-for-autonomous-q-a-forwarding*
*Completed: 2026-03-27*
