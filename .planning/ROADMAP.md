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
- [ ] **Phase 25: Transport Abstraction** - AgentTransport protocol, LocalTransport, and socket-based agent signaling
- [ ] **Phase 26: Docker Runtime** - DockerTransport implementation, Dockerfile, and container configuration

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
- [ ] 24-05-PLAN.md -- Gap closure: fix handle_plan_approval/rejection post_event and [Review] format consistency

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
**Plans**: TBD

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
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 24 -> 24.1 -> 24.2 -> 25 -> ... -> 26

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 24. Discord Visibility | 4/5 | Gap closure | 2026-03-29 |
| 25. Transport Abstraction | 0/? | Not started | - |
| 26. Docker Runtime | 0/? | Not started | - |
