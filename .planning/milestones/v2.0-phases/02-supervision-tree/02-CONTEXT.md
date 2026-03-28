# Phase 2: Supervision Tree - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Supervisors manage child containers with Erlang-style restart policies, intensity-limited restart windows, and escalation to parent when limits are exceeded. This phase builds the two-level supervision hierarchy (CompanyRoot → ProjectSupervisor → agent containers), three restart strategies (one_for_one, all_for_one, rest_for_one), restart intensity tracking with 10-minute windows, and escalation protocol.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key technical anchors from requirements:
- Two-level hierarchy: CompanyRoot → ProjectSupervisor → agent containers (SUPV-01)
- one_for_one: restart only failed child (SUPV-02)
- all_for_one: restart all children when one fails (SUPV-03)
- rest_for_one: restart failed child + all started after it (SUPV-04)
- Max restart intensity with 10-minute windows (not 60s) for slow Claude Code bootstrap (SUPV-05)
- Escalation to parent when max restarts exceeded; top-level alerts owner via Discord (SUPV-06)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/container/` — Phase 1 container foundation (AgentContainer, ContainerLifecycle, ChildSpec, HealthReport, CommunicationPort)
- `src/vcompany/container/child_spec.py` — RestartPolicy enum (PERMANENT, TEMPORARY, TRANSIENT), ChildSpec, ChildSpecRegistry
- `src/vcompany/container/state_machine.py` — ContainerLifecycle FSM with send_event dispatch
- `src/vcompany/container/container.py` — AgentContainer with from_spec() factory

### Established Patterns
- Pydantic models for data structures
- asyncio for async operations
- python-statemachine for FSMs
- TDD with pytest + pytest-asyncio

### Integration Points
- Supervisors consume ChildSpec from Phase 1 registry to spawn containers
- AgentContainer.start()/stop() methods called by supervisor during restart
- HealthReport from containers feeds into Phase 5 health tree
- CommunicationPort used for Discord escalation alerts (SUPV-06)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase with clear scope.

</deferred>
