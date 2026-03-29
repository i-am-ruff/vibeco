---
phase: 20-companyroot-extraction
plan: 03
subsystem: daemon
tags: [runtime-api, company-root, daemon, bot-refactor, extraction]

requires:
  - phase: 20-companyroot-extraction
    plan: 02
    provides: RuntimeAPI callback methods and inbound relay methods
provides:
  - Gutted VcoBot.on_ready() with zero CompanyRoot/container/agent imports
  - Daemon owns CompanyRoot lifecycle (init after bot connects, ordered shutdown)
  - Socket API endpoints for hire/give_task/dismiss/status/health_tree
  - Bot signals daemon readiness via _bot_ready_event.set()
affects: [20-04, 22-bot-refactor, cli-commands]

tech-stack:
  added: []
  patterns: [daemon-owns-business-logic, bot-as-thin-adapter, bot-ready-event signaling]

key-files:
  created: []
  modified:
    - src/vcompany/bot/client.py
    - src/vcompany/daemon/daemon.py

key-decisions:
  - "Bot is now a pure Discord I/O adapter -- all CompanyRoot/container/agent imports removed"
  - "Daemon waits for _bot_ready_event before initializing CompanyRoot -- handles bot crash before ready"
  - "CompanyRoot shutdown happens before socket/bot shutdown for ordered teardown"
  - "PlanReviewer/PMTier NOT injected into cogs -- deferred to Phase 22 via RuntimeAPI"
  - "api_ref forward-reference pattern for callbacks that need RuntimeAPI before it exists"

patterns-established:
  - "Bot-ready event pattern: bot.on_ready() sets daemon._bot_ready_event, daemon waits with asyncio.wait"
  - "Daemon sub-method decomposition: _create_runtime_api, _register_socket_endpoints, _init_project"

requirements-completed: [EXTRACT-03, EXTRACT-04, COMM-04, COMM-05]

duration: 329s
completed: 2026-03-29
---

# Phase 20 Plan 03: Bot Gutting and Daemon CompanyRoot Lifecycle Summary

**VcoBot.on_ready() gutted to thin Discord adapter (510 lines removed), CompanyRoot lifecycle moved to Daemon._run() with socket API endpoints**

## Performance

- **Duration:** 5 min 29 sec
- **Started:** 2026-03-29T03:20:10Z
- **Completed:** 2026-03-29T03:25:39Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Removed all CompanyRoot, container, agent, supervisor, MessageQueue, TmuxManager imports from client.py (510 lines removed, 86 added)
- Daemon now owns CompanyRoot lifecycle: init after bot connects, project setup, ordered shutdown
- Socket API exposes hire/give_task/dismiss/status/health_tree endpoints
- Bot signals daemon readiness via _bot_ready_event.set() with crash-before-ready detection
- Boot notifications route through CommunicationPort with direct-send fallback

## Task Commits

Each task was committed atomically:

1. **Task 1: Gut VcoBot.on_ready() and rewire to daemon** - `2f7feaa` (feat)
2. **Task 2: Add CompanyRoot lifecycle to Daemon._run()** - `ec59fa8` (feat)

## Files Created/Modified

- `src/vcompany/bot/client.py` - Gutted to thin Discord adapter: role creation, channels, CommunicationPort registration only
- `src/vcompany/daemon/daemon.py` - Added CompanyRoot lifecycle, socket API handlers, boot notifications, _init_company_root sub-methods

## Decisions Made

- Bot is now a pure Discord I/O adapter -- zero CompanyRoot/container/agent imports
- Daemon waits for _bot_ready_event before initializing CompanyRoot -- handles bot crash before ready gracefully
- CompanyRoot shutdown happens before socket/bot shutdown for ordered teardown
- PlanReviewer/PMTier NOT injected into cogs -- deferred to Phase 22 via RuntimeAPI
- api_ref forward-reference pattern (list[RuntimeAPI | None]) for callbacks that need RuntimeAPI before it exists
- Plain async def _noop_async() used instead of removed asyncio.coroutine()

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Bot is fully gutted and ready for Plan 20-04 cog updates
- Daemon owns all business logic, socket API ready for CLI commands
- Phase 22 (BOT-01..05) can now rewire cogs to use RuntimeAPI exclusively

## Known Stubs

None -- all methods are fully implemented.

## Self-Check: PASSED

---
*Phase: 20-companyroot-extraction*
*Completed: 2026-03-29*
