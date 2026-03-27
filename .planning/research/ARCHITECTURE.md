# Architecture: Agent Container & Supervision Tree Integration

**Domain:** Autonomous multi-agent orchestration system (v2 container architecture)
**Researched:** 2026-03-27
**Confidence:** HIGH

## Recommended Architecture

### System Overview: v1 to v2 Transformation

The v2 architecture introduces a **supervision tree** between the Discord bot and the raw tmux agent layer. Today, `VcoBot.on_ready()` directly wires `AgentManager`, `MonitorLoop`, `CrashTracker`, and `WorkflowOrchestrator` as flat peers. In v2, these collapse into a hierarchical container tree where each agent is a lifecycle unit managed by its parent supervisor.

```
v1 (current):
  VcoBot
    -> AgentManager (dispatch/kill tmux panes)
    -> MonitorLoop (60s external watchdog)
    -> CrashTracker (backoff/circuit breaker)
    -> WorkflowOrchestrator (per-agent state machine)

v2 (target):
  VcoBot
    -> CompanyRoot (top-level supervisor)
        -> CompanyAgent (Strategist - company-scoped, event-driven)
        -> Scheduler (timer service for wake/sleep cycles)
        -> ProjectSupervisor("my-project")
            -> FulltimeAgent (PM - project-scoped, event-driven)
            -> GsdAgent("BACKEND") (phase-driven lifecycle)
            -> GsdAgent("FRONTEND") (phase-driven lifecycle)
            -> ContinuousAgent("QA") (scheduled wake/sleep)
```

### Component Boundaries

| Component | Responsibility | New/Modified | Communicates With |
|-----------|---------------|--------------|-------------------|
| **AgentContainer** (base) | Lifecycle state machine, health reporting, context management, communication interface | NEW (`src/vcompany/containers/base.py`) | Supervisor (parent), TmuxManager (process), HealthTree |
| **GsdAgent** | Phase-driven lifecycle (IDLE->DISCUSS->PLAN->EXECUTE->VERIFY->SHIP), checkpoints at each transition | NEW (`src/vcompany/containers/gsd_agent.py`) | WorkflowOrchestrator (absorbs), AgentManager (absorbs tmux dispatch) |
| **ContinuousAgent** | Scheduled wake/sleep cycles (WAKE->GATHER->ANALYZE->ACT->REPORT->SLEEP), persistent memory | NEW (`src/vcompany/containers/continuous_agent.py`) | Scheduler, DelegationProtocol, ProjectSupervisor |
| **FulltimeAgent** | Event-driven, alive for project duration, reacts to state transitions and escalations | NEW (`src/vcompany/containers/fulltime_agent.py`) | ProjectSupervisor (events), PM subsystem |
| **CompanyAgent** | Event-driven, alive for company duration, cross-project state | NEW (`src/vcompany/containers/company_agent.py`) | CompanyRoot (events), Strategist subsystem |
| **Supervisor** (base) | Manages child containers, restart policies, health aggregation | NEW (`src/vcompany/supervision/supervisor.py`) | Children (AgentContainers), Parent supervisor |
| **CompanyRoot** | Top-level supervisor, owns Scheduler + ProjectSupervisors + CompanyAgents | NEW (`src/vcompany/supervision/company_root.py`) | VcoBot (startup/shutdown), ProjectSupervisor, Scheduler |
| **ProjectSupervisor** | Per-project supervisor, owns PM + dev agents, restart policies | NEW (`src/vcompany/supervision/project_supervisor.py`) | CompanyRoot (parent), child agents |
| **Scheduler** | Timer within CompanyRoot, triggers WAKE on sleeping containers | NEW (`src/vcompany/supervision/scheduler.py`) | CompanyRoot, ContinuousAgent containers |
| **HealthTree** | Aggregates self-reported HealthReport per container, renders tree | NEW (`src/vcompany/health/tree.py`) | All containers (report), Discord (display) |
| **HealthReport** | Per-container health snapshot (state, uptime, last checkpoint, error) | NEW (`src/vcompany/health/models.py`) | HealthTree |
| **MilestoneBacklog** | PM-managed mutable queue (append, insert_urgent, reorder, cancel) | NEW (`src/vcompany/coordination/backlog.py`) | FulltimeAgent (PM), ProjectSupervisor |
| **DelegationProtocol** | Continuous agents request task spawns through supervisor | NEW (`src/vcompany/coordination/delegation.py`) | ContinuousAgent, ProjectSupervisor |
| **AgentMemoryStore** | Persistent per-agent key-value store, checkpoints at state transitions | NEW (`src/vcompany/containers/memory_store.py`) | All container types |
| **AgentManager** | Retains tmux pane dispatch/kill, but called BY containers not directly | MODIFIED | AgentContainer (delegated tmux ops) |
| **MonitorLoop** | Simplified to health polling from tree (no longer does per-agent checks) | MODIFIED (eventually replaced) | HealthTree, CompanyRoot |
| **CrashTracker** | Absorbed into Supervisor restart logic | MODIFIED (absorbed) | Supervisor base class |
| **WorkflowOrchestrator** | Absorbed into GsdAgent internal state machine | MODIFIED (absorbed) | GsdAgent |
| **VcoBot** | Wires CompanyRoot instead of flat components, new HealthCog | MODIFIED | CompanyRoot, HealthTree |
| **ProjectConfig/AgentConfig** | Extended with `agent_type` field, schedule config | MODIFIED | Container factory |

