---
phase: 09-askuser-hook-sends-questions-to-agent-discord-channel-mentioning-pm-for-autonomous-q-a-forwarding
plan: 01
subsystem: discord
tags: [routing, discord, enum, dataclass, env-vars, hooks]

requires:
  - phase: 05-ask-user-question-hook
    provides: "AskUserQuestion hook and QuestionHandlerCog"
  - phase: 06-two-tier-ai-strategist
    provides: "PM tier and Strategist conversation"
provides:
  - "Message routing framework (route_message, RouteTarget, RouteResult, EntityRegistry)"
  - "is_question_embed helper for detecting agent question embeds"
  - "extract_entity_from_prefix helper for entity prefix parsing"
  - "VCO_AGENT_ID env var in agent dispatch"
  - "24h hook timeout for owner escalation support"
affects: [09-02, 09-03, strategist-cog, question-handler-cog]

tech-stack:
  added: []
  patterns:
    - "EntityRegistry dataclass for centralized entity identification"
    - "RouteTarget enum for type-safe routing decisions"
    - "Priority-based message routing: reply > mention > channel-owner > strategist"

key-files:
  created:
    - src/vcompany/bot/routing.py
    - tests/test_routing.py
  modified:
    - src/vcompany/orchestrator/agent_manager.py
    - src/vcompany/templates/settings.json.j2

key-decisions:
  - "Standalone routing module with no imports from vcompany.bot.cogs for reusability"
  - "replied_to_content passed as optional parameter to avoid async message fetch in routing logic"
  - "Strategist messages have no prefix (per D-05), so reply to unprefixed content routes to Strategist"
  - "@PM detection via content string match since PM is not a Discord user"

patterns-established:
  - "RouteTarget enum for routing decisions across all Cogs"
  - "EntityRegistry for centralized bot/entity identity management"

requirements-completed: [D-06, D-07, D-08, D-16]

duration: 4min
completed: 2026-03-27
---

# Phase 09 Plan 01: Message Routing Framework Summary

**D-06 routing framework with RouteTarget enum, reply/mention/channel-default priority, VCO_AGENT_ID dispatch env var, and 24h hook timeout**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-27T01:14:08Z
- **Completed:** 2026-03-27T01:18:16Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Message routing framework with 5-target RouteTarget enum and priority-based route_message() function
- 19 tests covering all D-06 routing rules, D-07 Strategist filtering, and helper functions
- VCO_AGENT_ID env var exported in both dispatch() and dispatch_all() for hook channel resolution
- Hook timeout bumped from 600s to 86400s (24h) supporting indefinite owner escalation

## Task Commits

Each task was committed atomically:

1. **Task 1: Message routing framework with tests** - `fe2a2f5` (test: RED) + `195d45b` (feat: GREEN)
2. **Task 2: Fix dispatch env vars and bump hook timeout** - `c719e34` (feat)

_Note: Task 1 used TDD with separate test and implementation commits._

## Files Created/Modified
- `src/vcompany/bot/routing.py` - Message routing framework with RouteTarget enum, RouteResult, EntityRegistry, route_message(), is_question_embed(), extract_entity_from_prefix()
- `tests/test_routing.py` - 19 tests covering all routing rules and helpers
- `src/vcompany/orchestrator/agent_manager.py` - Added VCO_AGENT_ID export in dispatch() and dispatch_all()
- `src/vcompany/templates/settings.json.j2` - Bumped hook timeout from 600 to 86400

## Decisions Made
- Standalone routing module with no imports from vcompany.bot.cogs for reusability across all Cogs
- replied_to_content passed as optional parameter to avoid async message fetch inside routing logic
- Strategist messages have no prefix (per D-05), so reply to unprefixed content defaults to Strategist
- @PM detection via content string match since PM is not a Discord user entity

## Deviations from Plan

None - plan executed exactly as written.

## Known Pre-existing Issues
- `tests/test_dispatch.py::TestDispatch::test_dispatch_sets_env_vars_before_claude` expects `DISCORD_AGENT_WEBHOOK_URL` in dispatch command which was never implemented. Pre-existing failure, not caused by this plan's changes.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Routing framework ready for Plans 02 and 03 to integrate into Cogs
- EntityRegistry pattern ready for bot client to instantiate at startup
- VCO_AGENT_ID available for hook channel resolution in Plan 02

---
*Phase: 09-askuser-hook-sends-questions-to-agent-discord-channel-mentioning-pm-for-autonomous-q-a-forwarding*
*Completed: 2026-03-27*
