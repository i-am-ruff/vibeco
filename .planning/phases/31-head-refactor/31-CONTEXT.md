# Phase 31: Head Refactor - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Daemon holds only transport handles and agent metadata — all container internals run inside the worker on the other side of the transport. No GsdAgent/CompanyAgent/FulltimeAgent Python objects instantiated daemon-side. `vco hire` sends a config blob through transport, worker bootstraps itself. Health tree populated from health-report messages through channel protocol. Discord channel/category lifecycle managed by head.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key constraints from project context:
- Containers run INSIDE transports, not as daemon-side Python objects
- Daemon only talks to transport — container is self-managed behind the abstraction boundary
- Transport channel is the ONLY communication between head and worker
- Agent metadata stored daemon-side: id, type, capabilities, channel_id, handler type, config
- Health tree receives HealthReportMessages through transport channel
- Discord channel/category lifecycle (create on hire, cleanup on dismiss) stays in head
- Use Pydantic v2 models (project standard)
- Phase 29 channel protocol and Phase 30 worker runtime are the building blocks

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/daemon/daemon.py` — Daemon class (main entry point)
- `src/vcompany/daemon/runtime_api.py` — RuntimeAPI gateway (600+ lines, wraps CompanyRoot operations)
- `src/vcompany/daemon/client.py` — DaemonClient for CLI
- `src/vcompany/supervisor/company_root.py` — CompanyRoot supervisor
- `src/vcompany/supervisor/project_supervisor.py` — ProjectSupervisor
- `src/vcompany/transport/` — AgentTransport protocol, LocalTransport, DockerTransport
- `src/vcompany/transport/channel/` — Phase 29 channel protocol
- `packages/vco-worker/` — Phase 30 worker runtime
- `src/vcompany/container/` — AgentContainer (to be replaced by worker-side WorkerContainer)
- `src/vcompany/agent/` — GsdAgent, CompanyAgent, FulltimeAgent, ContinuousAgent (to be removed from daemon)

### Established Patterns
- RuntimeAPI gateway wraps all CompanyRoot operations
- NDJSON over Unix socket for daemon API
- Supervisor tree: CompanyRoot → ProjectSupervisor → agents
- Agent types configured via agent-types.yaml

### Integration Points
- RuntimeAPI.hire() currently creates AgentContainer objects — needs to create transport handles instead
- CompanyRoot/ProjectSupervisor manage agent lifecycles — needs refactoring to manage transport handles
- Health tree currently calls container health methods — needs to read HealthReportMessages from channel
- Bot cogs relay commands to RuntimeAPI — should remain unchanged (thin relay)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
