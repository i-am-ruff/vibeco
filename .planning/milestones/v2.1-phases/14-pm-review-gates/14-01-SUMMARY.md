---
phase: 14-pm-review-gates
plan: 01
subsystem: agent
tags: [asyncio, future, gate, discord, review, throttle]

# Dependency graph
requires:
  - phase: 13-pm-event-routing
    provides: phase transition callbacks (_on_phase_transition) wired in VcoBot.on_ready

provides:
  - GsdAgent._pending_review Future blocking advance_phase() until PM decision
  - GsdAgent.resolve_review() for external gate resolution by PlanReviewCog
  - GsdAgent._on_review_request callback hook for VcoBot wiring
  - PlanReviewCog._post_throttled() with 30s per-agent rate limiting
  - PlanReviewCog._build_review_attachments() for stage-appropriate file collection
  - PlanReviewCog.post_review_request() main entry point for review dispatch

affects:
  - 14-pm-review-gates (Plan 02 wires VcoBot.on_ready to connect _on_review_request to post_review_request)
  - any future plans that call advance_phase() (now returns str gate decision)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "asyncio.Future gate pattern: advance_phase() creates Future, external caller resolves via resolve_review()"
    - "time.monotonic() per-agent throttle dict for Discord message rate limiting"
    - "stage-to-glob mapping for file attachment selection (discuss->CONTEXT.md, plan->PLAN.md, etc.)"

key-files:
  created: []
  modified:
    - src/vcompany/agent/gsd_agent.py
    - src/vcompany/bot/cogs/plan_review.py
    - tests/test_gsd_agent.py

key-decisions:
  - "Gate always activates in advance_phase() -- tests use auto-approve _on_review_request for isolation"
  - "resolve_review() returns bool (True if gate was active) to allow callers to detect no-op calls"
  - "post_review_request() is the wiring entry point -- VcoBot.on_ready will assign it to _on_review_request in Plan 02"
  - "1MB file size guard in _build_review_attachments prevents Discord attachment limit errors"
  - "attachments or None passed to _post_throttled -- empty list sends no files, None is cleaner"

patterns-established:
  - "Future gate pattern: create Future, post external notification, await Future, return result"
  - "Throttle dict pattern: dict[agent_id, float] monotonic time, sleep(remaining) before posting"

requirements-completed: [GATE-01, GATE-04, GATE-05]

# Metrics
duration: 15min
completed: 2026-03-28
---

# Phase 14 Plan 01: PM Review Gates — Agent Gate Mechanism Summary

**asyncio.Future gate in GsdAgent.advance_phase() blocks until PM decision, with PlanReviewCog throttled posting and stage-appropriate file attachment collection**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-28T16:41:12Z
- **Completed:** 2026-03-28T16:56:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- GsdAgent.advance_phase() now creates an asyncio.Future gate and blocks until resolve_review() is called with "approve", "modify", or "clarify"
- GsdAgent.resolve_review() provides the external resolution point for PlanReviewCog
- _on_review_request callback hook established for VcoBot wiring in Plan 02
- PlanReviewCog._post_throttled() enforces 30s per-agent message throttle using time.monotonic()
- PlanReviewCog._build_review_attachments() maps GSD stages to appropriate document globs
- PlanReviewCog.post_review_request() is the wired entry point that combines channel lookup, attachment collection, and throttled posting

## Task Commits

Each task was committed atomically:

1. **Task 1: Add gate Future and review request to GsdAgent** - `c9f69ad` (feat)
2. **Task 2: Add throttled review posting and file attachment builder to PlanReviewCog** - `5a36b2e` (feat)

## Files Created/Modified

- `src/vcompany/agent/gsd_agent.py` - _pending_review Future, resolve_review(), _on_review_request hook, advance_phase() gate logic
- `src/vcompany/bot/cogs/plan_review.py` - _last_review_time dict, _REVIEW_THROTTLE_SECS, _post_throttled(), _build_review_attachments(), post_review_request()
- `tests/test_gsd_agent.py` - _make_agent updated with auto-approve _on_review_request for test isolation

## Decisions Made

- Gate always activates in advance_phase() regardless of whether _on_review_request is wired. Tests use an auto-approve callback wired in _make_agent() for isolation.
- resolve_review() returns bool to allow callers to detect whether a gate was active (True = resolved, False = no-op).
- advance_phase() return type changed from None to str — this is a breaking API change but all tests updated.
- 1MB file size guard in _build_review_attachments prevents Discord upload limit errors.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing tests to work with gate-blocking advance_phase()**
- **Found during:** Task 1 (GsdAgent gate implementation)
- **Issue:** All 19 existing tests call advance_phase() without any mechanism to resolve the Future gate, so they would hang indefinitely
- **Fix:** Updated _make_agent() in test_gsd_agent.py to wire an auto-approve _on_review_request callback that immediately calls resolve_review("approve")
- **Files modified:** tests/test_gsd_agent.py
- **Verification:** 19 tests pass in 1.55s with no hangs
- **Committed in:** c9f69ad (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug)
**Impact on plan:** Required fix — without it, all existing tests hang. Auto-approve pattern is correct for test isolation.

## Issues Encountered

None.

## Next Phase Readiness

- Gate mechanism is complete and tested
- Plan 02 needs to wire VcoBot.on_ready: assign `plan_review_cog.post_review_request` to each GsdAgent's `_on_review_request` attribute
- Plan 02 also needs to wire `plan_review_cog.resolve_review(agent_id, decision)` dispatch when PM responds in Discord

---
*Phase: 14-pm-review-gates*
*Completed: 2026-03-28*

## Self-Check: PASSED

- FOUND: src/vcompany/agent/gsd_agent.py
- FOUND: src/vcompany/bot/cogs/plan_review.py
- FOUND: .planning/phases/14-pm-review-gates/14-01-SUMMARY.md
- FOUND commit: c9f69ad (Task 1)
- FOUND commit: 5a36b2e (Task 2)
