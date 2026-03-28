# Phase 7: Autonomy Features - Research

**Researched:** 2026-03-28
**Domain:** Living backlog queue, delegation protocol, crash-safe project state
**Confidence:** HIGH

## Summary

Phase 7 builds three interconnected autonomy features on top of the existing container/supervisor infrastructure (Phases 1-6). The PM (FulltimeAgent) gets a living milestone backlog -- a mutable queue with operations like append, insert_urgent, reorder, and cancel. GsdAgents consume work items from this queue instead of a static list. ContinuousAgents gain delegation capability -- they request task spawns through the supervisor, which validates caps and rate limits before spawning short-lived GsdAgents. Finally, project state ownership is formalized: the PM owns the backlog and project state, agents read assignments and write completions, and crashes never corrupt state.

The existing codebase provides strong foundations. MemoryStore (per-agent SQLite with WAL mode) handles persistence. FulltimeAgent already has an event queue and _handle_event override point. Supervisor already spawns containers from ChildSpecs. The main work is: (1) a BacklogQueue data structure stored in PM's MemoryStore, (2) a DelegationProtocol that routes spawn requests through supervisors with policy enforcement, and (3) transactional patterns ensuring crash safety for state mutations.

**Primary recommendation:** Build the backlog as a Pydantic-modeled JSON list in PM's MemoryStore KV, implement delegation as a request/response protocol through supervisors with a DelegationPolicy dataclass for caps/rate limits, and use SQLite transactions (already WAL-enabled) for crash-safe state writes.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices at Claude's discretion (pure infrastructure phase).

Key technical anchors from requirements:
- Living milestone backlog: PM-managed mutable queue (append, insert_after, insert_urgent, reorder, cancel) (AUTO-01)
- GsdAgent consumes work from living queue, not static list (AUTO-02)
- Delegation protocol: ContinuousAgent requests task spawns through supervisor with hard caps and rate limits (AUTO-03)
- Supervisor validates delegation requests, enforces policy, spawns short-lived task agents (AUTO-04)
- Project state owned by PM -- agents read assignments and write completions, crash never corrupts (AUTO-05)
- Scheduler triggers already built in Phase 4 (AUTO-06 complete)

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase.

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTO-01 | Living milestone backlog -- PM-managed mutable queue (append, insert_after, insert_urgent, reorder, cancel) | BacklogQueue class with Pydantic model, stored as JSON in PM's MemoryStore KV. Operations are atomic writes. |
| AUTO-02 | GSD state machine consumes milestones from the living queue, not a static list | GsdAgent gets `claim_next()` method that reads from PM's backlog via a BacklogReader protocol. PM marks items as assigned. |
| AUTO-03 | Delegation protocol -- ContinuousAgent requests task spawns through supervisor with hard caps and rate limits | DelegationRequest dataclass + DelegationPolicy (max_concurrent, rate_limit_per_hour). ContinuousAgent calls `request_delegation()` on supervisor. |
| AUTO-04 | Supervisor validates delegation requests, enforces policy, spawns short-lived task agents | Supervisor gains `handle_delegation_request()` method that checks policy, creates ChildSpec with TEMPORARY restart policy, spawns GsdAgent. |
| AUTO-05 | Project state owned by PM -- agents read assignments and write completions. Agent crash never corrupts. | PM's MemoryStore is the single source of truth. Agents write completion status via events posted to PM's queue. SQLite WAL + atomic writes ensure crash safety. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.11.x | BacklogItem, DelegationRequest, DelegationPolicy models | Already in stack. Type-safe serialization to/from MemoryStore JSON. |
| aiosqlite | 0.21.x | MemoryStore backend (already in use) | Already the persistence layer. WAL mode provides crash safety. |
| asyncio (stdlib) | N/A | Locks, queues, task spawning | Already used throughout. asyncio.Lock for backlog mutations. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-statemachine | 3.0.x | FSM for GsdLifecycle, EventDrivenLifecycle | Already in use. No changes needed to FSMs. |
| dataclasses (stdlib) | N/A | Internal-only structures (DelegationResult) | When Pydantic validation overhead is unnecessary. |

