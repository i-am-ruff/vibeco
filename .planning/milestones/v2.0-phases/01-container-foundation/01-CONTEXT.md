# Phase 1: Container Foundation - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Every agent is wrapped in a container with a validated lifecycle state machine, persistent memory, self-reported health, and a declared communication contract. This phase builds the foundational AgentContainer abstraction, state machine, memory store, child specification registry, and communication interface — all pure infrastructure with no user-facing behavior changes.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key technical anchors from requirements:
- State machine states: CREATING, RUNNING, SLEEPING, ERRORED, STOPPED, DESTROYED (CONT-01)
- Invalid transitions must raise validation errors (CONT-02)
- Container context: agent_id, type, parent_id, project_id, owned dirs, GSD mode, system prompt (CONT-03)
- Per-agent SQLite file for memory_store (CONT-04)
- Child specification registry for supervisor consumption (CONT-05)
- Communication designed for Discord-only message passing — no file IPC, no in-memory callbacks (CONT-06)
- HealthReport: state, inner_state, uptime, last_heartbeat, error_count, last_activity (HLTH-01)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/models/agent_state.py` — existing agent state model, may inform container state design
- `src/vcompany/models/config.py` — Pydantic config models (agents.yaml schema)
- `src/vcompany/orchestrator/agent_manager.py` — current agent lifecycle management (v1, to be replaced)
- `src/vcompany/orchestrator/crash_tracker.py` — crash recovery logic (v1, restart semantics to absorb)
- `src/vcompany/shared/` — shared utilities (file_ops, logging, paths, templates)

### Established Patterns
- Pydantic models for configuration and state validation
- Python 3.12+ with async patterns (discord.py, asyncio)
- uv for package management
- Module-per-concern under `src/vcompany/`

### Integration Points
- New container module will sit alongside existing `orchestrator/` and `models/`
- Supervision tree (Phase 2) will consume child specs from this phase
- Health reports feed into Phase 5 health tree aggregation

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase with clear scope.

</deferred>
