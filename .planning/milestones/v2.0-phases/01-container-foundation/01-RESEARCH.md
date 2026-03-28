# Phase 1: Container Foundation - Research

**Researched:** 2026-03-27
**Domain:** Agent container lifecycle, state machines, persistent memory, health reporting
**Confidence:** HIGH

## Summary

Phase 1 builds the foundational AgentContainer abstraction that wraps every agent in v2. The core deliverables are: (1) a validated lifecycle state machine with 6 states, (2) per-agent SQLite-based persistent memory, (3) a child specification registry for supervisor consumption, (4) self-reported health, and (5) a communication interface designed for Discord-only message passing.

The existing codebase uses Pydantic models extensively for validation and configuration. The v1 `AgentManager` and `CrashTracker` handle lifecycle and crash recovery today but will be replaced by the container abstraction in later phases. This phase creates new modules under `src/vcompany/container/` that sit alongside the existing code without modifying it.

**Primary recommendation:** Use `python-statemachine` 3.0.0 for the lifecycle FSM (well-maintained, Pythonic, handles transition validation natively), `aiosqlite` 0.22.1 for async SQLite memory persistence, and Pydantic models for all data structures (HealthReport, ContainerContext, ChildSpec) following existing project patterns.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked. All implementation choices are at Claude's discretion per CONTEXT.md.

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key technical anchors from requirements:
- State machine states: CREATING, RUNNING, SLEEPING, ERRORED, STOPPED, DESTROYED (CONT-01)
- Invalid transitions must raise validation errors (CONT-02)
- Container context: agent_id, type, parent_id, project_id, owned dirs, GSD mode, system prompt (CONT-03)
- Per-agent SQLite file for memory_store (CONT-04)
- Child specification registry for supervisor consumption (CONT-05)
- Communication designed for Discord-only message passing -- no file IPC, no in-memory callbacks (CONT-06)
- HealthReport: state, inner_state, uptime, last_heartbeat, error_count, last_activity (HLTH-01)

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase with clear scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONT-01 | Every agent wrapped in AgentContainer with validated lifecycle FSM (CREATING, RUNNING, SLEEPING, ERRORED, STOPPED, DESTROYED) | python-statemachine 3.0.0 provides declarative state/transition definition with `State` and `.to()` chaining. See Architecture Patterns. |
| CONT-02 | State transitions validated -- impossible transitions rejected with errors | python-statemachine raises `TransitionNotAllowed` on invalid transitions by default. Only declared transitions are permitted. |
| CONT-03 | Each container carries its own context (agent_id, type, parent_id, project_id, owned dirs, GSD mode, system prompt) | Pydantic BaseModel for ContainerContext -- follows existing `AgentConfig` and `AgentEntry` patterns in the codebase. |
| CONT-04 | Per-agent SQLite file for memory_store (checkpoints, seen items, decisions, config) | aiosqlite 0.22.1 with a thin MemoryStore wrapper class. SQLite file per agent at `state/containers/{agent_id}/memory.db`. |
| CONT-05 | Child specification registry declares container types with config and restart policy | Pydantic model for ChildSpec + a ChildSpecRegistry dict-based registry. Supervisors (Phase 2) read specs to instantiate containers. |
| CONT-06 | All communication through Discord -- no file IPC, no in-memory callbacks | Abstract `CommunicationPort` protocol class with `send_message()` and `receive_message()` methods. Discord implementation deferred to Phase 5/6. This phase defines the interface only. |
| HLTH-01 | Each container self-reports HealthReport (state, inner_state, uptime, last_heartbeat, error_count, last_activity) | Pydantic model for HealthReport. Container emits report on every state transition via a callback/event hook on the state machine. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-statemachine | 3.0.0 | Lifecycle FSM | Declarative state/transition definition. Raises on invalid transitions. Enter/exit callbacks. Active maintenance (Feb 2026 release). |
| aiosqlite | 0.22.1 | Async SQLite for memory_store | Async bridge to stdlib sqlite3. Non-blocking for use in async contexts. Per-agent file isolation. |
| pydantic | 2.11.x (existing) | Data models for ContainerContext, HealthReport, ChildSpec | Already in project. Validated on construction. Serializable to JSON. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sqlite3 (stdlib) | N/A | Sync SQLite fallback | For sync CLI contexts where aiosqlite's async is unnecessary |
| enum (stdlib) | N/A | ContainerState, RestartPolicy enums | State and policy definitions |
| datetime (stdlib) | N/A | Timestamps for health reports | uptime, last_heartbeat, last_activity |
| abc (stdlib) | N/A | Abstract base for CommunicationPort | Define interface without implementation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| python-statemachine | Hand-rolled enum + dict FSM | Simpler for 6 states, but loses enter/exit callbacks, transition guards, and validation for free. python-statemachine is small (no heavy deps) and prevents reimplementing what it already does well. |
| python-statemachine | pytransitions/transitions | Older library, dictionary-based config instead of declarative classes. Less Pythonic. python-statemachine 3.0 is more modern. |
| aiosqlite | sqlite3 (sync only) | Works for sync contexts but blocks the event loop. Since the monitor and bot are async, aiosqlite is necessary. Provide sync wrappers where needed. |

