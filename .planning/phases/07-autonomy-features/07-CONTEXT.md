# Phase 7: Autonomy Features - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

The PM manages a living milestone backlog, continuous agents can delegate task spawns through the supervisor, and agent crashes never corrupt project state. This phase builds the living backlog queue, delegation protocol with caps/rate limits, and crash-safe project state ownership.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase.

Key technical anchors from requirements:
- Living milestone backlog: PM-managed mutable queue (append, insert_after, insert_urgent, reorder, cancel) (AUTO-01)
- GsdAgent consumes work from living queue, not static list (AUTO-02)
- Delegation protocol: ContinuousAgent requests task spawns through supervisor with hard caps and rate limits (AUTO-03)
- Supervisor validates delegation requests, enforces policy, spawns short-lived task agents (AUTO-04)
- Project state owned by PM — agents read assignments and write completions, crash never corrupts (AUTO-05)
- Scheduler triggers already built in Phase 4 (AUTO-06 complete)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/agent/gsd_agent.py` — GsdAgent (task consumer)
- `src/vcompany/agent/fulltime_agent.py` — FulltimeAgent (PM, backlog owner)
- `src/vcompany/agent/continuous_agent.py` — ContinuousAgent (delegator)
- `src/vcompany/supervisor/supervisor.py` — Supervisor (delegation enforcement)
- `src/vcompany/supervisor/project_supervisor.py` — ProjectSupervisor
- `src/vcompany/container/memory_store.py` — MemoryStore for persistence

### Integration Points
- Living backlog stored in FulltimeAgent's memory_store
- GsdAgent reads assignments from backlog
- Delegation requests flow through Supervisor
- Project state persisted in PM's memory_store

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
