# Phase 16: Agent Completeness & Strategist - Research

**Researched:** 2026-03-28
**Domain:** Python async agent architecture — CompanyAgent wiring, ContinuousAgent state persistence, GsdAgent context recovery
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Claude's Discretion
All implementation choices are at Claude's discretion.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ARCH-01 | Strategist operates through CompanyAgent container event handler — StrategistCog becomes a thin Discord adapter | CompanyAgent._handle_event() is a pass no-op today; StrategistConversation lives in StrategistCog. Must move conversation logic into CompanyAgent and have StrategistCog forward inbound Discord messages as events, then receive responses via callback. |
| AGNT-01 | ContinuousAgent has a `request_task()` method that delegates work through supervisor via DelegationTracker | Supervisor already has `handle_delegation_request()` + DelegationTracker. ContinuousAgent has no reference to its supervisor today — needs a `_supervisor` callback or reference wired at construction/boot time. |
| AGNT-02 | ContinuousAgent persists seen_items, pending_actions, briefing_log, config to memory_store (not just cycle_count) | MemoryStore supports arbitrary key-value pairs via `set()`/`get()`. ContinuousAgent currently persists only `cycle_count`. Four additional keys must be persisted/restored on start(). |
| AGNT-03 | GsdAgent restores full work context on restart — current phase, task, and assignment from ProjectStateManager, not just FSM state | GsdAgent already persists FSM state (checkpoint) and `current_phase` key. It also has `get_assignment()`/`set_assignment()` backed by its own MemoryStore. The gap is that `_restore_from_checkpoint()` does not restore the assignment, and the GsdAgent has no reference to ProjectStateManager (which is PM-owned). The correct restore path is: read `current_assignment` from own MemoryStore (already written by set_assignment), not from ProjectStateManager. |
</phase_requirements>

---

## Summary

Phase 16 has four tightly scoped wiring tasks. No new infrastructure. No new libraries. The codebase is fully built — this phase connects existing pieces that were left as `pass` or incomplete.

**ARCH-01** is the largest change: `CompanyAgent._handle_event()` is a documented no-op (`pass` with comment "real Strategist logic added later"). The Strategist conversation and decision logic currently lives entirely in `StrategistCog`. The inversion requires moving the `StrategistConversation` instance into `CompanyAgent`, having `StrategistCog` post inbound messages as typed events to `CompanyAgent.post_event()`, and routing responses back via an async callback that StrategistCog registers on the container.

**AGNT-01** requires `ContinuousAgent.request_task()`, which calls `Supervisor.handle_delegation_request()`. The supervisor already implements the full delegation protocol with DelegationTracker. The only missing piece is giving ContinuousAgent a way to reach its supervisor — a `_request_delegation` callback wired at boot time by whoever constructs the agent (VcoBot.on_ready or ProjectSupervisor).

**AGNT-02** is purely additive persistence. Four keys — `seen_items`, `pending_actions`, `briefing_log`, `config` — need to be serialized to JSON and stored via `memory.set()` at cycle checkpoints, then deserialized in `start()` alongside `cycle_count`.

**AGNT-03** is already 80% done: GsdAgent persists FSM phase state and writes `current_assignment` via `set_assignment()`. On restart, `_restore_from_checkpoint()` already restores FSM state and `current_phase`. What is missing is restoring the assignment dict from `get_assignment()` into an instance attribute during `start()`.

**Primary recommendation:** Implement in two plans: Plan 01 covers ARCH-01 (Strategist inversion) and Plan 02 covers AGNT-01/02/03 (agent completeness).

---

## Standard Stack

### Core (no new dependencies required)

| Library | Version | Purpose | Already Used |
|---------|---------|---------|--------------|
| asyncio (stdlib) | N/A | Async queues, tasks, Futures | Yes — CompanyAgent, FulltimeAgent |
| aiosqlite | existing | MemoryStore persistence | Yes — MemoryStore |
| json (stdlib) | N/A | Serializing seen_items, pending_actions, etc. | Yes — GsdAgent.get_assignment |
| statemachine | existing | FSM compound states | Yes — all agents |

No new packages needed. All changes are pure Python using existing infrastructure.

---

## Architecture Patterns

### Pattern 1: Event-Driven Inversion (ARCH-01)