**Installation:**
```bash
uv add python-statemachine aiosqlite
```

**Version verification:** python-statemachine 3.0.0 (PyPI, 2026-02-24), aiosqlite 0.22.1 (PyPI, 2025-12-23). Both support Python >=3.9, compatible with project's >=3.12 requirement.

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/container/
    __init__.py          # Public API exports
    state_machine.py     # ContainerLifecycle FSM (python-statemachine)
    context.py           # ContainerContext Pydantic model
    health.py            # HealthReport Pydantic model
    memory_store.py      # MemoryStore class (aiosqlite wrapper)
    child_spec.py        # ChildSpec model + ChildSpecRegistry
    communication.py     # CommunicationPort protocol/ABC
    container.py         # AgentContainer class (ties everything together)
```

### Pattern 1: Declarative State Machine with python-statemachine
**What:** Define the 6-state lifecycle as a python-statemachine StateChart subclass with explicit transitions.
**When to use:** Every AgentContainer instance gets its own FSM instance.
**Example:**
```python
from statemachine import StateMachine, State

class ContainerLifecycle(StateMachine):
    # States
    creating = State(initial=True)
    running = State()
    sleeping = State()
    errored = State()
    stopped = State()
    destroyed = State(final=True)

    # Valid transitions
    start = creating.to(running)
    sleep = running.to(sleeping)
    wake = sleeping.to(running)
    error = creating.to(errored) | running.to(errored) | sleeping.to(errored)
    recover = errored.to(running)
    stop = running.to(stopped) | sleeping.to(stopped) | errored.to(stopped)
    destroy = stopped.to(destroyed) | errored.to(destroyed)

    # Callbacks for health reporting
    def after_transition(self, event, state):
        """Called after every transition -- emit HealthReport."""
        if self._container:
            self._container._emit_health_report()
```

**Key behavior:** Any transition not declared above (e.g., `stopped.to(running)`) will raise `TransitionNotAllowed` automatically. This satisfies CONT-02 without manual validation code.

### Pattern 2: Pydantic Model for Container Context (CONT-03)
**What:** Immutable container metadata set at creation time.
**Example:**
```python
from pydantic import BaseModel

class ContainerContext(BaseModel):
    agent_id: str
    agent_type: str  # "gsd", "continuous", "fulltime", "company"
    parent_id: str | None = None
    project_id: str | None = None
    owned_dirs: list[str] = []
    gsd_mode: str = "full"
    system_prompt: str = ""
```

### Pattern 3: Thin MemoryStore over aiosqlite (CONT-04)
**What:** Key-value + checkpoint persistence per agent.
**When to use:** Every container gets a MemoryStore initialized with its agent_id.
**Example:**
```python
import aiosqlite

