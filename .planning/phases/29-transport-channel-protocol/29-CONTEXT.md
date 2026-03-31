# Phase 29: Transport Channel Protocol - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

A well-defined bidirectional message protocol exists that head and worker use to communicate -- the foundation everything else builds on. Typed Pydantic models for all head-to-worker messages (start, give-task, message, stop, health-check) and worker-to-head messages (signal, report, ask, send-file, health-report). Transport-agnostic serialization to bytes/JSON. Protocol test suite validates round-trip serialization.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key constraints from project context:
- Containers run INSIDE transports, not as daemon-side Python objects (v4.0 architecture decision)
- Transport channel is the ONLY communication between head and worker
- Protocol must be transport-agnostic (stdin/stdout, socket, TCP, WebSocket)
- Use Pydantic v2 models (project standard)
- vco-worker must be installable standalone — no discord.py, no bot code, no orchestration dependencies

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/transport/protocol.py` — AgentTransport Protocol with setup/teardown/exec/read_file/write_file (current v3.1 interface, will be replaced by channel protocol)
- `src/vcompany/transport/local.py` — LocalTransport (tmux-based)
- `src/vcompany/transport/docker.py` — DockerTransport (Docker exec-based)
- `src/vcompany/transport/__init__.py` — Package exports
- Pydantic v2 models used throughout codebase for config validation

### Established Patterns
- `@runtime_checkable Protocol` pattern for interfaces (AgentTransport, CommunicationPort)
- NDJSON over Unix socket for daemon API (existing serialization pattern)
- Pydantic BaseModel with strict typing for all data contracts

### Integration Points
- AgentTransport protocol is the current transport interface — channel protocol will layer on top or replace
- Daemon RuntimeAPI currently calls transport methods directly — will need to use channel protocol instead
- Container layer (AgentContainer subclasses) uses transport for all execution

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
