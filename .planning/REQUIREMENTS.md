# Requirements: vCompany

**Defined:** 2026-03-31
**Core Value:** Agents run autonomously without hanging on terminal input, stay coordinated through contracts and status awareness, and produce integrated code that merges cleanly -- all operable from Discord.

## v4.0 Requirements

Requirements for Distributed Agent Runtime. Each maps to roadmap phases.

### Worker Runtime

- [x] **WORK-01**: vco-worker is a separate installable package with report/ask/send-file/signal commands that communicate through the transport channel
- [x] **WORK-02**: vco-worker accepts config blob at startup (handler type, capabilities, gsd_command, persona, env vars) and self-configures the right agent process
- [x] **WORK-03**: vco-worker manages agent lifecycle inside the execution environment (start, health reporting, graceful stop)
- [x] **WORK-04**: vco-worker communicates exclusively through the transport channel (no socket mounts, no shared filesystem, no direct Discord access)
- [x] **WORK-05**: Worker contains full agent container runtime -- handler logic (session/conversation/transient), lifecycle FSM, task queue, idle tracking, memory store, checkpoint/restore -- same capabilities as previous daemon-side containers but self-managed behind the transport boundary

### Head Refactor

- [ ] **HEAD-01**: Daemon holds transport handle + agent metadata per agent (id, type, capabilities, channel_id, handler type, config) -- enough to route messages, report health, and identify agents without knowing internals
- [ ] **HEAD-02**: Hire flow creates Discord channel, registers routing, sends config blob through transport -- worker bootstraps from config
- [ ] **HEAD-03**: Health tree populated from worker health reports received through transport, not daemon-side container objects
- [ ] **HEAD-04**: Dead code removed -- daemon-side GsdAgent/CompanyAgent/FulltimeAgent Python objects, handler factory injection, NoopCommunicationPort, StrategistConversation-from-daemon, all v3.1 shims
- [ ] **HEAD-05**: Discord channel/category lifecycle managed by head -- create on hire, cleanup on dismiss, routing persists across daemon restarts

### Transport Channel

- [x] **CHAN-01**: Bidirectional message protocol defined (head->worker: start/task/message/stop/health-check; worker->head: signal/report/ask/send-file/health-report)
- [ ] **CHAN-02**: Docker transport uses transport channel instead of Unix socket mount -- vco-worker inside Docker talks through the channel, not a mounted socket
- [ ] **CHAN-03**: Native transport uses transport channel (local socket or in-process bridge)
- [ ] **CHAN-04**: Network transport stub exists with TCP/WebSocket interface definition -- not full production impl, but the contract is defined and a basic implementation works

### Container Autonomy

- [ ] **AUTO-01**: Agent state (conversations, checkpoints, memory, session files) lives inside the execution environment -- not on the daemon side
- [ ] **AUTO-02**: Duplicating a transport creates a fully independent agent -- no shared daemon-side state between agents of the same type
- [ ] **AUTO-03**: Container survives daemon restart -- worker continues running, reconnects via transport channel when head comes back

## Previously Completed

<details>
<summary>v3.1 Container Runtime Abstraction (44 requirements) -- shipped 2026-03-31</summary>

### Discord Visibility
- [x] **VIS-01** through **VIS-06**: All inter-agent events surfaced through Discord

### Transport Abstraction
- [x] **TXPT-01** through **TXPT-06**: AgentTransport protocol, LocalTransport, socket signaling

### Docker Runtime
- [x] **DOCK-01** through **DOCK-06**: DockerTransport, Dockerfile, socket mount, persistent containers

### Docker Integration Wiring
- [x] **WIRE-01** through **WIRE-07**: Factory dep resolution, auto-build, parametric setup, type-check elimination

### Handler Separation
- [x] **HSEP-01** through **HSEP-08**: Handler protocols, factory registry, subclass thinning

</details>

<details>
<summary>v3.0 CLI-First Architecture Rewrite (36 requirements) -- shipped 2026-03-29</summary>

- [x] Runtime daemon with Unix socket API
- [x] CommunicationPort protocol + DiscordCommunicationPort adapter
- [x] CompanyRoot extracted to daemon with RuntimeAPI gateway
- [x] CLI commands as API clients
- [x] Bot refactored to thin relay
- [x] Strategist Bash-based autonomy

</details>

<details>
<summary>v2.0/v2.1 Agent Container Architecture -- shipped 2026-03-28</summary>

- [x] Lifecycle FSM, supervision tree, 4 agent types, health tree, resilience, PM autonomy
- [x] Work initiation, PM review gates, auto distribution, event routing, stuck detection

</details>

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full production network deployment | v4 defines the transport stub -- production multi-machine is v5 |
| Non-Discord CommunicationPort adapters (Slack, web) | Separate concern from transport architecture |
| Kubernetes/orchestrator integration | Docker compose or raw Docker only |
| Agent-to-agent direct messaging | By design -- all communication through Discord channels via head |
| State persistence across Docker container rebuilds | Handled by transport channel reconnect, not filesystem persistence |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CHAN-01 | Phase 29 | Complete |
| WORK-01 | Phase 30 | Complete |
| WORK-02 | Phase 30 | Complete |
| WORK-03 | Phase 30 | Complete |
| WORK-04 | Phase 30 | Complete |
| WORK-05 | Phase 30 | Complete |
| HEAD-01 | Phase 31 | Pending |
| HEAD-02 | Phase 31 | Pending |
| HEAD-03 | Phase 31 | Pending |
| HEAD-05 | Phase 31 | Pending |
| CHAN-02 | Phase 32 | Pending |
| CHAN-03 | Phase 32 | Pending |
| AUTO-01 | Phase 33 | Pending |
| AUTO-02 | Phase 33 | Pending |
| AUTO-03 | Phase 33 | Pending |
| HEAD-04 | Phase 34 | Pending |
| CHAN-04 | Phase 34 | Pending |
