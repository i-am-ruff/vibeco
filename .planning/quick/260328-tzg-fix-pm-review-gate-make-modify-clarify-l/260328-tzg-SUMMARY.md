---
type: quick
task_id: 260328-tzg
title: Fix PM review gate — modify/clarify re-entrant loop and all-stage PM review
one_liner: "PM review gate now loops on modify/clarify until approve, and PlanReviewer evaluates all GSD stage artifacts (not just plan)"
status: complete
completed_date: "2026-03-28"
duration_mins: 12
tasks_completed: 2
files_modified:
  - src/vcompany/agent/gsd_agent.py
  - src/vcompany/bot/cogs/plan_review.py
  - tests/test_gsd_agent.py
commits:
  - "846269e: feat(quick-tzg): advance_phase() loops on modify/clarify until approve"
  - "25a1136: feat(quick-tzg): dispatch_pm_review uses PlanReviewer for all GSD stages"
key_decisions:
  - "Gate loop re-creates Future each iteration to handle modify/clarify correctly"
  - "Max attempts safety valve (default 3) prevents infinite loops"
  - "PlanReviewer used for all stages — non-plan artifacts pass scope/dep/dup checks gracefully"
  - "Test phase names fixed to respect FSM transition order (discuss from idle)"
---

# Quick Task 260328-tzg: Fix PM review gate — modify/clarify re-entrant loop and all-stage PM review

## What Was Done

### Task 1: advance_phase() loops until approve (846269e)

Replaced the single `asyncio.Future` await-and-return in `GsdAgent.advance_phase()` with a `while True` loop that:

- Re-creates the `_pending_review` Future each iteration
- Only returns on `"approve"` decision
- Increments `_review_attempts` on modify/clarify and loops back
- Auto-approves after `_max_review_attempts` (default 3) to prevent infinite loops
- Properly clears `_pending_review = None` in the `finally` block each iteration

Added `TestReviewGateLoop` with 3 tests:
- `test_modify_then_approve`: Gate blocks after modify, continues after approve
- `test_clarify_then_modify_then_approve`: Multiple non-approvals loop correctly
- `test_max_attempts_auto_approves`: Safety valve fires after max attempts

### Task 2: dispatch_pm_review uses PlanReviewer for all stages (25a1136)

Replaced the `if stage == "plan" and self._plan_reviewer:` guard in `PlanReviewCog.dispatch_pm_review()` with `if self._plan_reviewer and artifact_content:`, enabling PM evaluation for all 5 GSD stages (discuss, plan, execute, uat, ship).

- Non-plan artifacts lacking YAML frontmatter still pass scope/dep/dup checks (empty `files_modified` = scope passes, no `depends_on` = dep passes)
- Fallback auto-approve only triggers when no reviewer is configured or no artifacts found
- Updated docstring to remove "auto-approves other stages" wording
- Removed outdated `# (Full PMTier integration for non-plan stages is Phase 15 scope)` comment

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test phase names to respect FSM transition order**

- **Found during:** Task 1, running tests
- **Issue:** Plan spec tests used `advance_phase("plan")` and `advance_phase("execute")` directly from idle state, but the GsdLifecycle FSM requires `idle -> discuss -> plan -> execute`. These caused `TransitionNotAllowed` errors.
- **Fix:** Changed all three TestReviewGateLoop tests to use `advance_phase("discuss")` (valid from idle). The looping behavior under test is phase-agnostic — the fix preserves test intent.
- **Files modified:** tests/test_gsd_agent.py

## Known Stubs

None.

## Self-Check: PASSED

- src/vcompany/agent/gsd_agent.py: FOUND
- src/vcompany/bot/cogs/plan_review.py: FOUND
- tests/test_gsd_agent.py: FOUND
- Commit 846269e: FOUND
- Commit 25a1136: FOUND
- All 51 tests pass (tests/test_plan_review_cog.py + tests/test_gsd_agent.py)