No new dependencies needed. Phase 7 builds entirely on the existing stack.

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
├── autonomy/
│   ├── __init__.py
│   ├── backlog.py          # BacklogQueue, BacklogItem model
│   ├── delegation.py       # DelegationRequest, DelegationPolicy, DelegationResult
│   └── project_state.py    # ProjectStateManager (crash-safe PM state)
├── agent/
│   ├── fulltime_agent.py   # Extended: backlog ownership, state management
│   └── gsd_agent.py        # Extended: queue consumption
└── supervisor/
    └── supervisor.py        # Extended: delegation request handling
```

### Pattern 1: BacklogQueue as JSON in MemoryStore KV
**What:** The living backlog is a list of BacklogItem Pydantic models, serialized as a single JSON string in PM's MemoryStore KV under key `backlog`.
**When to use:** Always -- this is the only backlog storage pattern.
**Why:** MemoryStore already exists per-agent with WAL mode. A single KV entry for the whole queue means atomic reads/writes (one SQLite write = one transaction). No need for a separate table or database.
**Example:**
```python
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
import uuid

class BacklogItemStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class BacklogItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    description: str = ""
    priority: int = 0  # lower = higher priority
    status: BacklogItemStatus = BacklogItemStatus.PENDING
    assigned_to: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

class BacklogQueue:
    """Mutable queue stored in PM's MemoryStore."""

    def __init__(self, memory: MemoryStore) -> None:
        self._memory = memory
        self._lock = asyncio.Lock()
        self._items: list[BacklogItem] = []

    async def load(self) -> None:
        """Load backlog from MemoryStore."""
        raw = await self._memory.get("backlog")
        if raw:
            self._items = [BacklogItem.model_validate(i) for i in json.loads(raw)]

    async def _persist(self) -> None:
        """Write current state to MemoryStore (call under _lock)."""
        data = json.dumps([i.model_dump() for i in self._items])
        await self._memory.set("backlog", data)

    async def append(self, item: BacklogItem) -> None:
        async with self._lock:
            self._items.append(item)
            await self._persist()

    async def insert_urgent(self, item: BacklogItem) -> None:
        """Insert at position 0 (highest priority)."""
        async with self._lock:
            self._items.insert(0, item)
            await self._persist()

    async def insert_after(self, after_id: str, item: BacklogItem) -> None:
        async with self._lock:
            for i, existing in enumerate(self._items):
                if existing.item_id == after_id:
                    self._items.insert(i + 1, item)
                    await self._persist()
                    return
            raise ValueError(f"Item {after_id} not found")

    async def reorder(self, item_id: str, new_position: int) -> None:
        async with self._lock:
            item = None
            for i, existing in enumerate(self._items):
                if existing.item_id == item_id:
                    item = self._items.pop(i)
                    break
            if item is None:
                raise ValueError(f"Item {item_id} not found")
            self._items.insert(min(new_position, len(self._items)), item)
            await self._persist()

    async def cancel(self, item_id: str) -> None:
        async with self._lock:
            for item in self._items:
                if item.item_id == item_id:
                    item.status = BacklogItemStatus.CANCELLED
                    await self._persist()
                    return
            raise ValueError(f"Item {item_id} not found")

    async def claim_next(self, agent_id: str) -> BacklogItem | None:
        """Claim the first PENDING item. Returns None if queue empty."""
        async with self._lock:
            for item in self._items:
                if item.status == BacklogItemStatus.PENDING:
                    item.status = BacklogItemStatus.ASSIGNED
                    item.assigned_to = agent_id
                    await self._persist()
                    return item
            return None
```

### Pattern 2: Delegation Protocol through Supervisor
**What:** ContinuousAgent creates a DelegationRequest. Supervisor validates against DelegationPolicy (caps, rate limits), then spawns a TEMPORARY GsdAgent.
**When to use:** When a ContinuousAgent (e.g., code reviewer, monitor) needs to spawn a short-lived task agent.
**Example:**
```python
from dataclasses import dataclass, field
from pydantic import BaseModel
import time