**What:** Move stateful logic from a Cog into the CompanyAgent container. The Cog becomes a thin Discord adapter: it converts Discord messages into typed event dicts, posts them to `CompanyAgent.post_event()`, and registers a response callback on the container.

**Current state (before Phase 16):**
- `StrategistCog` owns `StrategistConversation` instance
- `StrategistCog._send_to_channel()` calls `conversation.send()` and posts response
- `CompanyAgent._handle_event()` is `pass`

**Target state (after Phase 16):**
- `CompanyAgent` owns `StrategistConversation` instance
- `CompanyAgent._handle_event()` dispatches on `event["type"]`:
  - `"strategist_message"`: calls `self._conversation.send(content)`, then invokes `self._on_response(agent_id, response)` callback
  - `"pm_escalation"`: handles PM escalation path
- `StrategistCog` retains:
  - Discord `on_message` listener (routing, owner check, attachment handling)
  - Owner escalation logic (`post_owner_escalation`, `_pending_escalations`)
  - Response posting to Discord channel (via callback from CompanyAgent)
- VcoBot.on_ready wires a response callback on the CompanyAgent after creation

**Event types posted to CompanyAgent:**

```python
# Inbound message from Discord owner
{"type": "strategist_message", "content": str, "channel_id": int}

# PM escalation (from FulltimeAgent._on_escalate_to_strategist path)
{"type": "pm_escalation", "agent_id": str, "question": str, "confidence": float}
```

**Response routing:** CompanyAgent needs a callback slot:

```python
# Wired by VcoBot.on_ready
self._on_response: Callable[[str, int], Awaitable[None]] | None = None
# Args: response_text, channel_id
```

StrategistCog registers this callback and posts the response to the correct Discord channel.

**Key constraint:** `StrategistConversation.send()` is async. CompanyAgent._handle_event() is already async. No bridging needed.

**Initialization sequence change:** `strategist_cog.initialize()` currently creates the `StrategistConversation`. After Phase 16, `initialize()` only resolves channels and registers callbacks on the CompanyAgent. The CompanyAgent `start()` override (or a new `initialize()` method) creates `StrategistConversation`.

