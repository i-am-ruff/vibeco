# Feature Research

**Domain:** Agent container architecture, supervision trees, and lifecycle management for autonomous multi-agent orchestration
**Researched:** 2026-03-27
**Confidence:** HIGH (core patterns well-established via Erlang/OTP, Kubernetes, systemd; applied to AI agent context with MEDIUM confidence)

## Feature Landscape

This research targets the v2.0 milestone: replacing vCompany's flat agent model and external watchdog with a self-supervising container hierarchy. Features are evaluated against what exists (v1 flat dispatch + external monitor loop) and what the container architecture needs.

### Table Stakes (Users Expect These)

Features that the container architecture MUST have or the refactor delivers no value over v1.

#### AgentContainer Base Abstraction

| Feature | Why Expected | Complexity | Depends On (v1) |
|---------|--------------|------------|------------------|
| Lifecycle state machine (CREATING->RUNNING->SLEEPING->ERRORED->STOPPED->DESTROYED) | Without explicit states, the system guesses agent status from tmux pane liveness -- fragile and ambiguous. v1's `AgentEntry.status` has 5 ad-hoc strings; a proper FSM with validated transitions eliminates impossible states. | MEDIUM | `models/agent_state.py` AgentEntry (replace), `tmux/session.py` TmuxManager (wrap) |
| State transition validation | Preventing invalid transitions (e.g., STOPPED->RUNNING without going through CREATING) catches bugs that silently corrupt agent state. Erlang supervisors enforce this; without it, the tree can't trust child state. | LOW | New code, no v1 dependency |
| Context management per container | Each container must carry its own config (agent_id, owned dirs, GSD mode, system prompt path). v1 scatters this across agents.yaml parsing, dispatch_cmd, and clone_cmd. Centralizing it in the container means one place to query "what does this agent need?" | MEDIUM | `models/config.py` ProjectConfig/AgentConfig (reuse), `cli/dispatch_cmd.py` (absorb logic) |
| Communication interface (send/receive messages) | Containers need a way to emit events (state changed, health report, task complete) and receive commands (stop, wake, new assignment). v1 uses callbacks on MonitorLoop -- works but couples everything to the monitor. Event-based decoupling is the whole point. | HIGH | `monitor/loop.py` callback pattern (replace with event bus) |

#### Supervision Tree

