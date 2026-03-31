---
phase: 28-agent-transport-separation
plan: 01
subsystem: container
tags: [protocol, handler, composition, orderedset, discord]

# Dependency graph
requires:
  - phase: 27-docker-integration-wiring
    provides: AgentTransport protocol pattern, factory, agent-types config
provides:
  - SessionHandler, ConversationHandler, TransientHandler protocol definitions
  - Base AgentContainer _send_discord consolidated method
  - Base AgentContainer _channel_id and _handler fields
  - OrderedSet compound state handling on base class
affects: [28-02, 28-03, 28-04]

# Tech tracking
tech-stack:
  added: []
  patterns: [handler-protocol-composition, base-class-consolidation]

key-files:
  created:
    - src/vcompany/handler/__init__.py
    - src/vcompany/handler/protocol.py
  modified:
    - src/vcompany/container/container.py

key-decisions:
  - "Handler protocols have identical method signatures but are separate types for semantic isinstance checks"
  - "Base _send_discord uses daemon.comm.SendMessagePayload (not container.communication) for canonical import"
  - "_handler typed as Any to avoid import cycle; runtime isinstance checks via Protocol"

patterns-established:
  - "Handler Protocol pattern: @runtime_checkable with handle_message/on_start/on_stop async methods"
  - "Handler lifecycle hooks: start() calls on_start, stop() calls on_stop"
  - "TYPE_CHECKING guard for cross-module Protocol type hints"

requirements-completed: [HSEP-01, HSEP-02, HSEP-03, HSEP-08]

# Metrics
duration: 2min
completed: 2026-03-31
---

# Phase 28 Plan 01: Handler Protocols and Base Container Summary

**Three handler protocols (Session/Conversation/Transient) with consolidated _send_discord, OrderedSet state, and handler injection on base AgentContainer**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T04:36:54Z
- **Completed:** 2026-03-31T04:39:08Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Defined three @runtime_checkable handler Protocol classes in new vcompany.handler package
- Consolidated _send_discord from 3 duplicate subclass implementations into base AgentContainer
- Added OrderedSet compound state handling to base class (replaces 4 identical overrides in subclasses)
- Added _handler field with lifecycle hooks (on_start/on_stop) and message delegation

## Task Commits

Each task was committed atomically:

1. **Task 1: Create handler protocol definitions** - `219230e` (feat)
2. **Task 2: Consolidate _send_discord, _channel_id, _handler, OrderedSet into base** - `8a56051` (feat)

## Files Created/Modified
- `src/vcompany/handler/__init__.py` - Package init re-exporting three protocols
- `src/vcompany/handler/protocol.py` - SessionHandler, ConversationHandler, TransientHandler Protocol definitions
- `src/vcompany/container/container.py` - Added _send_discord, _channel_id, _handler, OrderedSet state, handler hooks

## Decisions Made
- Handler protocols have identical method signatures but are separate types -- enables isinstance checks for semantic dispatch even though interface shape is the same
- Base _send_discord imports SendMessagePayload from daemon.comm (canonical location), not container.communication
- _handler typed as Any to avoid circular imports; runtime Protocol isinstance checks remain available
- Handler on_start/on_stop hooks called in base start()/stop() -- subclasses that override these must call super()

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all protocols are fully defined, all base container fields are wired.

## Next Phase Readiness
- Handler protocols ready for concrete implementations in Plan 02 (session handler) and Plan 03 (factory wiring)
- Subclasses still have their own state/inner_state overrides and _send_discord -- Plan 02-04 will migrate them to use base versions
- _channel_id wiring from MentionRouterCog will be addressed in Plan 03

---
*Phase: 28-agent-transport-separation*
*Completed: 2026-03-31*
