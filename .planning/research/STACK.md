# Stack Research: Agent Container Architecture Additions

**Domain:** Supervision trees, state machines, persistent agent memory, scheduling, event-driven communication for Python asyncio orchestrator
**Researched:** 2026-03-27
**Confidence:** HIGH

**Scope:** This document covers ONLY new stack additions/changes for v2.0 container architecture. The existing validated stack (discord.py, click, libtmux, pydantic, httpx, watchfiles, etc.) is unchanged and not re-evaluated here.

## New Dependencies

### State Machines: python-statemachine 3.0.x

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| python-statemachine | 3.0.0 | Agent lifecycle state machines (CREATING->RUNNING->SLEEPING->ERRORED->STOPPED->DESTROYED) and GsdAgent internal states (IDLE->DISCUSS->PLAN->EXECUTE->UAT->SHIP) | Native async support (auto-detects async callbacks), zero runtime dependencies, SCXML-compliant statechart support for compound/parallel states, declarative Pythonic API, Pydantic-compatible. Production-stable, released Feb 2026, Python 3.9+. |

**Why python-statemachine over transitions:** `transitions` (0.9.3) still supports Python 2.7 which signals legacy-compatibility burden. Its async support exists but is bolted on via `AsyncMachine` subclass rather than auto-detected. python-statemachine 3.0 was redesigned from scratch with statechart semantics (compound states, parallel regions, history pseudo-states) which maps directly to the nested container/supervisor hierarchy. The declarative class-based API is cleaner for the 4+ distinct state machine types we need.

**Why python-statemachine over hand-rolled:** The container architecture defines at least 5 state machines (AgentContainer base, GsdAgent, ContinuousAgent, FulltimeAgent, CompanyAgent) each with transition guards, side effects, and error handling. A library provides: validated transition logic, event queuing, error-as-event handling (StateChart catches exceptions and routes them as `error.execution` events -- exactly what supervision needs), and testability via `send("event")`. Hand-rolling 5 state machines means reimplementing all of this.

**Key integration point:** State machine transitions emit events. These events drive the supervision tree (health changes, error states, completion signals). The library's callback system (`on_enter_state`, `on_exit_state`, `on_transition`) maps directly to supervisor notification hooks.

### Persistent Agent Memory: SQLite (stdlib) + aiosqlite 0.21.x

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| sqlite3 (stdlib) | N/A | Per-agent key-value store backing, checkpoint storage | Zero-dependency, ACID-compliant, single-file-per-agent, built into Python. Perfect for per-agent memory_store that survives restarts. |
| aiosqlite | 0.21.0 | Async SQLite wrapper for use within asyncio event loop | Thin wrapper around stdlib sqlite3 using thread executor. Does not replace sqlite3 -- just makes it non-blocking in async contexts. Actively maintained, minimal API surface. |

**Why SQLite over JSON files:** PROJECT.md's v1 decision to avoid databases was correct for v1 (state = markdown files read by agents). v2 is different: agent memory_store needs atomic writes (checkpoint at state transitions), key-value lookups, and data that grows over time (decision history, learned patterns). JSON files require read-modify-write with file locking. SQLite gives ACID atomicity, concurrent read access, and built-in WAL mode for non-blocking reads -- all for zero additional dependencies (stdlib). Each agent gets its own `.db` file, maintaining the isolation model.

**Why NOT a shared database:** Each agent's memory_store is its own SQLite file in the agent's directory. No shared database, no connection pooling, no schema migrations across agents. This preserves the isolation principle from v1. The supervisor reads agent state via the supervision tree API, not by querying agent databases.

**Schema is trivial:**
```sql
-- Per-agent memory store
CREATE TABLE memory (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
CREATE TABLE checkpoints (state TEXT, data TEXT, created_at TEXT);
```

### Scheduling: No New Dependency (asyncio stdlib)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| asyncio (stdlib) | N/A | Timer-based wake/sleep scheduling for ContinuousAgent | The scheduler requirements are simple: fire a WAKE event on sleeping ContinuousAgents at configured intervals. This is `asyncio.create_task` + `asyncio.sleep` in a loop, managed by CompanyRoot. No library needed. |

**Why NOT APScheduler:** APScheduler (3.11.2 stable, 4.0 alpha) is designed for job scheduling with persistence, missed-job recovery, cron expressions, and multiple backends. vCompany's scheduler needs exactly one thing: "wake this container every N minutes." APScheduler adds 15+ transitive dependencies for cron parsing, timezone handling, and job stores that will never be used. A 20-line async loop does the same thing with zero dependencies and full control over the wake/cancel semantics the supervision tree needs.

**Implementation pattern:**
```python
class Scheduler:
    """Managed by CompanyRoot. Tracks wake timers for sleeping containers."""

    async def schedule_wake(self, container_id: str, interval_seconds: int):
        """Schedule periodic wake for a container."""
        async def _wake_loop():
            while True:
                await asyncio.sleep(interval_seconds)
                await self.supervisor.wake(container_id)
        self._tasks[container_id] = asyncio.create_task(_wake_loop())

    async def cancel(self, container_id: str):
        self._tasks.pop(container_id, None)?.cancel()
```

