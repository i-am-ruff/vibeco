# Phase 33: Container Autonomy - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Agent containers are fully autonomous — state lives inside, duplicating a transport creates independent agents, and workers survive daemon restarts. Agent state (conversations, checkpoints, memory store, session files) lives inside the execution environment filesystem. Daemon reconnects to surviving workers after restart.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key constraints:
- Containers run INSIDE transports, not as daemon-side Python objects
- Transport channel is the ONLY communication between head and worker
- Agent state must live inside the worker's execution environment filesystem
- Duplicating a transport + config blob creates a fully independent agent (no shared state)
- Workers must survive daemon restarts and reconnect via transport channel
- Worker sends current state on reconnection, head reconstructs routing
- Phase 30 vco-worker already has MemoryStore, checkpoint/restore, lifecycle FSM
- Phase 31 AgentHandle + routing state persistence supports daemon restart recovery
- Phase 32 NativeTransport/DockerChannelTransport spawn workers via subprocess

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `packages/vco-worker/src/vco_worker/container/memory_store.py` — aiosqlite per-agent KV store
- `packages/vco-worker/src/vco_worker/container/container.py` — WorkerContainer with lifecycle FSM
- `src/vcompany/daemon/agent_handle.py` — AgentHandle with process attachment
- `src/vcompany/daemon/routing_state.py` — RoutingState JSON persistence
- `src/vcompany/supervisor/company_root.py` — CompanyRoot.hire() with transport spawn
- `src/vcompany/transport/channel/messages.py` — Channel protocol messages including HealthReportMessage

### Integration Points
- Worker MemoryStore currently uses daemon-side path — needs to use worker-local path
- AgentHandle.attach_process() — reconnection path for daemon restart recovery
- RoutingState load on daemon startup — reconstruct routing from persisted state
- Channel protocol may need a reconnect/state-sync message type

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
