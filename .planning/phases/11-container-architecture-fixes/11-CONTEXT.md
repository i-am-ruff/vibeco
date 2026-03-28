# Phase 11: Container Architecture Fixes - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Containers have correct structure — Strategist lives under CompanyRoot, BLOCKED/STOPPING are real FSM states visible in health, and every container has a wired CommunicationPort.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key structural facts from codebase scout:

- Strategist is currently a Cog (StrategistCog), not a container — needs CompanyAgent container under CompanyRoot
- FSM has 6 states (creating, running, sleeping, errored, stopped, destroyed) — BLOCKED and STOPPING are missing
- CommunicationPort is a Protocol in container/communication.py — containers don't wire it yet
- CompanyRoot creates ProjectSupervisors but has no direct Strategist child
- on_ready() and /new-project both create containers — both paths need comm_port wiring

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ContainerStateMachine` in `src/vcompany/container/state_machine.py` — python-statemachine FSM, add states here
- `CommunicationPort` Protocol in `src/vcompany/container/communication.py` — already defined, needs implementation
- `CompanyRoot` in `src/vcompany/supervisor/company_root.py` — add Strategist as direct child
- `HealthReport`/`HealthNode`/`HealthTree` in `src/vcompany/container/health.py` — expose new states
- Container factory in `src/vcompany/container/factory.py` — registers agent types including `company`

### Established Patterns
- Supervision tree: CompanyRoot → ProjectSupervisor → AgentContainers
- FSM uses python-statemachine library with explicit state/transition definitions
- Health tree built via `health_tree()` methods on supervisors
- Container creation via `ChildSpec` + factory pattern
- `FulltimeAgent` for event-driven agents (PM), `CompanyAgent` for company-level agents

### Integration Points
- `VcoBot.on_ready()` in `src/vcompany/bot/client.py` — container startup
- `/new-project` in `src/vcompany/bot/cogs/commands.py` — project container creation
- `build_health_tree_embed()` in `src/vcompany/bot/embeds.py` — health rendering
- `HealthCog` in `src/vcompany/bot/cogs/health.py` — /health command

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
