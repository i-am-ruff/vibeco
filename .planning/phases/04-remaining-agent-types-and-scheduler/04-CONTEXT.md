# Phase 4: Remaining Agent Types and Scheduler - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

ContinuousAgent, FulltimeAgent, and CompanyAgent are operational as containers, and sleeping agents wake on schedule. This phase builds three new agent type containers (each subclassing AgentContainer) and a scheduler that triggers WAKE on sleeping ContinuousAgents per their configured schedule.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key technical anchors from requirements:
- ContinuousAgent: scheduled wake/sleep cycles (WAKE→GATHER→ANALYZE→ACT→REPORT→SLEEP), persists state via memory_store (TYPE-03)
- FulltimeAgent (PM): event-driven, reacts to state transitions, health changes, escalations, briefings, lives for project duration (TYPE-04)
- CompanyAgent (Strategist): event-driven, survives project restarts, holds cross-project state (TYPE-05)
- Scheduler in CompanyRoot triggers WAKE on sleeping ContinuousAgents per configured schedule (AUTO-06)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/container/container.py` — AgentContainer base class
- `src/vcompany/agent/gsd_agent.py` — GsdAgent (first concrete type, pattern to follow)
- `src/vcompany/agent/gsd_lifecycle.py` — GsdLifecycle compound FSM (pattern for ContinuousAgent FSM)
- `src/vcompany/supervisor/company_root.py` — CompanyRoot (scheduler lives here)
- `src/vcompany/container/memory_store.py` — MemoryStore for state persistence

### Established Patterns
- Agent types subclass AgentContainer
- Custom lifecycle FSMs using python-statemachine compound states
- Pydantic models for data, asyncio for async
- ChildSpec for supervisor consumption

### Integration Points
- New agent types registered in ChildSpecRegistry
- CompanyRoot manages scheduler for ContinuousAgent wake
- FulltimeAgent receives events from supervision tree
- CompanyAgent persists cross-project state in memory_store

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
