# Phase 8: CompanyRoot Wiring and Migration - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

The supervision tree replaces flat VcoBot initialization, all commands are slash commands, v1 modules are removed, and the communication layer is ready for v3 abstraction. This is the capstone migration phase that wires everything together and removes legacy code.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure/migration phase.

Key technical anchors from requirements:
- CompanyRoot initializes full supervision tree on bot startup, replacing VcoBot.on_ready() (MIGR-01)
- All Discord commands converted to slash commands, no more `!` prefix (MIGR-02)
- v1 MonitorLoop, CrashTracker, WorkflowOrchestrator, AgentManager fully removed (MIGR-03)
- Communication layer has clean abstract interface for v3 channel abstraction (MIGR-04)

</decisions>

<code_context>
## Existing Code Insights

### v1 Modules to Remove
- `src/vcompany/monitor/loop.py` — MonitorLoop (replaced by supervisor health tree)
- `src/vcompany/orchestrator/crash_tracker.py` — CrashTracker (replaced by RestartTracker)
- `src/vcompany/orchestrator/workflow_orchestrator.py` — WorkflowOrchestrator (replaced by GsdAgent)
- `src/vcompany/orchestrator/agent_manager.py` — AgentManager (replaced by Supervisor)

### v2 Equivalents (already built)
- `src/vcompany/supervisor/` — Supervision tree (Phase 2)
- `src/vcompany/agent/gsd_agent.py` — GsdAgent (Phase 3)
- `src/vcompany/container/` — Container system (Phase 1)
- `src/vcompany/resilience/` — Resilience layer (Phase 6)
- `src/vcompany/autonomy/` — Autonomy features (Phase 7)

### Integration Points
- `src/vcompany/bot/client.py` — VcoBot.on_ready() to rewire
- `src/vcompany/bot/cogs/commands.py` — `!` commands to convert to slash
- `src/vcompany/container/communication.py` — CommunicationPort Protocol to implement for Discord

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure/migration phase.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
