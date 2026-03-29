---
phase: 20-companyroot-extraction
plan: 02
subsystem: daemon
tags: [runtime-api, callbacks, comm-port, relay, platform-agnostic]

requires:
  - phase: 20-companyroot-extraction
    plan: 01
    provides: RuntimeAPI gateway class and CommunicationPort extension
provides:
  - All 22 callback replacements as typed RuntimeAPI methods
  - Inbound relay methods for COMM-04 (strategist messages) and COMM-05 (plan review)
  - new_project() method for full project initialization
  - CompanyRoot.hire() without guild dependency
affects: [20-03, 20-04, bot-refactor]

tech-stack:
  added: []
  patterns: [callback-to-method extraction, inbound relay pattern, closure factory methods]

key-files:
  created: []
  modified:
    - src/vcompany/daemon/runtime_api.py
    - src/vcompany/supervisor/company_root.py

key-decisions:
  - "Callback methods use _get_comm().send_message with SendMessagePayload for all notifications"
  - "new_project() preserves PM event sink ordering constraint (wired LAST per Research Pitfall 2)"
  - "Inbound relay methods (relay_strategist_message, handle_plan_approval/rejection) decouple bot cogs from container internals"
  - "Guild parameter removed from CompanyRoot.hire() -- channel creation handled by RuntimeAPI via CommunicationPort"

patterns-established:
  - "Closure factory pattern: _make_pm_event_sink, _make_gsd_cb, _make_briefing_cb return typed callbacks"
  - "Inbound relay pattern: bot cogs call RuntimeAPI relay methods instead of container methods directly"

requirements-completed: [EXTRACT-03, COMM-04, COMM-05]

duration: 177s
completed: 2026-03-29
---

# Phase 20 Plan 02: Callback Replacement and Inbound Relay Methods Summary

**22 on_ready closure replacements as typed RuntimeAPI methods using CommunicationPort, plus inbound relay methods for bidirectional COMM-04/COMM-05 paths**

## Performance

- **Duration:** 2 min 57 sec
- **Started:** 2026-03-29T03:15:05Z
- **Completed:** 2026-03-29T03:18:02Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- All 22 on_ready callback closures replaced with typed RuntimeAPI methods
- Category A: 5 alert/notification methods (_on_escalation, _on_degraded, _on_recovered, _on_trigger_integration_review, _on_send_intervention)
- Category B: Strategist response callback (_on_strategist_response) with 2000-char chunking
- Category C: 3 PM event routing factory methods (_make_pm_event_sink, _make_gsd_cb, _make_briefing_cb)
- Category D: 2 review gate callbacks (_post_review_request, _dispatch_pm_review)
- Category E: 4 PM action callbacks (_on_assign_task, _on_recruit_agent, _on_remove_agent, _on_escalate_to_strategist)
- Category F: 4 inbound relay methods (relay_strategist_message, relay_strategist_escalation_reply, handle_plan_approval, handle_plan_rejection)
- new_project() method orchestrates full project initialization with correct PM event sink ordering
- CompanyRoot.hire() guild parameter removed; channel creation now in RuntimeAPI via CommunicationPort
- Zero discord.py imports in daemon package maintained

## Task Commits

Each task was committed atomically:

1. **Task 1: Add all callback methods and inbound relay methods to RuntimeAPI** - `7280d09` (feat)
2. **Task 2: Remove guild parameter from CompanyRoot.hire()** - `15168f3` (refactor)

## Files Created/Modified

- `src/vcompany/daemon/runtime_api.py` - Extended with 22 callback methods, 4 inbound relay methods, and new_project()
- `src/vcompany/supervisor/company_root.py` - Removed guild param from hire() and dispatch_task_agent(), removed Discord channel creation block

## Decisions Made

- Callback methods use _get_comm().send_message with SendMessagePayload for all notifications -- consistent CommunicationPort usage
- new_project() preserves PM event sink ordering constraint (wired LAST) per Research Pitfall 2
- Inbound relay methods decouple bot cogs from container internals -- bot calls RuntimeAPI, not containers directly
- Guild parameter removed from CompanyRoot.hire() -- channel creation is RuntimeAPI's responsibility

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- RuntimeAPI now has complete callback replacement methods for Plan 03 (bot refactoring)
- Inbound relay methods ready for StrategistCog and PlanReviewCog to call
- CompanyRoot decoupled from Discord -- no guild references remain

## Known Stubs

None -- all methods are fully implemented with CommunicationPort integration.

## Self-Check: PASSED

---
*Phase: 20-companyroot-extraction*
*Completed: 2026-03-29*
