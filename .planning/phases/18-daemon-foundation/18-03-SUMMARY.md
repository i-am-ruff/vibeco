---
phase: 18-daemon-foundation
plan: 03
subsystem: daemon
tags: [cli, unix-socket, ndjson, click, signal-handling, pid-file]

# Dependency graph
requires:
  - phase: 18-daemon-foundation plan 02
    provides: Daemon class with PID file, signal handlers, SocketServer, bot lifecycle
provides:
  - DaemonClient synchronous NDJSON socket client for CLI-to-daemon communication
  - vco down command for stopping daemon via SIGTERM
  - Refactored vco up that starts Daemon instead of bot directly
affects: [19-cli-api-protocol, 20-bot-extraction, 21-cli-commands]

# Tech tracking
tech-stack:
  added: []
  patterns: [sync-socket-client-for-cli, pid-based-process-management]

key-files:
  created:
    - src/vcompany/daemon/client.py
    - src/vcompany/cli/down_cmd.py
    - tests/test_down_cmd.py
  modified:
    - src/vcompany/cli/up_cmd.py
    - src/vcompany/cli/main.py

key-decisions:
  - "DaemonClient uses stdlib socket (sync) not httpx -- CLI commands are blocking, no async needed"
  - "vco down uses os.kill(pid, 0) polling rather than socket shutdown -- works even if socket is broken"

patterns-established:
  - "CLI-to-daemon: DaemonClient context manager with connect/call/close"
  - "Process lifecycle: PID file + SIGTERM + poll for exit"

requirements-completed: [DAEMON-05]

# Metrics
duration: 3min
completed: 2026-03-29
---

# Phase 18 Plan 03: CLI Wiring Summary

**Sync socket client, vco down with SIGTERM/PID polling, and vco up refactored to start Daemon lifecycle**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-29T02:13:45Z
- **Completed:** 2026-03-29T02:16:32Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- DaemonClient with hello handshake and synchronous RPC call method for future CLI commands
- vco down reads PID file, sends SIGTERM, polls for clean exit with timeout
- vco up now creates Daemon and calls daemon.run() instead of bot.run()
- vco down registered in CLI group alongside existing commands

## Task Commits

Each task was committed atomically:

1. **Task 1: Sync socket client and vco down command** - `48c4027` (feat)
2. **Task 2: Refactor vco up and register vco down** - `8c4ed77` (feat)

## Files Created/Modified
- `src/vcompany/daemon/client.py` - Synchronous NDJSON client with connect/call/close and context manager
- `src/vcompany/cli/down_cmd.py` - vco down command: PID lookup, SIGTERM, poll, stale PID handling
- `tests/test_down_cmd.py` - 4 tests: no PID file, stale PID, real SIGTERM, invalid PID
- `src/vcompany/cli/up_cmd.py` - Replaced bot_instance.run() with Daemon construction and daemon.run()
- `src/vcompany/cli/main.py` - Registered down command in CLI group

## Decisions Made
- DaemonClient uses stdlib socket (synchronous) -- CLI commands are blocking, no async overhead needed
- vco down uses os.kill(pid, 0) polling rather than socket-based shutdown -- more resilient when socket is broken
- Added PermissionError handling in down command for edge case where PID belongs to another user

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ProcessNotFoundError to ProcessLookupError**
- **Found during:** Task 1 (down_cmd.py)
- **Issue:** Plan used `ProcessNotFoundError` which doesn't exist in Python; correct exception is `ProcessLookupError`
- **Fix:** Used `ProcessLookupError` throughout
- **Files modified:** src/vcompany/cli/down_cmd.py
- **Verification:** All 4 tests pass
- **Committed in:** 48c4027

**2. [Rule 2 - Missing Critical] Added PermissionError handling in down command**
- **Found during:** Task 1 (down_cmd.py)
- **Issue:** Plan didn't handle PermissionError from os.kill() when PID belongs to another user
- **Fix:** Added PermissionError catch in both the alive-check and poll-loop sections
- **Files modified:** src/vcompany/cli/down_cmd.py
- **Verification:** Code handles edge case gracefully
- **Committed in:** 48c4027

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both fixes essential for correctness. No scope creep.

## Issues Encountered
- Test for SIGTERM initially failed due to zombie process not being reaped -- fixed by using `start_new_session=True` and a background reaper thread to match real-world scenario where daemon is not a child process

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 18 (Daemon Foundation) is functionally complete
- DaemonClient ready for Phase 21 CLI commands to use
- Socket protocol and server from 18-01/18-02 provide the daemon-side infrastructure
- vco up/down lifecycle is end-to-end operational

---
*Phase: 18-daemon-foundation*
*Completed: 2026-03-29*