| Feature | Why Expected | Complexity | Depends On (v1) |
|---------|--------------|------------|------------------|
| Two-level hierarchy: CompanyRoot -> ProjectSupervisor -> agents | Flat supervision can't express "restart all agents in project X when the project supervisor dies" vs "restart just the crashed agent." Hierarchy encodes dependency scope. Without it, restart policies have no structure to operate on. | HIGH | `orchestrator/agent_manager.py` (replace), `monitor/loop.py` (absorb supervision duties) |
| `one_for_one` restart strategy | The default: when one agent crashes, restart only that agent. This is what v1 does today via crash_tracker. Table stakes because most agents are independent (BACKEND doesn't need restart when FRONTEND crashes). | MEDIUM | `orchestrator/crash_tracker.py` (reuse backoff/circuit breaker logic, wrap in strategy) |
| `all_for_one` restart strategy | When agents have tight coupling (e.g., shared state that becomes inconsistent if one agent restarts with stale context), restart all children. Required for the ProjectSupervisor level -- if the PM's context becomes stale, all agents under it may need fresh context injection. | MEDIUM | New code, but restart mechanics reuse crash_tracker |
| `rest_for_one` restart strategy | When agents have ordered dependencies (B depends on A's output), restarting A should also restart B and everything after it. Encodes dependency ordering that v1 handles manually via "check PROJECT-STATUS.md." | MEDIUM | New code; dependency info comes from agents.yaml `consumes` field |
| Max restart intensity (count/period) | Circuit breaker at the supervisor level: if a child crashes N times in M seconds, escalate to parent supervisor instead of looping. v1's crash_tracker has this (3 crashes/hour) but only at the agent level. The tree needs it at every level. | LOW | `orchestrator/crash_tracker.py` MAX_CRASHES_PER_HOUR (generalize) |
| Child specification registry | The supervisor must know HOW to start each child (what type, what config, what restart policy). This replaces v1's implicit knowledge scattered across dispatch_cmd and agents.yaml parsing. | MEDIUM | `models/config.py` AgentConfig (extend with container type + restart policy) |

#### Agent Type Specializations

| Feature | Why Expected | Complexity | Depends On (v1) |
|---------|--------------|------------|------------------|
| GsdAgent: phase-driven lifecycle (IDLE->DISCUSS->PLAN->EXECUTE->UAT->SHIP) | The primary agent type. v1's WorkflowOrchestrator already tracks this state machine externally. Moving it INTO the agent container makes state authoritative (self-reported, not inferred from pane output). | HIGH | `orchestrator/workflow_orchestrator.py` WorkflowStage (absorb into GsdAgent internal FSM) |
| GsdAgent: checkpoint at state transitions | If a GsdAgent crashes mid-execute, it should resume from the last checkpoint, not restart the entire phase. v1 has no checkpointing -- crash = restart from IDLE. | MEDIUM | New code; checkpoint data stored in agent's memory_store |
| ContinuousAgent: scheduled wake/sleep cycles (WAKE->GATHER->ANALYZE->ACT->REPORT->SLEEP) | PM and monitor-like agents don't follow GSD phases. They wake on schedule, do a sweep, report, sleep. Without a distinct type, they'd be shoehorned into GsdAgent with hacks. | MEDIUM | `monitor/loop.py` cycle pattern (reuse as ContinuousAgent behavior) |
| FulltimeAgent (PM): event-driven, alive for project duration | The PM reacts to plan submissions, escalations, health changes. It doesn't follow phases or cycles. It needs to stay alive and process an event queue. Without this type, PM logic stays bolted onto the Discord bot rather than being a first-class container. | HIGH | `strategist/pm.py` (wrap in container), `bot/cogs/plan_review.py` (becomes event source) |
| CompanyAgent (Strategist): cross-project, event-driven | The Strategist spans projects and holds long-lived conversation context. It must survive project restarts. Without CompanyAgent, the Strategist's lifecycle is tangled with individual projects. | MEDIUM | `strategist/conversation.py` (wrap in container) |

#### Health Reporting

| Feature | Why Expected | Complexity | Depends On (v1) |
|---------|--------------|------------|------------------|
| Self-reported HealthReport per container | v1 infers health externally (is the pane alive? is the process stuck?). Self-reporting means the agent says "I'm healthy/degraded/failing" with structured data. Kubernetes proved this pattern: liveness + readiness probes from within the process are more reliable than external guessing. | MEDIUM | `monitor/checks.py` check_liveness/check_stuck (replace with self-report + fallback external check) |
| Health tree aggregation | A ProjectSupervisor's health is the aggregate of its children's health. CompanyRoot's health is the aggregate of all ProjectSupervisors. This gives "docker ps for the whole system" -- the single-glance view that v1 lacks. | MEDIUM | New code; tree traversal aggregation |
| Discord health status push | The owner needs to see health in Discord, not just terminal. v1 has AlertsCog for crashes; health tree extends this to show the full system state on demand (e.g., `!health` command). | LOW | `bot/cogs/alerts.py` (extend), `bot/embeds.py` (new embed format) |

### Differentiators (Competitive Advantage)

Features that go beyond basic supervision and make vCompany's container architecture genuinely better than flat process management.

| Feature | Value Proposition | Complexity | Depends On |
|---------|-------------------|------------|------------|
| Living milestone backlog (PM-managed mutable queue) | v1 uses static ROADMAP.md -- agents consume phases in order, no runtime reordering. A mutable queue lets the PM insert urgent tasks, reorder priorities, and cancel stale work WITHOUT stopping agents. This is the difference between a build system and an autonomous development team. | HIGH | FulltimeAgent (PM) must be operational; needs AgentContainer communication interface |
| Delegation protocol (continuous agents request task spawns) | A ContinuousAgent (e.g., QA monitor) discovers a regression and requests a fix-dispatch through its supervisor. v1 requires the human to dispatch fixes. Delegation makes the system self-healing for code issues, not just process issues. | HIGH | Supervision tree, ContinuousAgent type, child specification registry |
| Decoupled project/agent lifecycles | In v1, killing an agent can leave project state inconsistent (half-written status, stale plan gate). Decoupling means: project state is owned by PM, agents read assignments and write completions via message passing. Agent crash never corrupts project state. | HIGH | FulltimeAgent (PM) as state owner, event-based communication |
| Scheduler (timer-based WAKE for sleeping containers) | ContinuousAgents need to wake on schedule (e.g., every 30 min for monitoring sweeps). Without a scheduler, wake triggers are external cron jobs or manual -- defeating the self-contained tree model. | MEDIUM | CompanyRoot owns the scheduler; ContinuousAgent type must support SLEEPING state |
| Agent memory_store (persistent per-agent key-value) | Agents lose all context on crash/restart. A persistent store lets them resume with memory of past decisions, checkpoints, learned patterns. Differentiator because most agent frameworks treat agents as stateless. | MEDIUM | AgentContainer base provides the interface; implementation is JSON file or SQLite per agent |
| Graceful degradation with partial tree | If one ProjectSupervisor fails, other projects keep running. If one agent fails and circuit breaker opens, remaining agents continue. v1's monitor loop is a single point of failure -- if it crashes, all monitoring stops. The tree distributes supervision so no single failure is total. | MEDIUM | Two-level supervision hierarchy with independent supervisor loops |
| Hot agent replacement | Swap an agent's configuration (new system prompt, different owned dirs) without destroying and recreating the entire container. Enables live reconfiguration during milestones. | MEDIUM | AgentContainer state machine must support CREATING->RUNNING transition with config reload |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem valuable but would add complexity without proportional benefit for vCompany's single-machine, Claude-Code-based context.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Dynamic agent auto-scaling | "Spawn more agents when work piles up" | Claude Code sessions are expensive ($), context-heavy, and compete for machine resources. Auto-scaling on a single machine hits CPU/memory limits fast. The PM should manage agent count explicitly, not an autoscaler. | PM decides agent count at milestone boundaries via living backlog; manual `!dispatch` for ad-hoc agents |
| Agent-to-agent direct messaging | "Let BACKEND tell FRONTEND its API is ready" | Creates hidden coupling. Agent A's behavior now depends on messages from Agent B, making debugging and replay impossible. Erlang explicitly avoids this in supervision trees -- children communicate through the supervisor or shared state. | PROJECT-STATUS.md (existing), supervisor-mediated events, INTERFACES.md contract updates |
| Distributed supervision across machines | "Run agents on multiple machines for more parallelism" | Adds network partitioning, clock sync, distributed consensus -- enormous complexity. vCompany v2 is explicitly single-machine. The supervision tree pattern works locally without any of this overhead. | Keep single-machine constraint; optimize agent count and scheduling instead |
| Generic plugin/extension system for agent types | "Let users define custom agent types" | Four agent types (Gsd, Continuous, Fulltime, Company) cover all known use cases. A plugin system adds API surface to maintain, documentation burden, and backwards compatibility constraints before there's demand. | Hard-code the four types; add new types as needed in future milestones |
| Real-time agent output streaming to Discord | "See what each agent is doing live" | Claude Code sessions produce enormous output. Streaming it to Discord would hit rate limits within seconds and flood channels with unreadable text. v1 learned this -- checkins and standups are the right granularity. | Periodic checkins (existing), `!status` command for on-demand snapshots, health tree for system view |
| Centralized agent state database (SQLite/Postgres) | "Query agent history, build dashboards" | Adds a database dependency, migration tooling, and another failure mode. v1's filesystem state (agents.json, crash_log.json) works. The container model already gives structured state per container. | JSON files per container in a well-known directory; tree aggregation for queries; consider SQLite in v3 if query patterns demand it |
| Preemptive task migration | "Move a task from a stuck agent to a healthy one" | Claude Code sessions carry accumulated context. You can't "move" a session -- you'd have to start fresh, losing all work. The correct response to a stuck agent is restart (with checkpoint) or escalate, not migrate. | Checkpoint-based restart within the same agent container; escalation to PM for reassignment |

## Feature Dependencies

```
AgentContainer base (state machine, context, communication)
    |
    +---> Supervision tree (needs containers to supervise)
    |         |
    |         +---> Restart strategies (operate on supervised containers)
    |         |
    |         +---> Max restart intensity (supervisor-level circuit breaker)
    |         |
    |         +---> Child specification registry (how to create containers)
    |
    +---> Agent type specializations (extend AgentContainer)
    |         |
    |         +---> GsdAgent (needs base state machine + checkpoint)
    |         |         |
    |         |         +---> GsdAgent checkpoint (needs memory_store)
    |         |
    |         +---> ContinuousAgent (needs base + scheduler)
    |         |         |
    |         |         +---> Delegation protocol (ContinuousAgent requests spawns)
    |         |
    |         +---> FulltimeAgent/PM (needs base + event queue)
    |         |         |
    |         |         +---> Living milestone backlog (PM manages the queue)
    |         |         |
    |         |         +---> Decoupled lifecycles (PM owns project state)
    |         |
    |         +---> CompanyAgent/Strategist (needs base + cross-project scope)
    |
    +---> Health reporting (containers self-report)
              |
              +---> Health tree aggregation (supervisors aggregate children)
              |
              +---> Discord health push (display aggregated tree)

Scheduler (timer in CompanyRoot)
    +---> ContinuousAgent WAKE triggers

Agent memory_store
    +---> GsdAgent checkpoint
    +---> ContinuousAgent persistent memory
```

### Dependency Notes

- **AgentContainer base is the foundation.** Nothing else works without it. Build first.
- **Supervision tree requires AgentContainer** because supervisors manage container instances. Can't test restart policies without real containers to restart.
- **Agent types require AgentContainer** because they extend the base class. GsdAgent is highest priority since it replaces the existing workflow.
- **Health reporting requires AgentContainer** because containers self-report. External health checks (v1 pattern) can serve as fallback during migration.
- **Living milestone backlog requires FulltimeAgent (PM)** because the PM manages the queue. Without PM-as-container, the backlog has no owner.
- **Delegation protocol requires ContinuousAgent + supervision tree** because delegation flows through the supervisor. Needs both to be operational.
- **memory_store is a cross-cutting concern** used by GsdAgent (checkpoints) and ContinuousAgent (persistent state). Build early as a simple abstraction; implementations can evolve.
- **Scheduler is independent** but useless without ContinuousAgent to wake. Can be built alongside ContinuousAgent.

## MVP Definition

### Phase 1: Foundation (Build First)

- [ ] AgentContainer base with lifecycle state machine -- without this, nothing else exists
- [ ] State transition validation -- prevents impossible states from day one
- [ ] Context management per container -- centralizes scattered config
- [ ] Agent memory_store (simple JSON key-value) -- needed by checkpoints in Phase 2
- [ ] Child specification registry -- supervisors need to know how to create children

### Phase 2: Core Tree (Build Second)

- [ ] Two-level supervision hierarchy (CompanyRoot -> ProjectSupervisor -> agents) -- the structural backbone
- [ ] `one_for_one` restart strategy -- the default, covers 80% of cases
- [ ] Max restart intensity at supervisor level -- prevents crash loops at tree level
- [ ] GsdAgent type with internal state machine -- replaces WorkflowOrchestrator's external tracking
- [ ] GsdAgent checkpointing -- crash recovery that doesn't lose work
- [ ] Self-reported HealthReport per container -- containers declare their own health

### Phase 3: Specialized Types (Build Third)

- [ ] ContinuousAgent with wake/sleep cycles -- enables monitor-as-agent
- [ ] FulltimeAgent (PM) with event queue -- PM becomes a first-class container
- [ ] Scheduler in CompanyRoot -- drives ContinuousAgent WAKE triggers
- [ ] Health tree aggregation + Discord push -- "docker ps" for the system
- [ ] `all_for_one` and `rest_for_one` restart strategies -- handle coupled agents

### Phase 4: Autonomy (Build Last)

- [ ] Living milestone backlog (PM-managed mutable queue) -- dynamic work management
- [ ] Delegation protocol -- continuous agents request task spawns
- [ ] Decoupled project/agent lifecycles -- crash isolation guarantee
- [ ] CompanyAgent (Strategist) as container -- cross-project lifecycle
- [ ] Communication interface (event bus replacing MonitorLoop callbacks) -- clean decoupling

### Defer to v3+

- [ ] Hot agent replacement -- useful but not critical for initial container architecture
- [ ] Graceful degradation with partial tree -- implicit in the design but explicit testing/hardening can wait
- [ ] Agent performance metrics and historical tracking -- needs query patterns to emerge first

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | Phase |
|---------|------------|---------------------|----------|-------|
| AgentContainer base + state machine | HIGH | MEDIUM | P1 | 1 |
| State transition validation | HIGH | LOW | P1 | 1 |
| Context management per container | HIGH | MEDIUM | P1 | 1 |
| memory_store (JSON key-value) | MEDIUM | LOW | P1 | 1 |
| Child specification registry | HIGH | MEDIUM | P1 | 1 |
| Two-level supervision hierarchy | HIGH | HIGH | P1 | 2 |
| `one_for_one` restart strategy | HIGH | MEDIUM | P1 | 2 |
| Max restart intensity (tree-level) | HIGH | LOW | P1 | 2 |
| GsdAgent with internal FSM | HIGH | HIGH | P1 | 2 |
| GsdAgent checkpointing | MEDIUM | MEDIUM | P1 | 2 |
| Self-reported HealthReport | HIGH | MEDIUM | P1 | 2 |
| ContinuousAgent | MEDIUM | MEDIUM | P2 | 3 |
| FulltimeAgent (PM) | HIGH | HIGH | P2 | 3 |
| Scheduler | MEDIUM | LOW | P2 | 3 |
| Health tree aggregation + Discord | MEDIUM | MEDIUM | P2 | 3 |
| `all_for_one` / `rest_for_one` | LOW | MEDIUM | P2 | 3 |
| Living milestone backlog | HIGH | HIGH | P2 | 4 |
| Delegation protocol | MEDIUM | HIGH | P2 | 4 |
| Decoupled lifecycles | HIGH | HIGH | P2 | 4 |
| CompanyAgent (Strategist) | MEDIUM | MEDIUM | P2 | 4 |
| Event bus (replace callbacks) | MEDIUM | HIGH | P2 | 4 |

## Competitor Feature Analysis

| Feature | Erlang/OTP | Kubernetes | systemd | vCompany v2 Approach |
|---------|------------|------------|---------|---------------------|
| Supervision hierarchy | Native -- supervisors supervise supervisors, unlimited depth | Controllers -> Pods, two-level | Unit dependencies, flat | Two-level: CompanyRoot -> ProjectSupervisor -> agents. Sufficient for single-machine multi-project. |
| Restart strategies | one_for_one, all_for_one, rest_for_one, simple_one_for_one | Always restart (configurable backoff) | Restart=always/on-failure/no | All three OTP strategies. simple_one_for_one not needed (agents are heterogeneous). |
| Health checking | Process links + monitors (crash propagation) | Liveness + readiness probes (HTTP/TCP/exec) | Watchdog timer | Self-reported HealthReport (like K8s probes) + fallback external tmux check (like systemd watchdog) |
| State persistence | ETS/DETS/Mnesia | etcd, ConfigMaps, PersistentVolumes | Journal, state directory | Per-agent JSON memory_store. Simple, file-based, no external dependency. |
| Dynamic children | DynamicSupervisor (simple_one_for_one) | ReplicaSet, HPA | Template units | Child spec registry + `!dispatch` command. PM requests, supervisor creates. |
| Lifecycle states | Started/running/terminated | Pending/Running/Succeeded/Failed/Unknown | inactive/activating/active/deactivating/failed | CREATING/RUNNING/SLEEPING/ERRORED/STOPPED/DESTROYED -- richer than K8s, simpler than systemd |
| Task delegation | gen_server:call/cast between processes | Job/CronJob resources, operator pattern | Socket activation, D-Bus | Delegation protocol: ContinuousAgent -> Supervisor -> spawn GsdAgent. Mediated, not direct. |
| Scheduled execution | timer module, cron-like libraries | CronJob resource | Timer units | Scheduler in CompanyRoot triggers WAKE on sleeping ContinuousAgents |

## Sources

- [Erlang OTP Design Principles](https://www.erlang.org/doc/system/design_principles.html) -- supervision tree fundamentals (HIGH confidence)
- [Adopting Erlang -- Supervision Trees](https://adoptingerlang.org/docs/development/supervision_trees/) -- practical restart strategy guidance (HIGH confidence)
- [Elixir Supervisor documentation](https://hexdocs.pm/elixir/1.12/Supervisor.html) -- strategy definitions and max_restarts (HIGH confidence)
- [Kubernetes Health Probe patterns](https://www.oreilly.com/library/view/kubernetes-patterns-2nd/9781098131678/ch04.html) -- liveness/readiness self-reporting (HIGH confidence)
- [Deloitte: AI Agent Orchestration](https://www.deloitte.com/us/en/insights/industry/technology/technology-media-and-telecom-predictions/2026/ai-agent-orchestration.html) -- supervision and autonomy spectrum (MEDIUM confidence)
- [AI Agent Delegation Patterns](https://fast.io/resources/ai-agent-delegation-patterns/) -- supervisor-worker delegation architectures (MEDIUM confidence)
- [Scheduling Agent Supervisor Pattern](https://www.geeksforgeeks.org/system-design/scheduling-agent-supervisor-pattern-system-design/) -- scheduler + agent + supervisor coordination (MEDIUM confidence)
- [Learn You Some Erlang: Supervisors](https://learnyousomeerlang.com/supervisors) -- restart intensity and escalation (HIGH confidence)

---
*Feature research for: Agent container architecture (vCompany v2.0)*
*Researched: 2026-03-27*
