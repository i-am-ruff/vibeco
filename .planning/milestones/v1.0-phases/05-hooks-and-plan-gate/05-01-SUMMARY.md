---
phase: 05-hooks-and-plan-gate
plan: 01
subsystem: hooks
tags: [hook, discord, ask-user-question, pretooluse, stdlib]
dependency_graph:
  requires: []
  provides: [ask_discord_hook, pretooluse_handler]
  affects: [agent_autonomy, discord_communication]
tech_stack:
  added: []
  patterns: [pretooluse_hook_protocol, file_based_ipc, webhook_posting]
key_files:
  created:
    - tools/ask_discord.py
    - tools/__init__.py
    - tests/test_ask_discord.py
  modified: []
decisions:
  - "UUID4 for request IDs -- collision-proof across concurrent agents"
  - "Cleanup on read -- answer file deleted after hook consumes it"
  - "Top-level try/except wraps entire script to guarantee JSON output (HOOK-07)"
  - "Tests simulate __main__ top-level handler for error fallback scenarios"
metrics:
  duration: 3min
  completed: "2026-03-25T18:06:00Z"
  tasks_completed: 1
  tasks_total: 1
  files_created: 3
  files_modified: 0
  test_count: 12
  test_pass: 12
---

# Phase 05 Plan 01: ask_discord.py Hook Summary

Self-contained PreToolUse hook that intercepts AskUserQuestion tool calls, posts questions to Discord via webhook, polls for file-based answers with configurable timeout/fallback, and guarantees valid JSON output on any error path.

## What Was Built

### tools/ask_discord.py
Standalone Python script (stdlib-only) that serves as the PreToolUse hook for AskUserQuestion. The hook:

1. **Reads stdin JSON** via `sys.stdin.read()` to get the full Claude Code hook payload
2. **Filters by tool_name** -- allows non-AskUserQuestion calls through, only intercepts questions
3. **Posts to Discord** via `urllib.request` with a formatted embed (agent ID, question text, options, request ID in footer)
4. **Polls for answers** at `/tmp/vco-answers/{request_id}.json` every 5s for up to 10 minutes
5. **Handles timeouts** with two configurable modes:
   - `continue`: auto-selects first option, posts timeout alert to Discord
   - `block`: returns block message telling agent to wait
6. **Returns deny + permissionDecisionReason** carrying the answer text back to Claude Code
7. **Never hangs**: top-level try/except guarantees valid JSON output on any error

### tests/test_ask_discord.py
12 unit tests covering all hook behaviors:
- Stdin parsing (valid, non-ask, malformed)
- Webhook POST (success, failure)
- Answer polling (found, timeout-continue, timeout-block)
- Deny response format validation
- Error fallback guarantee
- Stdlib-only import verification via AST
- Answer file cleanup on read

## Requirements Covered

| Req ID | Description | Status |
|--------|-------------|--------|
| HOOK-01 | Intercepts AskUserQuestion via PreToolUse | Done |
| HOOK-02 | Posts formatted question with agent ID to Discord | Done |
| HOOK-03 | Polls for reply every 5s with 10-minute timeout | Done |
| HOOK-04 | Falls back to first option on timeout with alert | Done |
| HOOK-05 | Returns deny + permissionDecisionReason with answer | Done |
| HOOK-06 | Self-contained -- only stdlib imports | Done |
| HOOK-07 | Top-level try/except -- never hangs | Done |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 2089d50 | test | Add failing tests for ask_discord.py hook (RED) |
| 34f863c | feat | Implement ask_discord.py PreToolUse hook (GREEN) |

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None -- all functionality is fully wired.

## Verification

```
uv run pytest tests/test_ask_discord.py -v
12 passed in 0.02s
```

All acceptance criteria verified:
- tools/ask_discord.py exists and is executable
- Contains all required functions (main, output_deny, parse_stdin, post_question, poll_answer, get_fallback_answer, alert_timeout)
- Uses sys.stdin.read() for full stdin consumption
- No vcompany or external HTTP library imports
- All 12 tests pass

## Self-Check: PASSED