**DecisionLogger:** Currently lives in StrategistCog. Can stay in StrategistCog (it's a Discord-side concern — posting to #decisions channel). StrategistCog continues to own the logger; CompanyAgent calls a callback when a decision is logged.

### Pattern 2: Supervisor Callback Delegation (AGNT-01)

**What:** `ContinuousAgent.request_task()` calls through to `Supervisor.handle_delegation_request()` without holding a direct reference to the Supervisor object. The reference is injected as a callback, following the existing pattern used for `_on_briefing`, `_on_phase_transition`, etc.

**Callback slot on ContinuousAgent:**

```python
# Wired by Supervisor._start_child or by VcoBot.on_ready
self._request_delegation: Callable[[DelegationRequest], Awaitable[DelegationResult]] | None = None
```

**ContinuousAgent.request_task() implementation:**

```python
async def request_task(
    self,
    task_description: str,
    agent_type: str = "gsd",
    context_overrides: dict[str, str] | None = None,
) -> DelegationResult:
    """Delegate a task through the supervisor via DelegationTracker."""
    if self._request_delegation is None:
        return DelegationResult(approved=False, reason="Delegation not wired")
    request = DelegationRequest(
        requester_id=self.context.agent_id,
        task_description=task_description,
        agent_type=agent_type,
        context_overrides=context_overrides or {},
    )
    return await self._request_delegation(request)
```

**Wiring in Supervisor._start_child (or ProjectSupervisor.add_child_spec):**

```python
# After container is created, before start():
if isinstance(container, ContinuousAgent):
    async def _make_delegation_cb(sup: Supervisor) -> Callable:
        async def _cb(req: DelegationRequest) -> DelegationResult:
            return await sup.handle_delegation_request(req)
        return _cb
    container._request_delegation = await _make_delegation_cb(self)
```

**Alternative wiring location:** VcoBot.on_ready already wires all other ContinuousAgent callbacks. It can wire `_request_delegation` in the same loop that wires `_on_briefing`. However, wiring inside Supervisor._start_child is cleaner — it does not require VcoBot to know about delegation internals. Either approach is acceptable.

**DelegationPolicy requirement:** `Supervisor.handle_delegation_request()` returns `DelegationResult(approved=False, reason="Delegation not enabled")` when `self._delegation_tracker is None`. To enable delegation, the supervisor must be constructed with a `DelegationPolicy`. In VcoBot.on_ready, `company_root.add_project()` creates the ProjectSupervisor — the policy can be passed there, or ProjectSupervisor can default to a policy.

### Pattern 3: Additive Persistence (AGNT-02)

**What:** ContinuousAgent persists four additional keys to MemoryStore at every cycle checkpoint, and restores them during `start()`.

**Keys and types:**

| Key | Python type | Serialization | Default on restore |
|-----|-------------|---------------|-------------------|
| `seen_items` | `set[str]` | `json.dumps(list(seen_items))` | `set()` |
| `pending_actions` | `list[dict]` | `json.dumps(pending_actions)` | `[]` |
| `briefing_log` | `list[str]` | `json.dumps(briefing_log)` | `[]` |
| `config` | `dict[str, Any]` | `json.dumps(config)` | `{}` |

These attributes do not currently exist on ContinuousAgent — they must be added as instance attributes in `__init__`.

**Checkpoint write (in `_checkpoint_cycle()`, after existing checkpoint write):**

```python
await self.memory.set("seen_items", json.dumps(list(self._seen_items)))
await self.memory.set("pending_actions", json.dumps(self._pending_actions))
await self.memory.set("briefing_log", json.dumps(self._briefing_log))
await self.memory.set("config", json.dumps(self._config))
```

**Restore in `start()` (after `cycle_count` restore, before `_restore_from_checkpoint()`):**

```python
raw = await self.memory.get("seen_items")
if raw is not None:
    self._seen_items = set(json.loads(raw))
raw = await self.memory.get("pending_actions")
if raw is not None:
    self._pending_actions = json.loads(raw)
raw = await self.memory.get("briefing_log")
if raw is not None:
    self._briefing_log = json.loads(raw)
raw = await self.memory.get("config")
if raw is not None:
    self._config = json.loads(raw)
```

### Pattern 4: Assignment Context Restore (AGNT-03)

**What:** GsdAgent already persists assignment to its own MemoryStore (`current_assignment` key via `set_assignment()`). The `start()` override must call `get_assignment()` and load the result into a `_current_assignment` instance attribute.

**Current state:** `start()` restores FSM state from checkpoint and restores `current_phase` string. It does not restore the assignment dict.

**Target state — additions to `GsdAgent.start()`:**

```python
# After FSM restore, restore assignment context
assignment = await self.get_assignment()
if assignment is not None:
    self._current_assignment = assignment
    logger.info(
        "Restored assignment for %s: %s",
        self.context.agent_id,
        assignment.get("item_id", "unknown"),
    )
```

**New instance attribute in `__init__`:**

```python
self._current_assignment: dict[str, Any] | None = None
```

**Relationship to ProjectStateManager:** The success criterion says "from ProjectStateManager, not just FSM state." This does NOT mean reading from the PM's MemoryStore directly (agents never read from PM's store per architecture). It means: the assignment data was written to the agent's own MemoryStore by `set_assignment()`, which is called during task dispatch. The agent restores from its OWN store. ProjectStateManager is mentioned in the criterion because it is the authoritative source that drove the assignment write — restoring from the agent's own store is consistent with PM's record.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async queue for CompanyAgent events | Custom pub/sub | `asyncio.Queue` already in CompanyAgent._event_queue | Already implemented; `post_event()` / `process_next_event()` are the API |
| Delegation rate limiting / concurrent caps | Custom counters | `DelegationTracker` (autonomy/delegation.py) | Full sliding-window + per-requester cap already implemented |
| SQLite persistence for agent state | Raw aiosqlite | `MemoryStore.set()` / `MemoryStore.get()` | Already wraps aiosqlite with WAL mode + upsert semantics |
| Callback injection for supervisor access | Direct supervisor reference | Callback slot pattern (same as `_on_briefing`, `_on_phase_transition`) | Avoids tight coupling; follows existing codebase pattern |

---

## Common Pitfalls

