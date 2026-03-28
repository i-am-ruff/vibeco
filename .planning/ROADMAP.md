# Roadmap: vCompany

## Milestones

- ✅ **v1.0 MVP** - Phases 1-10 (shipped 2026-03-27)
- 🚧 **v2.0 Agent Container Architecture** - Phases 1-8 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-10) - SHIPPED 2026-03-27</summary>

### Phase 1: Foundation and Configuration
**Goal**: The system can parse agent configuration, create project structures, clone repos with per-agent isolation, and deploy all necessary artifacts to each clone
**Plans**: 4/4 complete

Plans:
- [x] 01-01-PLAN.md -- Project bootstrap + Pydantic config models
- [x] 01-02-PLAN.md -- Git wrapper, tmux wrapper, atomic file ops
- [x] 01-03-PLAN.md -- Jinja2 templates + vco init command
- [x] 01-04-PLAN.md -- vco clone command + artifact deployment

### Phase 2: Agent Lifecycle and Pre-flight
**Goal**: Agents can be launched, terminated, and automatically recovered from crashes
**Plans**: 3/3 complete

Plans:
- [x] 02-01-PLAN.md -- State models + crash tracker
- [x] 02-02-PLAN.md -- Agent manager + dispatch/kill/relaunch CLI commands
- [x] 02-03-PLAN.md -- Pre-flight test suite + CLI command

### Phase 3: Monitor Loop and Coordination
**Goal**: Agents are continuously supervised with liveness checks, stuck detection, and cross-agent status awareness
**Plans**: 4/4 complete

Plans:
- [x] 03-01-PLAN.md -- Monitor state models + check functions
- [x] 03-02-PLAN.md -- PROJECT-STATUS.md generation/distribution + heartbeat watchdog
- [x] 03-03-PLAN.md -- MonitorLoop class + vco monitor CLI command
- [x] 03-04-PLAN.md -- Coordination system (INTERFACES.md, sync-context, INTERACTIONS.md)

### Phase 4: Discord Bot Core
**Goal**: The owner can control and observe the entire agent fleet from Discord
**Plans**: 4/4 complete

Plans:
- [x] 04-01-PLAN.md -- Bot foundation
- [x] 04-02-PLAN.md -- CommandsCog
- [x] 04-03-PLAN.md -- AlertsCog
- [x] 04-04-PLAN.md -- Bot startup wiring

### Phase 5: Hooks and Plan Gate
**Goal**: Agents can ask questions through Discord and plans are gated for review
**Plans**: 4/4 complete

Plans:
- [x] 05-01-PLAN.md -- ask_discord.py hook
- [x] 05-02-PLAN.md -- Plan gate state model + safety table validator
- [x] 05-03-PLAN.md -- PlanReviewCog expansion
- [x] 05-04-PLAN.md -- QuestionHandlerCog + bot startup wiring

### Phase 6: PM/Strategist and Milestones
**Goal**: Two-tier AI decision system with PM and Strategist
**Plans**: 5/5 complete

Plans:
- [x] 06-01-PLAN.md -- PM data models + confidence scorer
- [x] 06-02-PLAN.md -- Strategist persistent conversation manager
- [x] 06-03-PLAN.md -- PM tier (question evaluation + plan reviewer)
- [x] 06-04-PLAN.md -- StrategistCog expansion + decision logging
- [x] 06-05-PLAN.md -- Wiring + milestone CLI

### Phase 7: Integration Pipeline and Communications
**Goal**: Agent branches merge cleanly with automated testing and structured communication rituals
**Plans**: 6/6 complete

Plans:
- [x] 07-01-PLAN.md -- Git ops extensions + integration pipeline core
- [x] 07-02-PLAN.md -- Conflict resolver + fix dispatch
- [x] 07-03-PLAN.md -- Checkin data gathering + embed builder
- [x] 07-04-PLAN.md -- Monitor integration interlock
- [x] 07-05-PLAN.md -- Standup session + ReleaseView
- [x] 07-06-PLAN.md -- Interaction regression tests

### Phase 8: Reliable tmux Agent Lifecycle
**Goal**: Work commands reliably delivered to agent tmux panes
**Plans**: 2/2 complete

Plans:
- [x] 08-01-PLAN.md -- TmuxManager send_command + readiness detection
- [x] 08-02-PLAN.md -- Fix callers + dispatch readiness-based launch

### Phase 9: Discord-Native Agent Communication
**Goal**: Agent questions route through Discord channels with PM auto-answering
**Plans**: 3/3 complete

