---
phase: 14-pm-review-gates
plan: 02
subsystem: agent
tags: [asyncio, future, gate, discord, review, pm, plan-reviewer]

# Dependency graph
requires:
  - phase: 14-pm-review-gates
    plan: 01
    provides: GsdAgent._pending_review Future, resolve_review(), _on_review_request hook, PlanReviewCog.post_review_request()

provides:
  - PlanReviewCog._handle_review_response() parsing PM review messages and resolving GsdAgent gate Futures
  - PlanReviewCog.dispatch_pm_review() evaluating stage artifacts via PlanReviewer (plan stage) or auto-approving others
  - FulltimeAgent._on_gsd_review callback attribute fired on every gsd_transition event
  - VcoBot.on_ready() wires _on_review_request on every GsdAgent and _on_gsd_review on FulltimeAgent

affects:
  - Phase 15 (full PMTier integration for non-plan stages builds on this auto-approve scaffold)
  - Any future plans that test the full gate loop end-to-end

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "on_message restructured: bot-authored [PM] messages handled before bot-author guard to avoid being silently skipped"
    - "Factory closures in on_ready: _make_review_cb and _make_gsd_review_cb prevent closure-over-loop-variable bug"
    - "GATE-01 wired outside pm_container guard (only needs PlanReviewCog), GATE-02 inside guard (needs PM)"

key-files:
  created: []
  modified:
    - src/vcompany/bot/cogs/plan_review.py
    - src/vcompany/agent/fulltime_agent.py
    - src/vcompany/bot/client.py

key-decisions:
  - "Bot [PM] messages detected before bot-author guard in on_message -- otherwise they are silently dropped"
  - "_on_review_request wired on all GsdAgents regardless of whether PM container exists (needs only PlanReviewCog)"
  - "dispatch_pm_review auto-approves non-plan stages with logging; full PMTier integration deferred to Phase 15"
  - "decision='clarify' as safe fallback in _handle_review_response when message matches no keyword"

patterns-established:
  - "Gate resolution pattern: on_message detects [PM] prefix -> _handle_review_response -> resolve_review()"
  - "PM dispatch pattern: FulltimeAgent._on_gsd_review -> dispatch_pm_review -> post [PM] response -> on_message resolves gate"

requirements-completed: [GATE-02, GATE-03]

# Metrics
duration: 10min
completed: 2026-03-28
---

# Phase 14 Plan 02: PM Review Gates -- PM Response Handler and VcoBot Wiring Summary

**Full bidirectional gate loop connected: agent stage transitions trigger PM review, PM evaluates artifacts via PlanReviewer, posts [PM] APPROVED/NEEDS CHANGES, on_message resolves the GsdAgent asyncio.Future gate**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-28T16:56:00Z
- **Completed:** 2026-03-28T17:04:01Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- PlanReviewCog.on_message restructured so bot-authored [PM] messages are intercepted before the bot-author guard, enabling automated PM response handling
- _handle_review_response() parses approve/modify/clarify keywords, looks up GsdAgent via company_root._find_container(), calls resolve_review() to unblock the waiting Future
- dispatch_pm_review() reads stage artifacts from clone directory, uses PlanReviewer for plan-stage evaluation, auto-approves other stages with logging
- FulltimeAgent gains _on_gsd_review callback attribute, fired on every gsd_transition event after logging
- VcoBot.on_ready() wires the complete gate loop: GATE-01 on all GsdAgents (outside pm_container guard), GATE-02 on FulltimeAgent (inside pm_container guard)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add gate response handler and PM review dispatch to PlanReviewCog** - `9edd5cf` (feat)
2. **Task 2: Wire review gate callbacks in VcoBot.on_ready()** - `9abe2e8` (feat)

## Files Created/Modified

- `src/vcompany/bot/cogs/plan_review.py` - Restructured on_message, added _handle_review_response(), dispatch_pm_review()
- `src/vcompany/agent/fulltime_agent.py` - Added _on_gsd_review callback attribute, fire it in gsd_transition handler
- `src/vcompany/bot/client.py` - GATE-01 and GATE-02 wiring with factory closures in on_ready()

## Decisions Made

- Bot-authored [PM] messages must be checked before the `if message.author.id == self.bot.user.id: return` guard -- otherwise the automated PM response loop never fires. The restructure checks for `[PM]` prefix first, then returns on non-[PM] bot messages.
- `_on_review_request` wired on all GsdAgents outside the `if pm_container is not None:` block -- GATE-01 only needs PlanReviewCog, not the PM container.
- `dispatch_pm_review` auto-approves non-plan stages (`discuss`, `execute`, `uat`, `ship`) with a log entry. Full PMTier integration for these stages is Phase 15 scope.
- Safe fallback: when no keyword matches in `_handle_review_response`, decision defaults to `"clarify"` (keeps gate open, does not auto-approve).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

- Full PM review gate loop is operational: agent calls advance_phase() -> Future gate created -> _on_review_request fires -> post_review_request() posts to Discord -> FulltimeAgent receives gsd_transition event -> dispatch_pm_review() evaluates -> posts [PM] response -> on_message detects -> _handle_review_response() resolves Future -> agent advances
- Phase 15 (PMTier for non-plan stages) can extend dispatch_pm_review() by adding PMTier evaluation in the fallback section
- All 29 PlanReviewCog tests pass; 7 VcoBot client tests pass

---
*Phase: 14-pm-review-gates*
*Completed: 2026-03-28*

## Self-Check: PASSED

- FOUND: src/vcompany/bot/cogs/plan_review.py
- FOUND: src/vcompany/agent/fulltime_agent.py
- FOUND: src/vcompany/bot/client.py
- FOUND: .planning/phases/14-pm-review-gates/14-02-SUMMARY.md
- FOUND commit: 9edd5cf (Task 1)
- FOUND commit: 9abe2e8 (Task 2)
