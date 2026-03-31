---
phase: 30-worker-runtime
plan: 01
subsystem: worker-runtime
tags: [pydantic, uv-workspace, ndjson, click, channel-protocol]

# Dependency graph
requires:
  - phase: 29-transport-channel-protocol
    provides: "Channel protocol message models and NDJSON framing"
provides:
  - "vco-worker standalone Python package installable via uv workspace"
  - "WorkerConfig Pydantic model for config blob validation"
  - "Channel protocol messages duplicated inside worker package (no vcompany dependency)"
  - "Handler registry with lazy string-based imports"
  - "Four CLI commands (report, ask, signal, send-file) producing NDJSON"
affects: [30-02, 30-03, 31-head-refactor, 32-transport-implementations]

# Tech tracking
tech-stack:
  added: [uv-workspace]
  patterns: [channel-protocol-duplication, lazy-handler-registry, cli-ndjson-stdout]

key-files:
  created:
    - packages/vco-worker/pyproject.toml
    - packages/vco-worker/src/vco_worker/__init__.py
    - packages/vco-worker/src/vco_worker/config.py
    - packages/vco-worker/src/vco_worker/channel/__init__.py
    - packages/vco-worker/src/vco_worker/channel/messages.py
    - packages/vco-worker/src/vco_worker/channel/framing.py
    - packages/vco-worker/src/vco_worker/handler/__init__.py
    - packages/vco-worker/src/vco_worker/handler/registry.py
    - packages/vco-worker/src/vco_worker/cli.py
    - tests/test_worker_config.py
  modified:
    - pyproject.toml

key-decisions:
  - "Duplicate channel protocol files verbatim into worker package for zero vcompany dependency"
  - "Handler registry uses lazy string-based imports so it can be defined before handler classes exist"
  - "CLI commands write NDJSON to stdout.buffer for binary-safe transport"

patterns-established:
  - "uv workspace: root pyproject.toml has [tool.uv.workspace] members = ['packages/*']"
  - "Channel protocol duplication: worker has its own copy of messages.py and framing.py"
  - "CLI-to-channel: click commands encode Pydantic models to NDJSON on stdout"

requirements-completed: [WORK-01, WORK-02, WORK-04]

# Metrics
duration: 2min
completed: 2026-03-31
---

# Phase 30 Plan 01: Worker Package Scaffold Summary

**Standalone vco-worker package with channel protocol, WorkerConfig model, handler registry, and 4 NDJSON CLI commands -- zero vcompany imports**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T15:13:41Z
- **Completed:** 2026-03-31T15:16:01Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- vco-worker installs as standalone package via uv workspace with no discord.py/anthropic/libtmux dependencies
- Channel protocol (10 message types + NDJSON framing) duplicated inside worker package
- WorkerConfig Pydantic model validates config blobs with handler_type, capabilities, gsd_command, persona, env_vars
- Handler registry maps "session", "conversation", "transient" to handler classes via lazy imports
- Four CLI commands (vco-worker-report, vco-worker-ask, vco-worker-signal, vco-worker-send-file) produce valid NDJSON

## Task Commits

Each task was committed atomically:

1. **Task 1: Create vco-worker package structure with channel protocol and config** - `07ffaeb` (feat)
2. **Task 2: Create handler registry and CLI entry point commands** - `70a1b9a` (feat)

## Files Created/Modified
- `pyproject.toml` - Added [tool.uv.workspace] with members = ["packages/*"]
- `packages/vco-worker/pyproject.toml` - Standalone package with 5 entry points, no heavy deps
- `packages/vco-worker/src/vco_worker/__init__.py` - Package init with version
- `packages/vco-worker/src/vco_worker/config.py` - WorkerConfig Pydantic model
- `packages/vco-worker/src/vco_worker/channel/__init__.py` - Re-exports all protocol names
- `packages/vco-worker/src/vco_worker/channel/messages.py` - 10 message models (verbatim copy)
- `packages/vco-worker/src/vco_worker/channel/framing.py` - NDJSON encode/decode (verbatim copy)
- `packages/vco-worker/src/vco_worker/handler/__init__.py` - Handler package init
- `packages/vco-worker/src/vco_worker/handler/registry.py` - Lazy import handler registry
- `packages/vco-worker/src/vco_worker/cli.py` - Four click commands writing NDJSON to stdout
- `tests/test_worker_config.py` - 6 tests for config validation and channel round-trip

## Decisions Made
- Duplicated channel protocol files verbatim rather than creating a shared library -- keeps worker truly standalone
- Handler registry uses string-based lazy imports ("module:Class") so it can exist before handler classes are created in Plan 02
- CLI commands write to sys.stdout.buffer (binary) for transport-safe NDJSON output

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Package foundation ready for Plan 02 (WorkerContainer with adapted handlers and lifecycle FSMs)
- Handler registry skeleton in place -- Plan 02 creates the actual handler classes it references
- CLI commands ready for integration with worker main loop in Plan 03

## Self-Check: PASSED

All 10 created files verified present. Both task commits (07ffaeb, 70a1b9a) verified in git log.

---
*Phase: 30-worker-runtime*
*Completed: 2026-03-31*
