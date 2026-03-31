# Roadmap: vCompany

## Milestones

- ✅ **v1.0 MVP** - Phases 1-10 (shipped 2026-03-27)
- ✅ **v2.0 Agent Container Architecture** - Phases 1-10 (shipped 2026-03-28)
- ✅ **v2.1 Behavioral Integration** - Phases 11-17 (shipped 2026-03-28)
- ✅ **v3.0 CLI-First Architecture Rewrite** - Phases 18-23 (shipped 2026-03-29)
- ✅ **v3.1 Container Runtime Abstraction** - Phases 24-28 (shipped 2026-03-31)
- 🚧 **v4.0 Distributed Agent Runtime** - Phases 29-34 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-10) - SHIPPED 2026-03-27</summary>

See `.planning/milestones/v1.0-ROADMAP.md` for full details.

</details>

<details>
<summary>v2.0 Agent Container Architecture (Phases 1-10, +8.1, +8.2, +9, +10) - SHIPPED 2026-03-28</summary>

- [x] Phase 1: Container Foundation (3/3 plans) -- completed 2026-03-27
- [x] Phase 2: Supervision Tree (2/2 plans) -- completed 2026-03-27
- [x] Phase 3: GsdAgent (2/2 plans) -- completed 2026-03-27
- [x] Phase 4: Remaining Agent Types and Scheduler (4/4 plans) -- completed 2026-03-27
- [x] Phase 5: Health Tree (2/2 plans) -- completed 2026-03-27
- [x] Phase 6: Resilience (3/3 plans) -- completed 2026-03-27
- [x] Phase 7: Autonomy Features (3/3 plans) -- completed 2026-03-28
- [x] Phase 8: CompanyRoot Wiring and Migration (3/3 plans) -- completed 2026-03-28
- [x] Phase 8.1: Integration Wiring (2/2 plans) -- completed 2026-03-28
- [x] Phase 8.2: Deep Integration (2/2 plans) -- completed 2026-03-28
- [x] Phase 9: Agent Type Routing + PM Event Dispatch (2/2 plans) -- completed 2026-03-28
- [x] Phase 10: MessageQueue Notification Routing (1/1 plan) -- completed 2026-03-28

See `.planning/milestones/v2.0-ROADMAP.md` for full details.

</details>

<details>
<summary>v2.1 Behavioral Integration (Phases 11-17) - SHIPPED 2026-03-28</summary>

- [x] Phase 11: Container Architecture Fixes (2/2 plans) -- completed 2026-03-28
- [x] Phase 12: Work Initiation (1/1 plan) -- completed 2026-03-28
- [x] Phase 13: PM Event Routing (1/1 plan) -- completed 2026-03-28
- [x] Phase 14: PM Review Gates (2/2 plans) -- completed 2026-03-28
- [x] Phase 15: PM Actions & Auto Distribution (2/2 plans) -- completed 2026-03-28
- [x] Phase 16: Agent Completeness & Strategist (2/2 plans) -- completed 2026-03-28
- [x] Phase 17: Health Tree Rendering (1/1 plan) -- completed 2026-03-28

See `.planning/milestones/v2.1-ROADMAP.md` for full details.

</details>

<details>
<summary>v3.0 CLI-First Architecture Rewrite (Phases 18-23) - SHIPPED 2026-03-29</summary>

- [x] Phase 18: Daemon Foundation (3/3 plans) -- completed 2026-03-29
- [x] Phase 19: Communication Abstraction (2/2 plans) -- completed 2026-03-29
- [x] Phase 20: CompanyRoot Extraction (4/4 plans) -- completed 2026-03-29
- [x] Phase 21: CLI Commands (2/2 plans) -- completed 2026-03-29
- [x] Phase 22: Bot Thin Relay (3/3 plans) -- completed 2026-03-29
- [x] Phase 23: Strategist Autonomy (1/1 plan) -- completed 2026-03-29

See phase details in `.planning/milestones/v3.0-ROADMAP.md`.

</details>

<details>
<summary>v3.1 Container Runtime Abstraction (Phases 24-28) - SHIPPED 2026-03-31</summary>

- [x] Phase 24: Discord Visibility (5/5 plans) -- completed 2026-03-29
- [x] Phase 25: Transport Abstraction (3/3 plans) -- completed 2026-03-29
- [x] Phase 26: Docker Runtime (2/2 plans) -- completed 2026-03-29
- [x] Phase 27: Docker Integration Wiring (4/4 plans) -- completed 2026-03-29
- [x] Phase 28: Agent-Transport Separation (4/4 plans) -- completed 2026-03-31