class MemoryStore:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await self._db.commit()

    async def get(self, key: str) -> str | None:
        async with self._db.execute(
            "SELECT value FROM kv WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set(self, key: str, value: str) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO kv (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, datetime.now(timezone.utc).isoformat()),
        )
        await self._db.commit()

    async def checkpoint(self, label: str, data: str) -> None:
        await self._db.execute(
            "INSERT INTO checkpoints (label, data, created_at) VALUES (?, ?, ?)",
            (label, data, datetime.now(timezone.utc).isoformat()),
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
```

### Pattern 4: Communication Port Protocol (CONT-06)
**What:** Abstract interface that containers use to communicate. Discord implements it later.
**When to use:** Define in Phase 1, implement in later phases.
**Example:**
```python
from typing import Protocol

class CommunicationPort(Protocol):
    async def send_message(self, target: str, content: str) -> bool: ...
    async def receive_message(self) -> Message | None: ...
```

**Key design:** Containers hold a reference to a CommunicationPort. They never import discord.py or know about file paths. This satisfies CONT-06 (no file IPC, no in-memory callbacks) and prepares for MIGR-04 (v3 channel abstraction).

### Pattern 5: Child Specification (CONT-05)
**What:** Declarative spec for how a supervisor creates a container.
**Example:**
```python
class RestartPolicy(str, Enum):
    PERMANENT = "permanent"    # Always restart
    TEMPORARY = "temporary"    # Never restart
    TRANSIENT = "transient"    # Restart only on abnormal exit

class ChildSpec(BaseModel):
    child_id: str
    agent_type: str
    context: ContainerContext
    restart_policy: RestartPolicy = RestartPolicy.PERMANENT
    max_restarts: int = 3
    restart_window_seconds: int = 600  # 10 minutes per SUPV-05

class ChildSpecRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ChildSpec] = {}

    def register(self, spec: ChildSpec) -> None:
        self._specs[spec.child_id] = spec

    def get(self, child_id: str) -> ChildSpec | None:
        return self._specs.get(child_id)

    def all_specs(self) -> list[ChildSpec]:
        return list(self._specs.values())
```

### Anti-Patterns to Avoid
- **Direct container-to-container references:** Never pass one container instance to another. All communication goes through CommunicationPort. This is the core invariant of CONT-06.
- **Shared SQLite database:** Each agent gets its own SQLite file. No shared DB (per Out of Scope). This prevents contention and corruption.
- **Mixing sync and async in MemoryStore:** Keep MemoryStore async-only. If sync access is needed (e.g., from CLI), provide a separate sync utility function that opens a new connection, not a mixed-mode class.
- **Hardcoding transition logic in if/elif chains:** Use python-statemachine's declarative transitions. Hand-rolled transition matrices become unmaintainable when Phase 3/4 add inner FSMs.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| State machine with transition validation | Dict of valid transitions + manual checking | python-statemachine 3.0.0 | Enter/exit callbacks, transition guards, automatic invalid transition rejection, visual debugging. ~200 lines you don't write. |
| Async SQLite access | Thread pool + sqlite3 manual wrapping | aiosqlite 0.22.1 | Correct thread safety, connection lifecycle, context managers. Threading bugs are subtle. |
| Data validation for models | Manual `__init__` checks | Pydantic BaseModel (already in project) | Validation on construction, JSON serialization, immutability via `frozen=True`. |

## Common Pitfalls

### Pitfall 1: SQLite WAL Mode for Concurrent Reads
**What goes wrong:** Default SQLite journal mode blocks readers during writes. Monitor reading health while container writes checkpoint = contention.
**Why it happens:** Default journal mode is DELETE which holds exclusive locks during writes.
**How to avoid:** Enable WAL mode on connection: `PRAGMA journal_mode=WAL;` in MemoryStore.open().
**Warning signs:** "database is locked" errors under concurrent access.

### Pitfall 2: State Machine Instance Per Container
**What goes wrong:** Sharing a single FSM instance across containers. State leaks between agents.
**Why it happens:** Treating the FSM as a singleton.
**How to avoid:** Each AgentContainer creates its own `ContainerLifecycle()` instance.
**Warning signs:** One agent's state transition affecting another's reported state.

### Pitfall 3: aiosqlite Connection Lifecycle
**What goes wrong:** Not closing connections properly. SQLite files stay locked after container stops.
**Why it happens:** aiosqlite 0.22.x no longer inherits from Thread. Must `await connection.close()` or use context manager.
**How to avoid:** Always use `async with` for connections, or explicitly close in container's destroy/stop handler.
**Warning signs:** "database is locked" on restart, file handles leaking.

### Pitfall 4: Circular Import Between Container and State Machine
**What goes wrong:** container.py imports state_machine.py which imports container.py for type hints.
**Why it happens:** State machine callbacks need container reference for health reporting.
**How to avoid:** Pass container to FSM via constructor (`ContainerLifecycle(container=self)`), use `TYPE_CHECKING` for type hints, or use a callback function instead of a direct reference.
**Warning signs:** ImportError on module load.

### Pitfall 5: HealthReport Timestamps Must Be UTC
**What goes wrong:** Mixing naive and aware datetimes. Health reports show wrong times.
**Why it happens:** `datetime.now()` returns naive datetime.
**How to avoid:** Always use `datetime.now(timezone.utc)`. Existing codebase already follows this pattern (see crash_tracker.py).
**Warning signs:** Timezone comparison errors, assertion failures in tests.

### Pitfall 6: Communication Port Must Be Async
**What goes wrong:** Defining CommunicationPort as sync, then needing to call Discord's async API.
**Why it happens:** Forgetting discord.py is fully async.
**How to avoid:** Define CommunicationPort methods as `async def` from the start. The entire bot/monitor context is async.
**Warning signs:** `RuntimeError: cannot call async function from sync context`.

## Code Examples

### Complete AgentContainer Skeleton
```python
# src/vcompany/container/container.py
from datetime import datetime, timezone
from pathlib import Path

