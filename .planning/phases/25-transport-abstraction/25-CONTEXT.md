# Phase 25: Transport Abstraction - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Abstract agent execution behind an AgentTransport protocol so business logic never knows where or how agents run. Implement LocalTransport (tmux + subprocess), replace sentinel temp files with HTTP-based daemon signaling, and inject transport via factory.

Architecture: Business Logic → Transport Layer → Agent Implementation

Requirements: TXPT-01, TXPT-02, TXPT-03, TXPT-04, TXPT-05, TXPT-06

</domain>

<decisions>
## Implementation Decisions

### Protocol Surface Area
- **D-01:** Thin transport — AgentTransport handles raw execution primitives only: setup env, teardown env, exec command, check alive, read/write files. AgentContainer keeps task queueing, idle gating, and signal interpretation. Signal delivery mechanism lives in transport but signal semantics stay in container.
- **D-02:** Include read_file/write_file on the protocol now even though LocalTransport just delegates to pathlib. When DockerTransport arrives these become docker cp or volume mount reads. Costs nothing now, saves a protocol change later.

### Signal Mechanism
- **D-03:** Agent readiness/idle signaling uses an HTTP endpoint on the daemon (not Unix socket, not temp files). `vco signal --ready/--idle` POSTs to the daemon's HTTP endpoint. Daemon receives signal and updates container state directly.
- **D-04:** Full implementation this phase — build the daemon HTTP endpoint, implement the `vco signal` CLI command, update Claude Code hooks to call it. Sentinel temp files fully removed. No shims or local fallbacks.

### Strategist Subprocess Handling
- **D-05:** Nothing stays internal. The architecture is Business Logic → Transport Layer → Agent Implementation. The Strategist is not special — its current piped subprocess calls are an agent implementation detail that belongs behind the transport. StrategistConversation stops calling asyncio.create_subprocess_exec directly and goes through AgentTransport.
- **D-06:** LocalTransport handles both execution modes: tmux for interactive agents (GSD, PM) and subprocess for piped agents (Strategist). Both are transport concerns, not business logic concerns. DockerTransport will handle both inside containers.

### Factory Injection
- **D-07:** Simple registry dict in the factory: `{"local": LocalTransport, "docker": DockerTransport}`. Looks up AgentConfig.transport field (default "local"), instantiates, injects into container. New transports = add one line. No plugin discovery.

### Claude's Discretion
- How LocalTransport internally decides between tmux session and subprocess based on agent type/config
- HTTP endpoint path and payload format for signal delivery
- Whether AgentTransport is a Protocol (structural typing) or ABC (nominal typing)
- How to migrate existing Claude Code hooks from temp file writes to HTTP calls

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core Transport Targets
- `src/vcompany/container/container.py` — AgentContainer with all TmuxManager calls to be replaced with AgentTransport
- `src/vcompany/tmux/session.py` — TmuxManager (only libtmux touchpoint) — becomes internal to LocalTransport
- `src/vcompany/strategist/conversation.py` — StrategistConversation with direct asyncio.create_subprocess_exec calls to abstract

### Factory and Config
- `src/vcompany/container/factory.py` — ContainerFactory where transport injection happens
- `src/vcompany/models/config.py` — AgentConfig model, needs transport field

### Signal Infrastructure
- `src/vcompany/daemon/daemon.py` — Daemon where HTTP signal endpoint will be added
- `src/vcompany/container/container.py` — Sentinel file logic (_signal_path, _read_signal, _wait_for_signal) to be replaced

### Communication Layer (established pattern)
- `src/vcompany/daemon/comm.py` — CommunicationPort protocol (Phase 19 abstraction pattern to follow)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `CommunicationPort` protocol (Phase 19) — established pattern for protocol-based abstraction; AgentTransport should follow same style
- `TmuxManager` — already isolated as the only libtmux touchpoint; clean boundary to wrap inside LocalTransport
- `ContainerFactory` — already handles dependency injection for containers; extend with transport injection

### Established Patterns
- Protocol-based abstraction (CommunicationPort) — structural typing with runtime_checkable
- Factory injection — ContainerFactory builds containers with injected dependencies
- Pydantic models for config — AgentConfig, ProjectConfig with field validators

### Integration Points
- AgentContainer.__init__ currently takes tmux_manager: TmuxManager | None — replace with transport: AgentTransport
- AgentContainer._launch_tmux_session, is_tmux_alive, deliver_next_task — all delegate to transport
- StrategistConversation lines 275, 348 — asyncio.create_subprocess_exec calls to route through transport
- Sentinel file constants and logic in container.py (SIGNAL_DIR, _signal_path, _read_signal, _wait_for_signal, _clear_signal)

</code_context>

<specifics>
## Specific Ideas

- Architecture is explicitly Business Logic → Transport Layer → Agent Implementation — the transport manages container lifecycle transparently regardless of where the agent lives (local, Docker, network)
- The Strategist is NOT special — its subprocess invocations are transport concerns, same as tmux sessions
- Follow the CommunicationPort pattern from Phase 19 for the protocol design

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 25-transport-abstraction*
*Context gathered: 2026-03-29*
