---
phase: 18-daemon-foundation
plan: 02
subsystem: daemon
tags: [asyncio, unix-socket, ndjson, pid-management, signal-handling, daemon]

# Dependency graph
requires:
  - phase: 18-daemon-foundation-01
    provides: "NDJSON protocol Pydantic models and shared path constants"
provides:
  - "SocketServer class with NDJSON protocol, hello handshake, ping, subscribe, event broadcast"
  - "Daemon class with PID lifecycle, signal handling, socket server ownership, bot co-start"
affects: [18-daemon-foundation, 19-cli-protocol, 20-extract-to-daemon]

# Tech tracking
tech-stack:
  added: []
  patterns: [asyncio-unix-socket-server, pid-file-lifecycle, signal-to-event-bridge]

key-files:
  created:
    - src/vcompany/daemon/server.py
    - src/vcompany/daemon/daemon.py
    - tests/test_daemon_socket.py
    - tests/test_daemon.py
  modified: []

key-decisions:
  - "Used asyncio.start_unix_server for socket server -- stdlib, no new deps"
  - "Signal handlers set asyncio.Event only -- no async work in signal context"
  - "Bot typed as object (not VcoBot) to avoid import coupling in daemon module"
  - "Socket permissions set to 0o600 for security"

patterns-established:
  - "SocketServer: register_method() for custom handlers, _dispatch routes by name"
  - "Hello-first handshake enforcement before any other method calls"
  - "Daemon lifecycle: PID check -> PID write -> signals -> socket -> bot -> wait -> shutdown -> cleanup"
  - "Ordered shutdown: server.stop() before bot.close()"

requirements-completed: [DAEMON-01, DAEMON-02, DAEMON-03, DAEMON-04, DAEMON-06, SOCK-01, SOCK-05]

# Metrics
duration: 3min
completed: 2026-03-29
---

# Phase 18 Plan 02: Daemon and Socket Server Summary

**Runtime daemon with PID lifecycle management and NDJSON Unix socket server supporting hello handshake, ping, subscribe, and event broadcast**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-29T02:08:42Z
- **Completed:** 2026-03-29T02:11:57Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- SocketServer class handling NDJSON client connections with hello-first handshake enforcement
- Built-in methods: hello (version validation), ping (pong), subscribe (event types), custom method registration
- Event broadcast to subscribed clients with dead-client cleanup
- Daemon class with full PID lifecycle: stale detection, write on start, cleanup on exit
- SIGTERM/SIGINT handling via asyncio.Event (signal-safe, no async in handler)
- Bot co-start via asyncio.create_task(bot.start(token)) sharing the event loop
- Ordered shutdown sequence: socket server stops before bot closes
- 15 passing tests total (9 socket, 6 daemon)

## Task Commits

Each task was committed atomically:

1. **Task 1: SocketServer class** - `77302ca` (feat)
2. **Task 2: Daemon class with lifecycle management** - `dc400a5` (feat)

## Files Created/Modified
- `src/vcompany/daemon/server.py` - SocketServer with NDJSON protocol, client management, event broadcast
- `src/vcompany/daemon/daemon.py` - Daemon class with PID, signals, socket server, bot co-start
- `tests/test_daemon_socket.py` - 9 tests: connection, handshake, ping, subscribe, events, permissions, errors
- `tests/test_daemon.py` - 6 tests: PID lifecycle, stale cleanup, SIGTERM, bot co-start, shutdown order

## Decisions Made
- Used asyncio.start_unix_server (stdlib) for socket server -- zero new dependencies
- Signal handlers only set asyncio.Event -- avoids async-in-signal-context bugs
- Bot parameter typed as `object` not `VcoBot` to avoid importing discord.py in daemon module
- Socket file permissions set to 0o600 for security (only owner can connect)
- Used asyncio.run() wrappers in tests instead of @pytest.mark.asyncio due to old pytest-asyncio version

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used ProcessLookupError instead of ProcessNotFoundError**
- **Found during:** Task 2 (Daemon class)
- **Issue:** Plan referenced `ProcessNotFoundError` which doesn't exist in Python stdlib; the correct exception is `ProcessLookupError`
- **Fix:** Used `ProcessLookupError` in _check_already_running
- **Files modified:** src/vcompany/daemon/daemon.py
- **Verification:** test_stale_pid_cleanup passes
- **Committed in:** dc400a5 (Task 2 commit)

**2. [Rule 3 - Blocking] Wrapped async tests with asyncio.run() instead of @pytest.mark.asyncio**
- **Found during:** Task 1 (SocketServer tests)
- **Issue:** pytest-asyncio 1.3.0 is too old for @pytest.mark.asyncio with pytest 9.x
- **Fix:** Used sync test functions wrapping async def _test() with asyncio.run()
- **Files modified:** tests/test_daemon_socket.py, tests/test_daemon.py
- **Verification:** All 15 tests pass
- **Committed in:** 77302ca, dc400a5

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Daemon and SocketServer ready for CLI wiring in Plan 03
- `vco up` can instantiate Daemon and call daemon.run()
- Protocol methods (hello, ping, subscribe) available for CLI client to call
- Custom method registration ready for future Phase 19-20 API methods

---
*Phase: 18-daemon-foundation*
*Completed: 2026-03-29*
