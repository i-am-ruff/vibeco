---
phase: 31-head-refactor
plan: 03
subsystem: daemon
tags: [agent-handle, mention-router, inbound-message, transport-channel, routing]

requires:
  - phase: 31-head-refactor (plan 01)
    provides: AgentHandle model and RoutingState persistence
  - phase: 31-head-refactor (plan 02)
    provides: RuntimeAPI.hire() calling register_agent_handle()
provides:
  - MentionRouterCog routes messages to AgentHandle via InboundMessage
  - register_agent_handle() method for Phase 31+ transport routing
  - Dual dispatch in _deliver_to_agent (AgentHandle vs AgentContainer)
  - Daemon routing state flow documented
affects: [34-dead-code-removal, 32-container-bootstrap]

tech-stack:
  added: []
  patterns:
    - "isinstance dispatch for AgentHandle vs AgentContainer in message routing"
    - "Runtime import of AgentHandle in _deliver_to_agent to avoid circular deps"

key-files:
  created: []
  modified:
    - src/vcompany/bot/cogs/mention_router.py
    - src/vcompany/daemon/daemon.py

key-decisions:
  - "Dual dispatch pattern in _deliver_to_agent using isinstance(agent, AgentHandle)"
  - "Legacy AgentContainer path preserved for project agents not yet on worker protocol"
  - "set_agent_types_config() retained in daemon -- still needed by hire() flow"

patterns-established:
  - "isinstance dispatch: AgentHandle gets InboundMessage, AgentContainer gets MessageContext"

requirements-completed: [HEAD-01, HEAD-02]

duration: 2min
completed: 2026-03-31
---

# Phase 31 Plan 03: MentionRouter + Daemon Wiring Summary

**MentionRouterCog dual dispatch -- AgentHandle receives InboundMessage via transport channel, AgentContainer preserved for legacy project agents**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T16:03:31Z
- **Completed:** 2026-03-31T16:05:31Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- MentionRouterCog delivers messages to AgentHandle via InboundMessage through transport channel protocol
- register_agent_handle() method added for RuntimeAPI.hire() to call during agent creation
- Legacy AgentContainer path fully preserved for backward compatibility
- Daemon routing state flow documented and verified

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor MentionRouterCog for AgentHandle message delivery** - `c7f5848` (feat)
2. **Task 2: Update Daemon wiring for handle-based architecture** - `7a8d565` (chore)

## Files Created/Modified
- `src/vcompany/bot/cogs/mention_router.py` - Added register_agent_handle(), dual dispatch in _deliver_to_agent(), InboundMessage import, updated type annotations
- `src/vcompany/daemon/daemon.py` - Documented routing state persistence flow through data_dir to CompanyRoot

## Decisions Made
- Used isinstance dispatch in _deliver_to_agent() rather than separate methods -- keeps routing logic centralized
- Runtime import of AgentHandle inside _deliver_to_agent() to avoid circular import at module level
- Kept set_agent_types_config() in daemon since CompanyRoot.hire() still uses it via container.factory

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- MentionRouterCog now supports both AgentHandle and AgentContainer routing
- Full hire-route-health flow works end-to-end with handles
- Ready for Phase 32 (container bootstrap) and Phase 34 (dead code removal of legacy container paths)

---
*Phase: 31-head-refactor*
*Completed: 2026-03-31*
