# Phase 4: Remaining Agent Types and Scheduler - Research

**Researched:** 2026-03-28
**Domain:** Agent container subtypes, compound FSM design, async scheduling
**Confidence:** HIGH

## Summary

Phase 4 builds three new AgentContainer subclasses (ContinuousAgent, FulltimeAgent, CompanyAgent) following the established GsdAgent pattern, plus a scheduler in CompanyRoot that wakes sleeping ContinuousAgents on schedule. The existing codebase provides a very clear blueprint: GsdAgent demonstrates how to subclass AgentContainer, override the lifecycle with a compound FSM, checkpoint state via memory_store, and restore on crash recovery.

The primary technical challenges are: (1) designing a ContinuousAgent lifecycle FSM with WAKE/GATHER/ANALYZE/ACT/REPORT/SLEEP cycle states as a compound state machine, (2) making FulltimeAgent and CompanyAgent event-driven (they react to events rather than following a fixed cycle), (3) building a persistent scheduler that survives bot restarts, and (4) resolving the supervisor's container factory problem -- `Supervisor._start_child()` currently hardcodes `AgentContainer.from_spec()`, so it cannot create subclass instances.

**Primary recommendation:** Follow the GsdAgent/GsdLifecycle pattern exactly for each new agent type. Use a container factory registry (agent_type string -> class) to let the supervisor create the correct subclass. The scheduler should be a simple asyncio task in CompanyRoot that checks wake times from a persistent store (YAML or MemoryStore) on a 60-second loop.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all choices at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key technical anchors from requirements:
- ContinuousAgent: scheduled wake/sleep cycles (WAKE->GATHER->ANALYZE->ACT->REPORT->SLEEP), persists state via memory_store (TYPE-03)
- FulltimeAgent (PM): event-driven, reacts to state transitions, health changes, escalations, briefings, lives for project duration (TYPE-04)
- CompanyAgent (Strategist): event-driven, survives project restarts, holds cross-project state (TYPE-05)
- Scheduler in CompanyRoot triggers WAKE on sleeping ContinuousAgents per configured schedule (AUTO-06)

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TYPE-03 | ContinuousAgent with scheduled wake/sleep cycles and persistent memory_store | ContinuousLifecycle compound FSM following GsdLifecycle pattern; checkpoint/restore via memory_store identical to GsdAgent |
| TYPE-04 | FulltimeAgent (PM) event-driven, reacts to state transitions, health changes, escalations, briefings | EventDrivenLifecycle with compound running state containing LISTENING/PROCESSING sub-states; event queue via asyncio.Queue |
| TYPE-05 | CompanyAgent (Strategist) event-driven, survives project restarts, holds cross-project state | Same EventDrivenLifecycle as FulltimeAgent; cross-project state in memory_store KV; parent_id=None (owned by CompanyRoot, not ProjectSupervisor) |
| AUTO-06 | Scheduler in CompanyRoot triggers WAKE on sleeping ContinuousAgents per configured schedule | Scheduler asyncio task in CompanyRoot with persistent schedule store; 60s check loop; survives restarts via MemoryStore or YAML |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.12+, asyncio-native
- python-statemachine for FSMs (already used for ContainerLifecycle, GsdLifecycle)
- Pydantic models for data validation
- aiosqlite for MemoryStore persistence (per-agent SQLite)
- No database beyond per-agent SQLite files
- No agent-to-agent direct messaging -- communicate through Discord and supervision tree
- Agent isolation -- agents never share working directories
- Use subprocess for git, not GitPython
- httpx for HTTP (not requests)

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-statemachine | 3.0.0 | Compound FSMs for agent lifecycles | Already used for ContainerLifecycle and GsdLifecycle; compound states and HistoryState are proven patterns |
| aiosqlite | 0.21.x | Async SQLite for MemoryStore | Already used by all containers for checkpoint persistence |
| pydantic | 2.11.x | Data models for checkpoints, events, schedule config | Already used throughout (ContainerContext, ChildSpec, CheckpointData) |
| asyncio (stdlib) | N/A | Event loops, tasks, queues for scheduler and event handling | Already used for supervisor monitoring, locks, etc. |

### No new dependencies required
This phase uses only existing project dependencies. No new packages need to be installed.

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/agent/
    __init__.py
    gsd_agent.py              # Existing (TYPE-01/02)
    gsd_lifecycle.py           # Existing
    gsd_phases.py              # Existing
    continuous_agent.py        # NEW (TYPE-03)
    continuous_lifecycle.py    # NEW
    continuous_phases.py       # NEW (CyclePhase enum, CycleCheckpointData)
    fulltime_agent.py          # NEW (TYPE-04)
    fulltime_lifecycle.py      # NEW
    company_agent.py           # NEW (TYPE-05)