### Pitfall 1: Moving StrategistConversation but breaking existing escalation callbacks
**What goes wrong:** `StrategistCog.handle_pm_escalation()` is currently called directly by `FulltimeAgent._on_escalate_to_strategist`. If `StrategistConversation` moves to CompanyAgent, but `_on_escalate_to_strategist` still calls `StrategistCog.handle_pm_escalation()`, the cog must forward to CompanyAgent. Otherwise the event bypasses the container entirely.
**How to avoid:** Replace `_on_escalate_to_strategist` callback wiring in VcoBot.on_ready so it posts a `"pm_escalation"` event to the CompanyAgent and awaits a Future, instead of calling `strategist_cog.handle_pm_escalation()` directly.
**Warning signs:** `handle_pm_escalation` in StrategistCog still calling `self._conversation.send()` after Phase 16.

### Pitfall 2: CompanyAgent event loop — process_next_event is not driven
**What goes wrong:** `CompanyAgent.post_event()` puts onto a queue; `process_next_event()` drains it. But nothing drives `process_next_event()` in a loop. FulltimeAgent has the same gap — it's driven externally (by tests or by a monitor loop). After Phase 16, if a Strategist message is posted but nothing calls `process_next_event()`, the response never comes.
**How to avoid:** Add a background task in `CompanyAgent.start()` that loops calling `process_next_event()` (with `await asyncio.sleep(0)` between calls), same pattern as FulltimeAgent's stuck detector. OR: document that callers of `post_event()` must also call `process_next_event()`. The simplest and most correct fix is a continuous drain task started in `start()` and cancelled in `stop()`.
**Warning signs:** Tests pass (they call `process_next_event()` manually) but real Discord messages get no response.

### Pitfall 3: DelegationTracker not enabled on ProjectSupervisor
**What goes wrong:** `Supervisor.__init__` only creates `self._delegation_tracker` when `delegation_policy` is passed. `ProjectSupervisor.__init__` passes no `delegation_policy`. So `handle_delegation_request()` returns `approved=False, reason="Delegation not enabled"` for all requests.
**How to avoid:** Pass a default `DelegationPolicy()` to `ProjectSupervisor.__init__` or to `Supervisor.__init__` via `add_project()`.
**Warning signs:** `request_task()` always returns `DelegationResult(approved=False, reason="Delegation not enabled")`.

### Pitfall 4: JSON serialization of set for seen_items
**What goes wrong:** `json.dumps(self._seen_items)` raises `TypeError: Object of type set is not JSON serializable`.
**How to avoid:** Always serialize as `json.dumps(list(self._seen_items))` and restore as `set(json.loads(raw))`.

### Pitfall 5: StrategistCog.initialize() ordering with CompanyAgent
**What goes wrong:** `strategist_cog.initialize()` is called before `company_root` and the Strategist CompanyAgent are created (it's in the "always-run" block; CompanyRoot is in the "project-only" block). After Phase 16, if `initialize()` needs the CompanyAgent reference to register callbacks, this ordering breaks.
**How to avoid:** Move CompanyAgent callback wiring to after `add_company_agent()` in the project-only block, separate from `strategist_cog.initialize()`. The cog's `initialize()` call in the always-run block can remain for channel resolution; a second wiring step connects the cog to the container in the project-only block.

---

## Code Examples

### CompanyAgent._handle_event() — target implementation

```python
# Source: codebase pattern from FulltimeAgent._handle_event()
async def _handle_event(self, event: dict[str, Any]) -> None:
    event_type = event.get("type", "")

    if event_type == "strategist_message":
        if self._conversation is None:
            logger.warning("Strategist conversation not initialized")
            return
        content = event.get("content", "")
        channel_id = event.get("channel_id")
        response = await self._conversation.send(content)
        if self._on_response is not None:
            await self._on_response(response, channel_id)

    elif event_type == "pm_escalation":
        if self._conversation is None:
            return
        agent_id = event.get("agent_id", "")
        question = event.get("question", "")
        confidence = event.get("confidence", 0.0)
        formatted = (
            f"[PM Escalation] Agent {agent_id} asks: {question}\n"
            f"PM confidence: {confidence:.0%}. Please provide your assessment."
        )
        response = await self._conversation.send(formatted)
        future = event.get("_response_future")
        if future is not None and not future.done():
            future.set_result(response)

    else:
        logger.warning("CompanyAgent: unhandled event type: %s", event_type)
```

### ContinuousAgent.request_task() — target implementation

```python
# Source: codebase pattern from FulltimeAgent.escalate_to_strategist()
async def request_task(
    self,
    task_description: str,
    agent_type: str = "gsd",
    context_overrides: dict[str, str] | None = None,
) -> "DelegationResult":
    """Delegate a task through supervisor via DelegationTracker (AGNT-01)."""
    from vcompany.autonomy.delegation import DelegationRequest, DelegationResult
    if self._request_delegation is None:
        return DelegationResult(approved=False, reason="Delegation not wired")
    request = DelegationRequest(
        requester_id=self.context.agent_id,
        task_description=task_description,
        agent_type=agent_type,
        context_overrides=context_overrides or {},
    )
    return await self._request_delegation(request)
```

### GsdAgent.start() — target addition

```python
# Source: existing pattern in GsdAgent._restore_from_checkpoint()
async def start(self) -> None:
    """Transition to running, open memory, restore FSM state and assignment."""
    await super().start()
    await self._restore_from_checkpoint()
    # AGNT-03: Restore assignment context
    assignment = await self.get_assignment()
    if assignment is not None:
        self._current_assignment = assignment
        logger.info(
            "Restored assignment for %s: item_id=%s",
            self.context.agent_id,
            assignment.get("item_id", "unknown"),
        )
```

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies identified — pure Python wiring of existing code)