### Event Communication: No New Dependency (asyncio stdlib)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| asyncio (stdlib) | N/A | Internal event bus for container-to-supervisor and supervisor-to-container communication | The communication pattern is tree-shaped (child notifies parent, parent commands child), not pub/sub fan-out. asyncio primitives (Queue, Event, callbacks) handle this directly. |

**Why NOT an event bus library:** Event bus libraries (bubus, lahja, aiopubsub) solve fan-out pub/sub across decoupled components. The supervision tree has a known, fixed topology: containers report UP to their supervisor, supervisors command DOWN to children. This is method calls + asyncio.Queue, not pub/sub. Adding an event bus would obscure the tree structure with indirection.

**Implementation pattern:** Each container has an `event_queue: asyncio.Queue` for receiving commands from its supervisor. Containers call `self.supervisor.report(event)` to push events up. The supervisor processes child events in its own loop. This is the Erlang gen_server pattern translated to asyncio.

## Updated Dependency: Filesystem State

The v1 STACK.md stated "No database needed." For v2, this changes slightly:

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Filesystem (YAML/Markdown) | N/A | Project-level state (agents.yaml, PROJECT-STATUS.md, milestone backlog) | Unchanged from v1. Human-readable, agent-readable, git-trackable. |
| SQLite (stdlib) | N/A | Per-agent persistent memory, checkpoint storage | New for v2. One file per agent. Not a "database" in the traditional sense -- it's a structured file format with ACID guarantees. No shared state, no migrations, no ORM. |

## No Changes Required

These existing stack items need NO changes for v2:

| Existing Tech | v2 Role | Notes |
|---------------|---------|-------|
| pydantic 2.11.x | HealthReport models, container config validation, event schemas | Already in stack. Use for all data structures crossing boundaries (health reports, delegation requests, milestone items). |
| discord.py 2.7.x | Health tree display, delegation approval UI, milestone management commands | Already in stack. New Cogs for health/delegation, but no new discord dependency. |
| libtmux 0.55.x | Still manages tmux sessions inside GsdAgent/ContinuousAgent | Container wraps the existing tmux lifecycle. libtmux usage moves inside container types rather than being called directly by dispatch. |
| watchfiles 0.24.x | Monitor role partially absorbed by supervision tree | watchfiles still useful for file-based triggers (plan gate). The supervision tree handles liveness/health that the monitor loop previously owned. |
| asyncio (stdlib) | Foundation for entire supervision tree | Already the async backbone. Containers are async context managers. Supervisors run async event loops. No new async library needed. |
| dataclasses (stdlib) | Internal container state, lightweight event objects | Use for events and internal state where Pydantic validation overhead is unnecessary. |

## Installation (New Dependencies Only)

```bash
# New for v2 container architecture
uv add "python-statemachine>=3.0,<4" "aiosqlite>=0.21,<1"

# That's it. Everything else is stdlib or already installed.
```

**Total new PyPI dependencies: 2** (python-statemachine has zero transitive deps, aiosqlite has zero transitive deps). This is intentional -- the container architecture should be built primarily on stdlib asyncio primitives with minimal external coupling.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| python-statemachine 3.0 | transitions 0.9.3 | If you need graphviz diagram generation of state machines during development. transitions has more mature diagram tooling. python-statemachine 3.0 supports diagrams too but transitions has been doing it longer. |
| python-statemachine 3.0 | Hand-rolled enums + match/case | If you only had 1-2 simple state machines. With 5+ state machine types, each with guards and side effects, a library pays for itself in correctness and testability. |
| asyncio scheduler | APScheduler 3.11.x | If wake schedules later need cron expressions (e.g., "wake PM agent every weekday at 9am"). Currently unnecessary -- intervals suffice. Easy to add later if needed. |
| asyncio Queue/callbacks | bubus (event bus) | If the communication pattern evolves from tree-shaped to mesh-shaped (agents talking to each other). Current architecture is strictly hierarchical. |
| SQLite (stdlib) | JSON files + filelock | If agent memory is truly tiny (< 10 key-value pairs) and never queried. Once you need "find all checkpoints where state=ERRORED", SQLite is strictly better. |
| aiosqlite | sqlite3 in thread executor | If aiosqlite has bugs. Fallback is `await asyncio.to_thread(sync_sqlite_function)`. aiosqlite is essentially this pattern packaged -- the fallback is trivial. |

## What NOT to Add

