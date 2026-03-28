# Phase 11: Container Architecture Fixes - Research

**Researched:** 2026-03-28
**Domain:** Container FSM, supervision hierarchy, communication wiring
**Confidence:** HIGH

## Summary

Phase 11 is a foundational refactoring phase that fixes four structural issues in the container architecture: (1) Strategist container placement in the supervision tree, (2) BLOCKED as a real FSM state, (3) STOPPING as a transitional FSM state, and (4) CommunicationPort wiring during container creation. All four changes are internal to existing code with no new libraries or infrastructure needed.

The codebase is well-structured for these changes. The FSM uses python-statemachine 3.0, which supports adding states cleanly. The CommunicationPort Protocol already exists but is never wired. The CompanyRoot already manages ProjectSupervisors dynamically; adding Strategist as a direct child follows the same pattern. The health tree rendering code (embeds.py) already handles state-to-emoji mapping and just needs new entries for BLOCKED and STOPPING.

**Primary recommendation:** Make all four changes incrementally -- FSM states first (BLOCKED, STOPPING), then hierarchy fix (Strategist under CompanyRoot), then comm_port wiring -- since later changes depend on the FSM being correct.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion (infrastructure phase).

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key structural facts from codebase scout:

- Strategist is currently a Cog (StrategistCog), not a container -- needs CompanyAgent container under CompanyRoot
- FSM has 6 states (creating, running, sleeping, errored, stopped, destroyed) -- BLOCKED and STOPPING are missing
- CommunicationPort is a Protocol in container/communication.py -- containers don't wire it yet
- CompanyRoot creates ProjectSupervisors but has no direct Strategist child
- on_ready() and /new-project both create containers -- both paths need comm_port wiring

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ARCH-02 | Strategist is a direct child of CompanyRoot, peer to ProjectSupervisors -- not under ProjectSupervisor | CompanyRoot already manages children dynamically. CompanyAgent class exists and is registered in factory. Health tree needs a new field for "company agents" alongside "projects". |
| ARCH-03 | BLOCKED is a real FSM state (not a bool) -- visible in health tree with reason | python-statemachine 3.0 supports adding states. GsdAgent currently uses `_blocked_since`/`_blocked_reason` attributes -- must migrate to FSM state. HealthReport needs `blocked_reason` field. |
| ARCH-04 | CommunicationPort is wired during container creation -- agents use comm_port for structured messaging | CommunicationPort Protocol exists. Factory `create_container()` already accepts `comm_port` param. Supervisor `_start_child()` does NOT pass it. Two creation paths: `on_ready()` and `/new-project`. |
| LIFE-01 | STOPPING is a transitional FSM state before STOPPED -- visible in health tree during graceful shutdown | All three FSM classes (ContainerLifecycle, GsdLifecycle, EventDrivenLifecycle) need STOPPING state. Container `stop()` must transition through STOPPING before STOPPED. |
</phase_requirements>

## Standard Stack

No new libraries needed. All changes use existing dependencies:

| Library | Version | Purpose | Role in Phase |
|---------|---------|---------|---------------|
| python-statemachine | 3.0.0 | FSM library | Add BLOCKED and STOPPING states to all three lifecycle FSMs |
| pydantic | 2.11.x | Data models | Add `blocked_reason` field to HealthReport |
| discord.py | 2.7.x | Bot framework | Already used -- embeds.py needs new state indicators |

## Architecture Patterns

### Affected Files Map

```
src/vcompany/
  container/
    state_machine.py          # Add BLOCKED, STOPPING states to ContainerLifecycle
    health.py                 # Add blocked_reason to HealthReport, company_agents to CompanyHealthTree
    container.py              # Modify stop() to go through STOPPING, add block()/unblock()
    factory.py                # No changes needed (already passes comm_port)
    communication.py          # No changes needed (Protocol already defined)
  agent/
    gsd_lifecycle.py          # Add BLOCKED, STOPPING states
    gsd_agent.py              # Migrate mark_blocked()/clear_blocked() to FSM transitions
    event_driven_lifecycle.py # Add BLOCKED, STOPPING states
    company_agent.py          # Add block()/unblock() methods
  supervisor/
    supervisor.py             # Pass comm_port in _start_child(), handle STOPPING in monitor
    company_root.py           # Add _company_agents dict, health_tree() includes them
  bot/
    client.py                 # Create Strategist CompanyAgent in on_ready(), wire comm_port
    cogs/commands.py          # Wire comm_port in /new-project path
    embeds.py                 # Add BLOCKED and STOPPING state indicators
    cogs/health.py            # Handle STOPPING in _notify_state_change
```

