# Phase 2: Supervision Tree - Research

**Researched:** 2026-03-27
**Domain:** Erlang/OTP-style supervision trees implemented in Python asyncio
**Confidence:** HIGH

## Summary

Phase 2 builds a supervision tree on top of the Phase 1 container foundation. The core abstraction is a `Supervisor` class that manages child `AgentContainer` instances using asyncio Tasks, implementing three Erlang-style restart strategies (`one_for_one`, `all_for_one`, `rest_for_one`), restart intensity tracking with sliding windows, and escalation when limits are exceeded.

The Phase 1 codebase provides strong building blocks: `AgentContainer` with async `start()`/`stop()`/`error()`/`recover()` methods, `ChildSpec` with `RestartPolicy` enum and `max_restarts`/`restart_window_seconds` fields (already defaulting to 3 restarts in 600 seconds), `ContainerLifecycle` FSM with validated transitions, and `HealthReport` with `on_state_change` callbacks. The supervision tree needs to orchestrate these primitives -- not replace them.

**Primary recommendation:** Implement `Supervisor` as a base class (itself an `AgentContainer` subclass or wrapper) that holds an ordered list of children, monitors them via asyncio Tasks, and implements restart/escalation logic. `CompanyRoot` and `ProjectSupervisor` are thin subclasses or configured instances of `Supervisor`. Keep the supervisor pure Python/asyncio -- no new dependencies needed.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion (infrastructure phase).

### Claude's Discretion
All implementation choices including:
- Two-level hierarchy: CompanyRoot -> ProjectSupervisor -> agent containers (SUPV-01)
- one_for_one: restart only failed child (SUPV-02)
- all_for_one: restart all children when one fails (SUPV-03)
- rest_for_one: restart failed child + all started after it (SUPV-04)
- Max restart intensity with 10-minute windows (not 60s) for slow Claude Code bootstrap (SUPV-05)
- Escalation to parent when max restarts exceeded; top-level alerts owner via Discord (SUPV-06)

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SUPV-01 | Two-level supervision hierarchy: CompanyRoot -> ProjectSupervisor -> agent containers | Architecture pattern: Supervisor base class with CompanyRoot and ProjectSupervisor as configured instances |
| SUPV-02 | `one_for_one` restart strategy -- only restart the failed child | Erlang OTP reference: restart only terminated child, siblings unaffected |
| SUPV-03 | `all_for_one` restart strategy -- restart all children when one fails | Erlang OTP reference: terminate all remaining children, then restart all including failed |
| SUPV-04 | `rest_for_one` restart strategy -- restart failed child and all children started after it | Erlang OTP reference: terminate children after failed in start order, restart them in order |
| SUPV-05 | Max restart intensity at supervisor level with 10-minute windows | ChildSpec already has max_restarts=3, restart_window_seconds=600; supervisor tracks sliding window of restart timestamps |
| SUPV-06 | When max restarts exceeded, supervisor escalates to parent; top-level alerts owner via Discord | Erlang OTP: supervisor terminates self, parent takes action. Top-level uses CommunicationPort for Discord alert |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.12+, asyncio for async orchestration
- Pydantic for data models, python-statemachine for FSMs
- All communication flows through Discord (CommunicationPort protocol)
- No new database -- filesystem state only
- No GitPython, no requests, no celery
- Testing with pytest + pytest-asyncio
- Ruff for linting/formatting (line-length=100, target py312)

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio (stdlib) | N/A | Task management for child monitoring | Supervisor wraps each child in an asyncio.Task for crash detection |
| python-statemachine | 3.0.0 | Supervisor lifecycle FSM (if needed) | Already used for ContainerLifecycle; supervisor may reuse or extend |
| pydantic | 2.11.x | SupervisorSpec, RestartStrategy models | Project convention for validated data structures |

### Supporting (already in project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-asyncio | 0.24+ | Testing async supervisor operations | All supervisor tests need async |

