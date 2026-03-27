---
phase: 05-hooks-and-plan-gate
plan: 03
subsystem: discord
tags: [discord.py, views, modals, embeds, plan-gate, cog]

# Dependency graph
requires:
  - phase: 04-discord-bot
    provides: VcoBot client, Cog architecture, ConfirmView pattern, embeds.py
  - phase: 05-hooks-and-plan-gate
    provides: AgentMonitorState with plan_gate fields (plan 02), safety_validator (plan 02)
provides:
  - PlanReviewView with Approve/Reject buttons for plan gate UI
  - RejectFeedbackModal for rejection feedback capture
  - build_plan_review_embed for rich plan review embeds
  - Full PlanReviewCog with plan gate workflow (detect, post, approve/reject, trigger execution)
  - make_sync_callback bridge for monitor integration
affects: [05-04, 06-strategist]

# Tech tracking
tech-stack:
  added: []
  patterns: [discord.ui.View with button callbacks, discord.ui.Modal for text input, sync-to-async callback bridge]

key-files:
  created:
    - src/vcompany/bot/views/plan_review.py
    - src/vcompany/bot/views/reject_modal.py
    - tests/test_plan_review_cog.py
  modified:
    - src/vcompany/bot/cogs/plan_review.py
    - src/vcompany/bot/embeds.py
    - src/vcompany/bot/views/__init__.py

key-decisions:
  - "3600s view timeout for plan review (1 hour) -- plans may sit unreviewed while owner is away"
  - "TextInput._value used in tests to work around discord.py property with no setter"
  - "State transitions tracked in AgentMonitorState via _update_gate_state method"

patterns-established:
  - "discord.ui.Modal pattern: TextInput fields as class attributes, on_submit captures values"
  - "Plan gate state machine: idle -> awaiting_review -> approved/rejected"
  - "Frontmatter extraction via regex for plan metadata parsing"

requirements-completed: [GATE-02, GATE-03, GATE-04]

# Metrics
duration: 5min
completed: 2026-03-25
---

# Phase 05 Plan 03: Plan Review Cog Summary

**Discord plan gate UI with Approve/Reject buttons, rejection feedback modal, safety-validated embeds, and full PlanReviewCog workflow for agent plan review**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-25T18:11:06Z
- **Completed:** 2026-03-25T18:15:51Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- PlanReviewView with Approve/Reject buttons following ConfirmView pattern, 3600s timeout
- RejectFeedbackModal capturing rejection feedback text via discord.ui.Modal
- build_plan_review_embed with safety validation status indicator (green/orange)
- Full PlanReviewCog: reads plans, validates safety tables, posts embeds with file attachments, handles approve/reject, triggers execution when all plans approved, sends rejection feedback to tmux pane
- 29 tests covering all components

## Task Commits

Each task was committed atomically:

1. **Task 1: Create PlanReviewView, RejectFeedbackModal, and plan review embed builder** - `03c2142` (test: RED), `a14539d` (feat: GREEN)
2. **Task 2: Expand PlanReviewCog with full plan gate workflow** - `6a6907e` (feat)

_Note: Task 1 used TDD with RED/GREEN commits_

## Files Created/Modified
- `src/vcompany/bot/views/plan_review.py` - PlanReviewView with Approve/Reject buttons
- `src/vcompany/bot/views/reject_modal.py` - RejectFeedbackModal for rejection feedback
- `src/vcompany/bot/views/__init__.py` - Updated exports for new views
- `src/vcompany/bot/embeds.py` - Added build_plan_review_embed with safety warning support
- `src/vcompany/bot/cogs/plan_review.py` - Full PlanReviewCog with plan gate workflow
- `tests/test_plan_review_cog.py` - 29 tests for all components

## Decisions Made
- 3600s view timeout for plan review -- plans may sit unreviewed while owner is away
- TextInput._value used in tests to work around discord.py property with no setter
- State transitions tracked in AgentMonitorState via _update_gate_state method
- Frontmatter extraction via regex (simple, no YAML dependency for plan parsing)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TextInput value property in tests**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** discord.py TextInput.value is a read-only property, cannot be set directly in tests
- **Fix:** Used modal.feedback._value to set the internal value for testing
- **Files modified:** tests/test_plan_review_cog.py
- **Verification:** All 29 tests pass
- **Committed in:** a14539d (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor test adjustment, no scope change.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan gate UI complete and testable
- PlanReviewCog ready for integration with monitor loop callbacks
- Phase 05 Plan 04 can wire the PlanReviewCog callbacks into the bot startup flow

## Self-Check: PASSED

All 6 files verified present. All 3 commit hashes found in git log.

---
*Phase: 05-hooks-and-plan-gate*
*Completed: 2026-03-25*
