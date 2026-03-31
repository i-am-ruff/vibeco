---
phase: 33-container-autonomy
plan: 02
subsystem: transport
tags: [unix-socket, asyncio, docker, detached-process, reconnection]

# Dependency graph
requires:
  - phase: 32-transport-implementations
    provides: ChannelTransport protocol, NativeTransport, DockerChannelTransport
provides:
  - Socket-based NativeTransport with spawn and connect methods
  - Detached Docker transport with socket mount
  - AgentHandle with attach_socket for socket-based communication
  - AgentRouting with transport_type field for reconnection routing
affects: [33-container-autonomy, 34-dead-code-removal]

# Tech tracking
tech-stack:
  added: []
  patterns: [unix-domain-socket communication, detached-process spawning, socket-based reconnection]

key-files:
  created: []
  modified:
    - src/vcompany/transport/channel_transport.py
    - src/vcompany/transport/native.py
    - src/vcompany/transport/docker_channel.py
    - src/vcompany/daemon/agent_handle.py
    - src/vcompany/daemon/routing_state.py

key-decisions:
  - "Socket path convention: /tmp/vco-worker-{agent_id}.sock for native, /tmp/vco-sockets/ for docker"
  - "Workers spawned with start_new_session=True and stdin=DEVNULL to survive daemon death"
  - "Docker containers run detached (-d) with socket dir mount instead of interactive (-i) with piped stdin"

patterns-established:
  - "Transport spawn returns (reader, writer) tuple instead of Process object"
  - "Transport connect() method for reconnecting to surviving workers"
  - "AgentHandle prefers socket writer over process stdin for send()"

requirements-completed: [AUTO-02, AUTO-03]

# Metrics
duration: 2min
completed: 2026-03-31
---

# Phase 33 Plan 02: Head-Side Transport Refactor Summary

**Socket-based transports with detached workers, Unix domain socket communication, and reconnection support for daemon restart survival**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T16:50:53Z
- **Completed:** 2026-03-31T16:53:08Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Transports now return (reader, writer) socket pairs instead of Process objects
- NativeTransport spawns workers with --socket flag and start_new_session=True for daemon death survival
- DockerChannelTransport uses detached mode (-d) with socket directory mount, no -i or --rm
- AgentHandle supports dual communication: socket-first with process stdin fallback
- RoutingState persists transport_type per agent for reconnection routing

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor transports to socket-based communication** - `e067192` (feat)
2. **Task 2: Add socket support to AgentHandle and transport_type to RoutingState** - `98bb67d` (feat)

## Files Created/Modified
- `src/vcompany/transport/channel_transport.py` - Protocol updated: spawn returns (reader, writer), connect() added
- `src/vcompany/transport/native.py` - Socket-based spawn with --socket flag, detached sessions, connect/reconnect
- `src/vcompany/transport/docker_channel.py` - Detached docker run -d with /var/run/vco socket mount
- `src/vcompany/daemon/agent_handle.py` - attach_socket(), reader property, socket-aware send/is_alive/stop
- `src/vcompany/daemon/routing_state.py` - transport_type field added to AgentRouting

## Decisions Made
- Socket path convention: `/tmp/vco-worker-{agent_id}.sock` for native, `/tmp/vco-sockets/` directory for docker
- Workers spawned with `start_new_session=True` and `stdin=DEVNULL` -- no pipe dependency on daemon
- Docker uses detached mode with socket directory mount instead of interactive stdin piping
- AgentHandle.send() prefers socket writer, falls back to process stdin for backward compat

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Socket-based transport layer ready for Plan 03 reconnection logic
- transport_type in RoutingState enables reconnect_agents() to pick correct transport
- AgentHandle.reader property and attach_socket() ready for CompanyRoot integration

---
*Phase: 33-container-autonomy*
*Completed: 2026-03-31*