## Data Flow: Container Lifecycle

### Container State Machine (base)

All containers share a common lifecycle state machine:

```
CREATING -> RUNNING -> SLEEPING -> ERRORED -> STOPPED -> DESTROYED
    |           |          |          |          |
    |           +-> SLEEPING (voluntary)        |
    |           +-> ERRORED (crash/failure)     |
    |           +-> STOPPED (supervisor request)|
    +------------------------------------------+
              (DESTROYED = terminal, GC eligible)
```

Transitions are **events**, not polling. The container calls `self._transition(new_state)` which:
1. Persists checkpoint to `memory_store`
2. Emits event to parent supervisor
3. Updates health report

### GsdAgent Internal State Machine

Nested within the RUNNING state of the base container:

```
IDLE -> DISCUSS -> PLAN -> EXECUTE -> VERIFY -> SHIP -> IDLE (next phase)
                                                   |
                                                   +-> PHASE_COMPLETE (all done)
```

This absorbs `WorkflowOrchestrator.WorkflowStage` directly. The GsdAgent owns its own state transitions rather than an external orchestrator driving them. The key difference: **the agent is the state machine**, not an external object tracking agent state.

### Health Reporting Flow

```
Each Container:
  - self._health = HealthReport(
      container_id, container_type, state,
      uptime, last_checkpoint, last_error,
      children_summary (if supervisor)
    )
  - Reports to parent supervisor on every state change
  - Parent aggregates into tree

CompanyRoot.health_tree() -> nested dict:
  {
    "company": { state: RUNNING, children: [
      { "strategist": { state: RUNNING, type: "company_agent" } },
      { "scheduler": { state: RUNNING } },
      { "project:my-project": { state: RUNNING, children: [
        { "pm": { state: RUNNING, type: "fulltime_agent" } },
        { "BACKEND": { state: RUNNING, type: "gsd_agent", gsd_stage: "EXECUTE" } },
        { "FRONTEND": { state: SLEEPING, type: "gsd_agent", gsd_stage: "IDLE" } }
      ]}}
    ]}
  }

Discord: !health -> renders as tree (like `docker ps`)
```

### Supervision and Restart Flow

