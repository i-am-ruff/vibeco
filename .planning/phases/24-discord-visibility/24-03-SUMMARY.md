---
phase: 24-discord-visibility
plan: 03
subsystem: agent
tags: [discord, messaging, event-driven, pydantic, asyncio]

# Dependency graph
requires:
  - phase: 24-01
    provides: MessageContext model, AgentContainer.receive_discord_message base method, MentionRouterCog
provides:
  - FulltimeAgent with Discord-based receive_discord_message (PM role)
  - CompanyAgent with Discord-based receive_discord_message (Strategist role)
  - GsdAgent emitting phase transitions and review requests as Discord messages
  - GsdAgent receiving review decisions and task assignments via Discord
  - All callback fields and event queues removed from all three agent types
affects: [24-04, runtime-api, bot-cogs, plan-review]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Prefix-based message dispatch in receive_discord_message ([Phase Complete], [Task Assigned], etc.)"
    - "_send_discord() helper pattern using CommunicationPort across all agent types"
    - "_extract_field() utility for parsing key=value pairs from message content"

key-files:
  created: []
  modified:
    - src/vcompany/agent/fulltime_agent.py
    - src/vcompany/agent/company_agent.py
    - src/vcompany/agent/gsd_agent.py

key-decisions:
  - "Prefix-based message dispatch pattern: [Phase Complete], [Task Assigned], [Review Decision], etc."
  - "escalate_to_strategist now sends Discord message instead of returning response (fire-and-forget via channel)"
  - "CompanyAgent start/stop simplified -- no drain loop needed without event queue"

patterns-established:
  - "Agent _send_discord() helper: import SendMessagePayload inline, use comm_port"
  - "Message prefix convention: [Type] followed by key=value or structured text"

requirements-completed: [VIS-01, VIS-03, VIS-05, VIS-06]

# Metrics
duration: 4min
completed: 2026-03-29
---

# Phase 24 Plan 03: Agent Discord Messaging Summary

**All three agent types (PM, Strategist, GSD) converted from internal event queues/callbacks to Discord message-driven communication via receive_discord_message() and _send_discord()**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-29T16:19:14Z
- **Completed:** 2026-03-29T16:23:13Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- FulltimeAgent processes PM events via receive_discord_message with prefix-based dispatch ([Phase Complete], [Task Completed], [Task Failed], [Request Assignment], [Health Change])
- CompanyAgent forwards Discord messages to StrategistConversation and posts responses back via _send_discord
- GsdAgent emits [Phase Complete] and [Review Request] Discord messages in advance_phase(), receives [Review Decision] and [Task Assigned] via receive_discord_message
- All internal event queues (asyncio.Queue) removed from FulltimeAgent and CompanyAgent
- All callback fields removed: _on_gsd_review, _on_assign_task, _on_escalate_to_strategist, _on_phase_transition, _on_review_request, _on_response, _on_hire, _on_give_task, _on_dismiss, _on_send_intervention, _on_trigger_integration_review, _on_recruit_agent, _on_remove_agent
- Task assignment now emits visible Discord message per VIS-06: [Task Assigned] @agent-id: title (item: id)

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace FulltimeAgent event queue with Discord message handler** - `d949824` (feat)
2. **Task 2: Replace CompanyAgent/GsdAgent queues and callbacks with Discord messaging** - `b6dfaa7` (feat)

## Files Created/Modified
- `src/vcompany/agent/fulltime_agent.py` - PM agent: receive_discord_message with prefix dispatch, _send_discord, removed event queue and 7 callback fields
- `src/vcompany/agent/company_agent.py` - Strategist agent: receive_discord_message forwarding to StrategistConversation, removed event queue and 4 callback fields
- `src/vcompany/agent/gsd_agent.py` - GSD agent: _send_discord for phase transitions/reviews, receive_discord_message for review decisions/task assignments, removed 2 callback fields

## Decisions Made
- Used prefix-based message dispatch pattern ([Phase Complete], [Task Assigned], etc.) for structured yet human-readable Discord messages
- escalate_to_strategist changed from request-response to fire-and-forget Discord message (strategist channel routing handles response)
- CompanyAgent simplified significantly -- no drain task needed without event queue, just forward messages to conversation

## Deviations from Plan

None - plan executed exactly as written.

## Known Dependencies

RuntimeAPI (src/vcompany/daemon/runtime_api.py) still references the removed methods (post_event, _on_phase_transition, _on_review_request, _on_gsd_review, _on_assign_task, _on_response, _on_hire, etc.). Plan 04 handles the RuntimeAPI wiring update. Tests also reference old API and will need updating alongside RuntimeAPI.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three agent types ready for Discord-based communication
- Plan 04 must update RuntimeAPI to stop wiring removed callbacks and use receive_discord_message/MentionRouterCog instead
- Bot cogs may need updates to route messages through receive_discord_message instead of post_event

---
*Phase: 24-discord-visibility*
*Completed: 2026-03-29*
