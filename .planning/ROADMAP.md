# Roadmap: vCompany

## Milestones

- ✅ **v1.0 MVP** - Phases 1-10 (shipped 2026-03-27)
- ✅ **v2.0 Agent Container Architecture** - Phases 1-10 (shipped 2026-03-28)
- 🚧 **v2.1 Behavioral Integration** - Phases 11-17 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-10) - SHIPPED 2026-03-27</summary>

See `.planning/milestones/v1.0-ROADMAP.md` for full details.

</details>

<details>
<summary>v2.0 Agent Container Architecture (Phases 1-10, +8.1, +8.2, +9, +10) - SHIPPED 2026-03-28</summary>

- [x] Phase 1: Container Foundation (3/3 plans) — completed 2026-03-27
- [x] Phase 2: Supervision Tree (2/2 plans) — completed 2026-03-27
- [x] Phase 3: GsdAgent (2/2 plans) — completed 2026-03-27
- [x] Phase 4: Remaining Agent Types and Scheduler (4/4 plans) — completed 2026-03-27
- [x] Phase 5: Health Tree (2/2 plans) — completed 2026-03-27
- [x] Phase 6: Resilience (3/3 plans) — completed 2026-03-27
- [x] Phase 7: Autonomy Features (3/3 plans) — completed 2026-03-28
- [x] Phase 8: CompanyRoot Wiring and Migration (3/3 plans) — completed 2026-03-28
- [x] Phase 8.1: Integration Wiring (2/2 plans) — completed 2026-03-28
- [x] Phase 8.2: Deep Integration (2/2 plans) — completed 2026-03-28
- [x] Phase 9: Agent Type Routing + PM Event Dispatch (2/2 plans) — completed 2026-03-28
- [x] Phase 10: MessageQueue Notification Routing (1/1 plan) — completed 2026-03-28

See `.planning/milestones/v2.0-ROADMAP.md` for full details.

</details>

### v2.1 Behavioral Integration (In Progress)

**Milestone Goal:** Make v2.0 container infrastructure operational — agents do real work, PM leads development through conversational review gates, health tree shows the full supervision hierarchy.

- [x] **Phase 11: Container Architecture Fixes** - Fix supervision hierarchy, add BLOCKED/STOPPING states, wire CommunicationPort (completed 2026-03-28)
- [x] **Phase 12: Work Initiation** - Agents receive GSD commands in tmux and start working autonomously (completed 2026-03-28)
- [x] **Phase 13: PM Event Routing** - All agent events (health, GSD transitions, briefings, escalations) flow to PM (completed 2026-03-28)
- [x] **Phase 14: PM Review Gates** - PM-led conversational approve/modify/clarify gates at every GSD stage transition (completed 2026-03-28)
- [x] **Phase 15: PM Actions & Auto Distribution** - PM outbound triggers and automatic next-item assignment from backlog (completed 2026-03-28)
- [x] **Phase 16: Agent Completeness & Strategist** - Strategist operates through container, agents persist full state and delegate work (completed 2026-03-28)
- [ ] **Phase 17: Health Tree Rendering** - Full supervision hierarchy with inner states, uptime, and last activity

## Phase Details

### Phase 11: Container Architecture Fixes
**Goal**: Containers have correct structure — Strategist lives under CompanyRoot, BLOCKED/STOPPING are real FSM states visible in health, and every container has a wired CommunicationPort
**Depends on**: Nothing (foundational fixes for v2.1)
**Requirements**: ARCH-02, ARCH-03, ARCH-04, LIFE-01
**Success Criteria** (what must be TRUE):
  1. Strategist container is a direct child of CompanyRoot, not under any ProjectSupervisor — health tree confirms Strategist as peer to ProjectSupervisors
  2. When an agent becomes blocked, the health tree shows state BLOCKED with a reason string — not a boolean flag
  3. When a container shuts down, it transitions through STOPPING before reaching STOPPED — health tree shows STOPPING during graceful shutdown
  4. Every container created via on_ready or /new-project has a non-None comm_port — agents send messages through CommunicationPort, not raw channel.send()
**Plans**: 2 plans
Plans:
- [x] 11-01-PLAN.md — FSM states (BLOCKED, STOPPING), health model, container lifecycle, supervisor state checks
- [x] 11-02-PLAN.md — Strategist hierarchy, NoopCommunicationPort wiring, display layer updates

### Phase 12: Work Initiation
**Goal**: After dispatch, agents autonomously begin GSD work — Claude Code receives a real GSD command in tmux
**Depends on**: Phase 11
**Requirements**: WORK-01, WORK-02
**Success Criteria** (what must be TRUE):
  1. After /dispatch, the agent's tmux pane receives a GSD command (e.g., `/gsd:discuss-phase 1`) and Claude Code begins executing it — no human intervention required
  2. Container waits for Claude Code readiness (prompt detection) before sending the GSD command — no blind sleep/timeout waits
**Plans**: 1 plan
Plans:
- [x] 12-01-PLAN.md — Readiness poll, GSD command injection, ContainerContext gsd_command field

### Phase 13: PM Event Routing
**Goal**: PM receives all significant agent events in its event queue — not just task completions
**Depends on**: Phase 11
**Requirements**: PMRT-01, PMRT-02, PMRT-03, PMRT-04
**Success Criteria** (what must be TRUE):
  1. When an agent's health state changes (e.g., RUNNING to ERRORED), PM's event queue receives a health_change event with the agent ID and new state
  2. When a GsdAgent transitions GSD stages (e.g., DISCUSS to PLAN), PM's event queue receives a gsd_transition event with stage details
  3. When a ContinuousAgent completes its REPORT phase, PM's event queue receives a briefing event with the report content
  4. When an agent enters BLOCKED state, PM's event queue receives an escalation event with the block reason