### Pattern 1: Adding FSM States (BLOCKED, STOPPING)

**What:** Add `blocked` and `stopping` states to all three lifecycle FSMs with appropriate transitions.

**All three FSMs must stay consistent:**
- `ContainerLifecycle` (simple agents)
- `GsdLifecycle` (GSD agents with compound running state)
- `EventDrivenLifecycle` (PM and Strategist with compound running state)

**ContainerLifecycle changes:**
```python
# New states
blocked = State()
stopping = State()

# New transitions
block = running.to(blocked)
unblock = blocked.to(running)

# Modified transitions -- STOPPING intermediate
begin_stop = running.to(stopping) | sleeping.to(stopping) | errored.to(stopping) | blocked.to(stopping)
finish_stop = stopping.to(stopped)

# Error must also handle blocked state
error = creating.to(errored) | running.to(errored) | sleeping.to(errored) | blocked.to(errored)
```

**GsdLifecycle and EventDrivenLifecycle changes:**
Same pattern but `blocked` transitions from/to `running` compound state using `running.h` (HistoryState) for unblock so the inner phase/sub-state is preserved.

```python
block = running.to(blocked)
unblock = blocked.to(running.h)  # Restore inner phase
begin_stop = running.to(stopping) | sleeping.to(stopping) | errored.to(stopping) | blocked.to(stopping)
finish_stop = stopping.to(stopped)
```

**Verified with python-statemachine 3.0:** Both patterns work correctly. The `_fsm_state` field writes `"blocked"` and `"stopping"` as plain strings for simple states, and HistoryState correctly restores compound state on `unblock`.

### Pattern 2: BLOCKED with Reason

**What:** HealthReport carries `blocked_reason` so health tree shows why an agent is blocked.

```python
# health.py -- add field
class HealthReport(BaseModel):
    # ... existing fields ...
    blocked_reason: str | None = None  # Populated when state == "blocked"
```

```python
# container.py -- health_report() populates it
def health_report(self) -> HealthReport:
    return HealthReport(
        # ... existing fields ...
        blocked_reason=getattr(self, '_blocked_reason', None),
    )
```

For GsdAgent, `_blocked_reason` already exists. For base AgentContainer, add a `_blocked_reason` attribute that `block()` sets.

### Pattern 3: Two-Phase Stop (STOPPING -> STOPPED)

**What:** Container `stop()` transitions through STOPPING before STOPPED.

```python
async def stop(self) -> None:
    # Transition to STOPPING first (visible in health tree)
    self._lifecycle.begin_stop()
    # Do actual cleanup (kill tmux, close memory)
    if self._tmux is not None and self._pane_id is not None:
        pane = await asyncio.to_thread(self._tmux.get_pane_by_id, self._pane_id)
        if pane is not None:
            await asyncio.to_thread(self._tmux.kill_pane, pane)
        self._pane_id = None
    # Transition to STOPPED
    self._lifecycle.finish_stop()
    await self.memory.close()
```

**Caveat:** The old `stop` transition name must be renamed or removed since `stop` now has two steps. The existing code has `self._lifecycle.stop()` -- must become `self._lifecycle.begin_stop()` + `self._lifecycle.finish_stop()`.

### Pattern 4: Strategist as CompanyRoot Child

**What:** CompanyRoot creates a CompanyAgent for Strategist directly, not under any ProjectSupervisor.