```
Agent crashes (tmux pane dies / process error)
  -> Container catches exception, transitions to ERRORED
  -> Container emits event to parent Supervisor
  -> Supervisor consults restart policy:
      one_for_one:   restart only crashed child
      all_for_one:   restart ALL children (coordinated reset)
      rest_for_one:  restart crashed + all started after it
  -> Supervisor checks crash history (absorbed CrashTracker logic):
      backoff_schedule: [30s, 120s, 600s]
      max_crashes_per_hour: 3
      If circuit open -> transition to STOPPED, alert Discord
      Else -> wait backoff delay, restart child
  -> On restart: Container re-enters CREATING -> RUNNING
      GsdAgent: recovers from last checkpoint (memory_store)
      ContinuousAgent: resumes at last cycle phase
```

### Delegation Protocol Flow

```
ContinuousAgent("QA") during ACT phase:
  -> Identifies work item requiring a GSD agent
  -> Calls self.delegate(TaskSpec(type="gsd_quick", target_agent="BACKEND", ...))
  -> Message goes to parent ProjectSupervisor
  -> ProjectSupervisor validates policy (is delegation allowed? is target available?)
  -> ProjectSupervisor routes to target agent:
      If GsdAgent is IDLE -> inject task, transition to appropriate stage
      If GsdAgent is busy -> queue task in MilestoneBacklog
  -> Result flows back through supervisor to requesting agent
```

## Integration Points with Existing Code

### What Gets Absorbed (code moves INTO new modules)

| Existing Module | Absorbed By | What Moves |
|----------------|-------------|------------|
| `orchestrator/workflow_orchestrator.py` | `containers/gsd_agent.py` | `WorkflowStage` enum, `AgentWorkflowState`, stage transition logic, gate handling |
| `orchestrator/crash_tracker.py` | `supervision/supervisor.py` | `CrashClassification`, backoff schedule, circuit breaker logic, crash recording |
| `monitor/checks.py` (liveness) | `containers/base.py` | Self-reported liveness replaces external polling |
| `monitor/checks.py` (stuck) | `containers/gsd_agent.py` | Stuck detection becomes internal timeout on state transitions |
| `models/agent_state.py` (AgentEntry) | `health/models.py` | Runtime state moves to HealthReport; AgentEntry becomes thinner |
| `models/monitor_state.py` (AgentMonitorState) | `health/models.py` | Per-agent state replaced by container health reports |

### What Gets Modified (stays in place, API changes)

| Existing Module | Change | Why |
|----------------|--------|-----|
| `orchestrator/agent_manager.py` | Becomes internal to containers (called by `AgentContainer._spawn_tmux()`) | Containers own their own tmux pane lifecycle; AgentManager becomes a utility, not an orchestrator |
| `monitor/loop.py` | Simplified: polls HealthTree instead of checking each agent individually | Health is self-reported; monitor becomes a thin bridge to Discord alerts |
| `bot/client.py` | `on_ready()` creates CompanyRoot instead of flat wiring; new HealthCog | Entry point changes from flat to hierarchical |
| `bot/cogs/workflow_orchestrator_cog.py` | Routes commands to containers via CompanyRoot, not WorkflowOrchestrator | Cog becomes a thin Discord command layer over container operations |
| `bot/cogs/alerts.py` | Receives events from HealthTree instead of MonitorLoop callbacks | Event source changes |
| `models/config.py` | Add `agent_type: Literal["gsd", "continuous", "fulltime", "company"]` to AgentConfig | Container factory needs to know which type to create |
| `tmux/session.py` | No changes | Stays as-is; containers call TmuxManager through AgentManager |

### What Stays Unchanged

| Module | Why |
|--------|-----|
| `bot/cogs/commands.py` | User-facing commands (!dispatch, !status) become thin wrappers; internal routing changes but command surface stays |
| `bot/cogs/plan_review.py` | Plan gate is orthogonal to container architecture; still detects PLAN.md, still routes to Discord |
| `bot/cogs/strategist.py` | Strategist conversation logic is unchanged; it just runs inside a CompanyAgent container |
| `bot/cogs/question_handler.py` | AskUserQuestion hook is agent-side, not orchestrator-side |
| `coordination/interfaces.py` | Contract system is unchanged |
| `coordination/sync_context.py` | Context distribution is unchanged |
| `git/ops.py` | Git operations are unchanged |
| `integration/pipeline.py` | Integration is post-agent, not affected by container refactor |
| `strategist/` (all) | PM/Strategist logic moves INTO FulltimeAgent/CompanyAgent containers but the logic itself is reused |