**Plans**: 1 plan
Plans:
- [x] 13-01-PLAN.md — PM event sink on Supervisor, callback hooks on GsdAgent/ContinuousAgent, event handlers in FulltimeAgent, wiring in VcoBot.on_ready()

### Phase 14: PM Review Gates
**Goal**: PM leads development through conversational gates — agents stop after each GSD stage, PM reviews, and agents only advance on approval
**Depends on**: Phase 12, Phase 13
**Requirements**: GATE-01, GATE-02, GATE-03, GATE-04, GATE-05
**Success Criteria** (what must be TRUE):
  1. After completing a GSD stage (discuss, plan, execute), the agent posts to its Discord channel with a review request and attaches relevant files (PLAN.md, SUMMARY.md, etc.)
  2. PM reads the attached files, evaluates quality against project context, and responds with approve, modify, or clarify — not a rubber stamp
  3. When PM says modify, the agent makes changes and re-submits for review; when PM says clarify, a multi-turn conversation happens until PM is satisfied
  4. Agent only advances to the next GSD stage after PM explicitly approves — no auto-advancement past gates
  5. Messages between PM and agents are throttled to maximum 1 per 30 seconds per agent
**Plans**: 2 plans
Plans:
- [x] 14-01-PLAN.md — Gate Future on GsdAgent, throttled review posting, file attachment builder
- [x] 14-02-PLAN.md — PM review dispatch, gate response handler, VcoBot wiring

### Phase 15: PM Actions & Auto Distribution
**Goal**: PM proactively manages the project — assigns next work items, triggers integrations, detects stuck agents, escalates to Strategist
**Depends on**: Phase 14
**Requirements**: PMAC-01, PMAC-02, PMAC-03, PMAC-04, PMAC-05, WORK-03
**Success Criteria** (what must be TRUE):
  1. When a GsdAgent completes its current backlog item, PM claims the next item from BacklogQueue and assigns it — the agent starts the new work automatically
  2. PM can trigger an integration review through ProjectSupervisor and inject urgent milestones into BacklogQueue
  3. PM can request agent recruitment or removal through ProjectSupervisor and escalate decisions to Strategist
  4. When an agent is stuck in the same GSD state beyond the configured threshold, PM sends a message to the agent's Discord channel to intervene
**Plans**: 2 plans
Plans:
- [x] 15-01-PLAN.md — PM action methods, callback slots, stuck detector on FulltimeAgent; add/remove helpers on ProjectSupervisor
- [x] 15-02-PLAN.md — VcoBot.on_ready wiring for all Phase 15 PM action callbacks

### Phase 16: Agent Completeness & Strategist
**Goal**: Strategist operates through its CompanyAgent container, ContinuousAgents delegate and persist state, GsdAgents recover full work context
**Depends on**: Phase 11
**Requirements**: ARCH-01, AGNT-01, AGNT-02, AGNT-03
**Success Criteria** (what must be TRUE):
  1. Strategist logic runs inside CompanyAgent._handle_event() — StrategistCog is a thin Discord adapter that forwards to the container, not the other way around
  2. ContinuousAgent can call request_task() to delegate work through supervisor via DelegationTracker
  3. ContinuousAgent persists seen_items, pending_actions, briefing_log, and config to memory_store — survives restart
  4. When a GsdAgent restarts, it restores current phase, task, and assignment from ProjectStateManager — not just FSM state
**Plans**: 2 plans
Plans:
- [x] 16-01-PLAN.md — Strategist inversion: move conversation into CompanyAgent._handle_event(), StrategistCog becomes thin adapter
- [x] 16-02-PLAN.md — Agent completeness: ContinuousAgent delegation + persistence, GsdAgent assignment restore

### Phase 17: Health Tree Rendering
**Goal**: /health command shows the complete supervision hierarchy matching the architecture doc's format
**Depends on**: Phase 11, Phase 16
**Requirements**: HLTH-05, HLTH-06
**Success Criteria** (what must be TRUE):
  1. /health shows CompanyRoot at the top, Strategist/CompanyAgents as its direct children, then ProjectSupervisors with their PM and GsdAgents underneath
  2. Each agent in the health tree displays inner_state (e.g., GSD sub-state), uptime, and last_activity — not just lifecycle state
**Plans**: 1 plan
Plans:
- [ ] 17-01-PLAN.md — Update build_health_tree_embed with CompanyRoot header and per-agent uptime/last_activity

## Progress

**Execution Order:**
Phases execute in numeric order: 11 -> 12 -> 13 -> 14 -> 15 -> 16 -> 17
(Phases 12/13 and 16 can proceed in parallel after Phase 11)

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 11. Container Architecture Fixes | v2.1 | 2/2 | Complete    | 2026-03-28 |
| 12. Work Initiation | v2.1 | 1/1 | Complete    | 2026-03-28 |
| 13. PM Event Routing | v2.1 | 1/1 | Complete    | 2026-03-28 |
| 14. PM Review Gates | v2.1 | 2/2 | Complete    | 2026-03-28 |
| 15. PM Actions & Auto Distribution | v2.1 | 2/2 | Complete    | 2026-03-28 |
| 16. Agent Completeness & Strategist | v2.1 | 2/2 | Complete    | 2026-03-28 |
| 17. Health Tree Rendering | v2.1 | 0/0 | Not started | - |