Plans:
- [x] 09-01-PLAN.md -- Message routing framework
- [x] 09-02-PLAN.md -- Hook rewrite (Discord REST API)
- [x] 09-03-PLAN.md -- Bot-side rework

### Phase 10: Autonomous GSD Agent Dispatch
**Goal**: WorkflowOrchestrator drives deterministic per-agent state machine
**Plans**: 3/3 complete

Plans:
- [x] 10-01-PLAN.md -- GSD config template update + workflow patcher
- [x] 10-02-PLAN.md -- WorkflowOrchestrator state machine + signal detection
- [x] 10-03-PLAN.md -- WorkflowOrchestratorCog + bot startup wiring

</details>

### v2.0 Agent Container Architecture (In Progress)

**Milestone Goal:** Replace the flat agent model and external watchdog with a self-supervising container hierarchy where every agent is a lifecycle unit with its own state machine, health reporting, and restart semantics.

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Container Foundation** - AgentContainer base with lifecycle state machine, context, memory store, health self-reporting, child specs, and communication contract *(completed 2026-03-27)*
- [x] **Phase 2: Supervision Tree** - Two-level supervision hierarchy with Erlang-style restart policies, escalation, and 10-minute restart windows *(completed 2026-03-27)*
- [x] **Phase 3: GsdAgent** - Phase-driven agent type absorbing WorkflowOrchestrator with nested FSM and checkpoint-based crash recovery *(completed 2026-03-27)*
- [x] **Phase 4: Remaining Agent Types and Scheduler** - ContinuousAgent, FulltimeAgent (PM), CompanyAgent (Strategist), and scheduler for wake cycles *(completed 2026-03-27)*
- [x] **Phase 5: Health Tree** - Health aggregation across the supervision tree with Discord /health rendering and state-change notifications (completed 2026-03-27)
- [x] **Phase 6: Resilience** - Rate-aware communication, upstream outage detection, and degraded mode for Claude server unavailability *(completed 2026-03-27)*
- [x] **Phase 7: Autonomy Features** - Living milestone backlog, delegation protocol, and decoupled project/agent lifecycles *(completed 2026-03-28)*
- [x] **Phase 8: CompanyRoot Wiring and Migration** - CompanyRoot replaces VcoBot.on_ready(), slash command conversion, v1 module removal, communication layer abstraction *(completed 2026-03-28)*
- [x] **Phase 8.1: Integration Wiring** - Wire cross-phase integration gaps (HealthCog, BacklogQueue, MessageQueue, DegradedMode) *(completed 2026-03-28)*
- [x] **Phase 8.2: Deep Integration** - Make v2 container system operational end-to-end (2026-03-28)
- [ ] **Phase 9: Agent Type Routing and PM Event Dispatch** - Fix AgentConfig.type field, enable correct agent type instantiation, wire GsdAgent→PM event dispatch
- [ ] **Phase 10: MessageQueue Notification Routing** - Route all Discord notification senders through MessageQueue for rate limiting and priority ordering

## Phase Details

### Phase 1: Container Foundation
**Goal**: Every agent is wrapped in a container with a validated lifecycle state machine, persistent memory, self-reported health, and a declared communication contract
**Depends on**: Nothing (first phase of v2.0)
**Requirements**: CONT-01, CONT-02, CONT-03, CONT-04, CONT-05, CONT-06, HLTH-01
**Success Criteria** (what must be TRUE):
  1. An AgentContainer can be created and transitioned through CREATING, RUNNING, SLEEPING, ERRORED, STOPPED, DESTROYED -- and impossible transitions (e.g., STOPPED to RUNNING) raise validation errors
  2. Each container's memory_store persists key-value data and checkpoints to an agent-specific SQLite file that survives process restarts
  3. A child specification registry can declare container types with config and restart policy, and a supervisor can read specs to instantiate containers
  4. Each container self-reports a HealthReport (state, uptime, last_heartbeat, error_count, last_activity) on every state transition
  5. No container communicates with another through file-based IPC or in-memory callbacks -- the communication interface is designed for Discord-only message passing
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md -- Types, state machine, data models (ContainerLifecycle, ContainerContext, HealthReport, CommunicationPort)
- [x] 01-02-PLAN.md -- MemoryStore (async SQLite persistence) + ChildSpec registry
- [ ] 01-03-PLAN.md -- AgentContainer class wiring all modules together

