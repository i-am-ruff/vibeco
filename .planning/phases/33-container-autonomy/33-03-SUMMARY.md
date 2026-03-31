---
phase: 33-container-autonomy
plan: 03
subsystem: orchestration
tags: [reconnection, socket-transport, daemon-restart, routing-state, channel-protocol]

# Dependency graph
requires:
  - phase: 33-01
    provides: Worker autonomy (SocketWriter, data_dir derivation, reconnect handling)
  - phase: 33-02
    provides: AgentHandle socket support, RoutingState transport_type, NativeTransport socket-based spawn/connect
provides:
  - CompanyRoot.reconnect_agents() for daemon restart survival
  - Socket-based hire() flow using attach_socket instead of process assignment
  - Channel reader using handle.reader property (transport-agnostic)
  - Routing state with transport_type persistence
affects: [34-dead-code-removal]

# Tech tracking
tech-stack:
  added: []
  patterns: [reconnection-on-startup, transport-agnostic-reader, stale-entry-cleanup]

key-files:
  created: []
  modified:
    - src/vcompany/supervisor/company_root.py

key-decisions:
  - "reconnect_agents() called in start() after RoutingState load -- straightforward startup integration"
  - "_save_routing accepts transport_name parameter rather than storing transport_type on AgentHandle"

patterns-established:
  - "Reconnection pattern: load routing -> iterate agents -> transport.connect() -> attach_socket -> send ReconnectMessage -> start reader"
  - "Stale cleanup: failed reconnections removed from RoutingState and persisted to disk"

requirements-completed: [AUTO-01, AUTO-02, AUTO-03]

# Metrics
duration: 2min
completed: 2026-03-31
---

# Phase 33 Plan 03: CompanyRoot Reconnection Summary

**CompanyRoot wired for daemon restart survival: reconnect_agents() reconnects to surviving workers via socket transport, hire() uses attach_socket, channel reader uses handle.reader property**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T16:54:42Z
- **Completed:** 2026-03-31T16:56:03Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- hire() updated to use (reader, writer) tuple from transport.spawn() via handle.attach_socket()
- _channel_reader rewritten to use handle.reader property (works with socket or process stdout)
- reconnect_agents() method added: iterates RoutingState, connects via transport.connect(), sends ReconnectMessage, starts channel reader
- _save_routing now persists transport_type for each agent
- Stale routing entries cleaned up when reconnection fails
- ConnectionResetError/BrokenPipeError handling added to channel reader

## Task Commits

Each task was committed atomically:

1. **Task 1: Update hire() flow for socket transport and add reconnect_agents()** - `44706ec` (feat)

## Files Created/Modified
- `src/vcompany/supervisor/company_root.py` - Updated hire(), _channel_reader, _save_routing; added reconnect_agents() method and startup call

## Decisions Made
- _save_routing takes transport_name as a parameter (default "native") rather than adding transport_type to AgentHandle -- keeps handle clean, transport_type is a routing concern
- reconnect_agents() called immediately after RoutingState.load() in start() -- before degraded mode or scheduler, so workers are reconnected first

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Daemon restart survival story complete: start() -> load RoutingState -> reconnect_agents() -> connect sockets -> send ReconnectMessage -> resume operations
- hire() flow complete: spawn() -> (reader, writer) -> attach_socket() -> send StartMessage -> start channel reader
- No references to handle._process.stdout or handle._process = process remain in CompanyRoot
- Ready for Phase 34 dead code removal

---
*Phase: 33-container-autonomy*
*Completed: 2026-03-31*