### No New Dependencies
This phase requires zero new packages. Everything is built on asyncio primitives (Tasks, Events, locks) and existing project libraries.

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
  container/           # Phase 1 (existing)
    container.py       # AgentContainer
    child_spec.py      # ChildSpec, RestartPolicy
    state_machine.py   # ContainerLifecycle
    ...
  supervisor/          # Phase 2 (new)
    __init__.py        # Public exports
    supervisor.py      # Supervisor base class
    strategies.py      # RestartStrategy enum + restart logic
    restart_tracker.py # Sliding window restart intensity tracker
    company_root.py    # CompanyRoot (top-level supervisor)
    project_supervisor.py  # ProjectSupervisor (mid-level)
tests/
  test_supervisor.py           # Unit tests for Supervisor base
  test_restart_strategies.py   # Strategy-specific tests
  test_restart_tracker.py      # Intensity window tests
  test_supervision_tree.py     # Integration: two-level hierarchy
```

### Pattern 1: Supervisor as Child Container Manager

**What:** A `Supervisor` class that holds an ordered list of `(ChildSpec, AgentContainer, asyncio.Task)` tuples. Each child runs inside an asyncio Task. When a task completes unexpectedly (child crashed), the supervisor's monitor loop detects it and applies the restart strategy.

**When to use:** Always -- this is the core pattern.

**Key design decisions:**
- Supervisor itself can be a plain class (not an AgentContainer subclass) because supervisors don't need memory stores or FSM lifecycles -- they manage others. However, making it a subclass enables the tree to be uniform (supervisors are containers too, supervisable by parents).
- **Recommendation:** Make Supervisor a standalone class that *composes* rather than inherits AgentContainer. A supervisor's "lifecycle" is simpler (starting/stopping children). It can still have a `state` property for health tree integration later.

**Example:**
```python
# Source: Erlang/OTP supervisor pattern adapted for asyncio
from enum import Enum

class RestartStrategy(str, Enum):
    ONE_FOR_ONE = "one_for_one"
    ALL_FOR_ONE = "all_for_one"
    REST_FOR_ONE = "rest_for_one"

class Supervisor:
    def __init__(
        self,
        supervisor_id: str,
        strategy: RestartStrategy,
        child_specs: list[ChildSpec],
        parent: Supervisor | None = None,
    ) -> None:
        self.supervisor_id = supervisor_id
        self.strategy = strategy
        self._child_specs = child_specs  # ordered
        self._children: dict[str, AgentContainer] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._restart_tracker = RestartTracker()
        self._parent = parent

    async def start_children(self) -> None:
        """Start all children in spec order."""
        for spec in self._child_specs:
            await self._start_child(spec)

    async def _start_child(self, spec: ChildSpec) -> None:
        """Create container from spec, start it, wrap in Task."""
        container = AgentContainer.from_spec(spec, data_dir=self._data_dir)
        await container.start()
        self._children[spec.child_id] = container
        self._tasks[spec.child_id] = asyncio.create_task(
            self._monitor_child(spec.child_id)
        )
```

### Pattern 2: Task-Based Child Monitoring

**What:** Each child gets an asyncio Task that awaits the child's "run" completion. When the task finishes (child exited or crashed), the supervisor catches it and applies restart logic.

**Design consideration:** Phase 1 AgentContainer does not have a long-running "run" coroutine -- it has `start()` and then is externally driven. For supervision purposes, the monitor task needs something to await. Options:
1. Add an `asyncio.Event` to AgentContainer that is set when the container enters ERRORED or STOPPED state (preferred -- minimal change to Phase 1).
2. Have the supervisor poll container state periodically (wasteful).
3. Use the `on_state_change` callback to notify the supervisor (good complement to option 1).

**Recommendation:** Use the existing `on_state_change` callback. When a child transitions to ERRORED, the callback signals the supervisor (via asyncio.Event or direct method call). The supervisor then applies its restart strategy.

```python
async def _monitor_child(self, child_id: str) -> None:
    """Wait for child to need attention, then handle."""
    event = self._child_events[child_id]
    while True:
        await event.wait()
        event.clear()
        container = self._children[child_id]
        if container.state == "errored":
            await self._handle_child_failure(child_id)
        elif container.state in ("stopped", "destroyed"):
            break  # Normal exit, no restart needed