### Phase 2: Supervision Tree
**Goal**: Supervisors manage child containers with Erlang-style restart policies, intensity-limited restart windows, and escalation to parent when limits are exceeded
**Depends on**: Phase 1
**Requirements**: SUPV-01, SUPV-02, SUPV-03, SUPV-04, SUPV-05, SUPV-06
**Success Criteria** (what must be TRUE):
  1. A two-level hierarchy (CompanyRoot placeholder to ProjectSupervisor to agent containers) starts, supervises, and restarts children using asyncio Tasks
  2. one_for_one restarts only the failed child, all_for_one restarts all siblings, and rest_for_one restarts the failed child plus all children started after it
  3. When a child crashes 3 times within a 10-minute window, the supervisor stops restarting and escalates to its parent
  4. When the top-level supervisor receives an escalation it cannot handle, it alerts the owner through Discord
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md -- Supervisor base class with restart strategies, intensity tracker, and escalation
- [x] 02-02-PLAN.md -- CompanyRoot, ProjectSupervisor, two-level hierarchy integration tests

### Phase 3: GsdAgent
**Goal**: GsdAgent is the first real container type with an internal phase state machine that replaces WorkflowOrchestrator, with checkpoint-based crash recovery
**Depends on**: Phase 2
**Requirements**: TYPE-01, TYPE-02
**Success Criteria** (what must be TRUE):
  1. GsdAgent runs an internal phase FSM (IDLE to DISCUSS to PLAN to EXECUTE to UAT to SHIP) nested inside the container's RUNNING state using python-statemachine compound states
  2. Each GsdAgent phase transition checkpoints to memory_store -- a crash mid-phase resumes from the last checkpointed state instead of restarting from scratch
  3. GsdAgent fully absorbs WorkflowOrchestrator's state tracking -- no external system tracks GsdAgent phase state
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md -- GsdLifecycle compound state FSM + GsdPhase enum + CheckpointData model
- [x] 03-02-PLAN.md -- GsdAgent class with checkpoint recovery + WorkflowOrchestrator absorption

### Phase 4: Remaining Agent Types and Scheduler
**Goal**: ContinuousAgent, FulltimeAgent, and CompanyAgent are operational as containers, and sleeping agents wake on schedule
**Depends on**: Phase 2
**Requirements**: TYPE-03, TYPE-04, TYPE-05, AUTO-06
**Success Criteria** (what must be TRUE):
  1. ContinuousAgent runs scheduled wake/sleep cycles (WAKE to GATHER to ANALYZE to ACT to REPORT to SLEEP) and persists state across cycles via memory_store
  2. FulltimeAgent (PM) reacts to agent state transitions, health changes, escalations, and briefings as an event-driven container that lives for the project duration
  3. CompanyAgent (Strategist) runs as an event-driven container that survives project restarts and holds cross-project state
  4. Sleeping ContinuousAgents are automatically woken by the scheduler at their configured times, and scheduled wake times survive bot restarts
**Plans**: 4 plans

Plans:
- [x] 04-01-PLAN.md -- Container factory registry + Supervisor._start_child() update
- [x] 04-02-PLAN.md -- ContinuousLifecycle FSM + ContinuousAgent with checkpoint recovery
- [x] 04-03-PLAN.md -- EventDrivenLifecycle FSM + FulltimeAgent + CompanyAgent
- [ ] 04-04-PLAN.md -- Scheduler in CompanyRoot + factory registration for all agent types

### Phase 5: Health Tree
**Goal**: Health reports aggregate across the supervision tree into a queryable, renderable status view pushed to Discord
**Depends on**: Phase 4
**Requirements**: HLTH-02, HLTH-03, HLTH-04
**Success Criteria** (what must be TRUE):
  1. Supervisors aggregate children's health into a tree queryable at company, project, and individual agent levels
  2. Running `/health` in Discord renders the full supervision tree with color-coded state indicators
  3. State transitions (RUNNING to ERRORED, etc.) automatically push notifications to Discord without polling
**Plans**: 2 plans
**UI hint**: yes

Plans:
- [x] 05-01-PLAN.md -- Health tree models, supervisor aggregation, notification callback
- [x] 05-02-PLAN.md -- HealthCog with /health slash command and embed builder

### Phase 6: Resilience
**Goal**: The communication layer handles Discord rate limits gracefully, supervisors detect upstream outages, and the system degrades safely when Claude servers are unreachable
**Depends on**: Phase 2
**Requirements**: RESL-01, RESL-02, RESL-03
**Success Criteria** (what must be TRUE):
  1. Outbound Discord messages are queued with rate-aware batching -- health reports debounced, supervisor commands prioritized, exponential backoff on 429s
  2. When all children fail simultaneously, the supervisor detects an upstream outage and triggers global backoff instead of per-agent restart loops
  3. When Claude servers are unreachable, the system enters degraded mode -- existing containers stay alive, no new dispatches occur, the owner is notified, and the system recovers automatically when service returns
