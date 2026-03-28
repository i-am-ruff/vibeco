---
phase: 16-agent-completeness-strategist
plan: 01
subsystem: agent
tags: [company-agent, strategist, event-driven, discord-bot, asyncio]

# Dependency graph
requires:
  - phase: 15-pm-actions-auto-distribution
    provides: PM action callbacks, escalate_to_strategist slot on FulltimeAgent
  - phase: 11-container-architecture-fixes
    provides: CompanyAgent base class with event queue and EventDrivenLifecycle

provides:
  - CompanyAgent._handle_event dispatching strategist_message and pm_escalation
  - CompanyAgent.initialize_conversation() owning StrategistConversation
  - CompanyAgent._drain_events() background task for self-draining queue
  - StrategistCog as thin Discord adapter forwarding events via post_event()
  - VcoBot.on_ready wiring: CompanyAgent response callback + set_company_agent()
  - PM escalation path routed through CompanyAgent container

affects: [17-inter-container-comm, testing-strategist, health-tree]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Event-driven container pattern: cog posts typed event dict, container handles via _handle_event, result returned via asyncio.Future embedded in event"
    - "Drain loop pattern: background asyncio.Task calls process_next_event() in 0.1s poll loop -- mirrors FulltimeAgent stuck detector pattern"
    - "Backward compat fallback: if _company_agent not wired, StrategistCog falls back to direct _conversation.send() to avoid breaking early startup"

key-files:
  created: []
  modified:
    - src/vcompany/agent/company_agent.py
    - src/vcompany/bot/cogs/strategist.py
    - src/vcompany/bot/client.py

key-decisions:
  - "Future embedded in event dict for request-response pattern: StrategistCog._send_to_channel and handle_pm_escalation embed asyncio.Future in the event they post, await it for the response"
  - "Both _on_response callback and _response_future supported: _on_response fires for direct channel posting; _response_future used when cog awaits the response inline"
  - "StrategistCog backward compat: if _company_agent not set, falls through to _conversation.send() so early-startup and test scenarios work without full wiring"
  - "_strategist_persona_path local variable in on_ready bridges always-run section to project section for CompanyAgent.initialize_conversation()"
  - "PM escalation wired directly to CompanyAgent.post_event() in client.py (bypasses cog), with cog fallback if container is not a CompanyAgent"

patterns-established:
  - "Typed event dict with embedded Future: post {type, payload, _response_future} to container, await future for sync-like result from async event handler"

requirements-completed: [ARCH-01]

# Metrics
duration: 15min
completed: 2026-03-28
---

# Phase 16 Plan 01: Agent Completeness Strategist Summary

**Strategist conversation moved into CompanyAgent._handle_event() with event-driven dispatch for strategist_message and pm_escalation, StrategistCog reduced to thin Discord adapter using post_event()**

## Performance

- **Duration:** 15 min
- **Started:** 2026-03-28T17:30:00Z
- **Completed:** 2026-03-28T17:45:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- CompanyAgent now owns StrategistConversation via initialize_conversation() and handles all strategist events in _handle_event()
- StrategistCog._send_to_channel and handle_pm_escalation route through CompanyAgent.post_event() with asyncio.Future for response
- VcoBot.on_ready wires conversation, response callback, and set_company_agent() -- ARCH-01 satisfied
- Background drain loop (_drain_events) ensures event queue is self-draining without external polling
- PM escalation path in client.py posts pm_escalation event directly to CompanyAgent instead of going through cog

## Task Commits

Each task was committed atomically:

1. **Task 1: Move StrategistConversation into CompanyAgent and implement _handle_event** - `0ccac82` (feat)
2. **Task 2: Wire CompanyAgent response callback and strategist connection in VcoBot.on_ready** - `b44e18b` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/vcompany/agent/company_agent.py` - Added initialize_conversation(), _handle_event() with strategist_message/pm_escalation dispatch, _drain_events() loop, start()/stop() overrides
- `src/vcompany/bot/cogs/strategist.py` - Added _company_agent attr, set_company_agent(), updated _send_to_channel and handle_pm_escalation to route through container with Future-based response
- `src/vcompany/bot/client.py` - Added CompanyAgent import, asyncio import; capture strategist_container, call initialize_conversation()+_on_response+set_company_agent(); route PM escalation directly through container

## Decisions Made

- Future embedded in event dict for request-response: StrategistCog embeds asyncio.Future in the event dict and awaits it, allowing synchronous-looking results from the async event handler
- Both _on_response callback and _response_future supported for flexibility: cog awaits future, standalone channel posting uses callback
- StrategistCog backward compat: direct _conversation.send() fallback when _company_agent not wired (early startup / test isolation)
- PM escalation wired directly to CompanyAgent.post_event() in client.py, not through cog, for clean ARCH-01 compliance

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Strategist operates fully through CompanyAgent container (ARCH-01 satisfied)
- Inter-container communication (Phase 17) can now target CompanyAgent event queue
- Health tree rendering will show CompanyAgent with correct drain loop state

---
*Phase: 16-agent-completeness-strategist*
*Completed: 2026-03-28*
