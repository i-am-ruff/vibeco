# Phase 10: MessageQueue Notification Routing - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure/gap-closure phase)

<domain>
## Phase Boundary

Route all outbound Discord notifications through MessageQueue for rate-limit backoff and priority ordering. Remove all direct channel.send() calls from notification paths.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure/gap-closure phase. Key constraints from milestone audit:
- HealthCog._notify_state_change() must use message_queue.enqueue(QueuedMessage(...)) instead of channel.send()
- on_escalation, on_degraded, on_recovered callbacks in client.py must route through message_queue.enqueue()
- No direct channel.send() calls should remain in notification paths
- Escalations must have higher priority than health state change notifications
- Old direct-send code paths must be fully removed

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — gap closure phase. Refer to ROADMAP phase description, success criteria, and v2.0-MILESTONE-AUDIT.md.

</specifics>

<deferred>
## Deferred Ideas

None — gap closure phase.

</deferred>