| Avoid | Why | What to Do Instead |
|-------|-----|---------------------|
| APScheduler | Massive overkill for interval-based wake timers. Adds cron parsing, job stores, timezone handling, 15+ transitive deps for a 20-line asyncio loop. | `asyncio.create_task` + `asyncio.sleep` loop managed by CompanyRoot. |
| mode (ask/mode) | Unmaintained (241 GitHub stars, unclear last commit, stuck on older Python). Provides service supervision but with an opinionated service base class that conflicts with our container hierarchy design. | Build supervision tree on asyncio primitives. The Erlang supervisor pattern is ~200 lines of Python, not a library problem. |
| celery / dramatiq | Task queue for distributed systems. vCompany is single-machine with known topology. Adding a message broker creates a dependency that provides zero value. | Direct asyncio method calls through the supervision tree. |
| Redis / RabbitMQ | Message brokers for distributed pub/sub. No distributed components exist. | asyncio.Queue for container command channels. |
| SQLAlchemy | ORM for relational databases. Agent memory is key-value, not relational. SQLAlchemy adds migration tooling, session management, and complexity for `CREATE TABLE memory (key, value)`. | Raw sqlite3/aiosqlite with 2 tables. |
| pydantic-statemachine or similar | Pydantic integration for state machines. python-statemachine 3.0 already works with Pydantic models as state machine model data. No bridge library needed. | Use python-statemachine's built-in model support. |
| Any "supervision framework" | No production-grade Python supervision library exists. mode is abandoned, and the concept maps cleanly to asyncio patterns. This is a 200-line module, not a framework adoption. | Implement `Supervisor` and `RestartPolicy` classes using asyncio.Task management. |

## Stack Patterns for Container Architecture

**Pattern: State machine per container type**
- Define a base `ContainerStateMachine(StateChart)` with CREATING/RUNNING/SLEEPING/ERRORED/STOPPED/DESTROYED
- GsdAgent extends with compound states inside RUNNING (IDLE/DISCUSS/PLAN/EXECUTE/UAT/SHIP)
- python-statemachine 3.0's compound states handle this natively -- no workaround needed

**Pattern: Supervision as asyncio Task management**
- Each container runs as an `asyncio.Task` owned by its supervisor
- Supervisor wraps child tasks with `try/except` + restart policy logic
- `one_for_one`: restart only the failed child
- `all_for_one`: cancel and restart all children
- `rest_for_one`: cancel and restart children started after the failed one
- This is 150-200 lines of clean asyncio code, not a library

**Pattern: Health reporting as Pydantic models**
- `HealthReport` is a Pydantic model (status, uptime, error_count, last_state_change, children)
- Tree rendering uses Rich (already in stack) for terminal output
- Discord push uses existing discord.py Cog pattern

**Pattern: Memory store isolation**
- Each agent gets `{agent_clone_dir}/.vco/memory.db`
- SQLite in WAL mode for non-blocking reads
- Checkpoint writes happen in state machine `on_exit_state` callbacks
- aiosqlite for async access within the event loop

**Pattern: Event-driven not poll-driven**
- v1 monitor polls every 60s. v2 containers push events up the tree on state changes
- Supervisor reacts immediately to child events (health change, error, completion)
- The 60s poll loop becomes a heartbeat/timeout detector only (if a container stops reporting, it's stuck)
- watchfiles remains for file-system triggers (plan gate) that originate outside the container tree

## Version Compatibility

| New Package | Compatible With | Notes |
|-------------|-----------------|-------|
| python-statemachine 3.0.0 | Python 3.9+ | Zero runtime dependencies. No conflicts with existing stack. |
| aiosqlite 0.21.0 | Python 3.9+, sqlite3 (stdlib) | Wraps stdlib sqlite3. No conflicts. Uses thread pool executor internally. |
| sqlite3 (stdlib) | Python 3.12 | Ships with Python. WAL mode available since SQLite 3.7 (Python 3.12 ships SQLite 3.41+). |

## Sources

- [python-statemachine PyPI](https://pypi.org/project/python-statemachine/) -- version 3.0.0, Python 3.9+, zero deps confirmed (HIGH confidence)
- [python-statemachine docs](https://python-statemachine.readthedocs.io/) -- async support, StateChart class, compound states confirmed (HIGH confidence)
- [python-statemachine GitHub](https://github.com/fgmacedo/python-statemachine) -- SCXML compliance, 3.0 release Feb 2026 confirmed (HIGH confidence)
- [transitions PyPI](https://pypi.org/project/transitions/) -- version 0.9.3, AsyncMachine confirmed (HIGH confidence)
- [APScheduler PyPI](https://pypi.org/project/APScheduler/) -- version 3.11.2 stable, 4.0.0a6 alpha confirmed (HIGH confidence)
- [aiosqlite PyPI](https://pypi.org/project/aiosqlite/) -- version 0.21.0 confirmed (MEDIUM confidence, version from training data)
- [mode GitHub](https://github.com/ask/mode) -- 241 stars, unclear maintenance status confirmed (MEDIUM confidence)
- [Erlang Supervisor docs](https://www.erlang.org/doc/system/sup_princ.html) -- restart strategy semantics referenced (HIGH confidence)
- [bubus GitHub](https://github.com/browser-use/bubus) -- event bus with Pydantic, WAL persistence noted (LOW confidence, not recommended)

---
*Stack research for: Agent container architecture additions (v2.0)*
*Researched: 2026-03-27*
