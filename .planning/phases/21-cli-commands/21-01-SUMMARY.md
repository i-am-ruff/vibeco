---
phase: 21-cli-commands
plan: 01
subsystem: cli
tags: [click, rich, unix-socket, daemon-client]

# Dependency graph
requires:
  - phase: 18-daemon-socket
    provides: DaemonClient NDJSON socket client
  - phase: 20-extract-runtime
    provides: RuntimeAPI socket endpoints (hire, give_task, dismiss, status, health_tree)
provides:
  - Five CLI commands as thin DaemonClient wrappers (hire, give-task, dismiss, status, health)
  - daemon_client() connection helper with error handling
affects: [22-bot-relay, 23-persistence]

# Tech tracking
tech-stack:
  added: []
  patterns: [daemon_client context manager for CLI-to-daemon communication, Rich Table/Tree for CLI output]

key-files:
  created:
    - src/vcompany/cli/helpers.py
    - src/vcompany/cli/hire_cmd.py
    - src/vcompany/cli/give_task_cmd.py
    - src/vcompany/cli/dismiss_cmd.py
    - src/vcompany/cli/status_cmd.py
    - src/vcompany/cli/health_cmd.py
    - tests/test_cli_commands.py
  modified:
    - src/vcompany/cli/main.py

key-decisions:
  - "daemon_client() helper catches ConnectionRefusedError/FileNotFoundError/ConnectionError uniformly"
  - "Rich Console used for formatted output, click.echo for plain text and errors"

patterns-established:
  - "CLI command pattern: click command -> daemon_client() context manager -> client.call() -> Rich output"
  - "Error pattern: connection errors -> 'Daemon not running' stderr message + exit 1"

requirements-completed: [CLI-01, CLI-02, CLI-03, CLI-04, CLI-05]

# Metrics
duration: 4min
completed: 2026-03-29
---

# Phase 21 Plan 01: CLI Commands Summary

**Five thin CLI commands (hire, give-task, dismiss, status, health) wrapping DaemonClient socket calls with Rich output formatting**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-29T11:58:35Z
- **Completed:** 2026-03-29T12:02:31Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Three CRUD commands (hire, give-task, dismiss) as Click commands calling daemon via socket
- Status command with Rich Table showing projects and company agents
- Health command with Rich Tree showing color-coded agent states, inner states, and uptime
- Shared daemon_client() context manager handling connection and RPC errors uniformly
- 11 tests covering success paths, connection errors, RPC errors, and empty state

## Task Commits

Each task was committed atomically:

1. **Task 1: Connection helper and CRUD commands** - `8a85d38` (feat)
2. **Task 2: Status and health display commands** - `00020ba` (feat)

## Files Created/Modified
- `src/vcompany/cli/helpers.py` - daemon_client() context manager with connection error handling
- `src/vcompany/cli/hire_cmd.py` - vco hire TYPE NAME command
- `src/vcompany/cli/give_task_cmd.py` - vco give-task AGENT_NAME TASK command
- `src/vcompany/cli/dismiss_cmd.py` - vco dismiss AGENT_NAME command
- `src/vcompany/cli/status_cmd.py` - vco status with Rich Table output
- `src/vcompany/cli/health_cmd.py` - vco health with color-coded Rich Tree
- `src/vcompany/cli/main.py` - Registered all 5 new commands
- `tests/test_cli_commands.py` - 11 tests for all commands

## Decisions Made
- daemon_client() catches ConnectionRefusedError, FileNotFoundError, and ConnectionError all as "Daemon not running" -- covers socket missing and socket refused cases
- Rich Console().print() for formatted output, click.echo(err=True) for error messages to stderr
- Health tree uses Rich Tree widget with color-mapped states (running=green, idle=blue, error=red, etc.)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Click 8.3+ removed CliRunner mix_stderr parameter -- adjusted tests to use default CliRunner() which captures stderr separately via result.stderr attribute
- Pre-existing test failure in test_bot_client.py (VcoBot.company_root removed in Phase 20) -- out of scope, not related to this plan

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All 5 CLI commands registered and tested, ready for bot relay integration in Phase 22
- Commands follow the daemon_client() pattern established here -- future commands (new-project) can reuse it

---
*Phase: 21-cli-commands*
*Completed: 2026-03-29*
