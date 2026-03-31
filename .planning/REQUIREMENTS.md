# Requirements: vCompany

**Defined:** 2026-03-29
**Core Value:** Agents run autonomously without hanging on terminal input, stay coordinated through contracts and status awareness, and produce integrated code that merges cleanly -- all operable from Discord.

## v3.1 Requirements

Requirements for Container Runtime Abstraction. Each maps to roadmap phases.

### Discord Visibility

- [x] **VIS-01**: Every inter-agent event (phase complete, task assigned, plan reviewed, escalation) produces a Discord message in the appropriate channel before the event takes effect
- [x] **VIS-02**: PM backlog operations (add, remove, prioritize) are posted to Discord with the change described, not silently mutated
- [x] **VIS-03**: Plan review decisions (approve/reject with confidence score and reasoning) are posted to Discord before the approval/rejection is processed
- [x] **VIS-04**: RuntimeAPI has no agent-type-specific routing methods -- no hardcoded "send this to PM" or "send this to Strategist" wiring
- [x] **VIS-05**: Agent-to-agent coordination uses Discord channel subscriptions, not Python post_event() calls -- any agent watching a channel can react to events
- [x] **VIS-06**: Task assignment from PM to GSD agent is a Discord message in the agent's channel, not an internal queue_task() bypass

### Transport Abstraction

- [x] **TXPT-01**: AgentTransport protocol exists with setup/teardown/exec/is_alive/read_file/write_file methods that abstract the execution environment boundary
- [x] **TXPT-02**: LocalTransport implements AgentTransport using TmuxManager for interactive sessions and subprocess for piped invocations
- [x] **TXPT-03**: AgentContainer uses injected AgentTransport instead of direct TmuxManager calls
- [x] **TXPT-04**: StrategistConversation uses injected AgentTransport.exec() instead of direct asyncio.create_subprocess_exec
- [x] **TXPT-05**: Agent readiness and idle signaling uses daemon socket (vco signal --ready/--idle) instead of sentinel temp files
- [x] **TXPT-06**: AgentConfig has a transport field (default "local") that factory uses to inject the correct transport implementation

### Docker Runtime

- [x] **DOCK-01**: DockerTransport implements AgentTransport using docker exec for both interactive (tmux inside container) and piped (claude -p) modes
- [x] **DOCK-02**: Dockerfile exists for building a Claude Code image with tweakcc patches applied
- [x] **DOCK-03**: Docker container receives daemon Unix socket via volume mount so vco CLI commands work from inside
- [x] **DOCK-04**: Docker container mounts agent work directory as a volume for code access
- [x] **DOCK-05**: AgentConfig.docker_image field specifies which image to use when transport is "docker"
- [x] **DOCK-06**: Persistent Docker containers (docker create + start/stop) preserve ~/.claude session state across agent restarts

### Docker Integration Wiring

- [x] **WIRE-01**: Factory resolves transport_deps per transport type -- LocalTransport receives tmux_manager, DockerTransport receives docker_image and project_name -- daemon passes transport-agnostic context, factory maps to constructor args
- [x] **WIRE-02**: docker_image flows from AgentConfig through ChildSpec (or transport_deps) to DockerTransport constructor without manual intervention
- [x] **WIRE-03**: Docker image auto-builds on first use when agent with transport "docker" is hired and image is missing, OR a `vco build` command exists for explicit builds
- [x] **WIRE-04**: DockerTransport.setup() accepts parametric kwargs (tweakcc profile name, custom settings.json content/path) enabling per-agent customization from a single universal image
- [x] **WIRE-05**: No hardcoded agent-type string checks (if/in on type literals) remain in runtime_api.py or supervisor.py -- agent capabilities (uses_tmux, gsd_command, etc.) derived from AgentConfig fields or container class capabilities
- [x] **WIRE-06**: Full e2e: Discord hire command -> Docker container created -> agent executes task -> signals readiness via mounted daemon socket -> appears in health tree
- [x] **WIRE-07**: Adding a new agent type requires only an AgentConfig entry (agents.yaml) and optional container subclass registration -- zero business logic changes in runtime_api.py or supervisor.py

