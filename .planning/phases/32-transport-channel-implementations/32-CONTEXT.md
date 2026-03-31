# Phase 32: Transport Channel Implementations - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Both Docker and native transports use the channel protocol end-to-end — no socket mounts, no shared filesystem between head and worker. Docker transport creates a container running vco-worker, communicates through channel protocol (docker exec stdin/stdout). Native transport starts vco-worker in a local process, communicates through channel protocol. Both transports produce identical observable behavior.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key constraints from project context:
- Containers run INSIDE transports, not as daemon-side Python objects
- Transport channel is the ONLY communication between head and worker
- Docker transport must NOT mount Unix sockets into containers
- Both transports must produce identical observable behavior (signals, health reports, Discord message routing)
- Phase 29 channel protocol (NDJSON framing) is the wire format
- Phase 30 vco-worker is what runs inside the transport
- Phase 31 AgentHandle + CompanyRoot.hire() spawns workers — transports need to integrate with this

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/transport/protocol.py` — AgentTransport Protocol (v3.1 interface — being replaced)
- `src/vcompany/transport/local.py` — LocalTransport (tmux-based, to be replaced with channel-based)
- `src/vcompany/transport/docker.py` — DockerTransport (docker exec-based, to be replaced with channel-based)
- `src/vcompany/transport/channel/` — Phase 29 channel protocol messages + framing
- `packages/vco-worker/` — Phase 30 worker runtime
- `src/vcompany/daemon/agent_handle.py` — Phase 31 AgentHandle (subprocess communication)
- `src/vcompany/supervisor/company_root.py` — Phase 31 refactored CompanyRoot (spawns workers)

### Established Patterns
- CompanyRoot.hire() spawns vco-worker subprocess with stdin/stdout channel
- AgentHandle.send() writes HeadMessages to subprocess stdin
- Background _channel_reader reads WorkerMessages from subprocess stdout

### Integration Points
- CompanyRoot.hire() currently spawns `python -m vco_worker` directly — needs to go through transport layer
- Docker transport needs to run vco-worker inside container and pipe channel protocol
- Native transport needs to run vco-worker locally with channel protocol piping

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