```python
# company_root.py -- new dict and methods
class CompanyRoot(Supervisor):
    def __init__(self, ...):
        # ... existing init ...
        self._company_agents: dict[str, AgentContainer] = {}

    async def add_company_agent(self, spec: ChildSpec) -> AgentContainer:
        """Create and start a company-level agent (e.g., Strategist)."""
        container = create_container(spec, data_dir=self._data_dir, comm_port=...)
        await container.start()
        self._company_agents[spec.child_id] = container
        return container

    def health_tree(self) -> CompanyHealthTree:
        """Include company agents alongside project trees."""
        company_nodes = [
            HealthNode(report=agent.health_report())
            for agent in self._company_agents.values()
        ]
        # ... existing project_trees logic ...
        return CompanyHealthTree(
            supervisor_id=self.supervisor_id,
            state=self._state,
            company_agents=company_nodes,  # NEW FIELD
            projects=project_trees,
        )
```

```python
# health.py -- extend CompanyHealthTree
class CompanyHealthTree(BaseModel):
    supervisor_id: str
    state: str
    company_agents: list[HealthNode] = []  # NEW: Strategist, etc.
    projects: list[HealthTree] = []
```

### Pattern 5: CommunicationPort Wiring

**What:** Create a concrete CommunicationPort implementation and wire it during container creation.

The CommunicationPort Protocol is already defined. What's needed:
1. A concrete implementation (e.g., `DiscordCommunicationPort` or `NoopCommunicationPort` for now)
2. Pass it through `Supervisor._start_child()` to `create_container()`
3. Both `on_ready()` and `/new-project` paths pass comm_port

The simplest viable approach for v2.1: create a `NoopCommunicationPort` that logs messages (actual Discord routing comes in later phases). The key is that `container.comm_port is not None` -- the interface is wired even if the implementation is a stub.

```python
# communication.py -- add concrete implementation
class NoopCommunicationPort:
    """Stub implementation that satisfies the Protocol but logs instead of sending."""

    async def send_message(self, target: str, content: str) -> bool:
        logger.debug("CommunicationPort.send_message(%s, %s)", target, content[:50])
        return True

    async def receive_message(self) -> Message | None:
        return None
```

The Supervisor needs to either receive a comm_port factory or a shared instance:

```python
# supervisor.py -- _start_child passes comm_port
async def _start_child(self, spec: ChildSpec) -> None:
    container = create_container(
        spec,
        data_dir=self._data_dir,
        comm_port=self._comm_port,  # NEW: injected at supervisor level
        on_state_change=self._make_state_change_callback(spec.child_id),
        tmux_manager=self._tmux_manager,
        project_dir=self._project_dir,
        project_session_name=self._session_name,
    )
```

### Anti-Patterns to Avoid

- **Renaming the `stop` transition without updating all callers:** Multiple places call `self._lifecycle.stop()`. All must change to `begin_stop()`/`finish_stop()`. Search thoroughly.
- **Forgetting one of the three FSMs:** ContainerLifecycle, GsdLifecycle, and EventDrivenLifecycle must all get BLOCKED and STOPPING. Missing one causes runtime crashes for that agent type.
- **Breaking existing `stop()` calls in Supervisor:** The Supervisor calls `child.stop()` in multiple places (restart strategies, escalation, shutdown). The Container method name `stop()` stays the same -- only the internal FSM transition changes.
- **Modifying state comparisons without updating health cog:** `_notify_state_change()` checks `report.state in ("errored", "running", "stopped")` -- needs `"blocked"` and `"stopping"` added.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| FSM state definitions | Custom state tracking dicts | python-statemachine 3.0 State/transitions | Already in use, validates transitions automatically |
| CommunicationPort concrete impl | Full Discord-backed messaging | NoopCommunicationPort stub | v2.1 is wiring, not implementation; real routing comes later |

## Common Pitfalls

### Pitfall 1: python-statemachine Trap State Validation
**What goes wrong:** python-statemachine 3.0 validates that all non-final states have at least one outgoing transition. Adding STOPPING without outgoing transition to STOPPED causes `InvalidDefinition` at class definition time.
**Why it happens:** statemachine 3.0 added stricter validation vs 2.x.
**How to avoid:** Always define both `begin_stop` (into STOPPING) and `finish_stop` (out of STOPPING) transitions.
**Warning signs:** `InvalidDefinition: All non-final states should have at least one outgoing transition` error.

