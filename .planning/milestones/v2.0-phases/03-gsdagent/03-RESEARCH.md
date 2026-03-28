# Phase 3: GsdAgent - Research

**Researched:** 2026-03-27
**Domain:** Agent type implementation, nested state machines, checkpoint-based crash recovery
**Confidence:** HIGH

## Summary

GsdAgent is the first concrete agent type subclassing AgentContainer. It needs an internal phase FSM (IDLE, DISCUSS, PLAN, EXECUTE, UAT, SHIP) that runs while the container lifecycle is in the RUNNING state, with each phase transition checkpointed to memory_store for crash recovery. The implementation must absorb WorkflowOrchestrator's state-tracking responsibilities so no external system tracks GsdAgent phase state.

The critical technical question is whether to use python-statemachine compound states (single FSM with `running` as a compound containing phase sub-states) or two separate FSMs (ContainerLifecycle unchanged + standalone GsdPhaseFSM). Research confirms both approaches work with python-statemachine 3.0.0. The compound approach is recommended because it matches the success criteria ("compound states") and provides automatic consistency -- you cannot be in a phase sub-state without being in RUNNING.

**Primary recommendation:** Use a `GsdLifecycle` class (extending the compound state pattern) with `running` as `State.Compound` containing phase sub-states, paired with `HistoryState` for sleep/wake recovery. GsdAgent subclasses AgentContainer, overrides the lifecycle FSM, checkpoints phase state to memory_store on every transition, and restores from checkpoint on start.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion (infrastructure phase).

### Claude's Discretion
All implementation choices are at Claude's discretion. Key technical anchors from requirements:
- Internal phase FSM: IDLE->DISCUSS->PLAN->EXECUTE->UAT->SHIP nested inside container RUNNING state (TYPE-01)
- Checkpoint to memory_store on each phase transition -- crash recovery resumes from last checkpoint (TYPE-02)
- Absorbs WorkflowOrchestrator's state tracking -- no external system tracks phase state (TYPE-01)
- Use python-statemachine compound states for nesting (from success criteria)

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase with clear scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TYPE-01 | GsdAgent with internal phase FSM (IDLE->DISCUSS->PLAN->EXECUTE->UAT->SHIP) absorbing WorkflowOrchestrator | Compound state pattern verified working in python-statemachine 3.0.0. GsdLifecycle replaces ContainerLifecycle for GsdAgent. WorkflowOrchestrator state tracking (stage, gate transitions, blocked detection) absorbed into GsdAgent methods. |
| TYPE-02 | GsdAgent saves checkpoint to memory_store after each state transition -- crash recovery resumes from last completed state | MemoryStore.checkpoint() and get_latest_checkpoint() already exist. State can be serialized as list of strings from configuration_values and restored via current_state_value setter. After_transition callback triggers checkpoint persistence. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Use python-statemachine (already in dependencies as >=3.0.0)
- Use aiosqlite for MemoryStore (already in dependencies)
- Use Pydantic for data models
- Use pytest + pytest-asyncio for testing
- Use uv for package management
- Do NOT use GitPython, nextcord, requests, poetry, argparse, celery, SQLAlchemy, Flask/FastAPI

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-statemachine | 3.0.0 | Compound state FSM for GsdLifecycle | Already installed. Compound states, HistoryState, model binding all verified working. |
| aiosqlite | 0.22.1 | MemoryStore backend | Already installed. Used by existing MemoryStore for checkpoint persistence. |
| pydantic | 2.11.x | Data models for checkpoint data | Already installed. Used for ContainerContext, HealthReport, ChildSpec. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json (stdlib) | N/A | Checkpoint data serialization | Serialize phase state + metadata to JSON string for MemoryStore.checkpoint() |
| dataclasses (stdlib) | N/A | Internal state tracking | For lightweight state objects that don't need Pydantic validation |

No new dependencies required. Everything needed is already in pyproject.toml.

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
  container/
    container.py          # AgentContainer base (unchanged)
    state_machine.py      # ContainerLifecycle (unchanged)
    memory_store.py       # MemoryStore (unchanged)
  agent/
    __init__.py
    gsd_agent.py          # GsdAgent class
    gsd_lifecycle.py      # GsdLifecycle FSM (compound states)
    gsd_phases.py         # Phase enum + checkpoint data model