```

### Pattern 3: Restart Strategy Dispatch

**What:** When a child fails, the supervisor dispatches to the appropriate strategy handler.

**Erlang OTP semantics (verified from official docs):**

- **one_for_one:** Restart only the failed child. No other children affected.
- **all_for_one:** Terminate ALL remaining children (in reverse start order), then restart ALL children (in start order), including the one that failed.
- **rest_for_one:** Terminate children that were started AFTER the failed child (in reverse start order), then restart the failed child and those terminated children (in start order).

**Critical detail for all_for_one and rest_for_one:** Children must be stopped in reverse start order and restarted in start order. This preserves dependency ordering.

```python
async def _handle_child_failure(self, failed_id: str) -> None:
    """Apply restart strategy for a failed child."""
    spec = self._get_spec(failed_id)

    # Check restart policy (per-child)
    if spec.restart_policy == RestartPolicy.TEMPORARY:
        return  # Never restart
    if spec.restart_policy == RestartPolicy.TRANSIENT:
        # Only restart on abnormal exit -- check if error vs normal stop
        if self._children[failed_id].state != "errored":
            return

    # Check restart intensity (per-supervisor)
    if not self._restart_tracker.allow_restart():
        await self._escalate()
        return

    # Dispatch to strategy
    match self.strategy:
        case RestartStrategy.ONE_FOR_ONE:
            await self._restart_one(failed_id)
        case RestartStrategy.ALL_FOR_ONE:
            await self._restart_all(failed_id)
        case RestartStrategy.REST_FOR_ONE:
            await self._restart_rest(failed_id)
```

### Pattern 4: Sliding Window Restart Intensity Tracker

**What:** Track restart timestamps in a deque. Before each restart, purge timestamps older than the window, then check if count exceeds max.

**Erlang OTP semantics:** "If more than MaxR number of restarts occur in the last MaxT seconds, the supervisor terminates all the child processes and then itself."

The ChildSpec already has `max_restarts=3` and `restart_window_seconds=600` (10 minutes). The supervisor reads these from its children's specs. The tracker should be per-supervisor (not per-child) -- Erlang supervisors track intensity at the supervisor level.

```python
from collections import deque
from datetime import datetime, timezone

class RestartTracker:
    def __init__(self, max_restarts: int = 3, window_seconds: int = 600) -> None:
        self.max_restarts = max_restarts
        self.window_seconds = window_seconds
        self._timestamps: deque[datetime] = deque()

    def allow_restart(self) -> bool:
        """Check if a restart is allowed within intensity limits."""
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - self.window_seconds
        # Purge old timestamps
        while self._timestamps and self._timestamps[0].timestamp() < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_restarts:
            return False
        self._timestamps.append(now)
        return True
```

### Pattern 5: Escalation Protocol

**What:** When restart intensity is exceeded, the supervisor:
1. Stops all its children (in reverse order)
2. Notifies its parent supervisor
3. The parent then handles it according to ITS restart strategy (the failing supervisor is treated like a failed child)
4. If the top-level (CompanyRoot) receives an escalation it cannot handle, it alerts the owner via Discord

**For CompanyRoot (top-level):** Uses CommunicationPort to send a Discord alert. Since CommunicationPort is a Protocol not yet implemented, CompanyRoot should accept an optional escalation callback or CommunicationPort for sending alerts.

```python
async def _escalate(self) -> None:
    """Escalate to parent when restart intensity exceeded."""
    # Stop all children first
    await self._stop_all_children()

    if self._parent is not None:
        # Notify parent -- parent treats this as a child failure
        await self._parent.handle_child_escalation(self.supervisor_id)
    else:
        # Top-level: alert owner via Discord
        if self._comm_port is not None:
            await self._comm_port.send_message(
                target="owner",
                content=f"ESCALATION: Supervisor {self.supervisor_id} exceeded "
                        f"restart limits. Manual intervention required.",
            )