**Plans**: 3 plans

Plans:
- [ ] 06-01-PLAN.md -- MessageQueue with priority ordering, debounce, and exponential backoff
- [ ] 06-02-PLAN.md -- BulkFailureDetector and Supervisor integration for upstream outage detection
- [ ] 06-03-PLAN.md -- DegradedModeManager and CompanyRoot integration for Claude API unavailability

### Phase 7: Autonomy Features
**Goal**: The PM manages a living milestone backlog, continuous agents can delegate task spawns through the supervisor, and agent crashes never corrupt project state
**Depends on**: Phase 4, Phase 5
**Requirements**: AUTO-01, AUTO-02, AUTO-03, AUTO-04, AUTO-05
**Success Criteria** (what must be TRUE):
  1. The PM can append, insert_urgent, reorder, and cancel items in the living milestone backlog, and GsdAgent consumes work from this queue instead of a static list
  2. A ContinuousAgent can request a task spawn through the supervisor, the supervisor enforces hard caps and rate limits, and the spawned GsdAgent executes the delegated work
  3. Project state is owned by the PM -- agents read assignments and write completions, and an agent crash never leaves project state in an inconsistent or corrupted condition
**Plans**: 3 plans

Plans:
- [x] 07-01-PLAN.md -- BacklogQueue data structure with PM operations and GsdAgent consumption
- [x] 07-02-PLAN.md -- Delegation protocol with policy enforcement and supervisor integration
- [x] 07-03-PLAN.md -- ProjectStateManager, PM event handling, crash-safe state ownership

### Phase 8: CompanyRoot Wiring and Migration
**Goal**: The supervision tree replaces flat VcoBot initialization, all commands are slash commands, v1 modules are removed, and the communication layer is ready for v3 abstraction
**Depends on**: Phase 5, Phase 6, Phase 7
**Requirements**: MIGR-01, MIGR-02, MIGR-03, MIGR-04
**Success Criteria** (what must be TRUE):
  1. CompanyRoot initializes the full supervision tree on bot startup, replacing the flat VcoBot.on_ready() component wiring
  2. All Discord commands use slash command syntax (no more `!` prefix) and the command tree syncs on startup
  3. v1 MonitorLoop, CrashTracker, WorkflowOrchestrator, and AgentManager modules are fully removed, and all existing regression tests pass against v2 equivalents
  4. The communication layer has a clean abstract interface that Discord implements, documented as the extension point for v3 channel abstraction
**Plans**: 3 plans
**UI hint**: yes

Plans:
- [x] 08-01-PLAN.md -- DiscordCommunicationPort implementation + slash command prefix cleanup
- [x] 08-02-PLAN.md -- CompanyRoot wiring into VcoBot.on_ready(), CommandsCog and WorkflowOrchestratorCog adaptation
- [ ] 08-03-PLAN.md -- v1 module removal, CLI command updates, test cleanup

### Phase 8.1: Integration Wiring (INSERTED)
**Goal**: Wire all cross-phase integration gaps: HealthCog loading, BacklogQueue/ProjectStateManager assignment, GsdAgent consumption loop, DegradedModeManager activation, MessageQueue routing
**Depends on**: Phase 8
**Requirements**: HLTH-03, HLTH-04, RESL-01, RESL-03, AUTO-01, AUTO-02, AUTO-05
**Success Criteria** (what must be TRUE):
  1. HealthCog is loaded by VcoBot and /health command works at runtime
  2. FulltimeAgent.backlog and _project_state are assigned after add_project()
  3. GsdAgent consumption loop calls get_assignment() and routes completion events to PM
  4. DegradedModeManager activates with a health_check callable
  5. MessageQueue routes all outbound Discord notifications with priority and debounce
**Plans**: 2 plans

Plans:
- [x] 08.1-01-PLAN.md -- Wire HealthCog loading, DegradedMode health_check, and MessageQueue into bot startup
- [x] 08.1-02-PLAN.md -- Wire BacklogQueue/ProjectStateManager to FulltimeAgent and GsdAgent consumption loop

### Phase 8.2: Deep Integration (INSERTED)
**Goal**: Make v2 container system operational end-to-end: dispatch/kill/relaunch use container lifecycle, health reflects real tmux state, /status removed, agent running state correlates with actual liveness
**Depends on**: Phase 8.1
**Requirements**: MIGR-01, HLTH-02, HLTH-03
**Success Criteria** (what must be TRUE):
  1. `/dispatch` creates an AgentContainer, starts it via the supervision tree, and launches the tmux session -- container state tracks real tmux liveness
  2. `/kill` and `/relaunch` operate through the container lifecycle (stop/destroy/restart), not raw tmux commands
  3. `/health` shows the real supervision hierarchy (CompanyRoot -> ProjectSupervisor -> agents) with state that matches actual tmux session liveness -- no phantom containers
  4. `/status` command is removed -- `/health` is the replacement
  5. State-change notifications fire to #alerts when real agent state changes (tmux session dies -> container ERRORED -> notification)
