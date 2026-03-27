---
phase: 06-pm-strategist-and-milestones
plan: 02
subsystem: strategist
tags: [anthropic, claude-api, streaming, knowledge-transfer, asyncio, conversation-management]

# Dependency graph
requires:
  - phase: 06-pm-strategist-and-milestones/plan-01
    provides: strategist package structure and models
provides:
  - StrategistConversation class with persistent message accumulation
  - Knowledge Transfer document generation for context handoff
  - Token tracking with rough estimates and periodic API counts
  - asyncio.Lock concurrency guard for conversation access
affects: [06-pm-strategist-and-milestones/plan-03, 06-pm-strategist-and-milestones/plan-04]

# Tech tracking
tech-stack:
  added: [anthropic SDK 0.86.x]
  patterns: [persistent-conversation, rough-token-estimation, knowledge-transfer-handoff]

key-files:
  created:
    - src/vcompany/strategist/conversation.py
    - src/vcompany/strategist/knowledge_transfer.py
    - tests/test_conversation.py
    - src/vcompany/strategist/__init__.py
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Token check uses rough char/4 estimate first, only calls count_tokens API when estimate exceeds 700K or first check"
  - "KT document captures decisions, personality calibration, open threads, and original system prompt"
  - "asyncio.Lock on send() ensures sequential message processing"

patterns-established:
  - "Rough token estimation: len(chars)/4 as cheap heuristic before expensive API call"
  - "Knowledge Transfer pattern: auto-generate KT doc and reset conversation at token limit"
  - "Mock Anthropic client pattern: MockStreamResponse + MockTokenCountResult for tests"

requirements-completed: [STRAT-08]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 6 Plan 02: Strategist Conversation Summary

**Persistent Claude API conversation manager with token tracking, Knowledge Transfer handoff at 800K tokens, and asyncio.Lock concurrency guard**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T20:51:57Z
- **Completed:** 2026-03-25T20:55:24Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 6

## Accomplishments
- StrategistConversation class with streaming send(), persistent message list, and token tracking
- Knowledge Transfer document generation extracting decisions, personality, open threads from conversation
- Token counting with rough char/4 estimates and periodic count_tokens API calls (Pitfall 2)
- asyncio.Lock prevents concurrent message interleaving (Pitfall 8)
- Graceful fallback to DEFAULT_PERSONA when persona file missing (Pitfall 7)
- 13 tests all passing with fully mocked Anthropic client

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests** - `dec3e63` (test)
2. **Task 1 GREEN: Implementation** - `494b59c` (feat)

_TDD task with RED and GREEN commits._

## Files Created/Modified
- `src/vcompany/strategist/__init__.py` - Strategist package init
- `src/vcompany/strategist/conversation.py` - StrategistConversation class with persistent messages, token tracking, KT handoff
- `src/vcompany/strategist/knowledge_transfer.py` - generate_knowledge_transfer() builds KT markdown document
- `tests/test_conversation.py` - 13 tests covering send, persistence, tokens, KT, lock, persona, rough estimates
- `pyproject.toml` - Added anthropic SDK dependency
- `uv.lock` - Updated lockfile with anthropic and transitive deps

## Decisions Made
- Token check logic refined: always call count_tokens on first check (when _total_tokens == 0) regardless of message interval, to avoid missing the limit on conversations seeded with large content
- Rough estimate threshold (700K) gates API calls; only when rough estimate is high does the system call count_tokens
- KT document format uses plain markdown with sections for decisions, personality calibration, open threads, and system prompt

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed token check interval logic**
- **Found during:** Task 1 GREEN phase
- **Issue:** The original interval-gating condition (`_message_count_since_check < TOKEN_CHECK_INTERVAL and _total_tokens < TOKEN_CHECK_THRESHOLD`) would skip the API call even when rough estimate was very high, if no prior count had been done yet (_total_tokens == 0)
- **Fix:** Changed condition to always call count_tokens when _total_tokens is 0 (first check), or when rough estimate exceeds TOKEN_LIMIT (urgent)
- **Files modified:** src/vcompany/strategist/conversation.py
- **Verification:** test_token_check_triggers_kt_on_limit passes
- **Committed in:** 494b59c

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential for correctness -- without fix, KT would never trigger for conversations that hadn't previously been token-counted.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required. The anthropic SDK is installed but ANTHROPIC_API_KEY is only needed at runtime.

## Known Stubs
None - all code paths are fully wired.

## Next Phase Readiness
- StrategistConversation ready for use by StrategistCog (Plan 03/04)
- Knowledge Transfer ready for integration with conversation lifecycle
- Mock patterns established for future tests needing Anthropic client mocks

---
*Phase: 06-pm-strategist-and-milestones*
*Completed: 2026-03-25*