```

### Anti-Patterns to Avoid

- **Polling child state:** Do not use `asyncio.sleep()` loops to check child health. Use event-driven notification (on_state_change callback + asyncio.Event).
- **Per-child restart tracking:** Erlang tracks restart intensity at the supervisor level, not per-child. A supervisor that allows 3 restarts in 10 minutes means 3 total restarts across ALL children, not 3 per child.
- **Restarting without stopping first:** When applying all_for_one or rest_for_one, affected children must be fully stopped before being restarted. Do not try to restart a child that is still in RUNNING state.
- **Ignoring start order:** rest_for_one and all_for_one depend on children having a defined start order. Always stop in reverse order, restart in forward order.
- **Blocking the event loop during restart:** Container start() may involve I/O (memory store open). Always use await, never synchronous calls.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sliding window time tracking | Custom linked list or array manipulation | `collections.deque` with timestamp pruning | Deque has O(1) append/popleft, handles the sliding window perfectly |
| Child process monitoring | Custom polling loops | asyncio.Task + on_state_change callback | asyncio Tasks propagate exceptions naturally, callbacks are instant |
| Ordered restart sequencing | Manual index tracking | Maintain `list[ChildSpec]` in insertion order | Python lists preserve order; enumerate for index-based rest_for_one slicing |
| Concurrent child shutdown | Sequential await loops | `asyncio.gather(*stop_tasks)` for parallel shutdown | Stopping children in parallel is safe and faster (they are independent during shutdown) |

**Key insight:** The Phase 1 container foundation already provides the building blocks (lifecycle FSM, ChildSpec with restart config, on_state_change callbacks). The supervisor is orchestration logic over these primitives, not a reimplementation.

## Common Pitfalls

### Pitfall 1: Race Between Child Failure and Restart
**What goes wrong:** Child transitions to ERRORED, supervisor starts restart, but the on_state_change callback fires again during restart, causing double-restart.
**Why it happens:** The restart process (stop old -> create new -> start new) involves multiple state transitions, each triggering callbacks.
**How to avoid:** Use a per-child lock or "restarting" flag. While a restart is in progress for a child_id, ignore additional failure notifications for that child.
**Warning signs:** Restart count incrementing by 2+ for a single failure.

### Pitfall 2: all_for_one Cascade
**What goes wrong:** In all_for_one, stopping sibling children triggers their on_state_change callbacks, which the supervisor interprets as additional failures, causing recursive restart attempts.
**Why it happens:** Supervisor-initiated stops look the same as crash-induced stops to the callback.
**How to avoid:** Set a supervisor-level "restarting" flag during strategy execution. While true, suppress all failure handling. Clear it after restart completes.
**Warning signs:** Infinite restart loops, stack overflow from recursive failure handling.

### Pitfall 3: 10-Minute Window Too Long for Tests
**What goes wrong:** Tests that verify restart intensity limits take 10+ minutes because they use real time windows.
**Why it happens:** Hardcoded time constants.
**How to avoid:** Make RestartTracker accept a `clock` callable (dependency injection). Tests pass a mock clock that can be advanced instantly. Production uses `datetime.now(timezone.utc)`.
**Warning signs:** Slow tests, flaky time-dependent assertions.

### Pitfall 4: Memory Store Not Closed Before Restart
**What goes wrong:** AgentContainer.stop() closes the memory store. If the supervisor creates a new container with the same data_dir before the old one is fully stopped, SQLite file locking causes errors.
**Why it happens:** Async operations interleave -- new container start() runs before old container stop() completes.
**How to avoid:** Always `await old_container.stop()` fully before calling `new_container.start()`. Use sequential awaits, not gather, for stop-then-start sequences on the same child_id.
**Warning signs:** aiosqlite "database is locked" errors during restart.

### Pitfall 5: python-statemachine Async Initial State
**What goes wrong:** If Supervisor uses a ContainerLifecycle FSM, the initial state is not activated in `__init__` when async callbacks are involved.
**Why it happens:** python-statemachine 3.0 cannot await during `__init__`, so async-backed FSMs need explicit `activate_initial_state()`.
**How to avoid:** If supervisor has its own FSM, call `await activate_initial_state()` in the supervisor's `start()` method. Or avoid FSM for supervisor entirely -- a simple state string may suffice.
**Warning signs:** `configuration` returns `[None]`, transitions fail silently.

## Code Examples

### Restart Strategy: rest_for_one

```python
# Verified pattern from Erlang OTP semantics
async def _restart_rest(self, failed_id: str) -> None:
    """Restart failed child and all children started after it."""
    # Find index of failed child in ordered spec list
    failed_idx = next(
        i for i, spec in enumerate(self._child_specs)
        if spec.child_id == failed_id
    )
    # Children to restart: failed + all after it (in spec order)
    specs_to_restart = self._child_specs[failed_idx:]

    # Stop affected children in REVERSE order
    for spec in reversed(specs_to_restart):
        child = self._children.get(spec.child_id)
        if child is not None and child.state not in ("stopped", "destroyed"):
            await child.stop()

    # Restart in FORWARD (spec) order
    for spec in specs_to_restart:
        await self._start_child(spec)