from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport
from vcompany.container.memory_store import MemoryStore
from vcompany.container.state_machine import ContainerLifecycle


class AgentContainer:
    """Wraps an agent with lifecycle FSM, memory, and health reporting."""

    def __init__(self, context: ContainerContext, data_dir: Path) -> None:
        self.context = context
        self._lifecycle = ContainerLifecycle(model=self)
        self._memory = MemoryStore(data_dir / context.agent_id / "memory.db")
        self._created_at = datetime.now(timezone.utc)
        self._error_count = 0
        self._last_activity = self._created_at

    @property
    def state(self) -> str:
        return self._lifecycle.current_state.id

    def health_report(self) -> HealthReport:
        now = datetime.now(timezone.utc)
        return HealthReport(
            agent_id=self.context.agent_id,
            state=self.state,
            inner_state=None,  # Set by agent type subclasses
            uptime=(now - self._created_at).total_seconds(),
            last_heartbeat=now,
            error_count=self._error_count,
            last_activity=self._last_activity,
        )

    # State transition methods
    async def start(self) -> None:
        self._lifecycle.start()
        await self._memory.open()

    async def stop(self) -> None:
        self._lifecycle.stop()
        await self._memory.close()

    async def destroy(self) -> None:
        self._lifecycle.destroy()
        await self._memory.close()
```

### HealthReport Model
```python
# src/vcompany/container/health.py
from datetime import datetime
from pydantic import BaseModel

class HealthReport(BaseModel):
    agent_id: str
    state: str
    inner_state: str | None = None
    uptime: float  # seconds
    last_heartbeat: datetime
    error_count: int = 0
    last_activity: datetime
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| v1 flat status strings ("starting", "running", "stopped", "crashed") | v2 validated FSM with 6 states + transition rules | This phase | Eliminates impossible state transitions, enables supervision |
| v1 agents.json (flat file, no per-agent persistence) | Per-agent SQLite with checkpoints | This phase | Agents survive crashes, resume from checkpoint |
| v1 CrashTracker (centralized crash log) | Per-container HealthReport (self-reported) | This phase | Health owned by container, supervisor aggregates |
| v1 AgentManager (direct tmux management) | AgentContainer (abstract lifecycle, tmux is implementation detail) | This phase + Phase 2 | Containers are process-agnostic, testable without tmux |

## Open Questions

1. **Inner state serialization for checkpoints**
   - What we know: Phase 3 GsdAgent and Phase 4 ContinuousAgent will have inner FSMs (IDLE, DISCUSS, PLAN, etc.)
   - What's unclear: Exact inner state schema is not defined until Phase 3
   - Recommendation: MemoryStore uses generic `str` values for `set()`/`get()`. Inner state serialization is the agent type's responsibility. Keep MemoryStore schema-agnostic.

2. **Communication port message format**
   - What we know: CONT-06 says "Discord-only message passing" and MIGR-04 says "clean interface that Discord implements"
   - What's unclear: Exact message schema (headers? routing? envelope?)
   - Recommendation: Define a minimal `Message` dataclass with `source`, `target`, `content`, `timestamp`. Keep it simple now. Phase 5/6 will flesh out the protocol when Discord integration happens.

