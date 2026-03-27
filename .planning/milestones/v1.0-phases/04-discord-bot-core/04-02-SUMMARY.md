---
phase: 04-discord-bot-core
plan: 02
subsystem: discord-bot
tags: [discord.py, commands, cog, asyncio, to_thread, confirmation-view]

# Dependency graph
requires:
  - phase: 04-discord-bot-core-01
    provides: "VcoBot client, permissions, ConfirmView, channel_setup, embeds"
  - phase: 02-agent-lifecycle
    provides: "AgentManager with dispatch/kill/relaunch"
  - phase: 03-monitor-status
    provides: "generate_project_status for !status command"
provides:
  - "CommandsCog with 7 operator commands (new-project, dispatch, status, kill, relaunch, standup, integrate)"
  - "Module-level async setup() for discord.py cog loading"
affects: [05-hooks, 06-strategist, 07-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: ["discord.py command callback testing via .callback(cog, ctx)", "asyncio.to_thread wrapping for blocking calls in async cogs"]

key-files:
  created:
    - src/vcompany/bot/cogs/commands.py
    - tests/test_commands_cog.py
  modified: []

key-decisions:
  - "discord.py command callbacks tested via .callback(cog, ctx, ...) to bypass Command.__call__ routing"

patterns-established:
  - "Cog command testing: use cmd.callback(cog, ctx, ...) not cog.cmd(ctx, ...) to avoid Command.__call__ self-injection"
  - "All blocking orchestrator calls wrapped in asyncio.to_thread inside cog commands"
  - "Destructive commands use ConfirmView with interaction_user_id restriction"

requirements-completed: [DISC-03, DISC-04, DISC-05, DISC-06, DISC-07, DISC-08, DISC-09, DISC-10, DISC-11]

# Metrics
duration: 5min
completed: 2026-03-25
---

# Phase 04 Plan 02: CommandsCog Summary

**CommandsCog with 7 operator commands, vco-owner role gating, asyncio.to_thread for all blocking calls, and ConfirmView for destructive operations**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-25T14:59:58Z
- **Completed:** 2026-03-25T15:05:23Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- All 7 operator commands implemented: !new-project, !dispatch, !status, !kill, !relaunch, !standup, !integrate
- Every command gated by @is_owner() decorator for role-based access control
- All AgentManager/filesystem calls wrapped in asyncio.to_thread to avoid blocking event loop
- !kill and !integrate use ConfirmView for destructive operation confirmation
- 26 comprehensive tests covering all commands, edge cases, and async thread usage

## Task Commits

Each task was committed atomically:

1. **Task 1: CommandsCog with all operator commands** - `57dc479` (feat)

**Plan metadata:** [pending] (docs: complete plan)

## Files Created/Modified
- `src/vcompany/bot/cogs/commands.py` - CommandsCog implementing all 7 operator commands with role checks, async threading, and confirmation flows
- `tests/test_commands_cog.py` - 26 unit tests covering all commands, cog_check, edge cases, and asyncio.to_thread verification

## Decisions Made
- discord.py command callbacks tested via `.callback(cog, ctx, ...)` pattern to bypass `Command.__call__` self-injection that double-passes the cog instance

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed discord.py command callback invocation in tests**
- **Found during:** Task 1 (initial test run)
- **Issue:** Calling `cog.new_project(ctx, ...)` invokes `Command.__call__` which internally calls `callback(self.cog, ctx, ...)`, resulting in `ctx` being passed as the cog's `self` parameter
- **Fix:** Changed all test calls to `cog.cmd_name.callback(cog, ctx, ...)` pattern
- **Files modified:** tests/test_commands_cog.py
- **Verification:** All 26 tests pass
- **Committed in:** 57dc479 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test invocation pattern fix was necessary for correctness. No scope creep.

## Issues Encountered
None beyond the callback invocation pattern fix documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CommandsCog ready for integration with alerts cog (Plan 03), plan review cog (Plan 03), and strategist cog (Plan 04)
- All discord.py cog patterns established and tested
- Phase 7 scaffolds in !standup and !integrate ready for future implementation

## Self-Check: PASSED

- All created files exist on disk
- Task commit 57dc479 verified in git log
- All 26 tests passing, full suite (230) green

---
*Phase: 04-discord-bot-core*
*Completed: 2026-03-25*