---

## Open Questions

1. **Event drain loop for CompanyAgent**
   - What we know: `process_next_event()` must be called externally; no auto-drain exists today.
   - What's unclear: Should CompanyAgent own a self-contained drain task (simplest), or should the caller (VcoBot, test) drive it?
   - Recommendation: Add `_drain_task: asyncio.Task | None` in `CompanyAgent.__init__`, start it in `start()`, cancel in `stop()`. This mirrors the stuck detector pattern in FulltimeAgent and makes the container self-sufficient.

2. **PM escalation response path after ARCH-01**
   - What we know: `FulltimeAgent._on_escalate_to_strategist` currently calls `strategist_cog.handle_pm_escalation()` directly. After ARCH-01 this should route through the CompanyAgent container.
   - What's unclear: Does the response need to be synchronous from PM's perspective (await a Future), or fire-and-forget?
   - Recommendation: Use a `asyncio.Future` embedded in the event dict (see `pm_escalation` example above). PM creates a Future, embeds it, posts the event, then awaits the Future. CompanyAgent resolves it after getting the response. This is the same pattern as `_pending_escalations` in StrategistCog.

3. **DelegationPolicy defaults**
   - What we know: ProjectSupervisor passes no policy today, so delegation is disabled.
   - Recommendation: Add `delegation_policy: DelegationPolicy | None = DelegationPolicy()` as a default argument to `ProjectSupervisor.__init__`, which passes it to `Supervisor.__init__`. This enables delegation with conservative defaults (3 concurrent, 10/hour) without requiring VcoBot.on_ready changes.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase read: `src/vcompany/agent/company_agent.py` — CompanyAgent._handle_event() is confirmed `pass`
- Direct codebase read: `src/vcompany/bot/cogs/strategist.py` — StrategistConversation owned by StrategistCog, confirmed
- Direct codebase read: `src/vcompany/agent/continuous_agent.py` — only `cycle_count` persisted, no `seen_items` etc.
- Direct codebase read: `src/vcompany/agent/gsd_agent.py` — `set_assignment()` / `get_assignment()` exist; `start()` does not restore `_current_assignment`
- Direct codebase read: `src/vcompany/autonomy/delegation.py` — DelegationTracker fully implemented
- Direct codebase read: `src/vcompany/supervisor/supervisor.py` — `handle_delegation_request()` returns disabled when policy is None
- Direct codebase read: `src/vcompany/bot/client.py` — VcoBot.on_ready wiring patterns fully understood
- Direct codebase read: `src/vcompany/container/memory_store.py` — set/get/checkpoint API confirmed

---

## Metadata

**Confidence breakdown:**
- ARCH-01 (Strategist inversion): HIGH — `_handle_event()` is literally `pass`, StrategistConversation is in StrategistCog, clear inversion path
- AGNT-01 (request_task): HIGH — DelegationTracker, handle_delegation_request(), and DelegationRequest all exist; only missing is callback wiring + policy enablement
- AGNT-02 (ContinuousAgent persistence): HIGH — MemoryStore API is clear, keys and types are well-defined, pattern exists for cycle_count
- AGNT-03 (GsdAgent context restore): HIGH — set_assignment/get_assignment exist, start() gap is confirmed by code read

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable codebase, no external dependencies)
