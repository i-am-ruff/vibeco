---
phase: 12-work-initiation
plan: "01"
subsystem: container
tags: [tmux, asyncio, pydantic, readiness-poll, gsd-command]

# Dependency graph
requires:
  - phase: 11-container-fixes
    provides: AgentContainer with tmux bridge, ContainerContext, TmuxManager.get_output()
provides:
  - gsd_command field on ContainerContext (configurable per agent)
  - _wait_for_claude_ready() poll loop in AgentContainer (no blind sleep)
  - GSD command auto-sent to tmux pane after Claude Code readiness confirmed
  - Both bot startup paths (on_ready + /new-project) set gsd_command for gsd agents
affects: [13-event-routing, 14-pm-review-gates, 16-agent-completeness]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Readiness poll: poll TmuxManager.get_output() for '>' prompt, not blind sleep"
    - "gsd_command on ContainerContext: GSD config flows from context through _launch_tmux_session"

key-files:
  created: []
  modified:
    - src/vcompany/container/context.py
    - src/vcompany/container/container.py
    - src/vcompany/bot/client.py
    - src/vcompany/bot/cogs/commands.py
    - tests/test_container_tmux_bridge.py

key-decisions:
  - "Poll for '>' prompt (last non-empty pane line) instead of blind sleep(3) for Claude Code readiness"
  - "gsd_command stored on ContainerContext -- flows automatically through existing ChildSpec/container plumbing"
  - "Only gsd agents get gsd_command set; fulltime/company/continuous agents get None (backward compatible)"
  - "Fixed '/gsd:discuss-phase 1' for v2.1; PM will assign dynamic phase numbers in a later phase"

patterns-established:
  - "Pattern: Poll TmuxManager.get_output() with deadline loop + asyncio.sleep(poll_interval) for tmux readiness"
  - "Pattern: if self.context.gsd_command guard makes GSD injection backward compatible"
  - "Test pattern: mock_tmux.get_output.return_value = ['>'] for instant readiness in unit tests"

requirements-completed: [WORK-01, WORK-02]

# Metrics
duration: 2min
completed: 2026-03-28
---

# Phase 12 Plan 01: Work Initiation Summary

**Poll-based Claude Code readiness detection and automatic GSD command injection wired into AgentContainer tmux launch flow**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-28T16:09:36Z
- **Completed:** 2026-03-28T16:11:29Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added `gsd_command: str | None = None` to `ContainerContext` with full docstring
- Replaced blind `asyncio.sleep(3)` in `_launch_tmux_session()` with a poll loop (`_wait_for_claude_ready`) that detects the Claude Code `>` idle prompt via `TmuxManager.get_output()`
- GSD command auto-sent via `send_command` once readiness confirmed; warning logged on timeout
- Both `client.py` (on_ready) and `commands.py` (/new-project) now set `gsd_command="/gsd:discuss-phase 1"` for gsd agents
- All 14 tests pass including 3 new tests: gsd_command sent on ready, not sent when None, not sent on timeout

## Task Commits

1. **Task 1: Add gsd_command to ContainerContext and readiness poll to container.py** - `1291ce8` (feat)
2. **Task 2: Wire gsd_command in bot startup paths and update tests** - `d850fb7` (feat)

## Files Created/Modified

- `src/vcompany/container/context.py` - Added `gsd_command: str | None = None` field
- `src/vcompany/container/container.py` - Added `import logging/time`, logger, `_wait_for_claude_ready()`, rewrote `_launch_tmux_session()`
- `src/vcompany/bot/client.py` - Set `gsd_command` for gsd agents in on_ready startup loop
- `src/vcompany/bot/cogs/commands.py` - Set `gsd_command` for gsd agents in /new-project loop
- `tests/test_container_tmux_bridge.py` - Updated `_mock_tmux()`, updated existing test, added 2 new tests

## Decisions Made

- Poll for `>` prompt as the Claude Code ready indicator (last non-empty pane line stripped == ">" or ends with " >") -- loose but correct pattern from research
- `gsd_command` stored on `ContainerContext` rather than `ChildSpec` since it's agent config, not supervision policy
- Only gsd agents receive `gsd_command`; other types (fulltime, company, continuous) get None -- no change to their behavior
- Fixed phase number `/gsd:discuss-phase 1` for v2.1 Phase 12; dynamic assignment deferred to later phase

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Agents will now autonomously begin GSD work (`/gsd:discuss-phase 1`) after container starts
- Phase 13 (event routing) can build on the gsd_command field; agents completing phases will emit events that flow to PM
- Phase 14 PM review gates depend on agents reaching review checkpoints -- now possible since agents start work

---
*Phase: 12-work-initiation*
*Completed: 2026-03-28*
