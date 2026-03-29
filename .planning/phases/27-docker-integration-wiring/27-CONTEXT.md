# Phase 27: Docker Integration Wiring - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire all pieces so Docker agents work end-to-end: per-transport dependency resolution, docker_image flow from config to constructor, auto-build on first use, parametric agent setup (tweakcc profiles, custom settings via kwargs), removal of hardcoded agent-type checks from business logic, and a unified agent-types config file as the single source of truth for all agent types.

Requirements: WIRE-01, WIRE-02, WIRE-03, WIRE-04, WIRE-05, WIRE-06, WIRE-07

</domain>

<decisions>
## Implementation Decisions

### Per-Agent Transport Deps (WIRE-01, WIRE-02)
- **D-01:** Factory is the smart resolver — it reads docker_image and other per-agent fields from ChildSpec/config, merges with global transport_deps, then passes to the transport constructor. Daemon stays simple, just provides global deps (tmux_manager). Factory maps per-agent config to per-transport constructor args.
- **D-02:** `vco hire <type> <name>` knows nothing about transport details. All resolution happens from config lookup. The caller just names a type and an agent name — everything else is derived.

### Auto-Build Strategy (WIRE-03)
- **D-03:** Auto-build inline on first hire — when a Docker agent is hired and the image doesn't exist, build it automatically before creating the container. First hire takes longer but "just works."
- **D-04:** `vco build` command also exists for explicit pre-builds and rebuilds (after Dockerfile changes, CI, pre-warming). Auto-build handles the happy path, `vco build` handles everything else.

### Parametric Agent Setup (WIRE-04)
- **D-05:** Agent-types config file (separate from agents.yaml) is a **single source of truth for ALL agent types** — Docker and non-Docker. When `vco hire <type>` runs, it looks up this file to determine transport, capabilities, tweakcc profile, settings, everything. This is the extensibility foundation.
- **D-06:** Per-agent customization (tweakcc profile, Claude settings) applied at container start time. DockerTransport.setup() copies profile and settings into the container after start, before launching Claude Code. Universal image stays clean.
- **D-07:** Customization is defined at the type level in the agent-types config. Per-agent overrides may come later but are not in scope for Phase 27.

### Agent-Types Config File Format
- **D-08:** Full schema defined upfront. Includes fields needed now (transport, docker_image, tweakcc_profile, capabilities, container_class) AND future-facing fields (env vars, volume overrides). Parsed but not all enforced in Phase 27 — schema is complete, implementation covers what's needed.
- **D-09:** Schema includes from day one: environment variables (per-type env vars injected into containers) and volume overrides (additional mounts beyond standard workspace + daemon sockets). Resource limits and network mode deferred.
- **D-10:** Config file is separate from agents.yaml — dedicated file (e.g., `agent-types.yaml`) for the type-parameters map.

### Type-Check Elimination (WIRE-05, WIRE-07)
- **D-11:** Config-derived capabilities replace hardcoded type string checks. Agent type config declares capabilities (gsd_driven, event_driven, reviews_plans, etc.). Runtime code checks capabilities, not type strings. New type = new config entry with capability flags.
- **D-12:** All hardcoded `if agent_type == "pm"` or `if type in [...]` checks in runtime_api.py and supervisor.py must be replaced with capability checks or registry lookups.

### New Type Extensibility (WIRE-07)
- **D-13:** Container subclass registration via config — agent-types.yaml has `container_class: GsdAgent` (or omit for default AgentContainer). Factory has a `_CONTAINER_REGISTRY` mapping names to classes. New subclass = add to registry + reference in config. No business logic changes.

### E2E Hire-to-Health Flow (WIRE-06)
- **D-14:** Docker agents follow the same hire-to-health path as local agents: hire → config lookup → container created → transport.setup() → transport.exec() → agent signals readiness via `vco signal --ready` through mounted daemon socket → health tree shows agent.

