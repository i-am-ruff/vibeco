# Roadmap: vCompany

## Milestones

- ✅ **v1.0 MVP** - Phases 1-10 (shipped 2026-03-27)
- ✅ **v2.0 Agent Container Architecture** - Phases 1-10 (shipped 2026-03-28)
- ✅ **v2.1 Behavioral Integration** - Phases 11-17 (shipped 2026-03-28)
- ✅ **v3.0 CLI-First Architecture Rewrite** - Phases 18-23 (shipped 2026-03-29)
- 🚧 **v3.1 Container Runtime Abstraction** - Phases 24-26 (in progress)

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

### v3.1 Container Runtime Abstraction (In Progress)

**Milestone Goal:** Remove hidden inter-agent communication, surface all agent interactions through Discord, then abstract the execution environment so agents can run in Docker containers with isolated Claude Code configurations.

**Phase Numbering:**
- Integer phases (24, 25, 26): Planned milestone work
- Decimal phases (24.1, 24.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 24: Discord Visibility** - Surface all hidden inter-agent communication through Discord channels (completed 2026-03-29)
- [x] **Phase 25: Transport Abstraction** - AgentTransport protocol, LocalTransport, and socket-based agent signaling (completed 2026-03-29)
- [x] **Phase 26: Docker Runtime** - DockerTransport implementation, Dockerfile, and container configuration (completed 2026-03-29)

## Phase Details

### Phase 24: Discord Visibility
**Goal**: Every inter-agent event, PM action, and plan review decision is visible on Discord before taking effect -- no hidden internal routing
**Depends on**: Phase 23 (v3.0 complete)
**Requirements**: VIS-01, VIS-02, VIS-03, VIS-04, VIS-05, VIS-06
**Success Criteria** (what must be TRUE):
  1. When an agent completes a phase, a task is assigned, or a plan is reviewed, a Discord message appears in the relevant channel before the internal state changes
  2. PM backlog mutations (add/remove/prioritize) produce a Discord message describing the change -- no silent queue operations
  3. Plan review approve/reject decisions show confidence score and reasoning on Discord before the approval or rejection is processed internally
  4. RuntimeAPI contains no agent-type-specific routing methods (no "send to PM" or "send to Strategist" wiring) -- agent coordination goes through Discord channel subscriptions
  5. Task assignment from PM to a GSD agent appears as a message in the agent's Discord channel, not as an internal queue_task() call
**Plans**: 5 plans

Plans:
- [x] 24-01-PLAN.md -- MentionRouterCog, MessageContext model, channel setup, AgentContainer.receive_discord_message
- [x] 24-02-PLAN.md -- BacklogQueue mutation notification callback
- [x] 24-03-PLAN.md -- Agent Discord message handlers (FulltimeAgent, CompanyAgent, GsdAgent)
- [x] 24-04-PLAN.md -- RuntimeAPI cleanup, Supervisor unwiring, PlanReviewCog update
- [x] 24-05-PLAN.md -- Gap closure: fix handle_plan_approval/rejection post_event and [Review] format consistency

### Phase 25: Transport Abstraction
**Goal**: Agent execution environment is abstracted behind an AgentTransport protocol, with a working LocalTransport implementation and socket-based signaling replacing temp files
**Depends on**: Phase 24
**Requirements**: TXPT-01, TXPT-02, TXPT-03, TXPT-04, TXPT-05, TXPT-06
**Success Criteria** (what must be TRUE):
  1. An AgentTransport protocol exists with setup/teardown/exec/is_alive/read_file/write_file methods, and AgentContainer uses the injected transport instead of calling TmuxManager directly
  2. LocalTransport implements AgentTransport using TmuxManager for interactive sessions and subprocess for piped invocations -- existing agent behavior is unchanged
  3. StrategistConversation uses AgentTransport.exec() instead of direct asyncio.create_subprocess_exec calls
  4. Agent readiness and idle signals use `vco signal --ready/--idle` over the daemon socket instead of sentinel temp files
  5. AgentConfig.transport field (default "local") controls which transport implementation the factory injects
**Plans**: 3 plans

Plans:
- [x] 25-01-PLAN.md -- AgentTransport protocol, NoopTransport, LocalTransport, AgentConfig.transport field
- [x] 25-02-PLAN.md -- Daemon HTTP signal endpoint, vco signal CLI command, settings.json.j2 hook update
- [x] 25-03-PLAN.md -- Container/factory/supervisor rewiring to transport, StrategistConversation through transport

### Phase 26: Docker Runtime
**Goal**: Agents can run inside Docker containers with full daemon connectivity, persistent session state, and per-agent image configuration
**Depends on**: Phase 25
**Requirements**: DOCK-01, DOCK-02, DOCK-03, DOCK-04, DOCK-05, DOCK-06
**Success Criteria** (what must be TRUE):
  1. DockerTransport implements AgentTransport using docker exec for both interactive (tmux inside container) and piped (claude -p) modes
  2. A Dockerfile exists that builds a Claude Code image with tweakcc patches applied, and `docker build` succeeds
  3. Docker containers can run vco CLI commands (the daemon Unix socket is mounted as a volume) and agent work directories are accessible via volume mounts
  4. Setting AgentConfig.transport to "docker" with a docker_image field causes the factory to create a DockerTransport-backed agent
  5. Docker containers persist across agent restarts (docker create + start/stop) so ~/.claude session state survives restart cycles
**Plans**: 2 plans

Plans:
- [x] 26-01-PLAN.md -- Dockerfile, settings.json, AgentConfig.docker_image field, docker-py dependency
- [x] 26-02-PLAN.md -- DockerTransport implementation and factory registry wiring

## Progress

**Execution Order:**
Phases execute in numeric order: 24 -> 24.1 -> 24.2 -> 25 -> ... -> 26

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 24. Discord Visibility | 5/5 | Complete    | 2026-03-29 |
| 25. Transport Abstraction | 3/3 | Complete    | 2026-03-29 |
| 26. Docker Runtime | 2/2 | Complete    | 2026-03-29 |
| 27. Docker Integration Wiring | 4/4 | Complete    | 2026-03-29 |
| 28. Agent-Transport Separation | 3/4 | In Progress|  |

### Phase 27: Docker Integration Wiring
**Goal**: Docker agents work end-to-end: per-transport deps resolution, docker_image flow from config to constructor, auto-build on first use, parametric agent setup (tweakcc profiles, custom settings via kwargs), and removal of hardcoded agent-type checks from business logic
**Depends on**: Phase 26
**Requirements**: WIRE-01, WIRE-02, WIRE-03, WIRE-04, WIRE-05, WIRE-06, WIRE-07
**Success Criteria** (what must be TRUE):
  1. Factory resolves transport_deps per transport type (LocalTransport gets tmux_manager, DockerTransport gets docker_image + project_name) -- daemon no longer passes a single global dict
  2. docker_image flows from AgentConfig through ChildSpec to DockerTransport constructor without manual wiring
  3. Docker image auto-builds when an agent with transport "docker" is hired and the image doesn't exist (or `vco build` command exists)
  4. DockerTransport.setup() accepts parametric kwargs (tweakcc profile, custom settings.json path) so one universal image can be customized per agent at startup
  5. No hardcoded agent-type if/in checks remain in runtime_api.py or supervisor.py -- agent capabilities derived from config, not type string matching
  6. A Docker agent can be hired via Discord, receives a task, signals readiness through the mounted daemon socket, and appears in health tree
  7. Adding a new agent type (e.g., "cfo") requires only a config entry and optional container subclass -- no business logic changes
**Plans**: 4 plans

Plans:
- [x] 27-01-PLAN.md -- Agent-types config model, loader, factory smart dep resolution
- [x] 27-02-PLAN.md -- Docker auto-build utility and vco build CLI command
- [x] 27-03-PLAN.md -- Type-check elimination in runtime_api.py and supervisor.py
- [x] 27-04-PLAN.md -- Parametric DockerTransport setup, hire flow wiring, e2e validation

### Phase 28: Agent-Transport Separation Refactor

**Goal:** Extract handler types (tmux session, resume-conversation, memory-based transient) from agent subclasses into composable pieces orthogonal to transport (native, Docker, network). Any handler type can run on any transport without new classes.
**Requirements**: HSEP-01, HSEP-02, HSEP-03, HSEP-04, HSEP-05, HSEP-06, HSEP-07, HSEP-08
**Depends on:** Phase 27
**Success Criteria** (what must be TRUE):
  1. Three handler protocols (SessionHandler, ConversationHandler, TransientHandler) exist as @runtime_checkable Protocols
  2. _send_discord is consolidated into base AgentContainer -- no duplicate implementations in subclasses
  3. agent-types.yaml has a handler field, factory composes handler+transport from config
  4. Agent subclasses are thin wrappers: lifecycle FSM + domain methods only, no _send_discord/state/inner_state/receive_discord_message overrides
  5. Dead code (self._tmux, _launch_tmux_session) in GsdAgent and TaskAgent is removed
  6. RuntimeAPI hasattr checks (resolve_review, initialize_conversation, backlog) still work
**Plans**: 4 plans

Plans:
- [x] 28-01-PLAN.md -- Handler protocols, base container consolidation (_send_discord, _channel_id, _handler, OrderedSet state)
- [x] 28-02-PLAN.md -- Handler implementations (GsdSessionHandler, StrategistConversationHandler, PMTransientHandler)
- [x] 28-03-PLAN.md -- Config handler field and factory handler registry
- [ ] 28-04-PLAN.md -- Agent subclass thinning, dead code cleanup, handler hook ordering