class DelegationPolicy(BaseModel):
    """Policy constraints for delegation requests."""
    max_concurrent_delegations: int = 3
    max_delegations_per_hour: int = 10
    allowed_agent_types: list[str] = ["gsd"]

@dataclass
class DelegationRequest:
    """A request from a ContinuousAgent to spawn a task agent."""
    requester_id: str
    task_description: str
    agent_type: str = "gsd"
    context_overrides: dict = field(default_factory=dict)

@dataclass
class DelegationResult:
    """Response to a delegation request."""
    approved: bool
    agent_id: str | None = None
    reason: str = ""

class DelegationTracker:
    """Tracks active and historical delegations for rate limiting."""

    def __init__(self, policy: DelegationPolicy) -> None:
        self._policy = policy
        self._active: dict[str, set[str]] = {}  # requester -> {agent_ids}
        self._history: list[float] = []  # timestamps

    def can_delegate(self, requester_id: str) -> tuple[bool, str]:
        active_count = len(self._active.get(requester_id, set()))
        if active_count >= self._policy.max_concurrent_delegations:
            return False, f"Max concurrent ({self._policy.max_concurrent_delegations}) reached"

        cutoff = time.monotonic() - 3600
        recent = [t for t in self._history if t > cutoff]
        if len(recent) >= self._policy.max_delegations_per_hour:
            return False, f"Rate limit ({self._policy.max_delegations_per_hour}/hr) reached"

        return True, ""

    def record_delegation(self, requester_id: str, agent_id: str) -> None:
        self._active.setdefault(requester_id, set()).add(agent_id)
        self._history.append(time.monotonic())

    def record_completion(self, requester_id: str, agent_id: str) -> None:
        agents = self._active.get(requester_id)
        if agents:
            agents.discard(agent_id)
```

### Pattern 3: Crash-Safe Project State via PM Ownership
**What:** PM's MemoryStore is the single source of truth for project state. Agents don't write to project state directly -- they post events to PM's queue, and PM processes them atomically.
**When to use:** All project state mutations.
**Why:** If an agent crashes mid-write, the PM's state is unaffected because the agent never wrote to it. The event either made it to the queue or it didn't. PM processes events one at a time (already implemented in `process_next_event()`).
**Example:**
```python
# Agent reports completion via event
await pm.post_event({
    "type": "task_completed",
    "agent_id": "gsd-dev-1",
    "item_id": "abc123",
    "result": "success",
})

# PM handles it atomically in _handle_event()
async def _handle_event(self, event: dict) -> None:
    if event["type"] == "task_completed":
        await self._backlog.mark_completed(event["item_id"])
        # State is now persisted in PM's MemoryStore
