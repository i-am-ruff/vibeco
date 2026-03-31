---
phase: 31-head-refactor
plan: "01"
subsystem: daemon
tags: [agent-handle, routing-state, pydantic, transport-channel]
dependency_graph:
  requires: [transport-channel-protocol, health-report-model]
  provides: [agent-handle-model, routing-state-persistence]
  affects: [company-root, runtime-api, mention-router]
tech_stack:
  added: []
  patterns: [pydantic-private-attr, staleness-threshold, ndjson-stdin-transport]
key_files:
  created:
    - src/vcompany/daemon/agent_handle.py
    - src/vcompany/daemon/routing_state.py
    - tests/test_agent_handle.py
    - tests/test_routing_state.py
  modified: []
decisions:
  - "AgentHandle uses PrivateAttr for runtime state -- process, health cache excluded from serialization"
  - "Staleness threshold 120s for health reports -- matches typical health-check interval"
  - "RoutingState persists as JSON -- simple, human-readable, matches project filesystem-first pattern"
  - "attach_process() method instead of constructor param -- process assigned after subprocess creation"
metrics:
  duration: "2min"
  completed: "2026-03-31"
---

# Phase 31 Plan 01: AgentHandle Model and Routing State Summary

AgentHandle Pydantic model with NDJSON stdin transport and staleness-aware health caching; RoutingState persistence with JSON save/load for daemon restart resilience.

## What Was Built

### AgentHandle (`src/vcompany/daemon/agent_handle.py`)
- Pydantic model storing agent metadata (id, type, capabilities, channel_id, handler_type, config)
- `send()` encodes HeadMessage via NDJSON framing and writes to subprocess stdin
- `update_health()` caches HealthReportMessage with UTC timestamp
- `health_report()` returns HealthReport with staleness detection (120s threshold -> "unreachable")
- `state` property returns last reported status or "unknown"
- `is_alive` property checks subprocess returncode
- `stop_process()` sends StopMessage with graceful shutdown + timeout kill
- Runtime state (process, health cache) uses PrivateAttr -- excluded from Pydantic serialization

### RoutingState (`src/vcompany/daemon/routing_state.py`)
- AgentRouting model: agent_id, channel_id, category_id, agent_type, handler_type, config, capabilities
- RoutingState: dict of AgentRouting with add/remove/get operations
- `save()` persists as indented JSON, creates parent directories
- `load()` returns empty state when file missing, raises ValidationError on corruption

## Test Coverage

- **test_agent_handle.py**: 13 tests -- construction, send with mock stdin, send without process, health caching, state property, health_report with staleness, is_alive states
- **test_routing_state.py**: 9 tests -- round-trip save/load, CRUD operations, parent dir creation, missing file, corrupted JSON

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for AgentHandle | aa76023 | tests/test_agent_handle.py |
| 1 (GREEN) | Implement AgentHandle model | 01f7beb | src/vcompany/daemon/agent_handle.py |
| 2 | Routing state persistence | a486afe | src/vcompany/daemon/routing_state.py, tests/test_routing_state.py |

## Decisions Made

1. **PrivateAttr for runtime state** -- Process handle and health cache are runtime-only, not serialized. This keeps AgentHandle JSON-safe for potential future persistence while allowing full subprocess management.
2. **120s staleness threshold** -- Matches expected health-check polling interval. Configurable via module constant.
3. **attach_process() pattern** -- Process is attached after creation rather than at construction time, since subprocess.Process requires async creation.
4. **JSON persistence for routing** -- Filesystem-first approach consistent with project conventions (no database).

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None -- all functionality is fully wired.

## Self-Check: PASSED
