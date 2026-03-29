# Requirements: vCompany

**Defined:** 2026-03-29
**Core Value:** Agents run autonomously without hanging on terminal input, stay coordinated through contracts and status awareness, and produce integrated code that merges cleanly -- all operable from Discord.

## v3.1 Requirements

Requirements for Container Runtime Abstraction. Each maps to roadmap phases.

### Discord Visibility

- [ ] **VIS-01**: Every inter-agent event (phase complete, task assigned, plan reviewed, escalation) produces a Discord message in the appropriate channel before the event takes effect
- [ ] **VIS-02**: PM backlog operations (add, remove, prioritize) are posted to Discord with the change described, not silently mutated
- [ ] **VIS-03**: Plan review decisions (approve/reject with confidence score and reasoning) are posted to Discord before the approval/rejection is processed
- [ ] **VIS-04**: RuntimeAPI has no agent-type-specific routing methods -- no hardcoded "send this to PM" or "send this to Strategist" wiring
- [ ] **VIS-05**: Agent-to-agent coordination uses Discord channel subscriptions, not Python post_event() calls -- any agent watching a channel can react to events
- [ ] **VIS-06**: Task assignment from PM to GSD agent is a Discord message in the agent's channel, not an internal queue_task() bypass

### Transport Abstraction

- [ ] **TXPT-01**: AgentTransport protocol exists with setup/teardown/exec/is_alive/read_file/write_file methods that abstract the execution environment boundary
- [ ] **TXPT-02**: LocalTransport implements AgentTransport using TmuxManager for interactive sessions and subprocess for piped invocations
- [ ] **TXPT-03**: AgentContainer uses injected AgentTransport instead of direct TmuxManager calls
- [ ] **TXPT-04**: StrategistConversation uses injected AgentTransport.exec() instead of direct asyncio.create_subprocess_exec
- [ ] **TXPT-05**: Agent readiness and idle signaling uses daemon socket (vco signal --ready/--idle) instead of sentinel temp files
- [ ] **TXPT-06**: AgentConfig has a transport field (default "local") that factory uses to inject the correct transport implementation

### Docker Runtime

- [ ] **DOCK-01**: DockerTransport implements AgentTransport using docker exec for both interactive (tmux inside container) and piped (claude -p) modes
- [ ] **DOCK-02**: Dockerfile exists for building a Claude Code image with tweakcc patches applied
- [ ] **DOCK-03**: Docker container receives daemon Unix socket via volume mount so vco CLI commands work from inside
- [ ] **DOCK-04**: Docker container mounts agent work directory as a volume for code access
- [ ] **DOCK-05**: AgentConfig.docker_image field specifies which image to use when transport is "docker"
- [ ] **DOCK-06**: Persistent Docker containers (docker create + start/stop) preserve ~/.claude session state across agent restarts

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
| VIS-01 | Phase 24 | Pending |
| VIS-02 | Phase 24 | Pending |
| VIS-03 | Phase 24 | Pending |
| VIS-04 | Phase 24 | Pending |
| VIS-05 | Phase 24 | Pending |
| VIS-06 | Phase 24 | Pending |
| TXPT-01 | Phase 25 | Pending |
| TXPT-02 | Phase 25 | Pending |
| TXPT-03 | Phase 25 | Pending |
| TXPT-04 | Phase 25 | Pending |
| TXPT-05 | Phase 25 | Pending |
| TXPT-06 | Phase 25 | Pending |
| DOCK-01 | Phase 26 | Pending |
| DOCK-02 | Phase 26 | Pending |
| DOCK-03 | Phase 26 | Pending |
| DOCK-04 | Phase 26 | Pending |
| DOCK-05 | Phase 26 | Pending |
| DOCK-06 | Phase 26 | Pending |

**Coverage:**
- v3.1 requirements: 18 total
- Mapped to phases: 18/18
- Unmapped: 0

---
*Requirements defined: 2026-03-29*
*Traceability updated: 2026-03-29*