src/vcompany/supervisor/
    company_root.py            # MODIFIED (add scheduler)
src/vcompany/container/
    factory.py                 # NEW (container type registry)
```

### Pattern 1: Agent Type Subclass (follow GsdAgent exactly)

**What:** Each new agent type subclasses AgentContainer, replaces `_lifecycle` with a custom compound FSM, and uses memory_store for checkpointing.

**When to use:** Every new agent type.

**Example (from existing GsdAgent):**
```python
class ContinuousAgent(AgentContainer):
    def __init__(self, context, data_dir, comm_port=None, on_state_change=None):
        super().__init__(context, data_dir, comm_port, on_state_change)
        # Override parent's ContainerLifecycle with ContinuousLifecycle
        self._lifecycle = ContinuousLifecycle(model=self, state_field="_fsm_state")
        self._checkpoint_lock = asyncio.Lock()

    @property
    def state(self) -> str:
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            return str(list(val)[0])
        return str(val)

    @property
    def inner_state(self) -> str | None:
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            items = list(val)
            if len(items) >= 2:
                return str(items[1])
        return None
```

### Pattern 2: Compound FSM with HistoryState (follow GsdLifecycle exactly)

**What:** Define lifecycle as a StateMachine with `State.Compound` for the running state, containing agent-type-specific sub-states. Use `HistoryState` for sleep/wake preservation.

**Example (ContinuousLifecycle):**
```python
class ContinuousLifecycle(StateMachine):
    creating = State(initial=True)

    class running(State.Compound):
        wake = State(initial=True)   # Just woken, initializing
        gather = State()              # Collecting data/context
        analyze = State()             # Processing gathered data
        act = State()                 # Taking actions
        report = State()              # Reporting results
        sleeping_prep = State()       # Preparing to sleep (checkpoint)
        h = HistoryState()

        # Cycle transitions
        start_gather = wake.to(gather)
        start_analyze = gather.to(analyze)
        start_act = analyze.to(act)
        start_report = act.to(report)
        start_sleep_prep = report.to(sleeping_prep)
        # Restart cycle
        restart_cycle = sleeping_prep.to(wake) | wake.to(wake)

    sleeping = State()
    errored = State()
    stopped = State()
    destroyed = State(final=True)

    # Outer transitions (same pattern as GsdLifecycle)
    start = creating.to(running)
    sleep = running.to(sleeping)
    wake = sleeping.to(running.h)
    error = creating.to(errored) | running.to(errored) | sleeping.to(errored)
    recover = errored.to(running.h)
    stop = running.to(stopped) | sleeping.to(stopped) | errored.to(stopped)
    destroy = stopped.to(destroyed) | errored.to(destroyed)
```

### Pattern 3: Event-Driven Agent (FulltimeAgent, CompanyAgent)

**What:** Event-driven agents use an asyncio.Queue to receive events and process them in a loop. The compound running state has LISTENING and PROCESSING sub-states.

**Example:**
```python
class EventDrivenLifecycle(StateMachine):
    creating = State(initial=True)

    class running(State.Compound):
        listening = State(initial=True)   # Waiting for events
        processing = State()               # Handling an event
        h = HistoryState()

        start_processing = listening.to(processing)
        done_processing = processing.to(listening)

    sleeping = State()
    errored = State()
    stopped = State()
    destroyed = State(final=True)

    start = creating.to(running)
    sleep = running.to(sleeping)
    wake = sleeping.to(running.h)
    error = creating.to(errored) | running.to(errored) | sleeping.to(errored)
    recover = errored.to(running.h)
    stop = running.to(stopped) | sleeping.to(stopped) | errored.to(stopped)
    destroy = stopped.to(destroyed) | errored.to(destroyed)
```

FulltimeAgent and CompanyAgent share the same EventDrivenLifecycle FSM. They differ in:
- **FulltimeAgent:** Scoped to a project (has project_id), receives project-level events
- **CompanyAgent:** Scoped to company (no project_id, or special company-level project_id), survives project restarts, holds cross-project state

### Pattern 4: Container Factory for Supervisor

**What:** The Supervisor currently hardcodes `AgentContainer.from_spec()` in `_start_child()`. A factory registry maps `agent_type` strings to container classes so the supervisor creates the correct subclass.

**Critical finding:** `Supervisor._start_child()` line 145 does:
```python
container = AgentContainer.from_spec(spec, ...)
```
This always creates a base `AgentContainer`, never a `GsdAgent` or other subclass. This must be fixed.

**Solution:**
```python
# src/vcompany/container/factory.py
from vcompany.container.container import AgentContainer