### Pitfall 2: OrderedSet State Representation for Compound States
**What goes wrong:** When a container is in a compound state (running.idle), `_fsm_state` is an `OrderedSet(['running', 'idle'])`. String comparison `state == "running"` fails because it's an OrderedSet, not a string.
**Why it happens:** python-statemachine 3.0 uses OrderedSet for compound states.
**How to avoid:** GsdAgent and CompanyAgent already handle this with their `state` property. BLOCKED and STOPPING are simple (non-compound) states, so they'll be plain strings. Just ensure health tree comparisons use the container's `.state` property, not `_fsm_state` directly.
**Warning signs:** State comparisons silently failing, health tree showing wrong state.

### Pitfall 3: Supervisor Monitor Loop State Checks
**What goes wrong:** `_monitor_child()` and `_make_state_change_callback()` check for specific states like `"errored"`, `"stopped"`. Missing `"blocked"` and `"stopping"` causes incorrect restart behavior.
**Why it happens:** New states not accounted for in state-matching logic.
**How to avoid:** Audit every `report.state in (...)` and `container.state == ...` check. STOPPING should be treated like a transient state (no restart). BLOCKED should trigger escalation/notification but not restart.
**Warning signs:** Agents in BLOCKED state getting incorrectly restarted.

### Pitfall 4: GsdAgent _blocked_since Migration
**What goes wrong:** GsdAgent has existing `_blocked_since`, `is_blocked`, `mark_blocked()`, `clear_blocked()` that use boolean/timestamp tracking. Must migrate to FSM `block()`/`unblock()` transitions while preserving the `_blocked_reason` string.
**Why it happens:** Parallel implementations of the same concept.
**How to avoid:** Keep `_blocked_reason` as an attribute. Replace `mark_blocked()` to call `self._lifecycle.block()` and set `_blocked_reason`. Replace `clear_blocked()` to call `self._lifecycle.unblock()` and clear reason. Remove `_blocked_since` and `is_blocked` property -- use `self.state == "blocked"` instead.
**Warning signs:** Test failures in existing blocked-tracking tests, callers of `mark_blocked()` breaking.

### Pitfall 5: Health Tree Embed Missing New State Indicators
**What goes wrong:** Health tree Discord embed shows question mark for BLOCKED and STOPPING because `STATE_INDICATORS` dict in embeds.py lacks entries.
**Why it happens:** New states added to FSM but not to display layer.
**How to avoid:** Add entries to `STATE_INDICATORS` in embeds.py for `"blocked"` and `"stopping"`.
**Warning signs:** Question marks in /health output.

## Code Examples

### FSM State Addition (ContainerLifecycle)
```python
# Source: Verified with python-statemachine 3.0.0 on this project
class ContainerLifecycle(StateMachine):
    creating = State(initial=True)
    running = State()
    sleeping = State()
    blocked = State()       # NEW: ARCH-03
    errored = State()
    stopping = State()      # NEW: LIFE-01
    stopped = State()
    destroyed = State(final=True)

    start = creating.to(running)
    sleep = running.to(sleeping)
    wake = sleeping.to(running)
    block = running.to(blocked)                    # NEW
    unblock = blocked.to(running)                  # NEW
    error = creating.to(errored) | running.to(errored) | sleeping.to(errored) | blocked.to(errored)
    recover = errored.to(running)
    begin_stop = (running.to(stopping) | sleeping.to(stopping)   # NEW
                  | errored.to(stopping) | blocked.to(stopping))
    finish_stop = stopping.to(stopped)             # NEW
    destroy = stopped.to(destroyed) | errored.to(destroyed)
```

### Health Report with blocked_reason
```python
# Source: Existing HealthReport pattern in container/health.py
class HealthReport(BaseModel):
    agent_id: str
    state: str
    inner_state: str | None = None
    uptime: float
    last_heartbeat: datetime
    error_count: int = 0
    last_activity: datetime
    blocked_reason: str | None = None  # NEW: populated when state == "blocked"
```

### CompanyHealthTree with company_agents
```python
# Source: Existing CompanyHealthTree in container/health.py
class CompanyHealthTree(BaseModel):
    supervisor_id: str
    state: str
    company_agents: list[HealthNode] = []  # NEW: Strategist and other company-level agents
    projects: list[HealthTree] = []
```

