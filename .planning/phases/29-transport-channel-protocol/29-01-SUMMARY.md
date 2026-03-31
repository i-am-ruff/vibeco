---
phase: 29-transport-channel-protocol
plan: 01
subsystem: transport
tags: [pydantic, ndjson, protocol, channel, discriminated-union, typeadapter]

# Dependency graph
requires: []
provides:
  - "10 typed Pydantic v2 message models for head-worker channel protocol"
  - "HeadMessage/WorkerMessage discriminated unions"
  - "NDJSON encode/decode_head/decode_worker framing functions"
  - "PROTOCOL_VERSION constant"
affects: [30-worker-runtime, 31-head-refactor, 32-container-bootstrap, 33-docker-channel, 34-dead-code-removal]

# Tech tracking
tech-stack:
  added: []
  patterns: [discriminated-union-with-strenum, typeadapter-for-union-decode, ndjson-framing]

key-files:
  created:
    - src/vcompany/transport/channel/__init__.py
    - src/vcompany/transport/channel/messages.py
    - src/vcompany/transport/channel/framing.py
    - tests/test_channel_protocol.py
  modified: []

key-decisions:
  - "Used StrEnum for message type discriminators -- serializes to human-readable strings in JSON"
  - "Separate TypeAdapter per direction -- decode_head and decode_worker enforce direction safety at the type level"
  - "encode() accepts any BaseModel -- keeps framing generic while decode is direction-specific"

patterns-established:
  - "Channel protocol message pattern: StrEnum type + Literal default + discriminated union"
  - "NDJSON framing pattern: encode(msg) -> bytes, decode_X(data) -> typed union"

requirements-completed: [CHAN-01]

# Metrics
duration: 2min
completed: 2026-03-31
---

# Phase 29 Plan 01: Channel Protocol Message Models Summary

**10 Pydantic v2 message models with StrEnum discriminated unions and NDJSON framing for bidirectional head-worker transport**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T06:26:39Z
- **Completed:** 2026-03-31T06:28:24Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments
- Defined all 10 message types (5 head-to-worker, 5 worker-to-head) as typed Pydantic v2 models
- Created NDJSON encode/decode functions with TypeAdapter-based discriminated union parsing
- Full test suite: 14 tests covering round-trip serialization, cross-direction rejection, and malformed input handling
- Zero heavy dependencies -- protocol module uses only pydantic + stdlib

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests** - `01198b5` (test)
2. **Task 1 (GREEN): Implementation** - `814ca46` (feat)

## Files Created/Modified
- `src/vcompany/transport/channel/messages.py` - 10 message models, 2 StrEnums, 2 discriminated unions
- `src/vcompany/transport/channel/framing.py` - encode(), decode_head(), decode_worker(), PROTOCOL_VERSION
- `src/vcompany/transport/channel/__init__.py` - Public API re-exports with __all__
- `tests/test_channel_protocol.py` - 14 parametrized tests (round-trip, cross-direction, malformed)

## Decisions Made
- Used StrEnum for message type discriminators -- serializes to human-readable strings in JSON
- Separate TypeAdapter per direction -- decode_head and decode_worker enforce direction safety at the type level
- encode() accepts any BaseModel -- keeps framing generic while decode is direction-specific

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Channel protocol is the foundation for all subsequent v4.0 phases
- Worker runtime (phase 30) can import these message types directly
- Head refactor (phase 31) can use encode/decode for transport communication

---
*Phase: 29-transport-channel-protocol*
*Completed: 2026-03-31*