```

### Pattern 1: Compound State FSM (GsdLifecycle)

**What:** A new StateMachine class that extends ContainerLifecycle's states by making `running` a compound state containing phase sub-states.

**When to use:** For GsdAgent instances only. Plain AgentContainer continues to use ContainerLifecycle.

**Key design:**
```python
from statemachine import State, StateMachine, HistoryState

class GsdLifecycle(StateMachine):
    """Lifecycle FSM for GsdAgent with nested phase states inside running."""

    creating = State(initial=True)

    class running(State.Compound):
        idle = State(initial=True)
        discuss = State()
        plan = State()
        execute = State()
        uat = State()
        ship = State()
        h = HistoryState()

        # Phase transitions (inner)
        start_discuss = idle.to(discuss)
        start_plan = discuss.to(plan)
        start_execute = plan.to(execute)
        start_uat = execute.to(uat)
        start_ship = uat.to(ship)

    sleeping = State()
    errored = State()
    stopped = State()
    destroyed = State(final=True)

    # Outer lifecycle transitions (same as ContainerLifecycle)
    start = creating.to(running)
    sleep = running.to(sleeping)
    wake = sleeping.to(running.h)  # HistoryState restores inner phase
    error = creating.to(errored) | running.to(errored) | sleeping.to(errored)
    recover = errored.to(running.h)  # HistoryState restores inner phase
    stop = running.to(stopped) | sleeping.to(stopped) | errored.to(stopped)
    destroy = stopped.to(destroyed) | errored.to(destroyed)

    def after_transition(self, event, state):
        if self.model and hasattr(self.model, "_on_state_change"):
            self.model._on_state_change()
```

**Verified behavior (HIGH confidence -- tested locally):**
- `configuration_values` returns `OrderedSet({'running', 'plan'})` when in plan phase
- `HistoryState` preserves inner phase across sleep/wake and error/recover
- Model binding with `state_field` works -- but `_fsm_state` becomes `OrderedSet` instead of `str` when in compound state
- State can be serialized via `list(sm.configuration_values)` and restored via `sm.current_state_value = OrderedSet(saved_list)`

### Pattern 2: GsdAgent Subclass

**What:** GsdAgent subclasses AgentContainer, replaces the lifecycle FSM with GsdLifecycle, overrides `state` and `inner_state` properties, and adds checkpoint logic.

**Key design:**
```python
class GsdAgent(AgentContainer):
    def __init__(self, context, data_dir, comm_port=None, on_state_change=None):
        # Call parent but override the lifecycle FSM
        super().__init__(context, data_dir, comm_port, on_state_change)
        self._lifecycle = GsdLifecycle(model=self, state_field="_fsm_state")

    @property
    def state(self) -> str:
        """Outer lifecycle state (creating, running, sleeping, etc.)."""
        cv = self._lifecycle.configuration_values
        if isinstance(cv, str):
            return cv
        # Compound: first value is the outer state
        values = list(cv)
        return values[0] if values else "unknown"

    @property
    def inner_state(self) -> str | None:
        """Phase sub-state (idle, discuss, plan, etc.) or None if not running."""
        cv = self._lifecycle.configuration_values
        if not hasattr(cv, '__iter__') or isinstance(cv, str):
            return None
        values = list(cv)
        return values[1] if len(values) > 1 else None
```

### Pattern 3: Checkpoint-Based Crash Recovery

**What:** On every phase transition, serialize the current state to memory_store. On startup (or recovery), read the last checkpoint and restore FSM state.

**Key design:**
```python
import json
from statemachine.orderedset import OrderedSet

