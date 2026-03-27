---
phase: 04-discord-bot-core
plan: 04
subsystem: discord-bot
tags: [discord.py, asyncio, cli, click, monitoring, crash-recovery]

# Dependency graph
requires:
  - phase: 04-02
    provides: "AlertsCog with make_sync_callbacks for callback injection"
  - phase: 04-03
    provides: "CommandsCog with !status, !dispatch, !kill, !relaunch commands"
provides:
  - "Full bot startup wiring: AgentManager + MonitorLoop + CrashTracker initialized in on_ready"
  - "Monitor loop running as asyncio background task"
  - "AlertsCog callbacks injected into MonitorLoop and CrashTracker"
  - "Graceful shutdown via close() stopping monitor and cancelling task"
  - "vco bot CLI command for starting the Discord bot"
affects: [05-hooks, 06-strategist, 07-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Callback injection: AlertsCog.make_sync_callbacks() bridges async Discord sends to sync MonitorLoop/CrashTracker"
    - "Background task: asyncio.create_task in on_ready for monitor loop"
    - "Graceful shutdown: close() stops loop then cancels task before super().close()"

key-files:
  created:
    - src/vcompany/cli/bot_cmd.py
    - tests/test_bot_startup.py
  modified:
    - src/vcompany/bot/client.py
    - src/vcompany/cli/main.py

key-decisions:
  - "CrashTracker uses crash_log_path (not state_dir) matching actual constructor signature"
  - "TmuxManager imported at module level in client.py for consistent import pattern and testability"

patterns-established:
  - "Callback injection: on_ready fetches AlertsCog, calls make_sync_callbacks(), passes to MonitorLoop/CrashTracker"
  - "Background tasks: asyncio.create_task with named tasks for debuggability"

requirements-completed: [DISC-01, DISC-11, DISC-12]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 04 Plan 04: Bot Startup Wiring Summary

**Full bot startup with AgentManager, MonitorLoop, CrashTracker callback injection and vco bot CLI command**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T15:11:51Z
- **Completed:** 2026-03-25T15:15:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Bot on_ready wires AgentManager, MonitorLoop, CrashTracker with AlertsCog callback injection (D-13)
- Monitor loop runs as asyncio background task, graceful shutdown via close()
- vco bot CLI command starts the bot from environment config and agents.yaml (D-20, D-21)
- 9 integration tests covering full startup, callback injection, idempotency, failure resilience

## Task Commits

Each task was committed atomically:

1. **Task 1: Bot startup wiring in client.py on_ready** - `55553a3` (feat)
2. **Task 2: vco bot CLI command** - `0592195` (feat)

## Files Created/Modified
- `src/vcompany/bot/client.py` - Added orchestration wiring in on_ready and close() method
- `src/vcompany/cli/bot_cmd.py` - New Click command: vco bot with --project-dir and --log-level
- `src/vcompany/cli/main.py` - Registered bot command in CLI group
- `tests/test_bot_startup.py` - 9 integration tests for startup wiring, callbacks, shutdown

## Decisions Made
- CrashTracker constructor takes `crash_log_path: Path` (not `state_dir`), matched actual Phase 2 implementation
- TmuxManager imported at module level in client.py rather than lazy import inside on_ready, for consistent pattern with other imports and better testability via patch

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Discord bot is now a fully runnable system via `vco bot` command
- All Phase 4 plans complete: client, cogs (alerts + commands), plan review, strategist stub, and startup wiring
- Ready for Phase 5 (Hooks) which builds on the bot's callback infrastructure

---
*Phase: 04-discord-bot-core*
*Completed: 2026-03-25*