**Plans**: 2 plans

Plans:
- [x] 08.2-01-PLAN.md -- Container tmux bridge + supervisor liveness monitoring + tests
- [x] 08.2-02-PLAN.md -- Command updates (dispatch/kill/relaunch use tmux lifecycle, /status removed) + test updates

### Phase 9: Agent Type Routing and PM Event Dispatch (GAP CLOSURE)
**Goal**: AgentConfig carries a type field so FulltimeAgent and CompanyAgent are instantiated from agents.yaml, GsdAgent completion events are dispatched to the PM, /new-project wires PM backlog, and all dead code paths from old workflows are removed
**Depends on**: Phase 8.2
**Requirements**: TYPE-04, TYPE-05, AUTO-05
**Gap Closure**: Closes gaps from v2.0 milestone audit
**Success Criteria** (what must be TRUE):
  1. `AgentConfig` has a `type` field with values `gsd`, `continuous`, `fulltime`, `company` — agents.yaml entries with `type: fulltime` produce a FulltimeAgent
  2. `client.py` and `commands.py` read `agent_cfg.type` (not `hasattr` fallback) — FulltimeAgent and CompanyAgent are created when config specifies them
  3. A cog or dispatcher calls `gsd_agent.make_completion_event()` on phase completion and routes the event to `bot._pm_container.post_event()`
  4. `/new-project` command wires BacklogQueue and ProjectStateManager to FulltimeAgent (same wiring as on_ready path)
  5. `isinstance(child, FulltimeAgent)` finds the PM container in on_ready's post-wiring loop
  6. Dead code removed: `HealthCog.setup_notifications()` no-op method deleted, `build_status_embed` deprecated function removed from embeds.py, any other dead/unreachable code paths from v1→v2 migration cleaned up
  7. No `hasattr(..., "type")` fallback guards remain — replaced with direct attribute access
**Plans**: 2 plans

Plans:
- [ ] 09-01-PLAN.md -- AgentConfig type field + hasattr removal
- [ ] 09-02-PLAN.md -- PM event dispatch, /new-project wiring, dead code cleanup

### Phase 10: MessageQueue Notification Routing (GAP CLOSURE)
**Goal**: All outbound Discord notifications (health state changes, escalations, degraded mode alerts, recovery notices) route through MessageQueue for rate-limit backoff and priority ordering — old direct-send paths fully removed
**Depends on**: Phase 9
**Requirements**: RESL-01
**Gap Closure**: Closes gaps from v2.0 milestone audit
**Success Criteria** (what must be TRUE):
  1. `HealthCog._notify_state_change()` calls `message_queue.enqueue(QueuedMessage(...))` instead of `channel.send()`
  2. `on_escalation`, `on_degraded`, `on_recovered` callbacks in `client.py` route through `message_queue.enqueue()` instead of direct `channel.send()`
  3. No direct `channel.send()` calls remain in notification paths (health, alerts, escalation) — old direct-send code paths fully removed
  4. MessageQueue priority ordering is exercised — escalations have higher priority than health state change notifications
  5. Existing tests updated to verify queue routing, not direct sends
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8
(Phases 3/4 share dependency on Phase 2; Phase 6 can parallel Phases 3-5; Phase 7 depends on 4+5; Phase 8 is last)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Container Foundation | 3/3 | Complete | 2026-03-27 |
| 2. Supervision Tree | 2/2 | Complete | 2026-03-27 |
| 3. GsdAgent | 2/2 | Complete | 2026-03-27 |
| 4. Remaining Agent Types and Scheduler | 0/4 | Planned | - |
| 5. Health Tree | 2/2 | Complete   | 2026-03-27 |
| 6. Resilience | 0/3 | Planned | - |
| 7. Autonomy Features | 2/3 | In Progress|  |
| 8. CompanyRoot Wiring and Migration | 2/3 | In Progress|  |
| 8.1. Integration Wiring | 2/2 | Complete | 2026-03-28 |
| 8.2. Deep Integration | 2/2 | Complete | 2026-03-28 |
| 9. Agent Type Routing + PM Event Dispatch | 0/2 | Planned | - |
| 10. MessageQueue Notification Routing | 0/0 | Not Started | - |