</details>

### v4.0 Distributed Agent Runtime (In Progress)

**Milestone Goal:** Agent containers run inside transports as autonomous processes. Split vco into vco-head (orchestration) and vco-worker (container runtime). All communication through transport channel protocol. Dead code from daemon-side container architecture removed.

**Phase Numbering:**
- Integer phases (29, 30, 31, ...): Planned milestone work
- Decimal phases (29.1, 29.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 29: Transport Channel Protocol** - Define the bidirectional message protocol between head and worker (completed 2026-03-31)
- [x] **Phase 30: Worker Runtime** - Build vco-worker as a separate installable package with agent lifecycle management (completed 2026-03-31)
- [x] **Phase 31: Head Refactor** - Strip daemon to orchestrator with transport handles only, no agent Python objects (completed 2026-03-31)
- [x] **Phase 32: Transport Channel Implementations** - Docker and native transports use the channel protocol (completed 2026-03-31)
- [x] **Phase 33: Container Autonomy** - Agent state lives inside containers, independence and resilience proven (completed 2026-03-31)
- [ ] **Phase 34: Cleanup and Network Stub** - Remove dead daemon-side code and define network transport contract

## Phase Details

### Phase 29: Transport Channel Protocol
**Goal**: A well-defined bidirectional message protocol exists that head and worker use to communicate -- the foundation everything else builds on
**Depends on**: Phase 28 (v3.1 complete)
**Requirements**: CHAN-01
**Success Criteria** (what must be TRUE):
  1. A message protocol specification exists with typed Pydantic models for all head-to-worker messages (start, give-task, message, stop, health-check) and worker-to-head messages (signal, report, ask, send-file, health-report)
  2. The protocol is transport-agnostic -- serializes to bytes/JSON that any channel (stdin/stdout, socket, TCP) can carry
  3. A protocol test suite validates round-trip serialization for every message type
**Plans:** 1/1 plans complete

Plans:
- [x] 29-01-PLAN.md -- Define channel protocol message models and NDJSON framing

### Phase 30: Worker Runtime
**Goal**: vco-worker is a separate installable Python package that runs inside any execution environment, accepts a config blob, starts the right agent process, and communicates exclusively through the transport channel
**Depends on**: Phase 29
**Requirements**: WORK-01, WORK-02, WORK-03, WORK-04, WORK-05
**Success Criteria** (what must be TRUE):
  1. `pip install vco-worker` installs a package with report/ask/send-file/signal CLI commands that send messages through the transport channel (not via Unix socket or direct Discord)
  2. Worker accepts a config blob at startup specifying handler type, capabilities, gsd_command, persona, and env vars -- then starts the correct agent process (tmux session, claude -p, or Python handler) without any head-side guidance
  3. Worker manages full agent lifecycle inside the execution environment: start, health reporting on request, graceful stop on signal
  4. Worker contains the complete agent container runtime -- handler logic (session/conversation/transient), lifecycle FSM, task queue, idle tracking, memory store, checkpoint/restore -- previously daemon-side capabilities now self-managed
  5. Worker has no dependency on discord.py, bot code, or orchestration modules -- only transport channel client and agent process management
**Plans:** 3/3 plans complete

Plans:
- [x] 30-01-PLAN.md -- Scaffold vco-worker package with channel protocol, config, CLI commands
- [x] 30-02-PLAN.md -- Extract WorkerContainer with adapted handlers and lifecycle FSMs
- [x] 30-03-PLAN.md -- Wire worker main loop with message dispatch and bootstrap

### Phase 31: Head Refactor
**Goal**: Daemon holds only transport handles and agent metadata -- all container internals run inside the worker on the other side of the transport
**Depends on**: Phase 30
**Requirements**: HEAD-01, HEAD-02, HEAD-03, HEAD-05
**Success Criteria** (what must be TRUE):
  1. Daemon stores transport handle + agent metadata (id, type, capabilities, channel_id, handler type, config) per agent -- no GsdAgent/CompanyAgent/FulltimeAgent Python objects instantiated daemon-side
  2. `vco hire` creates a Discord channel, registers routing, and sends a config blob through the transport -- the worker bootstraps itself from that config
  3. Health tree is populated from health-report messages received through the transport channel, not from daemon-side container health methods
  4. Discord channel/category lifecycle is managed by head -- create on hire, cleanup on dismiss, routing state persists across daemon restarts
**Plans:** 3/3 plans complete

Plans:
- [x] 31-01-PLAN.md -- AgentHandle model and routing state persistence
- [x] 31-02-PLAN.md -- Refactor CompanyRoot and RuntimeAPI for channel messages
- [x] 31-03-PLAN.md -- Refactor MentionRouter and Daemon wiring

### Phase 32: Transport Channel Implementations
**Goal**: Both Docker and native transports use the channel protocol end-to-end -- no socket mounts, no shared filesystem between head and worker
**Depends on**: Phase 31
**Requirements**: CHAN-02, CHAN-03
**Success Criteria** (what must be TRUE):
  1. Docker transport creates a container running vco-worker, communicates through the channel protocol (docker exec stdin/stdout or mapped TCP port) -- no Unix socket mount into the container
  2. Native transport starts vco-worker in a local process, communicates through the channel protocol (local socket or in-process bridge)
  3. An agent hired with transport "docker" and an agent hired with transport "native" both produce the same observable behavior: signals appear, health reports come through, Discord messages route correctly
**Plans:** 2/2 plans complete

Plans:
- [x] 32-01-PLAN.md -- ChannelTransport protocol, NativeTransport, and DockerChannelTransport
- [x] 32-02-PLAN.md -- Wire transports into CompanyRoot.hire() and update Dockerfile

### Phase 33: Container Autonomy
**Goal**: Agent containers are fully autonomous -- state lives inside, duplicating a transport creates independent agents, and workers survive daemon restarts
**Depends on**: Phase 32
**Requirements**: AUTO-01, AUTO-02, AUTO-03
**Success Criteria** (what must be TRUE):
  1. Agent state (conversations, checkpoints, memory store, session files) lives inside the execution environment filesystem -- not on the daemon side
  2. Duplicating a transport and sending a new config blob creates a fully independent agent with its own state -- no shared daemon-side state between agents of the same type
  3. When the daemon restarts, running workers continue operating -- upon reconnection via transport channel, the worker sends its current state and the head reconstructs routing without the worker losing progress
**Plans:** 3/3 plans complete

Plans:
- [x] 33-01-PLAN.md -- Worker-side autonomy: ReconnectMessage, cwd-relative state, Unix socket server
- [x] 33-02-PLAN.md -- Head-side transports: socket-based NativeTransport, detached Docker, AgentHandle socket support
- [x] 33-03-PLAN.md -- CompanyRoot reconnection: reconnect_agents() on startup, updated hire/reader flows

### Phase 34: Cleanup and Network Stub
**Goal**: All daemon-side container dead code is removed, and a network transport stub defines the TCP/WebSocket contract for future remote agents
**Depends on**: Phase 33
**Requirements**: HEAD-04, CHAN-04
**Success Criteria** (what must be TRUE):
  1. Daemon-side GsdAgent, CompanyAgent, FulltimeAgent Python objects are deleted -- along with handler factory injection, NoopCommunicationPort, StrategistConversation-from-daemon, and all v3.1 shims
  2. A NetworkTransport stub exists with TCP/WebSocket interface definition -- not production-ready, but the contract is defined and a basic connect/send/receive works
  3. The codebase compiles and all existing functionality (hire, give-task, dismiss, health, status) works after dead code removal
**Plans:** 2/3 plans executed

Plans:
- [x] 34-01-PLAN.md -- Migrate live types from container/ and port StrategistConversation to direct subprocess
- [x] 34-02-PLAN.md -- Delete dead code directories, clean isinstance branches, remove dead tests
- [ ] 34-03-PLAN.md -- Create NetworkTransport TCP stub implementing ChannelTransport protocol

## Progress

**Execution Order:**
Phases execute in numeric order: 29 -> 29.1 -> 29.2 -> 30 -> ... -> 34

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 29. Transport Channel Protocol | 1/1 | Complete    | 2026-03-31 |
| 30. Worker Runtime | 3/3 | Complete    | 2026-03-31 |
| 31. Head Refactor | 3/3 | Complete    | 2026-03-31 |
| 32. Transport Channel Implementations | 2/2 | Complete    | 2026-03-31 |
| 33. Container Autonomy | 3/3 | Complete    | 2026-03-31 |
| 34. Cleanup and Network Stub | 2/3 | In Progress|  |