```

### Anti-Patterns to Avoid
- **Agents writing to PM's MemoryStore directly:** Violates ownership. If agent crashes mid-write, PM state corrupts. Always go through PM's event queue.
- **Separate database for backlog:** Adds a second persistence layer. PM already has MemoryStore with WAL mode. Don't duplicate.
- **Polling for new work:** GsdAgent should not poll the backlog. The PM (or supervisor) assigns work by posting events or calling methods on the agent.
- **Shared mutable state between agents:** Each agent has its own MemoryStore. Cross-agent state flows through events, not shared memory.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic JSON persistence | Custom file locking, manual fsync | MemoryStore.set() (SQLite WAL) | SQLite WAL mode already guarantees atomic writes. Single KV entry = single transaction. |
| Rate limiting | Custom token bucket, sliding window | DelegationTracker with time.monotonic() | Simple enough that a 20-line class suffices, but don't build a generic rate limiter framework. |
| Agent spawn orchestration | Custom process manager | Supervisor._start_child() + ChildSpec(TEMPORARY) | Supervisor already handles child lifecycle, monitoring, and cleanup. |
| Event-driven state updates | Custom pub/sub or file watchers | FulltimeAgent.post_event() + _handle_event() | Already implemented. PM's event queue is the coordination mechanism. |

**Key insight:** The existing infrastructure (MemoryStore, Supervisor, FulltimeAgent event queue) already provides the primitives. Phase 7 composes them into higher-level features rather than building new infrastructure.

## Common Pitfalls

### Pitfall 1: Backlog Corruption on Concurrent Access
**What goes wrong:** Two operations (e.g., `insert_urgent` + `claim_next`) interleave, one overwrites the other's write.
**Why it happens:** JSON-in-KV means read-modify-write. Without locking, TOCTOU bugs emerge.
**How to avoid:** Every BacklogQueue method acquires `self._lock` before reading and holds it through the write. The asyncio.Lock is sufficient because we're single-process.
**Warning signs:** Items disappearing from the backlog, duplicate assignments.

### Pitfall 2: Delegated Agent Leaks
**What goes wrong:** Supervisor spawns a GsdAgent via delegation, the agent finishes or crashes, but the DelegationTracker never records completion. Rate limits never release.
**Why it happens:** Forgotten cleanup path -- the on_state_change callback needs to detect when delegated agents reach stopped/destroyed.
**How to avoid:** Wire the supervisor's existing `_make_state_change_callback` to also call `DelegationTracker.record_completion()` when a delegated child terminates.
**Warning signs:** `can_delegate()` always returns False after running for a while.

### Pitfall 3: PM Event Queue Unbounded Growth
**What goes wrong:** If PM processes events slower than they arrive (many agents reporting), the asyncio.Queue grows unboundedly.
**Why it happens:** asyncio.Queue() with no maxsize has no backpressure.
**How to avoid:** Set a reasonable maxsize (e.g., 100) on the event queue. Or, since events are durable (posted one at a time by agents that will retry), accept that the queue is bounded by the number of active agents (typically <20).
**Warning signs:** Memory usage growing, event processing latency increasing.

### Pitfall 4: Stale Assignments After Agent Crash
**What goes wrong:** Agent claims a backlog item, crashes, item stays "assigned" forever.
**Why it happens:** The agent crashed before posting a completion event to PM.
**How to avoid:** PM should have a timeout mechanism -- if an assigned item hasn't been completed within a reasonable window, the PM can reassign it. Implement as part of PM's periodic event processing (or as a ContinuousAgent cycle step).
**Warning signs:** Items stuck in ASSIGNED status with no active agent.

### Pitfall 5: Delegation Request Reaches Wrong Supervisor
**What goes wrong:** ContinuousAgent sends delegation request but it goes to CompanyRoot instead of ProjectSupervisor.
**Why it happens:** Delegation needs to target the correct supervisor in the hierarchy.
**How to avoid:** ContinuousAgent's parent_id in ContainerContext identifies its ProjectSupervisor. Delegation requests should flow to the agent's immediate supervisor (the ProjectSupervisor that manages it).
**Warning signs:** Delegated agents spawned at wrong level of supervision tree.

## Code Examples

### BacklogQueue Integration with FulltimeAgent
```python
# In fulltime_agent.py (extended)
class FulltimeAgent(AgentContainer):
    async def start(self) -> None:
        await super().start()
        self._backlog = BacklogQueue(self.memory)
        await self._backlog.load()

    async def _handle_event(self, event: dict) -> None:
        event_type = event.get("type")
        if event_type == "task_completed":
            await self._backlog.mark_completed(event["item_id"])
        elif event_type == "task_failed":
            await self._backlog.mark_pending(event["item_id"])  # re-queue
        elif event_type == "add_backlog_item":
            item = BacklogItem(**event["item"])
            await self._backlog.append(item)