### NoopCommunicationPort
```python
# Source: Based on existing CommunicationPort Protocol in container/communication.py
import logging

logger = logging.getLogger(__name__)

class NoopCommunicationPort:
    """Stub CommunicationPort for v2.1 wiring. Logs instead of sending."""

    async def send_message(self, target: str, content: str) -> bool:
        logger.debug("comm_port.send_message(target=%s, len=%d)", target, len(content))
        return True

    async def receive_message(self) -> Message | None:
        return None
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `_blocked_since` float + `is_blocked` bool | FSM `blocked` state with reason | Phase 11 | Health tree shows BLOCKED state with reason string |
| Direct `running.to(stopped)` | `running.to(stopping).to(stopped)` | Phase 11 | Graceful shutdown visible in health tree |
| Strategist only as Cog | CompanyAgent under CompanyRoot | Phase 11 | Strategist visible in supervision/health tree |
| `comm_port=None` everywhere | NoopCommunicationPort wired | Phase 11 | Every container has non-None comm_port |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | pyproject.toml `[tool.pytest]` |
| Quick run command | `uv run python3 -m pytest tests/ -x -q` |
| Full suite command | `uv run python3 -m pytest tests/ -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ARCH-02 | Strategist is direct child of CompanyRoot, visible in health tree | unit | `uv run python3 -m pytest tests/test_company_root.py -x -q` | Exists, needs new tests |
| ARCH-03 | BLOCKED is FSM state with reason in health report | unit | `uv run python3 -m pytest tests/test_container_blocked.py -x -q` | Wave 0 |
| ARCH-04 | comm_port is non-None on all containers | unit | `uv run python3 -m pytest tests/test_comm_port_wiring.py -x -q` | Wave 0 |
| LIFE-01 | STOPPING is transitional FSM state visible in health | unit | `uv run python3 -m pytest tests/test_container_stopping.py -x -q` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run python3 -m pytest tests/ -x -q`
- **Per wave merge:** `uv run python3 -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_container_blocked.py` -- covers ARCH-03: FSM blocked state, health report blocked_reason
- [ ] `tests/test_container_stopping.py` -- covers LIFE-01: FSM stopping state, two-phase shutdown
- [ ] `tests/test_comm_port_wiring.py` -- covers ARCH-04: comm_port non-None after creation
- [ ] New tests in `tests/test_company_root.py` -- covers ARCH-02: Strategist as CompanyRoot child in health tree

## Open Questions

1. **Should NoopCommunicationPort be shared (one instance) or per-container?**
   - What we know: The Protocol is stateless (no per-container data). Factory already accepts comm_port param.
   - What's unclear: Whether future Discord-backed implementation needs per-container instances (for routing context).
   - Recommendation: Use one shared instance per supervisor for now. Per-container is easy to add later since the constructor already accepts it.

2. **Should BLOCKED state be available on ALL container types or just GsdAgent?**
   - What we know: Current `mark_blocked()` only exists on GsdAgent. But FulltimeAgent (PM) could also be blocked.
   - What's unclear: Whether non-GSD agents ever need BLOCKED.
   - Recommendation: Add BLOCKED to all three FSMs for consistency. Base AgentContainer gets `block(reason)`/`unblock()` methods. Subclasses inherit.

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/vcompany/container/state_machine.py`, `gsd_lifecycle.py`, `event_driven_lifecycle.py` -- current FSM definitions
- Codebase inspection: `src/vcompany/container/communication.py` -- CommunicationPort Protocol definition
- Codebase inspection: `src/vcompany/supervisor/company_root.py` -- current hierarchy structure
- Codebase inspection: `src/vcompany/bot/client.py` lines 101-360 -- on_ready container creation flow
- Codebase inspection: `src/vcompany/bot/cogs/commands.py` lines 71-291 -- /new-project container creation flow
- Live verification: python-statemachine 3.0.0 API tested directly (BLOCKED, STOPPING states with model/state_field)

### Secondary (MEDIUM confidence)
- python-statemachine 3.0 deprecation: `current_state` deprecated in favor of `configuration` (observed in runtime warnings)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, only existing code modifications
- Architecture: HIGH -- all patterns verified against live codebase, FSM changes tested
- Pitfalls: HIGH -- identified from direct code reading and statemachine 3.0 behavior verification

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable -- internal refactoring, no external dependencies changing)