## Patterns to Follow

### Pattern 1: Container as Actor

Each container is an actor with its own event loop, state, and message queue. Communication is through events, not shared mutable state.

**What:** Containers process events sequentially from their inbox. State transitions are atomic. Parent supervisors observe via event subscription.

**When:** All container-to-container communication.

**Example:**
```python
class AgentContainer(ABC):
    """Base container with lifecycle state machine and event-driven communication."""

    def __init__(self, container_id: str, parent: "Supervisor | None" = None):
        self._id = container_id
        self._parent = parent
        self._state = ContainerState.CREATING
        self._health = HealthReport(container_id=container_id)
        self._memory = AgentMemoryStore(container_id)
        self._inbox: asyncio.Queue[ContainerEvent] = asyncio.Queue()

    async def run(self) -> None:
        """Main event loop. Subclasses override _handle_event."""
        self._transition(ContainerState.RUNNING)
        try:
            await self._on_start()
            while self._state not in (ContainerState.STOPPED, ContainerState.DESTROYED):
                event = await self._inbox.get()
                await self._handle_event(event)
        except Exception as exc:
            self._transition(ContainerState.ERRORED)
            self._health.last_error = str(exc)
            if self._parent:
                await self._parent.on_child_error(self, exc)

    def _transition(self, new_state: ContainerState) -> None:
        old_state = self._state
        self._state = new_state
        self._health.state = new_state
        self._memory.checkpoint(f"state:{old_state.value}->{new_state.value}")
        if self._parent:
            self._parent.notify_state_change(self._id, old_state, new_state)
```

### Pattern 2: Erlang-Style Supervisor with Python asyncio

The supervisor manages child lifecycle using asyncio tasks. Each child runs as a coroutine task. The supervisor catches task exceptions and applies restart policy.

**What:** Supervisor creates asyncio.Task per child, monitors with `asyncio.wait`, applies restart policy on failure.

**When:** CompanyRoot, ProjectSupervisor.

**Example:**
```python
class Supervisor(AgentContainer):
    """Manages child containers with restart policies."""

    def __init__(self, container_id: str, policy: RestartPolicy, **kwargs):
        super().__init__(container_id, **kwargs)
        self._policy = policy
        self._children: dict[str, AgentContainer] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._crash_history: dict[str, list[datetime]] = {}

    async def start_child(self, child: AgentContainer) -> None:
        self._children[child._id] = child
        child._parent = self
        task = asyncio.create_task(child.run(), name=f"container-{child._id}")
        self._tasks[child._id] = task
        task.add_done_callback(lambda t: self._on_task_done(child._id, t))

    def _on_task_done(self, child_id: str, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            asyncio.create_task(self._handle_child_failure(child_id, exc))

    async def _handle_child_failure(self, child_id: str, exc: Exception) -> None:
        # Record crash, check circuit breaker
        now = datetime.now(timezone.utc)
        history = self._crash_history.setdefault(child_id, [])
        history.append(now)
        # Prune old entries (sliding 60m window)
        cutoff = now - timedelta(minutes=60)
        history[:] = [t for t in history if t >= cutoff]

        if len(history) > MAX_CRASHES_PER_HOUR:
            # Circuit open
            self._children[child_id]._transition(ContainerState.STOPPED)
            await self._emit_alert(child_id, "circuit_open")
            return

        # Apply restart policy
        if self._policy == RestartPolicy.ONE_FOR_ONE:
            delay = BACKOFF_SCHEDULE[min(len(history) - 1, len(BACKOFF_SCHEDULE) - 1)]
            await asyncio.sleep(delay)
            await self.start_child(self._children[child_id])

        elif self._policy == RestartPolicy.ALL_FOR_ONE:
            for cid in list(self._tasks):
                self._tasks[cid].cancel()
            await asyncio.sleep(BACKOFF_SCHEDULE[0])
            for child in self._children.values():
                await self.start_child(child)
```

