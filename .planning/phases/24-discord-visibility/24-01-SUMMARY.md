---
phase: 24-discord-visibility
plan: 01
subsystem: bot
tags: [discord, routing, pydantic, cog, mention]

# Dependency graph
requires: []
provides:
  - MentionRouterCog with generic @mention routing and agent handle registry
  - MessageContext pydantic model for inbound Discord message delivery
  - AgentContainer.receive_discord_message() base method
  - backlog channel in project channel setup
affects: [24-02, 24-03, 24-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Generic handle-based mention routing (no agent-type checks)"
    - "MessageContext as unified inbound message model"
    - "model_copy() for immutable pydantic update on reply context"

key-files:
  created:
    - src/vcompany/bot/cogs/mention_router.py
    - src/vcompany/models/messages.py
  modified:
    - src/vcompany/container/container.py
    - src/vcompany/bot/channel_setup.py

key-decisions:
  - "MessageContext uses model_copy() for reply context updates rather than mutable assignment"
  - "Bot messages skipped entirely in MentionRouterCog (message.author.bot check) to prevent loops"

patterns-established:
  - "Generic agent handle registry: register_agent(handle, container) with no type checks"
  - "MessageContext as the standard inbound message envelope for all agent types"

requirements-completed: [VIS-01, VIS-04, VIS-05]

# Metrics
duration: 2min
completed: 2026-03-29
---

# Phase 24 Plan 01: Mention Router Infrastructure Summary

**Generic MentionRouterCog with @mention text pattern routing, MessageContext pydantic model, and receive_discord_message base method on AgentContainer**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-29T16:15:57Z
- **Completed:** 2026-03-29T16:17:29Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- MessageContext pydantic model captures sender, channel, content, parent_message, message_id, is_reply
- MentionRouterCog scans messages for @Handle patterns and delivers to registered containers
- Reply context fetched with discord.NotFound safety (D-15: immediate parent only)
- backlog channel added to project channel setup (D-08, VIS-02)
- Zero agent-type-specific logic in routing infrastructure (D-04)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create MessageContext model and AgentContainer.receive_discord_message base method** - `c7ec2e9` (feat)
2. **Task 2: Create MentionRouterCog and update channel_setup.py** - `e948846` (feat)

## Files Created/Modified
- `src/vcompany/models/messages.py` - MessageContext pydantic model for inbound Discord message delivery
- `src/vcompany/bot/cogs/mention_router.py` - MentionRouterCog with generic @mention routing and agent handle registry
- `src/vcompany/container/container.py` - Added receive_discord_message() base method and MessageContext TYPE_CHECKING import
- `src/vcompany/bot/channel_setup.py` - Added "backlog" to _PROJECT_CHANNELS list

## Decisions Made
- Used model_copy() for immutable pydantic update when adding reply context to MessageContext
- Bot messages skipped entirely via message.author.bot check (not just self.bot.user.id) to prevent all bot loops
- MentionRouterCog uses text pattern matching (@Handle in content) rather than Discord mention API for flexibility

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- MentionRouterCog ready for agent registration by Plan 03 (agent subclass overrides)
- MessageContext model ready for use by all agent types
- Plan 02 can build on this to surface PM/RuntimeAPI events through Discord

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 24-discord-visibility*
*Completed: 2026-03-29*
