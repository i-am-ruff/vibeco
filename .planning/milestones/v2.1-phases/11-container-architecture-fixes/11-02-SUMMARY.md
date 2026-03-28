---
phase: 11-container-architecture-fixes
plan: "02"
subsystem: container-wiring
tags: [comm-port, company-root, strategist, health-display, noop-port]
dependency_graph:
  requires: [blocked-fsm-state, stopping-fsm-state, health-blocked-reason]
  provides: [noop-comm-port, strategist-company-child, comm-port-wiring, health-tree-display]
  affects: [company-root, supervisor, project-supervisor, bot-client, health-embed, health-cog]
tech_stack:
  added: []
  patterns: [noop-stub, supervisor-comm-port-injection, company-level-agent]
key_files:
  created:
    - tests/test_comm_port_wiring.py
  modified:
    - src/vcompany/container/communication.py
    - src/vcompany/supervisor/supervisor.py
    - src/vcompany/supervisor/company_root.py
    - src/vcompany/supervisor/project_supervisor.py
    - src/vcompany/bot/embeds.py
    - src/vcompany/bot/cogs/health.py
    - src/vcompany/bot/client.py
    - src/vcompany/bot/cogs/commands.py
    - tests/test_company_root.py
decisions:
  - "NoopCommunicationPort is a plain class (not Protocol subclass) that structurally satisfies CommunicationPort -- no inheritance needed"
  - "comm_port stored as _comm_port on Supervisor but as comm_port (public) on AgentContainer -- follow existing container convention"
  - "Strategist CompanyAgent created in both on_ready and /new-project paths inside the company_root is None guard to avoid double-creation on reconnect"
metrics:
  duration_seconds: 596
  completed_date: "2026-03-28"
  tasks_completed: 2
  files_changed: 9
---

# Phase 11 Plan 02: Wire Strategist, NoopCommunicationPort, and Display Layer Summary

NoopCommunicationPort wired through entire supervision hierarchy, Strategist registered as CompanyRoot direct child, and health embed updated to render blocked/stopping states with blocked_reason context.

## What Was Built

**Task 1: NoopCommunicationPort, Supervisor comm_port wiring, CompanyRoot company agents**

communication.py:
- Added `NoopCommunicationPort` class satisfying the `CommunicationPort` Protocol structurally
- `send_message` returns True and logs at DEBUG level; `receive_message` returns None
- Added `import logging` and module-level `logger`

supervisor.py:
- Added `comm_port: object | None = None` parameter to `__init__`
- Stored as `self._comm_port`
- `_start_child()` now passes `comm_port=self._comm_port` to `create_container()`

project_supervisor.py:
- Added `comm_port: object | None = None` parameter
- Passed through to `Supervisor.__init__`

company_root.py:
- Added `self._company_agents: dict[str, AgentContainer] = {}`
- Created `self._comm_port = NoopCommunicationPort()` in `__init__` (shared across all children)
- Added `add_company_agent(spec)` async method -- creates container with comm_port, starts it, stores in `_company_agents`
- Updated `health_tree()` to build `company_nodes` list and pass `company_agents=company_nodes` to `CompanyHealthTree`
- Updated `stop()` to stop and clear all company agents before stopping projects
- Updated `_find_container()` to check `_company_agents` first before project supervisors
- Updated `add_project()` to pass `comm_port=self._comm_port` to `ProjectSupervisor`
- Updated `handle_child_escalation()` to pass `comm_port=self._comm_port` when rebuilding a ProjectSupervisor

New tests: 9 tests in `tests/test_comm_port_wiring.py`, 5 new tests in `tests/test_company_root.py` -- all pass.

**Task 2: Display layer and bot wiring**

embeds.py:
- Added `"blocked": "\U0001f7e0"` (orange circle) and `"stopping": "\U0001f7e1"` (yellow) to `STATE_INDICATORS`
- Updated `build_health_tree_embed` to render `tree.company_agents` as a "Company Agents" field before project sections
- Added `blocked_reason` display in both company agent lines and per-project agent lines
- Updated embed color logic to check `company_agents` states in `all_running` calculation

health.py:
- Updated `_notify_state_change` filter to include "blocked" and "stopping" states
- Added `blocked_reason` to notification message string

client.py:
- After `await self.company_root.start()` in `on_ready`, creates a `ContainerContext` with `agent_id="strategist"`, `agent_type="company"`, `parent_id="company-root"`, `project_id=None`
- Creates `ChildSpec` and calls `await self.company_root.add_company_agent(strategist_spec)`

commands.py:
- After `await self.bot.company_root.start()` in the `/new-project` `company_root is None` block, same Strategist wiring as `on_ready`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test using _comm_port instead of comm_port on AgentContainer**
- **Found during:** Task 1 TDD GREEN
- **Issue:** Test asserted `container._comm_port` but AgentContainer stores the attribute as public `comm_port` (without underscore) per existing container conventions
- **Fix:** Updated test to assert `container.comm_port`
- **Files modified:** `tests/test_comm_port_wiring.py`
- **Commit:** e94a7dc

## Pre-existing Failures (Out of Scope)

- `tests/test_pm_tier.py::test_low_confidence_escalates_to_strategist` -- Claude CLI process communication error (external dependency, documented in Plan 01 SUMMARY)

## Known Stubs

None -- `NoopCommunicationPort` is an intentional stub documented as v2.1 wiring only. It is not a stub for this plan's goal (comm_port wiring is complete). Real Discord-backed implementation is a future phase concern.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| src/vcompany/container/communication.py contains NoopCommunicationPort | FOUND |
| src/vcompany/supervisor/supervisor.py contains comm_port=self._comm_port in _start_child | FOUND |
| src/vcompany/supervisor/company_root.py contains _company_agents dict | FOUND |
| src/vcompany/supervisor/company_root.py contains add_company_agent | FOUND |
| src/vcompany/bot/embeds.py contains "blocked" key in STATE_INDICATORS | FOUND |
| src/vcompany/bot/cogs/health.py notifies on blocked and stopping | FOUND |
| src/vcompany/bot/client.py contains add_company_agent for strategist | FOUND |
| tests/test_comm_port_wiring.py | FOUND |
| Commit e94a7dc (Task 1) | FOUND |
| Commit 7070245 (Task 2) | FOUND |