```

### RestartPolicy Integration

```python
# Source: Erlang OTP child restart policy semantics
def _should_restart(self, spec: ChildSpec, container: AgentContainer) -> bool:
    """Determine if a child should be restarted based on its policy."""
    match spec.restart_policy:
        case RestartPolicy.PERMANENT:
            return True  # Always restart
        case RestartPolicy.TEMPORARY:
            return False  # Never restart
        case RestartPolicy.TRANSIENT:
            # Restart only on abnormal exit (errored state)
            return container.state == "errored"
```

### Two-Level Hierarchy Setup

```python
# SUPV-01: CompanyRoot -> ProjectSupervisor -> AgentContainers
async def build_supervision_tree(
    project_specs: list[ChildSpec],
    data_dir: Path,
    comm_port: CommunicationPort | None = None,
) -> Supervisor:
    """Build the two-level supervision tree."""
    # Level 2: ProjectSupervisor manages agent containers
    project_sup = Supervisor(
        supervisor_id="project-sup",
        strategy=RestartStrategy.ONE_FOR_ONE,
        child_specs=project_specs,
        max_restarts=3,
        window_seconds=600,
    )

    # Level 1: CompanyRoot manages ProjectSupervisor(s)
    # CompanyRoot is a supervisor that treats ProjectSupervisor as a child
    company_root = CompanyRoot(
        supervisor_id="company-root",
        strategy=RestartStrategy.ONE_FOR_ONE,
        children=[project_sup],
        comm_port=comm_port,  # For Discord escalation alerts
    )

    await company_root.start()
    return company_root
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual process monitoring | Structured concurrency (asyncio TaskGroups) | Python 3.11+ (2022) | TaskGroups auto-cancel sibling tasks on failure -- useful but TOO aggressive for supervision (we want selective restart, not cancel-all) |
| Polling-based health checks | Event-driven callbacks + asyncio.Event | Current best practice | Instant failure detection, no polling overhead |
| Thread-per-child | asyncio Task-per-child | Python 3.4+ async maturity | Thousands of tasks with near-zero overhead |

**Note on TaskGroups:** Python 3.11+ `asyncio.TaskGroup` provides structured concurrency but has cancel-all-on-failure semantics. This is the OPPOSITE of what one_for_one needs. Do NOT use TaskGroup for supervision -- use bare `asyncio.create_task()` with manual monitoring instead.

**Deprecated/outdated:**
- `asyncio.ensure_future()`: Use `asyncio.create_task()` instead (Python 3.7+)
- `loop.create_task()`: Use module-level `asyncio.create_task()` (Python 3.10+)

## Open Questions