### Pattern 3: Self-Reported Health (Not External Polling)

Containers report their own health rather than an external monitor polling them. This inverts the v1 model where MonitorLoop externally checks liveness, stuck, and phase status.

**What:** Each container maintains a `HealthReport` object updated on every state transition. The HealthTree aggregates these reports passively.

**When:** All health/status reporting.

**Why better than v1:** External polling (MonitorLoop reading tmux panes) is fragile, racey, and has 60s latency. Self-reporting is instant and authoritative.

**Coexistence during migration:** MonitorLoop continues running as a safety net during the transition. It reads from HealthTree when available, falls back to direct tmux checks when containers haven't been migrated yet.

## Anti-Patterns to Avoid

### Anti-Pattern 1: God Supervisor
**What:** CompanyRoot directly managing all agents across all projects.
**Why bad:** Violates supervision hierarchy. If CompanyRoot applies `all_for_one`, restarting a crashed BACKEND agent restarts the Strategist and all other projects.
**Instead:** Two-level hierarchy: CompanyRoot -> ProjectSupervisor -> agents. Restart policies are per-level.

### Anti-Pattern 2: Shared Mutable State Between Containers
**What:** Containers reading/writing the same `agents.json` or sharing in-memory dicts.
**Why bad:** Race conditions, state corruption on crash. This is exactly what v1's `AgentsRegistry` does.
**Instead:** Each container owns its state via `AgentMemoryStore`. The HealthTree reads immutable snapshots.

### Anti-Pattern 3: Premature Deletion of v1 Modules
**What:** Deleting `MonitorLoop`, `CrashTracker`, `WorkflowOrchestrator` before v2 equivalents are proven.
**Why bad:** v2 containers are complex; bugs during transition could leave the system with no supervision.
**Instead:** v1 and v2 coexist during migration. MonitorLoop runs alongside the supervision tree as a safety net. Delete v1 modules only after v2 equivalents pass integration tests.

### Anti-Pattern 4: Blocking Operations in Container Event Loop
**What:** Calling `time.sleep()`, synchronous git operations, or synchronous tmux operations inside container `run()` coroutines.
**Why bad:** Blocks the asyncio event loop, prevents other containers from processing events.
**Instead:** Use `asyncio.sleep()`, `asyncio.to_thread()` for blocking operations (same pattern already used in MonitorLoop._check_agent).

## Suggested New Module Structure

```
src/vcompany/
  containers/
    __init__.py
    base.py              # AgentContainer base class, ContainerState enum
    gsd_agent.py         # GsdAgent: phase-driven lifecycle
    continuous_agent.py  # ContinuousAgent: scheduled cycles
    fulltime_agent.py    # FulltimeAgent: event-driven, project-lifetime
    company_agent.py     # CompanyAgent: event-driven, company-lifetime
    memory_store.py      # AgentMemoryStore: per-agent persistent KV
    events.py            # ContainerEvent types (StateChange, TaskRequest, etc.)
  supervision/
    __init__.py
    supervisor.py        # Supervisor base class, RestartPolicy enum
    company_root.py      # CompanyRoot: top-level supervisor
    project_supervisor.py # ProjectSupervisor: per-project supervisor
    scheduler.py         # Scheduler: timer for wake/sleep cycles
  health/
    __init__.py
    models.py            # HealthReport, HealthSnapshot
    tree.py              # HealthTree: aggregation and rendering
  coordination/
    backlog.py           # MilestoneBacklog: PM-managed mutable queue (NEW)
    delegation.py        # DelegationProtocol: task spawn requests (NEW)
    # existing files unchanged:
    interactions.py
    interfaces.py
    sync_context.py
```

