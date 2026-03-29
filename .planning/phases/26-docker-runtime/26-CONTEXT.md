# Phase 26: Docker Runtime - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement DockerTransport behind the AgentTransport protocol so agents can run inside Docker containers with full daemon connectivity, persistent session state, and per-agent image configuration. Build a Dockerfile for the Claude Code agent image with tweakcc patches baked in.

Requirements: DOCK-01, DOCK-02, DOCK-03, DOCK-04, DOCK-05, DOCK-06

</domain>

<decisions>
## Implementation Decisions

### Dockerfile Strategy
- **D-01:** Base image is `node:22-slim`. Install Python 3.12, uv, git, tmux on top. Claude Code runs on Node so this is the natural base.
- **D-02:** Install Claude Code (`npm install -g @anthropic-ai/claude-code`) and apply tweakcc patches at build time. Patches baked into image — deterministic, no runtime surprises.
- **D-03:** One universal Docker image for all agent types. Agent differences come from config (AgentConfig), not image contents. `AgentConfig.docker_image` specifies the tag.

### Container Lifecycle
- **D-04:** Deterministic container naming: `vco-{project}-{agent_id}`. Easy to find with `docker ps`, reconstructible without state.
- **D-05:** `docker stop` on teardown, container kept for inspection/restart. Explicit `docker rm` or cleanup command to remove. Preserves container-layer state per DOCK-06.
- **D-06:** When `DockerTransport.setup()` finds an existing stopped container, `docker start` it. If already running, reuse it. This is the core DOCK-06 persistence behavior — containers survive agent restarts and daemon recovery.

### Volume Mounts & Socket
- **D-07:** Bind mount daemon Unix sockets at same path: `-v /tmp/vco-daemon.sock:/tmp/vco-daemon.sock` (and `vco-signal.sock`). Zero config changes needed inside container — `vco` CLI and signal commands work with default paths.
- **D-08:** Bind mount agent work directories (git clones) from host: `-v /path/to/clone:/workspace`. Changes visible immediately on both sides. Works with existing clone management.
- **D-09:** `~/.claude` lives inside the container's writable layer. Bake default `settings.json` at build time. Each container gets its own copy and can modify it during setup. Persists across stop/start (DOCK-06). Lost only on explicit `docker rm`, which is acceptable.

### Docker Exec Mapping
- **D-10:** tmux runs inside the Docker container. `DockerTransport.exec()` uses docker SDK to exec into the container and interact with tmux. Same send-keys/pane pattern as LocalTransport but through Docker exec.
- **D-11:** Two-layer `is_alive()` check: (1) Docker inspect confirms container is running, (2) exec into container to check Claude Code process is alive (e.g., tmux pane exists). Matches LocalTransport's approach of checking both environment and process.
- **D-12:** Use `docker-py` SDK (`import docker`) instead of shelling out to docker CLI. Typed Python API with better error handling for complex container lifecycle operations. Exception to the subprocess-over-library convention used for git — Docker operations (lifecycle, inspect, exec with streaming) are more complex.

### Claude's Discretion
- Docker exec command construction for tmux send-keys inside containers
- Dockerfile layer ordering and caching strategy
- How piped mode (Strategist subprocess) maps through Docker exec
- Container network mode (host, bridge, none) — just needs socket access
- read_file/write_file implementation (docker cp vs volume path access)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Transport Protocol (Phase 25 — the contract to implement)
- `src/vcompany/transport/protocol.py` — AgentTransport protocol with all 8 methods DockerTransport must implement
- `src/vcompany/transport/local.py` — LocalTransport reference implementation (follow same patterns)

### Factory Integration
- `src/vcompany/container/factory.py` — _TRANSPORT_REGISTRY with Phase 26 placeholder comment; add DockerTransport here
- `src/vcompany/models/config.py` — AgentConfig with `transport: str = "local"` field; needs docker_image field (DOCK-05)
- `src/vcompany/container/child_spec.py` — ChildSpec with `transport: str = "local"` field

### Container Launch (how transport.setup/exec are called)
- `src/vcompany/container/container.py` — AgentContainer._launch_agent() calls transport.setup() then transport.exec()

### Daemon Sockets (mounted into containers)
- `src/vcompany/shared/paths.py` — VCO_SOCKET_PATH (`/tmp/vco-daemon.sock`) and signal socket path
- `src/vcompany/daemon/signal_handler.py` — Signal HTTP endpoint on Unix socket (agents POST readiness/idle signals)
- `src/vcompany/cli/signal_cmd.py` — `vco signal` CLI command that agents run inside containers

### Prior Phase Context
- `.planning/phases/25-transport-abstraction/25-CONTEXT.md` — Transport abstraction decisions that Phase 26 builds on

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AgentTransport` protocol — 8-method contract already defined; DockerTransport is a direct implementation
- `NoopTransport` — test/fallback implementation; useful as skeleton for DockerTransport
- `LocalTransport` — reference implementation showing how to handle both interactive (tmux) and piped (subprocess) modes
- `_TRANSPORT_REGISTRY` in factory.py — placeholder comment ready for `"docker": DockerTransport`

### Established Patterns
- `@runtime_checkable Protocol` — structural subtyping pattern used by both CommunicationPort and AgentTransport
- Constructor injection — LocalTransport takes `tmux_manager` via constructor; DockerTransport will take docker client
- `_AgentSession` dataclass — internal tracking per agent; DockerTransport needs similar for container IDs
- `asyncio.to_thread()` — used by LocalTransport for blocking tmux calls; same pattern for blocking docker-py calls

### Integration Points
- `factory.py:31` — uncomment/replace `# "docker": DockerTransport,  # Phase 26`
- `AgentConfig` — add `docker_image: str | None = None` field (DOCK-05)
- `create_container()` — `transport_deps` dict will carry docker client instance for DockerTransport

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 26-docker-runtime*
*Context gathered: 2026-03-29*