1. **Should Supervisor subclass AgentContainer?**
   - What we know: Erlang supervisors ARE processes. Making Supervisor an AgentContainer subclass would allow supervisors to be supervised uniformly. But supervisors don't need memory stores or most container features.
   - What's unclear: Whether the health tree (Phase 5) needs supervisors to be containers.
   - Recommendation: Start with Supervisor as a standalone class that implements a minimal interface (start/stop/state). If Phase 5 needs it to be a container, refactor is straightforward.

2. **How does CompanyRoot alert via Discord when CommunicationPort is not yet implemented?**
   - What we know: CommunicationPort is a Protocol. No concrete implementation exists yet.
   - What's unclear: When the Discord-backed implementation arrives (Phase 5/6/8?).
   - Recommendation: CompanyRoot accepts an optional `on_escalation: Callable[[str], Awaitable[None]]` callback. In production, this callback sends to Discord. In tests, it captures the alert message. This avoids depending on unimplemented CommunicationPort.

3. **Supervisor restart intensity: per-supervisor or per-child?**
   - What we know: Erlang tracks at supervisor level (3 total restarts across all children, not 3 per child).
   - Recommendation: Follow Erlang semantics -- per-supervisor tracking. The ChildSpec already has max_restarts/window fields which configure the SUPERVISOR, not the individual child.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 0.24+ |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_supervisor.py tests/test_restart_strategies.py tests/test_restart_tracker.py tests/test_supervision_tree.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SUPV-01 | Two-level hierarchy starts and supervises children | integration | `uv run pytest tests/test_supervision_tree.py -x -q` | Wave 0 |
| SUPV-02 | one_for_one restarts only failed child | unit | `uv run pytest tests/test_restart_strategies.py::test_one_for_one -x -q` | Wave 0 |
| SUPV-03 | all_for_one restarts all siblings | unit | `uv run pytest tests/test_restart_strategies.py::test_all_for_one -x -q` | Wave 0 |
| SUPV-04 | rest_for_one restarts failed + later children | unit | `uv run pytest tests/test_restart_strategies.py::test_rest_for_one -x -q` | Wave 0 |
| SUPV-05 | 3 crashes in 10-minute window triggers limit | unit | `uv run pytest tests/test_restart_tracker.py -x -q` | Wave 0 |
| SUPV-06 | Escalation to parent; top-level alerts owner | integration | `uv run pytest tests/test_supervision_tree.py::test_escalation -x -q` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_supervisor.py tests/test_restart_strategies.py tests/test_restart_tracker.py tests/test_supervision_tree.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_supervisor.py` -- covers Supervisor base class start/stop/add_child
- [ ] `tests/test_restart_strategies.py` -- covers SUPV-02, SUPV-03, SUPV-04
- [ ] `tests/test_restart_tracker.py` -- covers SUPV-05 sliding window
- [ ] `tests/test_supervision_tree.py` -- covers SUPV-01, SUPV-06 integration

## Sources

### Primary (HIGH confidence)
- [Erlang OTP Supervisor Principles](https://www.erlang.org/doc/system/sup_princ.html) - restart strategies, MaxR/MaxT semantics, escalation behavior
- [Erlang OTP Design Principles](https://www.erlang.org/doc/system/design_principles.html) - supervision tree overview
- [python-statemachine 3.0 async docs](https://python-statemachine.readthedocs.io/en/latest/async.html) - async gotchas, activate_initial_state requirement
- Phase 1 codebase (container.py, child_spec.py, state_machine.py) - existing API surface verified by reading source

### Secondary (MEDIUM confidence)
- [Learn You Some Erlang: Supervisors](https://learnyousomeerlang.com/supervisors) - detailed walkthrough of restart strategies and intensity
- [FauxTP on GitHub](https://github.com/fizzAI/fauxtp) - Python OTP implementation reference (uses anyio, not directly applicable but confirms patterns)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all asyncio stdlib
- Architecture: HIGH - Erlang OTP patterns are well-documented and directly translatable to asyncio Tasks
- Pitfalls: HIGH - race conditions and cascade issues are well-known in supervision implementations

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable domain, patterns unlikely to change)