## Suggested Build Order

The build order follows dependency chains. Each phase builds on the previous and can be tested independently.

### Phase 1: Container Foundation
**Build:** `containers/base.py`, `containers/events.py`, `containers/memory_store.py`, `health/models.py`
**Why first:** Everything else depends on the base container abstraction, event types, and health model. These have ZERO dependencies on existing v1 code.
**Test:** Unit tests for state machine transitions, event emission, memory store persistence, health report generation.
**Integration risk:** None -- pure new code.

### Phase 2: Supervisor Foundation
**Build:** `supervision/supervisor.py` (with restart policies, crash tracking)
**Why second:** Supervisors manage containers. Must have containers first. Absorbs `crash_tracker.py` logic.
**Test:** Unit tests for restart policies (one_for_one, all_for_one, rest_for_one), backoff schedule, circuit breaker.
**Integration risk:** Low -- CrashTracker logic is well-understood from v1.

### Phase 3: GsdAgent Type
**Build:** `containers/gsd_agent.py`
**Why third:** Most agents are GSD agents. This absorbs `WorkflowOrchestrator` stage machine and delegates to `AgentManager` for tmux operations.
**Test:** Unit tests for internal stage transitions. Integration test: GsdAgent managing a real tmux pane through IDLE->DISCUSS->PLAN->EXECUTE->VERIFY->SHIP.
**Integration risk:** MEDIUM -- must correctly absorb WorkflowOrchestrator behavior. This is the riskiest phase because it replaces the most complex v1 logic.
**Modified v1:** `AgentManager` API changes: no longer the entry point, becomes a utility called by GsdAgent.

### Phase 4: Health Tree
**Build:** `health/tree.py`, new `bot/cogs/health.py`
**Why fourth:** With containers and supervisors running, health reporting can be wired end-to-end. Provides the "docker ps" view.
**Test:** Integration test: multi-container tree renders correctly. Discord command test: !health outputs formatted tree.
**Integration risk:** Low -- additive feature.

### Phase 5: CompanyRoot + ProjectSupervisor
**Build:** `supervision/company_root.py`, `supervision/project_supervisor.py`
**Why fifth:** The concrete supervisor hierarchy. Wires containers into the tree structure. Modifies `VcoBot.on_ready()` to create CompanyRoot instead of flat wiring.
**Test:** Integration test: CompanyRoot starts ProjectSupervisor starts GsdAgents. Crash one agent, verify restart policy fires.
**Integration risk:** HIGH -- this is where v1 wiring in `bot/client.py` gets replaced. Must coexist with v1 MonitorLoop during transition.
**Modified v1:** `bot/client.py` on_ready(), CLI dispatch commands route through CompanyRoot.

### Phase 6: Remaining Agent Types
**Build:** `containers/fulltime_agent.py`, `containers/company_agent.py`, `containers/continuous_agent.py`
**Why sixth:** Specialized agent types depend on all foundation work. PM (FulltimeAgent) and Strategist (CompanyAgent) wrap existing strategist/ module logic. ContinuousAgent is net-new behavior.
**Test:** FulltimeAgent responds to events. CompanyAgent wraps Strategist conversation. ContinuousAgent runs wake/sleep cycle.
**Integration risk:** MEDIUM for ContinuousAgent (new behavior), LOW for Fulltime/Company (wrapping existing).

### Phase 7: Scheduler + Delegation + Backlog
**Build:** `supervision/scheduler.py`, `coordination/delegation.py`, `coordination/backlog.py`
**Why seventh:** These are coordination features that require all agent types to be working. Scheduler triggers ContinuousAgent wake. Delegation routes tasks through supervisor. Backlog manages PM's work queue.
**Test:** Scheduler triggers wake on schedule. Delegation request flows through supervisor to target agent. Backlog operations (append, reorder, cancel).
**Integration risk:** MEDIUM -- delegation protocol is new inter-container communication.