### Claude's Discretion
- Docker-specific health info in health tree (container ID, image version, uptime) — Claude decides what's useful based on existing health tree patterns
- Implementation details of factory dep extraction from ChildSpec/context
- ChildSpec field additions needed to carry docker_image through the pipeline
- How capability checks are structured in runtime code (dict lookups, has_capability(), etc.)
- Default values for agent-types config fields when omitted

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Transport Layer (Phase 25-26 — the foundation)
- `src/vcompany/transport/protocol.py` — AgentTransport protocol with all 8 methods
- `src/vcompany/transport/local.py` — LocalTransport reference implementation
- `src/vcompany/transport/docker.py` — DockerTransport (fully implemented, needs wiring)
- `src/vcompany/transport/__init__.py` — Transport exports

### Factory and Config (where wiring changes land)
- `src/vcompany/container/factory.py` — ContainerFactory with `_TRANSPORT_REGISTRY`, `create_container()`, transport instantiation via `**transport_deps`
- `src/vcompany/models/config.py` — AgentConfig with `transport`, `docker_image` fields
- `src/vcompany/container/child_spec.py` — ChildSpec (needs docker_image field or similar)

### Daemon (global transport_deps source)
- `src/vcompany/daemon/daemon.py` — Daemon builds `transport_deps = {"tmux_manager": tmux_manager}` at line 208
- `src/vcompany/daemon/runtime_api.py` — RuntimeAPI builds ChildSpecs from agents.yaml (lines 701-715), hardcoded type checks to eliminate

### Supervisor (type check elimination target)
- `src/vcompany/container/supervisor.py` — Supervisor passes transport_deps to factory

### Container Lifecycle
- `src/vcompany/container/container.py` — AgentContainer._launch_agent() calls transport.setup() then transport.exec()

### Docker Build
- `docker/Dockerfile` — Existing Dockerfile for Claude Code agent image

### Signal and Health (e2e path)
- `src/vcompany/daemon/signal_handler.py` — Signal HTTP endpoint (agents POST readiness/idle)
- `src/vcompany/cli/signal_cmd.py` — `vco signal` CLI command
- `src/vcompany/container/health.py` — Health reporting

### Prior Phase Context
- `.planning/phases/25-transport-abstraction/25-CONTEXT.md` — Transport abstraction decisions
- `.planning/phases/26-docker-runtime/26-CONTEXT.md` — Docker runtime decisions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DockerTransport` — fully implemented with all 8 protocol methods, just needs proper wiring from config
- `_TRANSPORT_REGISTRY` in factory.py — already maps "docker" to DockerTransport
- `ContainerFactory.create_container()` — already does `TransportClass(**transport_deps)`, just needs richer deps
- `AgentConfig.docker_image` field — exists but never flows to DockerTransport constructor
- `docker/Dockerfile` — complete Claude Code image with tweakcc patches

### Established Patterns
- Protocol-based abstraction (`AgentTransport`, `CommunicationPort`) — structural typing with `@runtime_checkable`
- Factory injection — ContainerFactory builds containers with injected dependencies
- Pydantic models for config — AgentConfig, ProjectConfig with field validators
- Registry dicts for extensibility — `_TRANSPORT_REGISTRY` pattern

### Integration Points
- `daemon.py` line 208 — where global transport_deps are built (extend or replace)
- `runtime_api.py` lines 701-715 — where ChildSpecs are built from agents.yaml (wire docker_image through)
- `factory.py` lines 78-84 — where transport is instantiated (factory becomes smart resolver)
- Container subclass selection — currently hardcoded in factory, needs registry

### Key Gaps Found
- `docker_image` never flows from AgentConfig → ChildSpec → DockerTransport constructor
- Daemon passes single global transport_deps — no per-agent resolution
- No auto-build logic exists
- Hardcoded type checks in runtime_api.py and supervisor.py (if/in on type strings)
- No agent-types config file exists yet
- No `vco build` CLI command

</code_context>

<specifics>
## Specific Ideas

- Agent-types config file is the **single source of truth for ALL agent types** — both Docker and non-Docker. `vco hire <type>` resolves everything from this one file. This is the extensibility foundation that can be "extended drastically later."
- The config file is NOT agents.yaml — it's a separate dedicated file for the type-parameters map
- Type-level config carries: transport, docker_image, tweakcc_profile, capabilities list, container_class, env vars, volume overrides
- Adding a new agent type (e.g., "cfo") = add entry to agent-types config + optionally register a container subclass. Zero changes to runtime_api.py or supervisor.py.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 27-docker-integration-wiring*
*Context gathered: 2026-03-30*