_REGISTRY: dict[str, type[AgentContainer]] = {}

def register_agent_type(agent_type: str, cls: type[AgentContainer]) -> None:
    _REGISTRY[agent_type] = cls

def create_container(spec, data_dir, comm_port=None, on_state_change=None):
    cls = _REGISTRY.get(spec.context.agent_type, AgentContainer)
    return cls.from_spec(spec, data_dir, comm_port, on_state_change)
```

Then update `Supervisor._start_child()` to call `create_container()` instead of `AgentContainer.from_spec()`.

### Pattern 5: Scheduler in CompanyRoot

**What:** An asyncio background task that periodically checks if any sleeping ContinuousAgent should be woken.

**Design:**
- Scheduler runs as `asyncio.Task` in CompanyRoot
- Schedule configuration stored in memory_store KV (agent_id -> cron-like schedule or next_wake_time)
- 60-second check loop (matches existing monitor loop cadence)
- On match: find the sleeping agent in the supervision tree, call `agent.wake()`
- Schedule survives restarts because it is persisted to a file or MemoryStore

**Schedule persistence options:**
- **Option A (recommended):** Store schedule in CompanyRoot's own MemoryStore as JSON. CompanyRoot doesn't currently have a MemoryStore, but it can have one since it needs persistent state for the scheduler.
- **Option B:** Store in a YAML config file alongside agents.yaml. Simpler but breaks the "state in memory_store" pattern.

**Recommendation:** Option A. Give CompanyRoot a MemoryStore for scheduler persistence. This is consistent with the container architecture.

### Anti-Patterns to Avoid
- **Sharing a single FSM class across different agent types:** Each type needs its own lifecycle -- compound states are type-specific. Do NOT try to parameterize a single FSM.
- **Polling for events in FulltimeAgent:** Use asyncio.Queue, not a polling loop. The supervision tree already uses event-driven callbacks.
- **Scheduler coupled to specific agents:** The scheduler should work with any ContinuousAgent by reading schedule config, not by having hardcoded references.
- **Cross-project state in a ProjectSupervisor child:** CompanyAgent must be managed by CompanyRoot directly, not by a ProjectSupervisor, since it survives project restarts.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| State machine transitions | Manual if/else state tracking | python-statemachine compound states | Invalid transitions rejected automatically, HistoryState for sleep/wake preservation |
| Cron-like scheduling | Full cron parser | Simple next-wake-time comparison | vCompany only needs "wake every N minutes" or "wake at HH:MM", not full cron |
| Event queuing | Custom event bus | asyncio.Queue | Built-in, async-native, back-pressure capable |
| Checkpoint serialization | Manual JSON construction | Pydantic BaseModel.model_dump_json() | Validation, type safety, consistent with existing CheckpointData |

**Key insight:** The GsdAgent implementation is the reference implementation. Follow it exactly for the compound state, checkpoint, and recovery patterns. The only new design work is the scheduler and the event-driven lifecycle.

## Common Pitfalls

### Pitfall 1: Supervisor Cannot Create Subclasses
**What goes wrong:** Supervisor._start_child() hardcodes AgentContainer.from_spec(). Even if you define ContinuousAgent, the supervisor will create a base AgentContainer.
**Why it happens:** Phase 2 only needed base AgentContainers; no factory dispatch was needed.
**How to avoid:** Implement a container factory registry FIRST, before creating any new agent types. Update Supervisor._start_child() to use it.
**Warning signs:** Tests pass but agents don't have compound states -- they are secretly base AgentContainers.

### Pitfall 2: CompanyAgent Lifecycle Tied to ProjectSupervisor
**What goes wrong:** If CompanyAgent is a child of ProjectSupervisor, it dies when the project is removed/restarted.
**Why it happens:** TYPE-05 requires "survives project restarts."
**How to avoid:** CompanyAgent must be a direct child of CompanyRoot, not any ProjectSupervisor. CompanyRoot already manages dynamic children; add CompanyAgent as a persistent child.
**Warning signs:** CompanyAgent's cross-project state is lost when a project is restarted.

### Pitfall 3: Scheduler Loses Schedule on Restart
**What goes wrong:** If schedule is only in memory (dict), bot restart loses all wake times.
**Why it happens:** AUTO-06 requires "scheduled wake times survive bot restarts."
**How to avoid:** Persist schedule to a MemoryStore. Load on CompanyRoot start. Write on every schedule change.
**Warning signs:** After bot restart, no agents wake up on schedule.

### Pitfall 4: OrderedSet State Decomposition
**What goes wrong:** Accessing compound state incorrectly -- getting the wrong index for outer/inner state.
**Why it happens:** python-statemachine represents compound states as OrderedSet(['running', 'idle']).
**How to avoid:** Use the exact pattern from GsdAgent: `list(val)[0]` for outer, `list(val)[1]` for inner. This is proven in Phase 3.
**Warning signs:** state property returns inner state, or inner_state returns None when it shouldn't.

### Pitfall 5: Event-Driven Agent Blocks on Empty Queue
**What goes wrong:** FulltimeAgent.process_events() does `await queue.get()` in a tight loop, making it impossible to stop cleanly.
**Why it happens:** asyncio.Queue.get() blocks forever if no events arrive.
**How to avoid:** Use `asyncio.wait_for(queue.get(), timeout=X)` or check a stop flag with `queue.get()` in a try/except. Alternatively, put a sentinel "stop" event to break the loop.
**Warning signs:** Agent hangs during supervisor shutdown.

### Pitfall 6: HistoryState for ContinuousAgent Cycle
**What goes wrong:** After sleep/wake, ContinuousAgent resumes at the last inner state (e.g., "analyze") instead of restarting the cycle at "wake".
**Why it happens:** HistoryState preserves the last inner state by design.
**How to avoid:** Two options: (a) always transition to the "wake" inner state explicitly after waking, or (b) do NOT use HistoryState for the sleep->running transition of ContinuousAgent -- use a fresh entry to the initial inner state. The cycle is meant to restart from the beginning each time.
**Warning signs:** Agent wakes up in the middle of a cycle instead of at the start.

## Code Examples

### ContinuousAgent Checkpoint (following GsdAgent pattern)
```python
# Source: adapted from src/vcompany/agent/gsd_agent.py
class CycleCheckpointData(BaseModel):
    configuration: list[str]
    cycle_phase: str
    cycle_count: int
    timestamp: str