### Phase 8: Migration Cleanup
**Build:** Remove v1 modules that have been fully absorbed.
**What to delete:** `orchestrator/workflow_orchestrator.py` (absorbed by GsdAgent), `orchestrator/crash_tracker.py` (absorbed by Supervisor). Simplify `monitor/loop.py` to a thin HealthTree poller or remove entirely if HealthTree + Discord push replaces it.
**Test:** Full regression suite. All existing Discord commands work. All existing CLI commands work.
**Integration risk:** LOW if previous phases have integration tests. HIGH if they don't.

## Key Architectural Decisions

### Decision 1: Containers as asyncio coroutines, not OS processes
**Why:** Agents already run as tmux panes (external processes). The container is a MANAGEMENT abstraction, not a process isolation boundary. Running containers as asyncio tasks within the VcoBot process gives:
- Zero-cost event passing (no IPC)
- Shared access to discord.py client
- Simple lifecycle (cancel task = stop container)
- No process management overhead

### Decision 2: Event-driven, not polling
**Why:** v1's 60s MonitorLoop poll cycle means up to 60s latency on crash detection. Container self-reporting means instant notification on state change. The Supervisor sees a child task complete (with exception) immediately via asyncio.Task callback.

### Decision 3: Two-level supervision hierarchy (Company -> Project -> Agent)
**Why:** Maps to natural scoping. CompanyRoot restart policy affects cross-project concerns (Strategist). ProjectSupervisor restart policy affects within-project concerns (dev agents). A crashed BACKEND agent should not restart the Strategist.

### Decision 4: agents.yaml extended with agent_type, not separate config
**Why:** Keep single config source. Add `agent_type: gsd | continuous | fulltime | company` with sensible default (`gsd`). ContinuousAgent adds `schedule` field. This is backward-compatible -- existing configs without `agent_type` default to `gsd`.

### Decision 5: Coexistence period with v1 MonitorLoop
**Why:** The MonitorLoop is battle-tested. The supervision tree is new. Running both during migration catches bugs in the new system. MonitorLoop becomes the "safety net" that catches anything the supervision tree misses. Delete only after confidence is established.

## Scalability Considerations

| Concern | Current (v1) | With Containers (v2) | At Scale (10+ agents) |
|---------|-------------|---------------------|----------------------|
| Crash detection latency | 60s (poll cycle) | Instant (task callback) | Instant (same mechanism) |
| State recovery | External (WorkflowOrchestrator reads STATE.md) | Internal (memory_store checkpoint) | Same -- per-agent, no contention |
| Health visibility | CLI reads agents.json | HealthTree renders full tree | Tree depth is 3 levels max, O(n) render |
| Restart coordination | Manual (relaunch command) | Automatic (supervisor policy) | Per-project policies, no cross-project blast radius |
| Adding agent types | Requires new orchestrator logic | Implement AgentContainer subclass | Plugin-style extensibility |
| Multiple projects | Not supported | CompanyRoot -> multiple ProjectSupervisors | Natural hierarchy, no code changes |

## Sources

- [Erlang OTP Supervision Design Principles](https://www.erlang.org/doc/system/design_principles.html) -- Restart strategies (one_for_one, all_for_one, rest_for_one) (HIGH confidence)
- [Erlang OTP Supervisor Behaviour](https://learnyousomeerlang.com/building-applications-with-otp) -- Implementation patterns for supervision trees (HIGH confidence)
- Existing codebase analysis: `src/vcompany/orchestrator/`, `src/vcompany/monitor/`, `src/vcompany/bot/client.py` -- Current architecture baseline (HIGH confidence)
- `VCO-ARCHITECTURE.md` -- Authoritative v1 design reference (HIGH confidence)
- `.planning/PROJECT.md` -- v2 milestone requirements and active features list (HIGH confidence)
- Python asyncio Task management -- stdlib, well-documented (HIGH confidence)
- Erlang-style supervision in Python is custom-built (no mature library exists) -- pattern translation from OTP principles is the standard approach (MEDIUM confidence)