```

### Supervisor Delegation Handling
```python
# In supervisor.py (extended)
class Supervisor:
    async def handle_delegation_request(
        self, request: DelegationRequest
    ) -> DelegationResult:
        if self._delegation_tracker is None:
            return DelegationResult(approved=False, reason="Delegation not enabled")

        can, reason = self._delegation_tracker.can_delegate(request.requester_id)
        if not can:
            return DelegationResult(approved=False, reason=reason)

        # Build ChildSpec for temporary GsdAgent
        agent_id = f"delegated-{request.requester_id}-{uuid.uuid4().hex[:6]}"
        spec = ChildSpec(
            child_id=agent_id,
            agent_type=request.agent_type,
            context=ContainerContext(
                agent_id=agent_id,
                agent_type=request.agent_type,
                parent_id=self.supervisor_id,
                project_id=self._get_project_id(),
            ),
            restart_policy=RestartPolicy.TEMPORARY,  # never restart
        )

        # Spawn the agent
        self._child_specs.append(spec)
        await self._start_child(spec)
        self._delegation_tracker.record_delegation(request.requester_id, agent_id)

        return DelegationResult(approved=True, agent_id=agent_id)
```

### GsdAgent Consuming from Queue
```python
# GsdAgent reads assignment from its own MemoryStore (set by PM)
class GsdAgent(AgentContainer):
    async def get_assignment(self) -> dict | None:
        """Read current assignment from memory (set by PM via event)."""
        raw = await self.memory.get("current_assignment")
        if raw:
            return json.loads(raw)
        return None
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Static milestone list | Living mutable backlog queue | Phase 7 | PM can react to changing priorities without restarting agents |
| Manual agent spawning via CLI | Delegation protocol through supervisor | Phase 7 | ContinuousAgents can autonomously request help for sub-tasks |
| Agents write project state directly | PM owns state, agents communicate via events | Phase 7 | Crash safety guaranteed by single-writer pattern |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_backlog.py tests/test_delegation.py tests/test_project_state.py -x` |
| Full suite command | `uv run pytest tests/ -x --ignore=tests/test_interaction_regression.py` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTO-01 | BacklogQueue append/insert_urgent/insert_after/reorder/cancel operations | unit | `uv run pytest tests/test_backlog.py -x` | -- Wave 0 |
| AUTO-02 | GsdAgent claims next item from backlog, PM assigns work | unit | `uv run pytest tests/test_backlog.py::TestClaimNext -x` | -- Wave 0 |
| AUTO-03 | ContinuousAgent requests delegation, respects caps/rate limits | unit | `uv run pytest tests/test_delegation.py -x` | -- Wave 0 |
| AUTO-04 | Supervisor validates delegation, spawns TEMPORARY GsdAgent, cleans up | unit | `uv run pytest tests/test_delegation.py::TestSupervisorDelegation -x` | -- Wave 0 |
| AUTO-05 | PM owns state, agent crash does not corrupt backlog/assignments | unit | `uv run pytest tests/test_project_state.py -x` | -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_backlog.py tests/test_delegation.py tests/test_project_state.py -x`
- **Per wave merge:** `uv run pytest tests/ -x --ignore=tests/test_interaction_regression.py`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_backlog.py` -- covers AUTO-01, AUTO-02
- [ ] `tests/test_delegation.py` -- covers AUTO-03, AUTO-04
- [ ] `tests/test_project_state.py` -- covers AUTO-05

## Sources

### Primary (HIGH confidence)
- Existing codebase: `src/vcompany/container/memory_store.py` -- MemoryStore API (KV + checkpoints, WAL mode)
- Existing codebase: `src/vcompany/agent/fulltime_agent.py` -- FulltimeAgent event queue pattern
- Existing codebase: `src/vcompany/supervisor/supervisor.py` -- Supervisor child lifecycle management
- Existing codebase: `src/vcompany/container/child_spec.py` -- ChildSpec with RestartPolicy.TEMPORARY
- Existing codebase: `src/vcompany/container/factory.py` -- create_container() from ChildSpec

### Secondary (MEDIUM confidence)
- SQLite WAL mode crash safety guarantees -- well-documented in SQLite documentation, verified by existing MemoryStore usage

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies, all patterns use existing infrastructure
- Architecture: HIGH - Directly extends existing FulltimeAgent, Supervisor, MemoryStore patterns established in Phases 1-6
- Pitfalls: HIGH - Identified from code analysis of existing locking patterns and lifecycle callbacks

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable -- internal architecture, no external dependency changes)
