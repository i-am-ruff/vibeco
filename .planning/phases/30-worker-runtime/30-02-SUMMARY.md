---
phase: 30-worker-runtime
plan: 02
subsystem: infra
tags: [worker, container, lifecycle-fsm, statemachine, pydantic, aiosqlite, channel-protocol]

# Dependency graph
requires:
  - phase: 30-worker-runtime/01
    provides: "channel protocol (messages, framing), WorkerConfig, handler registry, CLI entry point"
provides:
  - "WorkerContainer with channel-based communication (no Discord, no CommunicationPort)"
  - "ContainerLifecycle, GsdLifecycle, EventDrivenLifecycle FSMs"
  - "MemoryStore async SQLite persistence for KV and checkpoints"
  - "HealthReport model (worker-only, stripped of head-side fields)"
  - "GsdSessionHandler adapted for InboundMessage with checkpoint/restore"
  - "WorkerConversationHandler with relay mode (no anthropic SDK)"
  - "PMTransientHandler with prefix dispatch and stuck detection"
  - "Handler protocol definitions (SessionHandler, ConversationHandler, TransientHandler)"
affects: [30-worker-runtime/03, 31-head-extraction, 34-dead-code]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Channel-based container communication (send_report/send_signal via NDJSON writer)"
    - "Handler protocols using WorkerContainer and InboundMessage (not AgentContainer/MessageContext)"
    - "Lazy FSM selection via agent_type in _create_lifecycle()"

key-files:
  created:
    - packages/vco-worker/src/vco_worker/container/container.py
    - packages/vco-worker/src/vco_worker/container/state_machine.py
    - packages/vco-worker/src/vco_worker/container/context.py
    - packages/vco-worker/src/vco_worker/container/health.py
    - packages/vco-worker/src/vco_worker/container/memory_store.py
    - packages/vco-worker/src/vco_worker/agent/gsd_lifecycle.py
    - packages/vco-worker/src/vco_worker/agent/gsd_phases.py
    - packages/vco-worker/src/vco_worker/agent/event_driven_lifecycle.py
    - packages/vco-worker/src/vco_worker/handler/protocol.py
    - packages/vco-worker/src/vco_worker/handler/session.py
    - packages/vco-worker/src/vco_worker/handler/conversation.py
    - packages/vco-worker/src/vco_worker/handler/transient.py
    - tests/test_worker_container.py
  modified:
    - packages/vco-worker/src/vco_worker/container/__init__.py
    - packages/vco-worker/src/vco_worker/agent/__init__.py

key-decisions:
  - "HealthReport stripped of transport_type, docker_container_id, docker_image fields -- head adds transport metadata"
  - "WorkerConversationHandler uses relay mode when no conversation subprocess is wired"
  - "InboundMessage.sender='pm' or channel.startswith('review-') replaces MessageContext.is_pm_reply"

patterns-established:
  - "WorkerContainer._write_message() for all outbound channel communication"
  - "Handler.handle_message takes InboundMessage instead of MessageContext"
  - "Container owns handler state (timestamps, stuck set, conversation) -- handlers are stateless"

requirements-completed: [WORK-03, WORK-05]

# Metrics
duration: 4min
completed: 2026-03-31
---

# Phase 30 Plan 02: Worker Container Runtime Summary

**WorkerContainer with lifecycle FSM, channel-based communication, and three adapted handler types (session, conversation, transient) -- complete agent runtime inside worker process**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-31T15:18:14Z
- **Completed:** 2026-03-31T15:22:41Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments
- Extracted all container infrastructure (FSMs, context, health, memory store) into worker package with zero daemon-side dependencies
- Created WorkerContainer class with channel-based communication replacing all CommunicationPort/Discord calls
- Adapted all three handler types (GsdSessionHandler, WorkerConversationHandler, PMTransientHandler) to use InboundMessage and send_report
- 8 tests covering lifecycle transitions, health reporting, task queue, handler dispatch, and channel output

## Task Commits

Each task was committed atomically:

1. **Task 1: Extract container infrastructure (FSMs, context, health, memory store)** - `44cae78` (feat)
2. **Task 2: Create WorkerContainer and adapted handlers with channel communication** - `1feae8c` (feat)

## Files Created/Modified
- `packages/vco-worker/src/vco_worker/container/container.py` - WorkerContainer with lifecycle FSM, channel output, health, task queue
- `packages/vco-worker/src/vco_worker/container/state_machine.py` - ContainerLifecycle 8-state FSM
- `packages/vco-worker/src/vco_worker/container/context.py` - ContainerContext Pydantic model
- `packages/vco-worker/src/vco_worker/container/health.py` - HealthReport (worker-only, no HealthTree)
- `packages/vco-worker/src/vco_worker/container/memory_store.py` - MemoryStore async SQLite for KV and checkpoints
- `packages/vco-worker/src/vco_worker/agent/gsd_lifecycle.py` - GsdLifecycle compound FSM
- `packages/vco-worker/src/vco_worker/agent/gsd_phases.py` - GsdPhase enum and CheckpointData model
- `packages/vco-worker/src/vco_worker/agent/event_driven_lifecycle.py` - EventDrivenLifecycle compound FSM
- `packages/vco-worker/src/vco_worker/handler/protocol.py` - SessionHandler, ConversationHandler, TransientHandler protocols
- `packages/vco-worker/src/vco_worker/handler/session.py` - GsdSessionHandler for worker
- `packages/vco-worker/src/vco_worker/handler/conversation.py` - WorkerConversationHandler with relay mode
- `packages/vco-worker/src/vco_worker/handler/transient.py` - PMTransientHandler with stuck detection
- `tests/test_worker_container.py` - 8 tests for container lifecycle and handlers

## Decisions Made
- HealthReport stripped of transport_type, docker_container_id, docker_image fields -- these are head-side concepts; worker reports status via HealthReportMessage, head adds transport metadata when building health tree
- WorkerConversationHandler uses relay mode (forwards message via channel report) when no conversation subprocess is wired, avoiding anthropic SDK dependency
- PM review detection uses `message.sender == "pm"` or `message.channel.startswith("review-")` to replace daemon-side `MessageContext.is_pm_reply`

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Known Stubs

None -- all functionality is wired and operational.

## Next Phase Readiness
- WorkerContainer is ready for Plan 03 (main loop integration)
- Handler registry from Plan 01 can instantiate all three handler types
- Channel protocol messages flow correctly through container

## Self-Check: PASSED

All 13 created files verified present. Both task commits (44cae78, 1feae8c) verified in git log.

---
*Phase: 30-worker-runtime*
*Completed: 2026-03-31*
