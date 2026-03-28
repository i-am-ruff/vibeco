---
phase: 11-container-architecture-fixes
plan: "01"
subsystem: container-fsm
tags: [fsm, lifecycle, blocked, stopping, health]
dependency_graph:
  requires: []
  provides: [blocked-fsm-state, stopping-fsm-state, two-phase-stop, health-blocked-reason]
  affects: [container, supervisor, gsd-agent, company-agent]
tech_stack:
  added: []
  patterns: [two-phase-stop, erlang-blocked-state, history-state-restore]
key_files:
  created:
    - tests/test_container_blocked.py
    - tests/test_container_stopping.py
  modified:
    - src/vcompany/container/state_machine.py
    - src/vcompany/agent/gsd_lifecycle.py
    - src/vcompany/agent/event_driven_lifecycle.py
    - src/vcompany/agent/continuous_lifecycle.py
    - src/vcompany/container/health.py
    - src/vcompany/container/container.py
    - src/vcompany/agent/gsd_agent.py
    - src/vcompany/supervisor/supervisor.py
    - tests/test_container_lifecycle.py
    - tests/test_continuous_lifecycle.py
    - tests/test_event_driven_lifecycle.py
decisions:
  - "BLOCKED and STOPPING added to all 4 lifecycle FSMs (ContainerLifecycle, GsdLifecycle, EventDrivenLifecycle, ContinuousLifecycle) for consistency with AgentContainer.stop()"
  - "block()/unblock() methods are synchronous on AgentContainer since FSM transitions are sync; no async needed"
  - "GsdAgent mark_blocked/clear_blocked kept as thin wrappers over block()/unblock() for backward API compatibility"
  - "ContinuousLifecycle extended with begin_stop/finish_stop (not in plan scope) to fix AgentContainer.stop() incompatibility"
metrics:
  duration_seconds: 1097
  completed_date: "2026-03-28"
  tasks_completed: 2
  files_changed: 11
---

# Phase 11 Plan 01: Add BLOCKED and STOPPING FSM States Summary

BLOCKED and STOPPING added as real FSM states across all lifecycle machines with two-phase stop, GsdAgent blocked tracking migrated from boolean to FSM, and health reporting updated.

## What Was Built

**Task 1: FSM state additions and health model**

Added `blocked` and `stopping` states to ContainerLifecycle, GsdLifecycle, and EventDrivenLifecycle with:
- `block = running.to(blocked)` / `unblock = blocked.to(running[.h])` transitions
- `begin_stop = (running|sleeping|errored|blocked).to(stopping)` and `finish_stop = stopping.to(stopped)` replacing old bare `stop` transition
- `error` transition extended to include `blocked` as a valid source state
- HistoryState (`running.h`) used in `unblock` for GsdLifecycle and EventDrivenLifecycle so inner phase/sub-state is restored on unblock

HealthReport gained `blocked_reason: str | None = None` field (ARCH-03).
CompanyHealthTree gained `company_agents: list[HealthNode] = []` field.
GsdAgent `_VALID_STATES` frozenset extended with "blocked" and "stopping".

37 new tests in test_container_blocked.py and test_container_stopping.py — all pass.

**Task 2: Container and supervisor integration**

AgentContainer:
- `_blocked_reason: str | None = None` attribute added
- `block(reason: str)` and `unblock()` sync methods added
- `stop()` now uses `begin_stop()` + `finish_stop()` two-phase transition
- `health_report()` includes `blocked_reason=self._blocked_reason`

GsdAgent:
- Removed `_blocked_since: float | None` boolean tracking
- Removed `import time`
- `is_blocked` now returns `self.state == "blocked"` (FSM-based, ARCH-03)
- `mark_blocked()` delegates to `self.block(reason)`
- `clear_blocked()` delegates to `self.unblock()`

Supervisor:
- State-change event trigger: added "stopping" to `("errored", "stopped", "stopping")`
- Health change notifications: added "blocked" and "stopping" to notification states
- `_monitor_child`: added `elif container.state == "stopping": pass` and `elif container.state == "blocked": pass` cases — no restart for either
- All stop-skip guards extended from `("stopped", "destroyed")` to `("stopped", "destroyed", "stopping")`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Extended ContinuousLifecycle with begin_stop/finish_stop**
- **Found during:** Task 2
- **Issue:** `AgentContainer.stop()` updated to use `begin_stop/finish_stop` but `ContinuousLifecycle` only had old bare `stop`. `ContinuousAgent` (which inherits `AgentContainer.stop()`) would fail at runtime with `AttributeError: 'ContinuousLifecycle' has no attribute 'begin_stop'`
- **Fix:** Added `stopping = State()`, `begin_stop`, and `finish_stop` transitions to `ContinuousLifecycle` matching the same pattern. Removed old `stop` transition from ContinuousLifecycle.
- **Files modified:** `src/vcompany/agent/continuous_lifecycle.py`, `tests/test_continuous_lifecycle.py`
- **Commit:** f522260

**2. [Rule 1 - Bug] Updated existing FSM tests using old stop() API**
- **Found during:** Task 2
- **Issue:** test_container_lifecycle.py, test_continuous_lifecycle.py, test_event_driven_lifecycle.py called `sm.stop()` which no longer exists on updated FSMs
- **Fix:** Updated all affected tests to use `sm.begin_stop()` + `sm.finish_stop()` two-phase pattern
- **Files modified:** `tests/test_container_lifecycle.py`, `tests/test_continuous_lifecycle.py`, `tests/test_event_driven_lifecycle.py`
- **Commit:** f522260

**3. [Rule 1 - Bug] Fixed current_state API deprecation in new tests**
- **Found during:** Task 1 (TDD RED->GREEN)
- **Issue:** Initial test code used deprecated `current_state.id` (raises `TypeError: unhashable type: 'OrderedSet'` for compound states)
- **Fix:** Tests updated to use `current_state_value` (outer state) and `configuration_values` (compound state) per existing test conventions
- **Commit:** 8b87fa5

## Pre-existing Failures (Out of Scope)

The following test failures existed before this plan and are unrelated:
- `tests/test_pm_tier.py::test_low_confidence_escalates_to_strategist` — Claude CLI process communication error (external dependency)
- `tests/test_report_cmd.py` (4 tests) — httpx import path mismatch in mocks

These are logged to deferred-items.md.

## Known Stubs

None — all FSM transitions are fully wired with real state transitions. Health report includes blocked_reason. Supervisor correctly handles all new states.

## Self-Check: PASSED

All key files verified present. Both commits verified in git log.

| Check | Result |
|-------|--------|
| src/vcompany/container/state_machine.py | FOUND |
| src/vcompany/agent/gsd_lifecycle.py | FOUND |
| src/vcompany/container/health.py | FOUND |
| src/vcompany/container/container.py | FOUND |
| tests/test_container_blocked.py | FOUND |
| tests/test_container_stopping.py | FOUND |
| Commit 8b87fa5 (Task 1) | FOUND |
| Commit f522260 (Task 2) | FOUND |
