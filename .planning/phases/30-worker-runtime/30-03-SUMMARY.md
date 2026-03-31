---
phase: 30-worker-runtime
plan: 03
subsystem: runtime
tags: [asyncio, ndjson, worker, message-loop, pydantic]

# Dependency graph
requires:
  - phase: 30-worker-runtime/01
    provides: "Channel protocol (framing, messages, config, CLI)"
  - phase: 30-worker-runtime/02
    provides: "WorkerContainer, handler registry, lifecycle FSM"
provides:
  - "Worker main entry point with async message loop (run_worker)"
  - "Container bootstrap from StartMessage config blob"
  - "StdioWriter for public-API-only stdout transport"
  - "python -m vco_worker support via __main__.py"
affects: [31-head-orchestration, 32-container-bootstrap, 34-dead-code-removal]

# Tech tracking
tech-stack:
  added: []
  patterns: ["duck-typed writer protocol for testable async I/O", "StreamReader async-for line iteration for NDJSON"]

key-files:
  created:
    - packages/vco-worker/src/vco_worker/main.py
    - packages/vco-worker/src/vco_worker/__main__.py
    - tests/test_worker_main.py
  modified:
    - pyproject.toml

key-decisions:
  - "StdioWriter uses sync stdout.buffer.write + flush instead of private asyncio StreamWriter APIs"
  - "run_worker accepts duck-typed writer (write + drain) for easy test mocking"
  - "pytest asyncio_mode=auto configured in root pyproject.toml for all async tests"

patterns-established:
  - "Duck-typed writer: any object with .write(bytes) and async .drain() works as channel output"
  - "Message loop pattern: async-for on StreamReader with decode_head per line"

requirements-completed: [WORK-03, WORK-04]

# Metrics
duration: 2min
completed: 2026-03-31
---

# Phase 30 Plan 03: Worker Main Loop Summary

**Async worker main loop reading HeadMessages from stdin, dispatching to WorkerContainer, writing NDJSON responses to stdout via duck-typed writer**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T15:24:51Z
- **Completed:** 2026-03-31T15:26:18Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments
- Worker main loop (`run_worker`) processes full HeadMessage lifecycle: Start, GiveTask, Inbound, HealthCheck, Stop
- Bootstrap from StartMessage config blob creates WorkerContainer with correct handler via registry
- StdioWriter uses only public asyncio APIs -- no FlowControlMixin, no private StreamWriter construction
- 4 integration tests prove end-to-end message flow with simulated streams

## Task Commits

Each task was committed atomically:

1. **Task 1: Create worker main loop with message dispatch and bootstrap** - `7e8ebb2` (feat)

## Files Created/Modified
- `packages/vco-worker/src/vco_worker/main.py` - Worker entry point with run_worker async loop, bootstrap_container, StdioWriter
- `packages/vco-worker/src/vco_worker/__main__.py` - python -m vco_worker support
- `tests/test_worker_main.py` - 4 integration tests for message loop
- `pyproject.toml` - Added asyncio_mode=auto and vco-worker pythonpath

## Decisions Made
- Used duck-typed writer protocol instead of asyncio.StreamWriter for testability and public-API-only approach
- StdioWriter does synchronous writes to stdout.buffer (acceptable for NDJSON line output, no backpressure concern)
- Configured pytest asyncio_mode=auto at root level so all workspace packages benefit

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- vco-worker is now a complete standalone runtime: channel protocol, config, container, handlers, and main loop
- Ready for Phase 31 (head-orchestration) to spawn worker processes and communicate via transport channel
- Worker can receive StartMessage, bootstrap container, process tasks/messages/health checks, and shut down cleanly

## Self-Check: PASSED

---
*Phase: 30-worker-runtime*
*Completed: 2026-03-31*