### Handler Separation

- [x] **HSEP-01**: Three handler protocols (SessionHandler, ConversationHandler, TransientHandler) exist as @runtime_checkable Python Protocols with async handle_message/on_start/on_stop methods
- [x] **HSEP-02**: _send_discord is consolidated into base AgentContainer -- no duplicate implementations across agent subclasses
- [x] **HSEP-03**: Base AgentContainer delegates receive_discord_message() to injected handler, stores _channel_id for outbound messages
- [x] **HSEP-04**: agent-types.yaml has a handler field (session/conversation/transient) on every agent type entry
- [x] **HSEP-05**: Factory has _HANDLER_REGISTRY and injects the correct handler into containers based on agent type config
- [x] **HSEP-06**: Agent subclasses are thin wrappers (lifecycle FSM + domain methods only) -- handler logic extracted to handler implementations
- [x] **HSEP-07**: Dead code paths (self._tmux, _launch_tmux_session) removed from GsdAgent and TaskAgent
- [x] **HSEP-08**: Base AgentContainer handles OrderedSet compound state/inner_state -- no duplicate overrides in subclasses

## v3.2+ Requirements

Deferred to future release.

### State Persistence

- **PERSIST-01**: Container state persists to disk and survives daemon restart
- **PERSIST-02**: Task queue state persists and recovers on restart
- **PERSIST-03**: Daemon reconnects to running tmux sessions on restart
- **PERSIST-04**: FSM state recovery from persisted snapshots

## Out of Scope

| Feature | Reason |
|---------|--------|
| State persistence / crash recovery | Deferred to v3.2 -- daemon restart loses state for now |
| Multi-machine distributed agents | v4 scope -- NetworkTransport not in v3.1 |
| Non-Discord CommunicationPort adapters (Slack, web) | v4 scope -- only DiscordCommunicationPort |
| Kubernetes/orchestrator integration | v4 scope -- Docker only for v3.1 |
| Agent-to-agent direct messaging | By design -- all communication through Discord channels |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| VIS-01 | Phase 24 | Complete |
| VIS-02 | Phase 24 | Complete |
| VIS-03 | Phase 24 | Complete |
| VIS-04 | Phase 24 | Complete |
| VIS-05 | Phase 24 | Complete |
| VIS-06 | Phase 24 | Complete |
| TXPT-01 | Phase 25 | Complete |
| TXPT-02 | Phase 25 | Complete |
| TXPT-03 | Phase 25 | Complete |
| TXPT-04 | Phase 25 | Complete |
| TXPT-05 | Phase 25 | Complete |
| TXPT-06 | Phase 25 | Complete |
| DOCK-01 | Phase 26 | Complete |
| DOCK-02 | Phase 26 | Complete |
| DOCK-03 | Phase 26 | Complete |
| DOCK-04 | Phase 26 | Complete |
| DOCK-05 | Phase 26 | Complete |
| DOCK-06 | Phase 26 | Complete |
| WIRE-01 | Phase 27 | Complete |
| WIRE-02 | Phase 27 | Complete |
| WIRE-03 | Phase 27 | Complete |
| WIRE-04 | Phase 27 | Complete |
| WIRE-05 | Phase 27 | Complete |
| WIRE-06 | Phase 27 | Complete |
| WIRE-07 | Phase 27 | Complete |
| HSEP-01 | Phase 28 | Planned |
| HSEP-02 | Phase 28 | Planned |
| HSEP-03 | Phase 28 | Planned |
| HSEP-04 | Phase 28 | Planned |
| HSEP-05 | Phase 28 | Planned |
| HSEP-06 | Phase 28 | Planned |
| HSEP-07 | Phase 28 | Planned |
| HSEP-08 | Phase 28 | Planned |

**Coverage:**
- v3.1 requirements: 33 total
- Mapped to phases: 33/33
- Unmapped: 0

---
*Requirements defined: 2026-03-29*
*Traceability updated: 2026-03-31*