# Checkpoint on transition (in _on_state_change or after_transition):
async def _checkpoint_phase(self):
    state_data = json.dumps({
        "configuration": list(self._lifecycle.configuration_values),
        "phase": self.inner_state,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    await self.memory.checkpoint("gsd_phase", state_data)
    await self.memory.set("current_phase", self.inner_state or "idle")

# Recover on start:
async def start(self):
    await super().start()  # opens memory, transitions to running
    checkpoint_data = await self.memory.get_latest_checkpoint("gsd_phase")
    if checkpoint_data:
        saved = json.loads(checkpoint_data)
        config = OrderedSet(saved["configuration"])
        self._lifecycle.current_state_value = config
```

### Pattern 4: Absorbing WorkflowOrchestrator

**What:** GsdAgent takes ownership of all state-tracking that WorkflowOrchestrator did externally.

**WorkflowOrchestrator responsibilities to absorb:**
1. **Stage tracking** (`AgentWorkflowState.stage`) -- replaced by inner phase FSM state
2. **Phase number tracking** (`current_phase`) -- stored in memory_store as KV
3. **Stage completion signals** (`on_stage_complete`) -- GsdAgent advances its own FSM
4. **Gate transitions** (`advance_from_gate`) -- GsdAgent handles gate logic internally
5. **Blocked agent detection** (`handle_unknown_prompt`, `check_blocked_agents`) -- GsdAgent tracks its own blocked state
6. **Recovery from STATE.md** (`recover_from_state`) -- replaced by checkpoint recovery from memory_store

**What NOT to absorb (stays external, different concern):**
- Signal detection patterns (`detect_stage_signal`, `STAGE_COMPLETE_PATTERNS`) -- these are message parsing utilities, not agent state
- Command templates (`_GATE_APPROVED`, `_GATE_REJECTED`) -- GsdAgent will own its own command dispatch logic
- Agent manager interaction (`send_work_command`) -- GsdAgent will use its own dispatch mechanism

### Anti-Patterns to Avoid

- **Modifying ContainerLifecycle directly:** The base FSM must remain unchanged for non-GSD agent types. GsdAgent uses GsdLifecycle, not a modified ContainerLifecycle.
- **External state tracking of GsdAgent phases:** No Supervisor, Orchestrator, or other system should track what phase a GsdAgent is in. The agent owns its own phase state (TYPE-01).
- **Assuming `_fsm_state` is always a string:** With compound states, `_fsm_state` is an `OrderedSet`. The `state` and `inner_state` properties must handle both types.
- **Synchronous checkpoint writes:** Memory store operations are async. The `after_transition` callback in python-statemachine is synchronous. Use `asyncio.create_task` or schedule checkpoint writes appropriately.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Nested state machine | Custom state tracking with if/elif chains | python-statemachine compound states | Validated transitions, history states, serialization all built-in |
| State persistence | Custom file-based state tracking | MemoryStore.checkpoint() + get_latest_checkpoint() | Already built, tested, WAL-mode SQLite with atomic writes |
| State serialization | Custom binary format | JSON via `list(configuration_values)` | Human-readable, debuggable, works with MemoryStore's text storage |
| Transition validation | Manual state checking before transitions | python-statemachine TransitionNotAllowed | Automatic, cannot reach invalid states |

## Common Pitfalls

### Pitfall 1: _fsm_state Type Change with Compound States
**What goes wrong:** `AgentContainer.state` property does `str(self._fsm_state)` which returns `{running, plan}` (the OrderedSet repr) instead of `"running"`.
**Why it happens:** Compound states store `OrderedSet` in `state_field` instead of a plain string.
**How to avoid:** GsdAgent must override `state` property to extract the outer state from the OrderedSet. Also override `inner_state` to extract the phase sub-state.
**Warning signs:** Health reports showing state as `{running, plan}` instead of `running`.

### Pitfall 2: Synchronous after_transition vs Async Checkpoint
**What goes wrong:** `after_transition` is called synchronously by python-statemachine, but `memory.checkpoint()` is async.
**Why it happens:** python-statemachine's transition engine is synchronous even when used with an async application.
**How to avoid:** In `_on_state_change`, schedule the checkpoint as a background task via `asyncio.create_task()`, or maintain a "dirty" flag and flush checkpoints in the next async opportunity. Alternatively, use a synchronous signal and let the caller (which is async) do the actual checkpoint write after the transition completes.
**Warning signs:** `RuntimeWarning: coroutine was never awaited`.

### Pitfall 3: Checkpoint Race on Rapid Transitions
**What goes wrong:** If two transitions happen quickly, the second checkpoint might be written before the first finishes, or checkpoints might be out of order.
**Why it happens:** `asyncio.create_task` for checkpoint writes can interleave.
**How to avoid:** Use an `asyncio.Lock` around checkpoint writes, or serialize them through a queue. Since phase transitions in GSD are minutes apart (not milliseconds), this is low risk but should be guarded.
**Warning signs:** Out-of-order checkpoint labels in the database.

### Pitfall 4: Recovery Restoring Invalid State
**What goes wrong:** A checkpoint was written for a state that is no longer valid (e.g., the FSM definition changed between versions).
**Why it happens:** Schema evolution of the state machine.
**How to avoid:** Validate the restored `OrderedSet` against known state names before applying. If invalid, fall back to the initial state (idle) and log a warning.
**Warning signs:** `TransitionNotAllowed` or `ValueError` on startup after recovery.

### Pitfall 5: from_spec Factory Not Creating GsdAgent
**What goes wrong:** `AgentContainer.from_spec()` creates an `AgentContainer`, not a `GsdAgent`, because the factory uses `cls()` but is called on the base class.
**Why it happens:** The factory is a classmethod on `AgentContainer`. If called as `AgentContainer.from_spec(spec)` it creates the base type.
**How to avoid:** Either override `from_spec` on GsdAgent, or have the Supervisor use `GsdAgent.from_spec(spec)` directly when `spec.agent_type == "gsd"`. A factory dispatch based on `agent_type` would be clean.
**Warning signs:** `inner_state` always returns `None` because the base class's property is used.

## Code Examples

### Creating a GsdAgent and Running Through Phases
```python
# Source: Verified locally with python-statemachine 3.0.0
from statemachine import State, StateMachine, HistoryState
from statemachine.orderedset import OrderedSet

# FSM definition (compound states)
class GsdLifecycle(StateMachine):
    creating = State(initial=True)
    class running(State.Compound):
        idle = State(initial=True)
        discuss = State()
        plan = State()
        execute = State()
        uat = State()
        ship = State()
        h = HistoryState()
        start_discuss = idle.to(discuss)
        start_plan = discuss.to(plan)
        start_execute = plan.to(execute)
        start_uat = execute.to(uat)
        start_ship = uat.to(ship)
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

# Lifecycle flow
sm = GsdLifecycle()
sm.start()       # -> {running, idle}
sm.start_discuss()  # -> {running, discuss}
sm.start_plan()     # -> {running, plan}
sm.sleep()          # -> {sleeping}
sm.wake()           # -> {running, plan}  (HistoryState preserves phase!)
```

### Serializing and Restoring State for Crash Recovery
```python
import json
from statemachine.orderedset import OrderedSet

# Save
config = list(sm.configuration_values)  # ['running', 'plan']
checkpoint_data = json.dumps({"configuration": config})

# Restore
saved = json.loads(checkpoint_data)
sm2 = GsdLifecycle()
sm2.current_state_value = OrderedSet(saved["configuration"])
# sm2 is now in {running, plan} -- can continue transitions
```

### Extracting Outer and Inner State
```python
cv = sm.configuration_values
if isinstance(cv, str):
    outer, inner = cv, None  # Simple state (creating, sleeping, etc.)
else:
    values = list(cv)
    outer = values[0]  # 'running'
    inner = values[1] if len(values) > 1 else None  # 'plan'
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| WorkflowOrchestrator external tracking | GsdAgent internal phase FSM | Phase 3 (this phase) | Agent owns its own state -- supervisor only sees outer lifecycle |
| Manual state recovery from STATE.md | Checkpoint-based recovery from memory_store | Phase 3 (this phase) | Reliable, atomic, version-independent recovery |
| Enum-based WorkflowStage | python-statemachine compound states | Phase 3 (this phase) | Validated transitions, history, automatic nesting |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24.x |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_gsd_agent.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TYPE-01 | GsdAgent has internal phase FSM (IDLE->DISCUSS->PLAN->EXECUTE->UAT->SHIP) | unit | `uv run pytest tests/test_gsd_lifecycle.py -x` | No -- Wave 0 |
| TYPE-01 | Phase FSM nested inside container RUNNING state | unit | `uv run pytest tests/test_gsd_lifecycle.py::test_phases_only_in_running -x` | No -- Wave 0 |
| TYPE-01 | GsdAgent absorbs WorkflowOrchestrator state tracking | unit | `uv run pytest tests/test_gsd_agent.py::TestStateTracking -x` | No -- Wave 0 |
| TYPE-02 | Checkpoint saved on each phase transition | unit | `uv run pytest tests/test_gsd_agent.py::TestCheckpointing -x` | No -- Wave 0 |
| TYPE-02 | Crash recovery resumes from last checkpoint | unit | `uv run pytest tests/test_gsd_agent.py::TestCrashRecovery -x` | No -- Wave 0 |
| TYPE-01 | inner_state property returns phase sub-state | unit | `uv run pytest tests/test_gsd_agent.py::test_inner_state -x` | No -- Wave 0 |
| TYPE-01 | HistoryState preserves phase across sleep/wake | unit | `uv run pytest tests/test_gsd_lifecycle.py::test_history_state_sleep_wake -x` | No -- Wave 0 |
| TYPE-02 | Invalid checkpoint data falls back to initial state | unit | `uv run pytest tests/test_gsd_agent.py::test_invalid_checkpoint_fallback -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_gsd_lifecycle.py tests/test_gsd_agent.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_gsd_lifecycle.py` -- covers GsdLifecycle FSM transitions, compound state behavior, HistoryState
- [ ] `tests/test_gsd_agent.py` -- covers GsdAgent class, state properties, checkpointing, crash recovery, WorkflowOrchestrator absorption

## Open Questions

1. **Gate logic in GsdAgent**
   - What we know: WorkflowOrchestrator has gate states (DISCUSSION_GATE, PM_PLAN_REVIEW_GATE, VERIFY_GATE) between phases. The success criteria FSM (IDLE->DISCUSS->PLAN->EXECUTE->UAT->SHIP) does not include explicit gate states.
   - What's unclear: Should gate logic be modeled as explicit FSM states, or as conditions checked before transitioning?
   - Recommendation: Do NOT model gates as FSM states in this phase. The success criteria explicitly lists 6 states without gates. Gate logic (PM approval, verification) is a higher-level concern for Phase 7 (Autonomy) where the PM manages workflow. For Phase 3, the FSM advances directly between phases. Add gate states later if needed.

2. **Blocked agent detection**
   - What we know: WorkflowOrchestrator tracks `blocked_since` and `blocked_reason` for agents stuck on unknown prompts.
   - What's unclear: Whether GsdAgent should absorb blocked detection or if this is a Supervisor concern.
   - Recommendation: GsdAgent should track its own `blocked_since`/`blocked_reason` in memory_store KV. The Supervisor only sees outer lifecycle state (running/errored). Blocked detection is an internal concern.

3. **Async checkpoint in synchronous callback**
   - What we know: `after_transition` is sync. `memory.checkpoint()` is async.
   - What's unclear: Best pattern for bridging.
   - Recommendation: Make phase transition methods on GsdAgent async (they already are in AgentContainer). The async method calls `self._lifecycle.start_plan()` (sync FSM transition), then awaits `self._checkpoint_phase()` (async write). The `after_transition` callback handles the state_change notification (sync), and the caller handles the checkpoint (async). This avoids `create_task` complexity entirely.

## Sources

### Primary (HIGH confidence)
- python-statemachine 3.0.0 installed locally -- compound states, HistoryState, model binding all verified via interactive testing
- [python-statemachine states docs](https://python-statemachine.readthedocs.io/en/latest/states.html) -- compound state syntax, HistoryState usage
- [python-statemachine API docs](https://python-statemachine.readthedocs.io/en/latest/api.html) -- StateChart vs StateMachine, configuration_values, current_state_value

### Secondary (MEDIUM confidence)
- [python-statemachine PyPI](https://pypi.org/project/python-statemachine/) -- version 3.0.0 confirmed
- [python-statemachine GitHub](https://github.com/fgmacedo/python-statemachine) -- active maintenance confirmed

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already installed and verified locally
- Architecture: HIGH - compound states tested interactively, model binding verified, serialization confirmed
- Pitfalls: HIGH - discovered through direct testing (OrderedSet type change, HistoryState behavior, async/sync boundary)

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable -- python-statemachine 3.0.0 is a major release)
