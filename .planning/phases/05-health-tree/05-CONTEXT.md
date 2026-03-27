# Phase 5: Health Tree - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Health reports aggregate across the supervision tree into a queryable, renderable status view pushed to Discord. This phase builds health aggregation in supervisors, a Discord `/health` slash command, and automatic state-change notifications.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure phase with Discord integration. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key technical anchors from requirements:
- Supervisors aggregate children's health into a tree queryable at company/project/individual levels (HLTH-02)
- Discord `/health` slash command renders full supervision tree with color-coded state indicators (HLTH-03)
- State transitions push notifications to Discord automatically without polling (HLTH-04)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/container/health.py` — HealthReport Pydantic model (Phase 1)
- `src/vcompany/container/container.py` — AgentContainer.health_report() method
- `src/vcompany/supervisor/supervisor.py` — Supervisor base class
- `src/vcompany/supervisor/company_root.py` — CompanyRoot top-level
- `src/vcompany/supervisor/project_supervisor.py` — ProjectSupervisor
- `src/vcompany/bot/cogs/` — Existing Discord cog pattern
- `src/vcompany/container/communication.py` — CommunicationPort Protocol

### Established Patterns
- HealthReport already emitted on state transitions (Phase 1)
- Supervisor manages child containers
- discord.py cog architecture for slash commands
- on_state_change callback on AgentContainer

### Integration Points
- Health aggregation in Supervisor base class
- `/health` as new Discord slash command (new cog or extend existing)
- State transition notifications through CommunicationPort
- CompanyRoot.health_tree() for full tree view

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
