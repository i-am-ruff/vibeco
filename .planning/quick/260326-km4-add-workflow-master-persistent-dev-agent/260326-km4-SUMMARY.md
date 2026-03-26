---
phase: quick
plan: 260326-km4
subsystem: bot
tags: [discord, claude-code, workflow-master, worktree, cog]

requires:
  - phase: 06
    provides: StrategistConversation, StrategistCog patterns
provides:
  - WorkflowMasterCog for #workflow-master channel routing
  - workflow_master_persona.py with dev-focused persona and session UUID
  - allowed_tools parameter on StrategistConversation (backward-compatible)
  - Idempotent git worktree creation in vco up
affects: [bot, strategist, cli]

tech-stack:
  added: []
  patterns: [reuse StrategistConversation with custom session_id and allowed_tools]

key-files:
  created:
    - src/vcompany/strategist/workflow_master_persona.py
    - src/vcompany/bot/cogs/workflow_master.py
    - tests/test_workflow_master.py
  modified:
    - src/vcompany/strategist/conversation.py
    - src/vcompany/bot/channel_setup.py
    - src/vcompany/bot/client.py
    - src/vcompany/cli/up_cmd.py

key-decisions:
  - "Reuse StrategistConversation with allowed_tools parameter instead of subclassing"
  - "Write persona to ~/vco-workflow-master-persona.md at runtime for inspect-ability and restart survival"
  - "Worktree failure in vco up is non-blocking (warning logged, bot continues)"

patterns-established:
  - "StrategistConversation reuse: pass custom session_id + allowed_tools for different agent personas"

requirements-completed: []

duration: 4min
completed: 2026-03-26
---

# Quick 260326-km4: Add Workflow-Master Persistent Dev Agent Summary

**Workflow-master cog bridging #workflow-master to Claude with full dev tools (Bash/Read/Write/Edit/Glob/Grep) in a dedicated git worktree**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-26T12:57:05Z
- **Completed:** 2026-03-26T13:00:55Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- WorkflowMasterCog routes #workflow-master messages to a persistent Claude conversation with full dev tools
- workflow-master session UUID is deterministic and distinct from Strategist
- #workflow-master channel auto-created on bot startup alongside other system channels
- Git worktree created idempotently by `vco up` before bot startup
- 10 new tests, all 516 existing tests still pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Create WorkflowMasterConversation persona + WorkflowMasterCog** - `baf4d2e` (feat)
2. **Task 2: Wire into channel_setup, client.py, up_cmd.py + tests** - `644da66` (feat)

## Files Created/Modified

- `src/vcompany/strategist/workflow_master_persona.py` - Dev persona template with worktree path injection and deterministic session UUID
- `src/vcompany/bot/cogs/workflow_master.py` - Discord cog bridging #workflow-master to StrategistConversation with expanded tools
- `src/vcompany/strategist/conversation.py` - Added allowed_tools parameter (backward-compatible default "Bash Read Write")
- `src/vcompany/bot/channel_setup.py` - Added "workflow-master" to _SYSTEM_CHANNELS and _README_CONTENT
- `src/vcompany/bot/client.py` - Added WorkflowMasterCog to _COG_EXTENSIONS and on_ready initialization
- `src/vcompany/cli/up_cmd.py` - Added _ensure_worktree for idempotent git worktree creation
- `tests/test_workflow_master.py` - 10 tests covering persona, cog routing, worktree, channel setup, and allowed_tools

## Decisions Made

- Reused StrategistConversation with new `allowed_tools` parameter instead of subclassing -- minimal, backward-compatible change
- Persona written to `~/vco-workflow-master-persona.md` at runtime -- inspectable and survives restarts
- Worktree failure in `vco up` logs a warning but does not block bot startup

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- workflow-master is ready to use once bot starts and #workflow-master channel exists
- Worktree branch `worktree/workflow-master` created automatically on first `vco up`

---
*Quick: 260326-km4*
*Completed: 2026-03-26*
