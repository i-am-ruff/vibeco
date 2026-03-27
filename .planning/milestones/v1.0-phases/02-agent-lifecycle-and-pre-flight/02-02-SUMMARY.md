---
phase: 02-agent-lifecycle-and-pre-flight
plan: 02
subsystem: orchestrator
tags: [tmux, process-management, cli, click, agent-lifecycle]

# Dependency graph
requires:
  - phase: 01-foundation-and-scaffolding
    provides: "TmuxManager, write_atomic, AgentConfig/ProjectConfig, Click CLI group"
  - phase: 02-agent-lifecycle-and-pre-flight
    provides: "AgentEntry/AgentsRegistry models, CrashTracker"
provides:
  - "AgentManager class with dispatch, dispatch_all, kill, relaunch methods"
  - "DispatchResult dataclass for operation results"
  - "CLI commands: vco dispatch, vco kill, vco relaunch"
  - "PID verification and SIGTERM/SIGKILL escalation for graceful termination"
affects: [03-monitor-loop-and-coordination]

# Tech tracking
tech-stack:
  added: []
  patterns: [constructor-injection-for-testing, module-level-helpers-for-mocking, thin-cli-wrappers]

key-files:
  created:
    - src/vcompany/orchestrator/agent_manager.py
    - src/vcompany/cli/dispatch_cmd.py
    - src/vcompany/cli/kill_cmd.py
    - src/vcompany/cli/relaunch_cmd.py
    - tests/test_dispatch.py
    - tests/test_kill.py
    - tests/test_relaunch.py
  modified:
    - src/vcompany/cli/main.py

key-decisions:
  - "Env vars and claude command chained with && in single send_keys call to avoid tmux async race"
  - "Module-level _find_child_pids, _verify_pid_is_claude, _kill_process for easy mocking in tests"
  - "AgentManager tracks tmux panes in-memory dict for kill fallback"

patterns-established:
  - "Constructor injection: TmuxManager injected via __init__ for test mocking"
  - "Module-level helpers: process management functions at module scope for patch-based mocking"
  - "Thin CLI wrappers: Click commands do argument parsing, config loading, and display only"

requirements-completed: [LIFE-01, LIFE-02, LIFE-03, LIFE-04]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 2 Plan 2: Agent Lifecycle Manager Summary

**AgentManager dispatches Claude Code into tmux panes with env vars and flags, kills with SIGTERM/SIGKILL escalation and PID verification, relaunches with /gsd:resume-work**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T02:46:58Z
- **Completed:** 2026-03-25T02:50:50Z
- **Tasks:** 2 (Task 1: TDD RED+GREEN, Task 2: auto)
- **Files modified:** 8

## Accomplishments
- AgentManager orchestrator class with dispatch, dispatch_all, kill, relaunch methods
- Dispatch chains env vars (DISCORD_AGENT_WEBHOOK_URL, PROJECT_NAME, AGENT_ID, AGENT_ROLE) with claude command via && in single send_keys call
- Kill verifies PID cmdline contains "claude" or "node" before sending signals, with SIGTERM/10s/SIGKILL escalation and tmux pane fallback
- dispatch_all creates tmux session with one pane per agent plus monitor pane
- Three CLI commands (dispatch, kill, relaunch) registered as thin Click wrappers
- 20 tests covering all dispatch, kill, and relaunch behaviors

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for dispatch/kill/relaunch** - `09e444e` (test)
2. **Task 1 (GREEN): AgentManager implementation** - `db3b91d` (feat)
3. **Task 2: CLI commands for dispatch, kill, relaunch** - `b96f084` (feat)

_Task 1 was TDD with RED/GREEN commits._

## Files Created/Modified
- `src/vcompany/orchestrator/agent_manager.py` - AgentManager class with DispatchResult, dispatch, dispatch_all, kill, relaunch, and process management helpers
- `src/vcompany/cli/dispatch_cmd.py` - vco dispatch command (single agent or --all)
- `src/vcompany/cli/kill_cmd.py` - vco kill command (with --force option)
- `src/vcompany/cli/relaunch_cmd.py` - vco relaunch command
- `src/vcompany/cli/main.py` - Registered dispatch, kill, relaunch commands
- `tests/test_dispatch.py` - 11 tests for dispatch and dispatch_all
- `tests/test_kill.py` - 6 tests for kill with PID verification and signal escalation
- `tests/test_relaunch.py` - 3 tests for relaunch with resume-work

## Decisions Made
- Chained env vars and claude command with && in single send_keys call to prevent tmux async race condition (Pitfall 2)
- Used --append-system-prompt-file (not --append-system-prompt) per Pitfall 4
- Module-level helper functions (_find_child_pids, _verify_pid_is_claude, _kill_process) for easy patch-based mocking in tests
- AgentManager tracks tmux panes in an in-memory dict for kill fallback when signal delivery fails
- Session naming convention: vco-{project} for tmux sessions

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- AgentManager ready for monitor loop (Phase 3) to call kill/relaunch on crash detection
- agents.json state file bridges dispatch and monitor phases
- CLI commands operational for manual dispatch/kill/relaunch during development
- Monitor pane created by dispatch_all ready for Phase 3 monitor process

## Self-Check: PASSED

All 8 files verified present. All 3 commit hashes verified. All 21 acceptance criteria satisfied (13 for Task 1 + 8 for Task 2). 101/101 tests pass including 20 new tests.

---
*Phase: 02-agent-lifecycle-and-pre-flight*
*Completed: 2026-03-25*