async def _checkpoint_cycle(self) -> None:
    async with self._checkpoint_lock:
        config_values = self._lifecycle.current_state_value
        if isinstance(config_values, OrderedSet):
            configuration = list(config_values)
        else:
            configuration = [str(config_values)]
        checkpoint = CycleCheckpointData(
            configuration=configuration,
            cycle_phase=self.inner_state or "wake",
            cycle_count=self._cycle_count,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await self.memory.checkpoint("continuous_cycle", checkpoint.model_dump_json())
```

### Scheduler Wake Check
```python
# Source: design for CompanyRoot scheduler
import asyncio
import json
from datetime import datetime, timezone

async def _scheduler_loop(self) -> None:
    """Check sleeping ContinuousAgents against their schedules."""
    while True:
        try:
            now = datetime.now(timezone.utc)
            for project_id, ps in self._projects.items():
                for child_id, container in ps.children.items():
                    if (container.state == "sleeping"
                            and container.context.agent_type == "continuous"):
                        next_wake = await self._get_next_wake(child_id)
                        if next_wake and now >= next_wake:
                            await container.wake()
                            await self._schedule_next_wake(child_id)
        except Exception:
            logger.exception("Scheduler loop error")
        await asyncio.sleep(60)
```

### Container Factory Registration
```python
# Source: design pattern
from vcompany.container.factory import register_agent_type
from vcompany.agent.gsd_agent import GsdAgent
from vcompany.agent.continuous_agent import ContinuousAgent
from vcompany.agent.fulltime_agent import FulltimeAgent
from vcompany.agent.company_agent import CompanyAgent

register_agent_type("gsd", GsdAgent)
register_agent_type("continuous", ContinuousAgent)
register_agent_type("fulltime", FulltimeAgent)
register_agent_type("company", CompanyAgent)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flat FSM for all agents | Compound FSM per agent type | Phase 3 (GsdLifecycle) | Each type has its own inner states within running |
| AgentContainer only | AgentContainer subclasses | Phase 3 (GsdAgent) | Type-specific behavior via override |
| Static child creation | Need factory-based creation | Phase 4 (this phase) | Supervisor must dispatch to correct subclass |

## Open Questions

1. **ContinuousAgent: HistoryState or fresh start on wake?**
   - What we know: GsdAgent uses HistoryState to resume mid-phase after sleep/wake. ContinuousAgent cycles are designed to restart from WAKE each time.
   - What's unclear: Should ContinuousAgent use HistoryState (resume mid-cycle if crashed) or always start fresh at WAKE?
   - Recommendation: Use `running` (not `running.h`) for the `wake` transition so it enters the initial sub-state. For crash recovery mid-cycle, use checkpoint + restore as GsdAgent does. This gives: wake = fresh cycle, crash recovery = resume from last checkpoint.

2. **CompanyAgent ownership in supervision tree**
   - What we know: CompanyAgent survives project restarts, holds cross-project state. CompanyRoot manages ProjectSupervisors dynamically.
   - What's unclear: Should CompanyAgent be a direct field on CompanyRoot (like `self._company_agent`) or managed through the child_specs/children mechanism?
   - Recommendation: Direct field on CompanyRoot. CompanyRoot is a Supervisor but manages ProjectSupervisors dynamically already. CompanyAgent is a singleton -- no need for supervisor restart semantics. CompanyRoot starts it in `start()` and stops it in `stop()`.

3. **Schedule format**
   - What we know: Requirements say "configured schedule" and "scheduled wake times survive bot restarts."
   - What's unclear: Cron syntax? Simple interval? Time-of-day?
   - Recommendation: Simple interval (every N seconds) plus optional time-of-day (HH:MM UTC). Store as JSON in CompanyRoot's MemoryStore. No cron -- YAGNI.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 0.24+ |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/test_continuous_agent.py tests/test_fulltime_agent.py tests/test_company_agent.py tests/test_scheduler.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TYPE-03 | ContinuousAgent cycle FSM + checkpoint/restore | unit | `python -m pytest tests/test_continuous_agent.py -x` | Wave 0 |
| TYPE-03 | ContinuousLifecycle compound state transitions | unit | `python -m pytest tests/test_continuous_lifecycle.py -x` | Wave 0 |
| TYPE-04 | FulltimeAgent event handling + lifecycle | unit | `python -m pytest tests/test_fulltime_agent.py -x` | Wave 0 |
| TYPE-05 | CompanyAgent cross-project state persistence | unit | `python -m pytest tests/test_company_agent.py -x` | Wave 0 |
| AUTO-06 | Scheduler wakes sleeping agents on schedule | unit | `python -m pytest tests/test_scheduler.py -x` | Wave 0 |
| AUTO-06 | Schedule persists across restarts | unit | `python -m pytest tests/test_scheduler.py -x` | Wave 0 |
| ALL | Container factory creates correct subclasses | unit | `python -m pytest tests/test_container_factory.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_continuous_agent.py tests/test_fulltime_agent.py tests/test_company_agent.py tests/test_scheduler.py tests/test_container_factory.py -x`
- **Per wave merge:** `python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_continuous_agent.py` -- covers TYPE-03 (cycle FSM, checkpoint, restore)
- [ ] `tests/test_continuous_lifecycle.py` -- covers TYPE-03 (FSM transitions)
- [ ] `tests/test_fulltime_agent.py` -- covers TYPE-04 (event handling)
- [ ] `tests/test_company_agent.py` -- covers TYPE-05 (cross-project state)
- [ ] `tests/test_scheduler.py` -- covers AUTO-06 (wake scheduling, persistence)
- [ ] `tests/test_container_factory.py` -- covers factory registry

## Sources

### Primary (HIGH confidence)
- `src/vcompany/agent/gsd_agent.py` -- reference implementation for agent type subclass pattern
- `src/vcompany/agent/gsd_lifecycle.py` -- reference implementation for compound FSM with HistoryState
- `src/vcompany/container/container.py` -- AgentContainer base class API
- `src/vcompany/supervisor/supervisor.py` -- Supervisor._start_child() factory gap identified (line 145)
- `src/vcompany/supervisor/company_root.py` -- CompanyRoot dynamic project management
- `src/vcompany/container/memory_store.py` -- MemoryStore API for persistence
- `src/vcompany/container/child_spec.py` -- ChildSpec with agent_type field
- `src/vcompany/agent/gsd_phases.py` -- CheckpointData Pydantic model pattern

### Secondary (MEDIUM confidence)
- python-statemachine documentation (verified via codebase usage of State.Compound, HistoryState, OrderedSet)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in project, patterns established
- Architecture: HIGH - GsdAgent is a proven reference implementation, patterns directly transferable
- Pitfalls: HIGH - supervisor factory gap confirmed by code inspection, CompanyAgent ownership derived from requirements
- Scheduler: MEDIUM - design is straightforward but untested; asyncio.sleep loop is standard pattern

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable domain, no external API dependencies)
