# Phase 9: Agent Type Routing and PM Event Dispatch - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure/gap-closure phase)

<domain>
## Phase Boundary

Fix AgentConfig.type field so FulltimeAgent and CompanyAgent are instantiated from agents.yaml config. Wire GsdAgent completion events to PM via event dispatch. Wire /new-project PM backlog. Remove all dead code paths from v1→v2 migration.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure/gap-closure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions. Key constraints from milestone audit:
- AgentConfig needs a `type` field (Literal["gsd", "continuous", "fulltime", "company"] default "gsd")
- `hasattr(agent_cfg, "type")` guards in client.py:275 and commands.py:201 must be replaced with direct attribute access
- GsdAgent.make_completion_event() and make_failure_event() exist but need a caller
- bot._pm_container is stored but never read by any cog
- /new-project needs same BacklogQueue/ProjectStateManager wiring as on_ready
- Dead code: HealthCog.setup_notifications() no-op, build_status_embed deprecated

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
