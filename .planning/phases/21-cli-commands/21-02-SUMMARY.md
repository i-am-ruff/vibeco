---
phase: 21-cli-commands
plan: 02
subsystem: cli, daemon
tags: [click, rich, unix-socket, daemon-client, composite-command]

# Dependency graph
requires:
  - phase: 21-cli-commands/01
    provides: daemon_client() helper, CLI command pattern
  - phase: 20-extract-runtime
    provides: RuntimeAPI.new_project(), daemon socket endpoints
provides:
  - new_project daemon socket handler (loads config server-side)
  - vco new-project composite CLI command (init + clone + daemon call)
affects: [22-bot-relay]

# Tech tracking
tech-stack:
  added: []
  patterns: [composite CLI command orchestrating init+clone+daemon, server-side config loading over socket]

key-files:
  created:
    - src/vcompany/cli/new_project_cmd.py
  modified:
    - src/vcompany/daemon/daemon.py
    - src/vcompany/cli/main.py
    - tests/test_cli_commands.py

key-decisions:
  - "Config loaded server-side in daemon handler (not serialized over socket) per RESEARCH.md pitfall 1"
  - "new-project command catches daemon connection failure gracefully -- init+clone still succeed"
  - "StrategistCog wiring replicated in _handle_new_project per RESEARCH.md pitfall 5"

patterns-established:
  - "Composite CLI pattern: multi-step command with try/catch around daemon call for graceful degradation"

requirements-completed: [CLI-06]

# Metrics
duration: 236s
completed: 2026-03-29
---

# Phase 21 Plan 02: New-Project Command Summary

**Composite vco new-project command and daemon socket handler -- bootstraps full project from CLI with init, clone, and supervision startup**

## Performance

- **Duration:** 236s
- **Started:** 2026-03-29T12:04:15Z
- **Completed:** 2026-03-29T12:08:11Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Daemon _handle_new_project socket handler that loads config server-side from project_dir/agents.yaml
- Handler calls RuntimeAPI.new_project() and wires StrategistCog (same as _init_project boot path)
- Composite vco new-project CLI command: validates config, creates directory structure, copies context docs, clones repos, deploys artifacts, then calls daemon
- Graceful degradation: if daemon not running, init+clone still succeed with warning to user
- 7 new tests covering daemon handler (3) and CLI command (4) paths

## Task Commits

Each task was committed atomically:

1. **Task 1: Add new_project socket handler to daemon** - `5c689dc` (feat)
2. **Task 2: Composite vco new-project CLI command** - `8611182` (feat)

## Files Created/Modified
- `src/vcompany/daemon/daemon.py` - Added _handle_new_project handler and registered as socket endpoint
- `src/vcompany/cli/new_project_cmd.py` - Composite new-project command (init + clone + daemon call)
- `src/vcompany/cli/main.py` - Registered new-project as 6th CLI command
- `tests/test_cli_commands.py` - 7 new tests (18 total)

## Decisions Made
- Config loaded server-side in daemon handler (not serialized over socket) -- avoids Pydantic model serialization complexity
- new-project catches SystemExit from daemon_client() -- allows init+clone to succeed even without daemon
- Reused _deploy_artifacts from clone_cmd directly rather than duplicating -- cleaner code sharing

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None -- all data paths wired.

## Issues Encountered
- git.clone mock in tests needed to create actual directory for _deploy_artifacts to work -- mocked _deploy_artifacts instead

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness
- All 6 CLI commands registered and tested (hire, give-task, dismiss, status, health, new-project)
- Phase 21 complete -- ready for bot relay integration in Phase 22

---
*Phase: 21-cli-commands*
*Completed: 2026-03-29*
