---
phase: 06-pm-strategist-and-milestones
plan: 05
subsystem: bot, strategist, cli, coordination
tags: [pm, strategist, anthropic, discord, milestone, sync-context, escalation]

# Dependency graph
requires:
  - phase: 06-03
    provides: PMTier, PlanReviewer, ConfidenceScorer models
  - phase: 06-04
    provides: StrategistCog with handle_pm_escalation, post_owner_escalation, DecisionLogger
provides:
  - PM intercept in QuestionHandlerCog (HIGH auto-answer, MEDIUM suggest, LOW escalate)
  - PM review in PlanReviewCog (HIGH auto-approve, LOW manual review)
  - Strategist initialization at bot startup with persona and Anthropic API
  - Periodic status digests from MonitorLoop to Strategist (30 min interval)
  - vco new-milestone CLI command with scope update, reset, dispatch
  - PM-CONTEXT.md sync (D-20 rename from STRATEGIST-PROMPT.md)
  - Owner escalation with indefinite wait for strategic decisions (D-07)
affects: [07-integration-and-testing]

# Tech tracking
tech-stack:
  added: []
  patterns: [PM intercept before answer buttons, PM review before plan posting, graceful degradation without API key, indefinite-wait owner escalation]

key-files:
  created:
    - src/vcompany/cli/new_milestone_cmd.py
    - tests/test_pm_integration.py
    - tests/test_milestone.py
  modified:
    - src/vcompany/bot/cogs/question_handler.py
    - src/vcompany/bot/cogs/plan_review.py
    - src/vcompany/bot/client.py
    - src/vcompany/bot/config.py
    - src/vcompany/monitor/loop.py
    - src/vcompany/coordination/sync_context.py
    - src/vcompany/cli/main.py
    - tests/test_sync_context.py

key-decisions:
  - "PM intercept uses set_pm/set_plan_reviewer injection pattern for testability"
  - "LOW confidence exhausting PM+Strategist routes to Owner via post_owner_escalation with indefinite wait per D-07"
  - "Bot gracefully degrades when ANTHROPIC_API_KEY not set -- falls through to standard Phase 5 AnswerView buttons"
  - "Status digest callback wired as sync function for MonitorLoop thread compatibility"
  - "sync_context auto-generates PM-CONTEXT.md via context_builder before distributing"

patterns-established:
  - "PM injection: set_pm()/set_plan_reviewer() methods for dependency injection into cogs"
  - "Three-tier escalation: PM -> Strategist -> Owner with indefinite wait at owner level"
  - "Graceful degradation: All PM/Strategist features disabled without API key, standard flow preserved"
  - "Status digest change detection: only send when content differs from last digest"

requirements-completed: [MILE-01, STRAT-01, STRAT-02, STRAT-03, STRAT-04, STRAT-05, STRAT-06, STRAT-07]

# Metrics
duration: 9min
completed: 2026-03-25
---

# Phase 6 Plan 5: PM/Strategist Integration Wiring Summary

**Two-tier AI decision system wired into Discord bot: PM intercepts questions/plans with confidence-based routing, Strategist handles escalations, owner gets indefinite-wait escalation for LOW+LOW, plus milestone CLI and PM-CONTEXT.md sync**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-25T21:04:48Z
- **Completed:** 2026-03-25T21:13:59Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- QuestionHandlerCog routes through PM before answer buttons: HIGH auto-answers, MEDIUM suggests with override buttons, LOW escalates to Strategist then Owner
- PlanReviewCog runs PM three-check review before posting: HIGH auto-approves with notification, LOW falls through to manual button review
- Bot startup initializes PM/Strategist from BotConfig with graceful degradation when ANTHROPIC_API_KEY not set
- MonitorLoop sends periodic status digests every 30 minutes with change detection
- vco new-milestone command handles milestone transitions with scope update, PM-CONTEXT generation, context sync, optional reset and dispatch
- STRATEGIST-PROMPT.md renamed to PM-CONTEXT.md in sync-context with backward compatibility

## Task Commits

Each task was committed atomically:

1. **Task 1: PM intercepts + bot startup wiring** - `88e5568` (feat)
2. **Task 2: Milestone CLI + sync-context** - `72a7a61` (test, RED) + `f85fc9f` (feat, GREEN)

## Files Created/Modified
- `src/vcompany/bot/config.py` - Added anthropic_api_key, strategist_persona_path, status_digest_interval fields
- `src/vcompany/bot/cogs/question_handler.py` - PM intercept with three-tier escalation (HIGH/MEDIUM/LOW) before answer buttons
- `src/vcompany/bot/cogs/plan_review.py` - PM review intercept with auto-approve on HIGH confidence
- `src/vcompany/bot/client.py` - PM/Strategist initialization in on_ready with graceful degradation
- `src/vcompany/monitor/loop.py` - Periodic status digest callback with change detection
- `src/vcompany/coordination/sync_context.py` - PM-CONTEXT.md in SYNC_FILES, backward compat rename, auto-generation
- `src/vcompany/cli/new_milestone_cmd.py` - New vco new-milestone CLI command
- `src/vcompany/cli/main.py` - Registered new-milestone command
- `tests/test_pm_integration.py` - 10 tests for PM intercept, plan review, config, digest
- `tests/test_milestone.py` - 11 tests for milestone CLI and sync-context
- `tests/test_sync_context.py` - Updated for D-20 rename

## Decisions Made
- PM injection via set_pm()/set_plan_reviewer() methods for testability and optional initialization
- LOW confidence path that exhausts both PM and Strategist routes to Owner via post_owner_escalation which waits indefinitely per D-07 -- does NOT fall through to AnswerView 10-minute timeout
- Bot gracefully degrades when ANTHROPIC_API_KEY not set -- all PM/Strategist features disabled, standard Phase 5 flow preserved
- Status digest uses change detection to avoid sending duplicate content to Strategist

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing sync_context tests for D-20 rename**
- **Found during:** Task 2 (sync-context update)
- **Issue:** Existing tests in test_sync_context.py expected STRATEGIST-PROMPT.md in SYNC_FILES and exact file counts
- **Fix:** Updated 3 tests to use PM-CONTEXT.md and flexible counts since context_builder auto-generates PM-CONTEXT.md
- **Files modified:** tests/test_sync_context.py
- **Verification:** All 419 tests pass
- **Committed in:** f85fc9f (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary fix for existing tests broken by D-20 rename. No scope creep.

## Issues Encountered
None beyond the test update noted in deviations.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Full two-tier AI decision system wired and tested
- Milestone CLI ready for production use
- All PM/Strategist features from Plans 02-05 integrated into Discord bot
- Phase 7 (Integration) can proceed with all orchestration features in place

---
*Phase: 06-pm-strategist-and-milestones*
*Completed: 2026-03-25*

## Self-Check: PASSED

All 11 files verified present. All 3 commit hashes verified in git log.