3. **State machine event naming convention**
   - What we know: python-statemachine uses method names as event names (e.g., `start`, `stop`)
   - What's unclear: Whether Phase 2 supervisors will send events by name (string) or call methods directly
   - Recommendation: Expose both -- method calls for direct use, plus a `send_event(name: str)` dispatcher for supervisor use. python-statemachine supports `sm.send("event_name")`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.12.3 | -- |
| uv | Package management | Yes | 0.11.1 | -- |
| pytest | Testing | Yes | 9.0.2 (via uv run) | -- |
| python-statemachine | FSM (CONT-01/02) | Not installed | 3.0.0 on PyPI | -- (must install) |
| aiosqlite | Memory store (CONT-04) | Not installed | 0.22.1 on PyPI | -- (must install) |
| SQLite | Storage engine | Yes (stdlib) | Bundled with Python 3.12 | -- |

**Missing dependencies with no fallback:**
- python-statemachine and aiosqlite must be installed via `uv add`

**Missing dependencies with fallback:**
- None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 0.24.x |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_container*.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONT-01 | Container created, transitions through all 6 states | unit | `uv run pytest tests/test_container_lifecycle.py::test_valid_transitions -x` | Wave 0 |
| CONT-02 | Invalid transitions raise errors | unit | `uv run pytest tests/test_container_lifecycle.py::test_invalid_transitions -x` | Wave 0 |
| CONT-03 | ContainerContext holds all required fields | unit | `uv run pytest tests/test_container_context.py -x` | Wave 0 |
| CONT-04 | MemoryStore persists KV and checkpoints to SQLite | unit (async) | `uv run pytest tests/test_memory_store.py -x` | Wave 0 |
| CONT-05 | ChildSpecRegistry stores and retrieves specs | unit | `uv run pytest tests/test_child_spec.py -x` | Wave 0 |
| CONT-06 | CommunicationPort is abstract, no file/callback coupling | unit | `uv run pytest tests/test_communication_port.py -x` | Wave 0 |
| HLTH-01 | HealthReport emitted on state transition with correct fields | unit | `uv run pytest tests/test_container_health.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_container*.py tests/test_memory_store.py tests/test_child_spec.py tests/test_communication_port.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_container_lifecycle.py` -- covers CONT-01, CONT-02
- [ ] `tests/test_container_context.py` -- covers CONT-03
- [ ] `tests/test_memory_store.py` -- covers CONT-04
- [ ] `tests/test_child_spec.py` -- covers CONT-05
- [ ] `tests/test_communication_port.py` -- covers CONT-06
- [ ] `tests/test_container_health.py` -- covers HLTH-01
- [ ] Dependency install: `uv add python-statemachine aiosqlite`

## Sources

### Primary (HIGH confidence)
- [python-statemachine PyPI](https://pypi.org/project/python-statemachine/) -- version 3.0.0, released 2026-02-24
- [python-statemachine docs](https://python-statemachine.readthedocs.io/en/latest/) -- API, state/transition definition, callbacks
- [aiosqlite PyPI](https://pypi.org/project/aiosqlite/) -- version 0.22.1, released 2025-12-23
- [aiosqlite docs](https://aiosqlite.omnilib.dev/en/latest/) -- connection lifecycle changes in 0.22.x
- Existing codebase: `src/vcompany/models/agent_state.py`, `src/vcompany/models/config.py`, `src/vcompany/orchestrator/crash_tracker.py` -- established Pydantic patterns

### Secondary (MEDIUM confidence)
- [python-statemachine GitHub releases](https://github.com/fgmacedo/python-statemachine/releases) -- release history
- [aiosqlite GitHub](https://github.com/omnilib/aiosqlite) -- README and changelog

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- both libraries verified on PyPI with recent releases and Python 3.12 compatibility
- Architecture: HIGH -- patterns derived from existing codebase conventions (Pydantic models, module-per-concern) and requirements
- Pitfalls: HIGH -- based on documented aiosqlite 0.22.x changes and standard SQLite concurrency knowledge

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable libraries, no fast-moving dependencies)
