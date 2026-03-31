# Phase 34: Cleanup and Network Stub - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

All daemon-side container dead code is removed (GsdAgent, CompanyAgent, FulltimeAgent, handler factory injection, NoopCommunicationPort, StrategistConversation-from-daemon, v3.1 shims). A NetworkTransport stub defines TCP/WebSocket contract for future remote agents. Codebase compiles and all functionality works after cleanup.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key constraints:
- Remove ALL daemon-side container dead code — be thorough
- NetworkTransport stub must define the contract (not production-ready)
- All existing functionality must work after removal (hire, give-task, dismiss, health, status)
- Old AgentTransport protocol (v3.1) can be removed — replaced by ChannelTransport
- Old LocalTransport, DockerTransport can be removed — replaced by NativeTransport, DockerChannelTransport
- Keep the codebase compiling — verify imports after deletion

</decisions>

<code_context>
## Existing Code Insights

### Dead Code Candidates
- `src/vcompany/container/` — AgentContainer, ContainerLifecycle, ContainerContext (replaced by vco-worker WorkerContainer)
- `src/vcompany/agent/` — GsdAgent, CompanyAgent, FulltimeAgent, ContinuousAgent, TaskAgent (replaced by vco-worker)
- `src/vcompany/handler/` — handler protocols and implementations (replaced by vco-worker handlers)
- `src/vcompany/transport/protocol.py` — AgentTransport, NoopTransport (replaced by ChannelTransport)
- `src/vcompany/transport/local.py` — LocalTransport (replaced by NativeTransport)
- `src/vcompany/transport/docker.py` — DockerTransport (replaced by DockerChannelTransport)
- Any v3.1 shims, NoopCommunicationPort, StrategistConversation daemon-side management

### What to Keep
- `src/vcompany/transport/channel/` — Phase 29 channel protocol
- `src/vcompany/transport/channel_transport.py` — ChannelTransport protocol
- `src/vcompany/transport/native.py` — NativeTransport
- `src/vcompany/transport/docker_channel.py` — DockerChannelTransport
- `src/vcompany/daemon/` — Daemon, RuntimeAPI, DaemonClient, AgentHandle, RoutingState
- `src/vcompany/supervisor/` — CompanyRoot, ProjectSupervisor (refactored in Phase 31)
- `src/vcompany/bot/` — Discord bot cogs
- `packages/vco-worker/` — Worker runtime

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
