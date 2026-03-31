---
phase: 33-container-autonomy
plan: 01
subsystem: transport
tags: [unix-socket, channel-protocol, reconnect, worker-autonomy, pydantic]

# Dependency graph
requires:
  - phase: 32-transport-implementations
    provides: ChannelTransport protocol, NativeTransport, DockerChannelTransport
provides:
  - ReconnectMessage in channel protocol (both worker and head-side)
  - Unix domain socket server for worker channel protocol
  - Socket mode for vco-worker (--socket flag)
  - cwd-relative state paths (.vco-state/{agent_id})
affects: [33-02 head-side transports, 33-03 reconnection flow]

# Tech tracking
tech-stack:
  added: []
  patterns: [unix-socket-server, reconnect-protocol, cwd-relative-state]

key-files:
  created:
    - packages/vco-worker/src/vco_worker/channel/socket_server.py
  modified:
    - packages/vco-worker/src/vco_worker/channel/messages.py
    - packages/vco-worker/src/vco_worker/config.py
    - packages/vco-worker/src/vco_worker/container/container.py
    - packages/vco-worker/src/vco_worker/main.py
    - src/vcompany/transport/channel/messages.py

key-decisions:
  - "Worker derives data_dir from Path.cwd() / .vco-state / agent_id, not from daemon config"
  - "SocketWriter proxy wraps current connection writer for seamless reconnection"

patterns-established:
  - "Socket server with stale socket cleanup before bind"
  - "ReconnectMessage triggers HealthReport response for state recovery"

requirements-completed: [AUTO-01, AUTO-03]

# Metrics
duration: 2min
completed: 2026-03-31
---

# Phase 33 Plan 01: Worker-Side Autonomy Summary

**ReconnectMessage in channel protocol, Unix socket server for worker, cwd-relative .vco-state paths**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T16:50:53Z
- **Completed:** 2026-03-31T16:52:47Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Added ReconnectMessage to both worker and head-side channel protocol (6th head-to-worker message type)
- Created Unix domain socket server with stale socket detection and cleanup
- Worker supports --socket mode for head reconnection without worker restart
- WorkerContainer now derives state from cwd (.vco-state/{agent_id}) instead of daemon-specified config path

## Task Commits

Each task was committed atomically:

1. **Task 1: Add ReconnectMessage to channel protocol and make data_dir cwd-relative** - `f17ca34` (feat)
2. **Task 2: Create Unix socket server and add socket mode to worker main** - `baa5680` (feat)

## Files Created/Modified
- `packages/vco-worker/src/vco_worker/channel/socket_server.py` - Unix domain socket server with stale cleanup
- `packages/vco-worker/src/vco_worker/channel/messages.py` - Added RECONNECT enum, ReconnectMessage class, updated HeadMessage union
- `packages/vco-worker/src/vco_worker/config.py` - data_dir default changed to None (deprecated)
- `packages/vco-worker/src/vco_worker/container/container.py` - data_dir derived from Path.cwd() / ".vco-state"
- `packages/vco-worker/src/vco_worker/main.py` - ReconnectMessage handling, _run_socket(), --socket flag
- `src/vcompany/transport/channel/messages.py` - Identical ReconnectMessage addition (head-side copy)

## Decisions Made
- Worker derives data_dir from cwd instead of config.data_dir -- state lives inside execution environment
- SocketWriter proxy pattern allows seamless writer replacement on reconnection
- Stale socket cleanup tries connecting first to avoid removing a live socket

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Worker has socket server and reconnect protocol -- ready for 33-02 (head-side socket transport)
- Head-side messages.py already has ReconnectMessage -- ready for 33-03 (reconnect flow)

---
*Phase: 33-container-autonomy*
*Completed: 2026-03-31*
