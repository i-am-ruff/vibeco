# Phase 3: GsdAgent - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

GsdAgent is the first real container type with an internal phase state machine that replaces WorkflowOrchestrator, with checkpoint-based crash recovery. This phase builds the GsdAgent class (subclassing AgentContainer), the internal phase FSM (IDLE→DISCUSS→PLAN→EXECUTE→UAT→SHIP), checkpoint persistence to memory_store, and crash recovery that resumes from the last checkpointed state.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key technical anchors from requirements:
- Internal phase FSM: IDLE→DISCUSS→PLAN→EXECUTE→UAT→SHIP nested inside container RUNNING state (TYPE-01)
- Checkpoint to memory_store on each phase transition — crash recovery resumes from last checkpoint (TYPE-02)
- Absorbs WorkflowOrchestrator's state tracking — no external system tracks phase state (TYPE-01)
- Use python-statemachine compound states for nesting (from success criteria)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/container/container.py` — AgentContainer base class with lifecycle FSM, memory_store, health
- `src/vcompany/container/state_machine.py` — ContainerLifecycle FSM (6 states, after_transition callback)
- `src/vcompany/container/memory_store.py` — MemoryStore async SQLite (KV + checkpoints)
- `src/vcompany/supervisor/supervisor.py` — Supervisor with restart strategies
- `src/vcompany/orchestrator/workflow_orchestrator.py` — v1 WorkflowOrchestrator (to be absorbed)

### Established Patterns
- python-statemachine for FSMs
- Pydantic models for data
- asyncio + pytest-asyncio for testing
- AgentContainer.from_spec() factory pattern

### Integration Points
- GsdAgent subclasses AgentContainer
- Supervisor manages GsdAgent instances via ChildSpec
- MemoryStore persists checkpoint state
- Phase FSM nested inside container RUNNING state

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase with clear scope.

</deferred>
