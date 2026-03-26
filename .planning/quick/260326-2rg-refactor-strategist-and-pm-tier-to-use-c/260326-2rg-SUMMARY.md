---
phase: quick
plan: 260326-2rg
subsystem: strategist
tags: [refactor, claude-cli, pm, strategist, subprocess]
dependency_graph:
  requires: []
  provides: [claude-cli-pm, claude-cli-strategist]
  affects: [bot-startup, question-handling]
tech_stack:
  added: []
  patterns: [subprocess-for-claude-cli, json-output-parsing]
key_files:
  created: []
  modified:
    - src/vcompany/strategist/conversation.py
    - src/vcompany/strategist/pm.py
    - src/vcompany/bot/cogs/strategist.py
    - src/vcompany/bot/client.py
    - tests/test_conversation.py
    - tests/test_pm_tier.py
decisions:
  - "Claude CLI --session-id + --resume for Strategist persistent conversation (replaces manual messages array)"
  - "Claude CLI -p --output-format json for PM single-shot answers (replaces Anthropic messages.create)"
  - "System prompt passed only on first send via --system-prompt flag; subsequent sends use --resume"
  - "Token tracking and Knowledge Transfer removed (Claude CLI manages its own context window)"
  - "Tools disabled via --tools '' for both PM and Strategist CLI calls"
metrics:
  duration: 6min
  completed: "2026-03-26"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 6
---

# Quick Task 260326-2rg: Refactor Strategist and PM Tier to Use Claude CLI Summary

Replaced Anthropic Python SDK usage with Claude Code CLI subprocess calls for both Strategist (persistent conversation) and PM (stateless Q&A), enabling functionality without ANTHROPIC_API_KEY.

## What Changed

### conversation.py
- Removed AsyncAnthropic client parameter and all token tracking (TOKEN_LIMIT, _maybe_check_tokens, _perform_knowledge_transfer)
- New: uses `claude -p --session-id {uuid}` on first call with `--system-prompt`, then `--resume {uuid}` for subsequent calls
- Output parsed from `--output-format json` (result field extraction)
- asyncio.Lock for send serialization preserved; persona loading unchanged

### pm.py
- Removed `from anthropic import AsyncAnthropic` runtime import and client parameter
- _answer_directly() now uses `asyncio.create_subprocess_exec` running `claude -p --model sonnet --output-format json`
- Question passed via stdin; JSON response parsed for result field
- All confidence scoring, escalation logic, context loading, and decision log loading unchanged

### strategist.py (cog)
- Removed AsyncAnthropic from TYPE_CHECKING import
- `initialize()` signature simplified: removed `client` parameter, takes only `persona_path` and `decisions_path`
- Creates StrategistConversation(persona_path=...) without client

### client.py
- Removed `from anthropic import AsyncAnthropic` import and `AsyncAnthropic(api_key=...)` creation
- Removed `if bot_config.anthropic_api_key:` gate -- PM/Strategist always initialize
- Removed `except ImportError` for anthropic SDK
- PMTier constructed with `project_dir=self.project_dir` only
- Log message updated to "PM/Strategist initialized with Claude CLI"

### Tests
- test_conversation.py: Replaced MockStreamResponse/MockTokenCountResult/make_mock_client with make_mock_process that mocks asyncio.create_subprocess_exec. Removed 4 KT/token tests, added 3 CLI-specific tests (session reuse, system prompt on first call, error handling).
- test_pm_tier.py: All tests updated to mock asyncio.create_subprocess_exec instead of Anthropic client. PMTier constructed without client parameter. test_graceful_degradation mocks OSError instead of API Exception.
- test_strategist_cog.py: No changes needed -- tests mock conversation directly, never called initialize().

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used --output-format json instead of stream-json for Strategist**
- **Found during:** Task 1
- **Issue:** Claude CLI requires --verbose flag with --output-format stream-json in -p mode, and stream-json output includes system events mixed with content. The plan specified stream-json.
- **Fix:** Used --output-format json which returns clean single JSON result. The Strategist cog's _stream_to_channel already handles receiving all text at once (it just edits fewer times).
- **Files modified:** src/vcompany/strategist/conversation.py

**2. [Rule 3 - Blocking] Used --tools "" instead of --allowedTools ""**
- **Found during:** Task 1
- **Issue:** Plan specified `--allowedTools ""` but the CLI flag is `--tools ""` for disabling tools.
- **Fix:** Used `--tools ""` which is the correct flag name per `claude --help`.
- **Files modified:** src/vcompany/strategist/conversation.py, src/vcompany/strategist/pm.py

## Verification Results

1. All 34 tests in target files pass (test_conversation.py: 12, test_pm_tier.py: 7, test_strategist_cog.py: 15)
2. Imports work without anthropic: `from vcompany.strategist.conversation import StrategistConversation; from vcompany.strategist.pm import PMTier`
3. No runtime anthropic imports in modified source files: `grep -r "from anthropic import" src/vcompany/strategist/ src/vcompany/bot/cogs/strategist.py src/vcompany/bot/client.py` returns empty
4. Full test suite: 495 passed (1 pre-existing failure in test_bot_config.py unrelated to this change)

## Known Stubs

None -- all data paths are wired to Claude CLI subprocess calls.

## Self-Check: PASSED

- [x] src/vcompany/strategist/conversation.py exists and updated
- [x] src/vcompany/strategist/pm.py exists and updated
- [x] src/vcompany/bot/cogs/strategist.py exists and updated
- [x] src/vcompany/bot/client.py exists and updated
- [x] tests/test_conversation.py exists and updated
- [x] tests/test_pm_tier.py exists and updated
- [x] Commit 8db2f94 exists
- [x] Commit 8865fe0 exists
- [x] Commit 3a59e9c exists
