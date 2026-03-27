# Phase 6: Resilience - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

The communication layer handles Discord rate limits gracefully, supervisors detect upstream outages, and the system degrades safely when Claude servers are unreachable. This phase builds rate-aware message queuing, upstream outage detection in supervisors, and degraded mode for Claude API unavailability.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase.

Key technical anchors from requirements:
- Rate-aware batching: health reports debounced, supervisor commands prioritized, exponential backoff on 429s (RESL-01)
- Upstream outage detection: all children failing simultaneously triggers global backoff, not per-agent restart loops (RESL-02)
- Degraded mode: Claude unreachable → containers stay alive, no new dispatches, owner notified, auto-recovery (RESL-03)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/container/communication.py` — CommunicationPort Protocol
- `src/vcompany/supervisor/supervisor.py` — Supervisor with restart strategies
- `src/vcompany/supervisor/company_root.py` — CompanyRoot top-level
- `src/vcompany/bot/cogs/health.py` — HealthCog with notification delivery
- `src/vcompany/supervisor/restart_tracker.py` — RestartTracker sliding window

### Integration Points
- Message queue sits between containers/supervisors and Discord API
- Outage detection extends Supervisor._handle_child_failure()
- Degraded mode managed at CompanyRoot level
- Owner notification via existing HealthCog or AlertsCog

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
