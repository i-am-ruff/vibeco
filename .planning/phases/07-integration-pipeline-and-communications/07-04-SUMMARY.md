---
phase: "07-integration-pipeline-and-communications"
plan: "04"
subsystem: "integration-wiring"
tags: [integration, monitor, discord, interlock, checkin]
dependency_graph:
  requires: [07-01, 07-02]
  provides: [integration-interlock, integrate-command, checkin-auto-trigger]
  affects: [monitor-loop, bot-commands, agent-monitor-state]
tech_stack:
  added: []
  patterns: [callback-injection, public-api-over-private-state, tdd]
key_files:
  created:
    - tests/test_integration_interlock.py
  modified:
    - src/vcompany/models/monitor_state.py
    - src/vcompany/monitor/loop.py
    - src/vcompany/bot/cogs/commands.py
    - src/vcompany/bot/client.py
decisions:
  - "Public all_agents_idle() method on MonitorLoop to avoid private _agent_states access from commands"
  - "Checkin callback wired via CommandsCog.wire_monitor_callbacks() called from on_ready after monitor init"
  - "_on_checkin as CommandsCog method (not lambda) for testability and access to bot context"
metrics:
  duration: "3min"
  completed: "2026-03-25T22:21:40Z"
  tasks: 2
  files: 5
---

# Phase 7 Plan 4: Integration Interlock and Command Wiring Summary

Wire integration pipeline into monitor loop interlock model and full !integrate Discord command with auto-checkin trigger on phase completion.

## What Was Done

### Task 1: Monitor integration interlock + checkin auto-trigger + all_agents_idle() (TDD)

Added `integration_pending` and `checkin_sent` boolean fields to `AgentMonitorState` model. Extended `MonitorLoop` with:

- `set_integration_pending(bool)` -- sets the integration pending flag
- `all_agents_idle() -> bool` -- public API checking all agents have phase_status="completed" and plan_gate_status="idle"
- `_on_integration_ready` callback parameter -- fires when integration_pending=True and all agents idle
- `_on_checkin` callback parameter -- fires once per agent when phase_status="completed" and checkin_sent=False

Integration interlock check runs at the end of each `_run_cycle` after status generation. Checkin auto-trigger runs at the end of each `_check_agent` after plan gate checks.

16 tests covering all edge cases (TDD red/green flow).

### Task 2: Full !integrate command + checkin callback wiring

Replaced the placeholder `integrate_cmd` with full implementation:

1. Confirmation dialog via ConfirmView
2. Checks `monitor.all_agents_idle()` -- if not idle, sets pending and returns
3. If idle, runs `IntegrationPipeline.run()` immediately
4. Posts `build_integration_embed(result)` to channel
5. On `test_failure` with attribution: dispatches fixes via `agent_mgr.dispatch_fix()` for each responsible agent (skipping `_interaction`, `_flaky` pseudo-agents)
6. On `merge_conflict`: posts `build_conflict_embed()` to #alerts channel

Added `_on_checkin` method to CommandsCog that gathers checkin data and posts to `#agent-{id}` channel. Wired via `wire_monitor_callbacks()` called from `VcoBot.on_ready()` after monitor initialization.

## Commits

| Hash | Message |
|------|---------|
| 546ed92 | test(07-04): add failing tests for integration interlock |
| 7ac9c56 | feat(07-04): implement integration interlock, checkin auto-trigger, all_agents_idle |
| 47d0e12 | feat(07-04): implement full !integrate command and checkin callback wiring |

## Deviations from Plan

None -- plan executed exactly as written.

## Decisions Made

1. **Public all_agents_idle() over private state access**: The !integrate command uses `monitor.all_agents_idle()` instead of accessing `monitor._agent_states` directly. This maintains encapsulation and follows the plan's explicit guidance.

2. **Checkin callback as CommandsCog method**: Instead of a standalone lambda in on_ready, `_on_checkin` is a method on CommandsCog. This gives it access to `self.bot` context (project_dir, guilds) cleanly. Wired via `wire_monitor_callbacks()` called from on_ready.

3. **wire_monitor_callbacks pattern**: Added `CommandsCog.wire_monitor_callbacks()` called from `VcoBot.on_ready()` after monitor loop creation. This separates the timing concern (monitor doesn't exist at cog load time) from the wiring concern.

## Known Stubs

None -- all functionality is fully wired.

## Self-Check: PASSED
