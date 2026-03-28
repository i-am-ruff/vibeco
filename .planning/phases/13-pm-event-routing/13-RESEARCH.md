# Phase 13: PM Event Routing - Research

**Researched:** 2026-03-28
**Domain:** Python asyncio event queue wiring — supervision tree callbacks to FulltimeAgent.post_event()
**Confidence:** HIGH

## Summary

Phase 13 wires four categories of runtime signals into the PM's (FulltimeAgent) `asyncio.Queue`-based event queue. The queue infrastructure already exists and is fully functional — `FulltimeAgent.post_event()` enqueues events, `_handle_event()` processes them, and `process_next_event()` drives the loop. Phase 13 is pure wiring: make the right things call `post_event()` at the right time.

The existing callback mechanism in `Supervisor._make_state_change_callback()` already fires on significant state changes (errored, running, stopped, blocked, stopping). Currently that callback only updates `_health_reports` and optionally calls `on_health_change` (which routes to `HealthCog._notify_state_change`). The same callback is the natural injection point for PM event routing: after updating health reports, also call the PM's `post_event()`.

GSD transitions and ContinuousAgent briefings are NOT covered by the state-change callback because they are inner-state (compound state sub-state) transitions, not outer lifecycle transitions. These require targeted injection at the call sites where `advance_phase()` and `advance_cycle("report")` are invoked.

**Primary recommendation:** Add a `pm_event_callback` parameter to `Supervisor` and `CompanyRoot`, wire it to `FulltimeAgent.post_event()` in `VcoBot.on_ready()`, inject it into `GsdAgent.advance_phase()` and `ContinuousAgent.advance_cycle()` through an overridable hook, and produce correctly typed event dicts at each injection point.

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
| PMRT-01 | Agent health state changes (RUNNING→ERRORED, etc.) are routed to PM's event queue | Supervisor._make_state_change_callback() already observes these; extend callback to also call pm.post_event() with a health_change event dict |
| PMRT-02 | GSD state transitions (DISCUSS→PLAN, PLAN→EXECUTE, etc.) are routed to PM's event queue | GsdAgent.advance_phase() checkpoints but never notifies PM; needs an on_phase_transition hook called from advance_phase() |
| PMRT-03 | Briefings from ContinuousAgents are routed to PM's event queue | ContinuousAgent.advance_cycle("report") enters report phase; needs a hook that fires when inner_state becomes "report", capturing any briefing content |
| PMRT-04 | Escalations (agent BLOCKED) are routed to PM's event queue | AgentContainer.block() already fires _on_state_change_cb; state is "blocked", blocked_reason is available — extend state-change path to detect blocked and produce escalation event |
</phase_requirements>

## Standard Stack

No new libraries required. Phase 13 uses existing project stack exclusively.

### Core (existing)
| Component | Location | Purpose |
|-----------|----------|---------|
| `FulltimeAgent` | `src/vcompany/agent/fulltime_agent.py` | PM container with `asyncio.Queue` event queue |
| `FulltimeAgent.post_event()` | same | Target method — enqueues `dict[str, Any]` events |
| `FulltimeAgent._handle_event()` | same | Dispatcher — needs new event type cases |
| `Supervisor._make_state_change_callback()` | `src/vcompany/supervisor/supervisor.py` | Existing hook called on every FSM state change |
| `CompanyRoot` | `src/vcompany/supervisor/company_root.py` | Holds PM container reference via `_pm_container` on bot |
| `GsdAgent.advance_phase()` | `src/vcompany/agent/gsd_agent.py` | Called on every GSD stage transition |
| `ContinuousAgent.advance_cycle()` | `src/vcompany/agent/continuous_agent.py` | Called on every cycle phase transition |
| `AgentContainer.block()` | `src/vcompany/container/container.py` | Called when agent enters BLOCKED state |
| `VcoBot.on_ready()` | `src/vcompany/bot/client.py` | Wires PM container reference, correct place to inject callback |

**Version verification:** No new packages. Existing `python-statemachine>=3.0.0` and `asyncio` stdlib cover all needs.

## Architecture Patterns

### Existing Event Flow (before Phase 13)

```
FSM transition fires
  → ContainerLifecycle.after_transition()
    → AgentContainer._on_state_change()
      → updates _last_activity
      → calls _on_state_change_cb(health_report)
        → Supervisor._make_state_change_callback
          → updates _health_reports[child_id]
          → calls on_health_change(report)  [if configured]
            → HealthCog._notify_state_change()
```

PM event queue is never touched in this path. Phase 13 extends it.

### Pattern 1: Extending the State-Change Callback for PMRT-01 and PMRT-04

The `Supervisor._make_state_change_callback()` already receives a `HealthReport` on every significant transition. Extending it to also post PM events requires:

1. Add `pm_event_sink: Callable[[dict[str, Any]], Awaitable[None]] | None` parameter to `Supervisor.__init__()` and propagate it through `ProjectSupervisor` and `CompanyRoot.add_project()`.
2. Inside the callback, after updating `_health_reports`, check the new state and enqueue the appropriate event.

**health_change event** (PMRT-01):
```python
# Source: codebase analysis — HealthReport.state is a str like "errored", "running", "blocked"
{
    "type": "health_change",
    "agent_id": report.agent_id,
    "state": report.state,
    "inner_state": report.inner_state,  # may be None
    "error_count": report.error_count,
}
```

**escalation event** (PMRT-04):
```python
# Detect: report.state == "blocked" (from AgentContainer.block())
{
    "type": "escalation",
    "agent_id": report.agent_id,
    "reason": report.blocked_reason,  # str, max 200 chars (AgentContainer.block() enforces this)
}
```

Both events are produced inside the same sync callback. Since `post_event()` is `async`, use `asyncio.get_running_loop().create_task(pm_event_sink(event))` — the same pattern already used in `_make_state_change_callback()` for `on_health_change`.

### Pattern 2: GSD Transition Hook for PMRT-02

`GsdAgent.advance_phase()` is the single call site for all GSD phase transitions. Add an optional `on_phase_transition` callback to `GsdAgent.__init__()`:

```python
# Pattern: same as on_state_change_cb on AgentContainer
self._on_phase_transition: Callable[[str, str, str], Awaitable[None]] | None = None
# Signature: (agent_id, from_phase, to_phase) -> Awaitable[None]
```

Call it from `advance_phase()` after the FSM transition succeeds, before checkpointing:

```python
async def advance_phase(self, phase: str) -> None:
    from_phase = self.inner_state or "idle"
    # ... existing FSM transition call ...
    await self._checkpoint_phase()
    if self._on_phase_transition is not None:
        await self._on_phase_transition(self.context.agent_id, from_phase, phase)
```

**gsd_transition event** (PMRT-02):
```python
{
    "type": "gsd_transition",
    "agent_id": "<agent_id>",
    "from_phase": "plan",   # previous inner_state (e.g., idle/discuss/plan/execute/uat)
    "to_phase": "execute",  # new inner_state
}
```

The callback is wired at container creation time. The factory (`container/factory.py`) creates containers from specs; for `GsdAgent` instances the supervisor wires the callback after calling `create_container()`.

### Pattern 3: Briefing Hook for PMRT-03

`ContinuousAgent.advance_cycle("report")` is called when entering the REPORT phase. The briefing content is produced by the agent's work logic (not yet implemented per v2.1 scope). For Phase 13, wire the routing mechanism; content defaults to empty string or a placeholder.

Add `on_briefing` callback to `ContinuousAgent.__init__()`:

```python
self._on_briefing: Callable[[str, str], Awaitable[None]] | None = None
# Signature: (agent_id, content) -> Awaitable[None]
```

Override `advance_cycle()` to fire when phase == "report":

```python
async def advance_cycle(self, phase: str, briefing_content: str = "") -> None:
    # ... existing FSM transition and checkpoint ...
    if phase == "report" and self._on_briefing is not None:
        await self._on_briefing(self.context.agent_id, briefing_content)
```

**briefing event** (PMRT-03):
```python
{
    "type": "briefing",
    "agent_id": "<agent_id>",
    "content": "<report text or empty string>",
}
```

### Pattern 4: Wiring in VcoBot.on_ready()

All callbacks converge at `VcoBot.on_ready()` where both `pm_container` and the supervision tree are available. The wiring sequence:

```python
# After pm_container is found and wired (lines ~318-336 of client.py)
if pm_container is not None:
    # Create async sink that posts to PM's queue
    async def pm_event_sink(event: dict[str, Any]) -> None:
        await pm_container.post_event(event)

    # 1. Wire state-change routing (PMRT-01, PMRT-04) via project_sup
    project_sup.set_pm_event_sink(pm_event_sink)

    # 2. Wire GSD transitions and briefings on each child container
    for child in project_sup.children.values():
        if isinstance(child, GsdAgent):
            async def _make_phase_cb(agent: GsdAgent) -> Callable:
                async def _cb(agent_id: str, from_phase: str, to_phase: str) -> None:
                    await pm_container.post_event({
                        "type": "gsd_transition",
                        "agent_id": agent_id,
                        "from_phase": from_phase,
                        "to_phase": to_phase,
                    })
                return _cb
            child._on_phase_transition = await _make_phase_cb(child)
        elif isinstance(child, ContinuousAgent):
            # Similar pattern for briefing callback
            ...
```

### Pattern 5: Handling New Event Types in FulltimeAgent._handle_event()

`FulltimeAgent._handle_event()` currently handles: `task_completed`, `task_failed`, `add_backlog_item`, `request_assignment`. Unknown types log a warning. Add handlers for Phase 13 event types:

```python
elif event_type == "health_change":
    logger.info(
        "PM received health_change: agent=%s state=%s",
        event.get("agent_id"), event.get("state"),
    )
    # Phase 13: route to queue only, PM action logic deferred to Phase 14+
elif event_type == "gsd_transition":
    logger.info(
        "PM received gsd_transition: agent=%s %s->%s",
        event.get("agent_id"), event.get("from_phase"), event.get("to_phase"),
    )
elif event_type == "briefing":
    logger.info(
        "PM received briefing from agent=%s content_len=%d",
        event.get("agent_id"), len(event.get("content", "")),
    )
elif event_type == "escalation":
    logger.info(
        "PM received escalation: agent=%s reason=%s",
        event.get("agent_id"), event.get("reason"),
    )
```

These are logged-only handlers in Phase 13. Phase 14/15 (PM Actions) will add real logic.

### Recommended Project Structure (unchanged)
```
src/vcompany/
├── agent/
│   ├── gsd_agent.py           # Add _on_phase_transition callback hook
│   └── continuous_agent.py    # Add _on_briefing callback hook + briefing_content param
├── supervisor/
│   └── supervisor.py          # Add pm_event_sink param + extend state-change callback
└── agent/
    └── fulltime_agent.py      # Add health_change, gsd_transition, briefing, escalation handlers
```

### Anti-Patterns to Avoid

- **Async in sync callback without create_task:** The `_make_state_change_callback()` returns a sync function. `post_event()` is async. Always use `loop.create_task()` — the pattern used for `on_health_change` in the same method.
- **Import FulltimeAgent from supervisor.py:** `supervisor.py` does not import from `fulltime_agent.py`. Keep it that way. Pass the sink as a generic `Callable` — not a typed `FulltimeAgent` reference.
- **Wiring callbacks at container creation vs. after:** The `GsdAgent` and `ContinuousAgent` callbacks cannot be wired inside `_start_child()` because the supervisor doesn't know the PM container. Wire them in `VcoBot.on_ready()` after both the project supervisor and PM container are known.
- **Firing briefing event for every advance_cycle call:** Only fire `_on_briefing` when `phase == "report"`, not on every cycle advance.
- **Duplicate escalation events:** `block()` fires `_on_state_change_cb` which updates health. Both the PMRT-01 health_change path and a separate PMRT-04 escalation path would fire. Produce a `health_change` event for state transitions generally, and an additional `escalation` event specifically when `report.state == "blocked"`. The PM receives both; that is intentional — they carry different information.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Thread-safe async call from sync callback | Custom threading bridge | `asyncio.get_running_loop().create_task()` — already used in `_make_state_change_callback` for `on_health_change` |
| Event serialization | Custom codec | Plain `dict[str, Any]` — same as existing event types in `make_completion_event()` |
| Event queue | Custom buffer | `FulltimeAgent._event_queue` (asyncio.Queue) already exists |

**Key insight:** All required infrastructure exists. Phase 13 adds wiring, not new abstractions.

## Common Pitfalls

### Pitfall 1: Calling post_event() From a Sync Context
**What goes wrong:** `_make_state_change_callback()` returns a sync `Callable[[HealthReport], None]`. Calling an async method directly raises a RuntimeError or silently drops the coroutine.
**Why it happens:** FSM `after_transition` hooks are sync; the callback chain is sync.
**How to avoid:** Use `loop.create_task(coro)` inside the callback, exactly as done for `on_health_change` at line ~256 of `supervisor.py`. Capture `loop = asyncio.get_running_loop()` at callback creation time, not inside the inner function.
**Warning signs:** "coroutine was never awaited" warnings in logs.

### Pitfall 2: pm_event_sink Wired Before PM Container Exists
**What goes wrong:** `add_project()` is called in `on_ready()` before the PM container is identified (the identification loop happens after `add_project()`).
**Why it happens:** `on_ready()` calls `add_project()` to start the supervisor, then iterates `project_sup.children` to find the PM. The sink must be set after this loop.
**How to avoid:** Add a `set_pm_event_sink(sink)` method to `Supervisor` that can be called after construction. Do not pass the sink to `add_project()` — set it afterwards once the PM container is known.
**Warning signs:** Events never appear in the PM's queue because the sink was None at callback creation time.

### Pitfall 3: GsdAgent Callback Closure Bug
**What goes wrong:** Wiring phase callbacks in a loop with `for child in children.values()` and using `child` in the closure captures the loop variable, not the specific child. All closures reference the last child.
**Why it happens:** Python closure semantics — loop variable is captured by reference.
**How to avoid:** Use a factory function `_make_phase_cb(agent)` that takes the agent as a parameter, creating a proper closure per agent. Same pattern as `_make_state_change_callback(child_id)` in supervisor.py which uses a closure over `child_id`.
**Warning signs:** All GSD transition events show the same (last) agent_id.

### Pitfall 4: Missing event type cases cause "Unhandled event type" warnings
**What goes wrong:** `FulltimeAgent._handle_event()` logs a warning for unknown event types. If Phase 13 doesn't add handlers for the four new types, logs fill with warnings on every event.
**Why it happens:** The else branch on line 135 of `fulltime_agent.py` is a catch-all.
**How to avoid:** Add `elif event_type in ("health_change", "gsd_transition", "briefing", "escalation"):` before the else, with log-only handlers for Phase 13.
**Warning signs:** "Unhandled event type: health_change" appearing in logs.

### Pitfall 5: advance_cycle() signature change breaks existing callers
**What goes wrong:** Adding `briefing_content: str = ""` to `advance_cycle()` is safe (default argument). But if tests call `advance_cycle("report")` with positional args, the new signature must remain backward compatible.
**Why it happens:** Existing tests call `await agent.advance_cycle("report")` — the new optional arg must come after `phase`.
**How to avoid:** Always add `briefing_content` as a keyword argument with default `""`. Verify all existing test call sites.
**Warning signs:** TypeError in existing `test_continuous_agent.py` tests.

## Code Examples

### Example 1: Extending state-change callback (PMRT-01, PMRT-04)
```python
# In Supervisor._make_state_change_callback() — extend existing callback
def _make_state_change_callback(self, child_id: str) -> Callable[[HealthReport], None]:
    loop_ref: list[asyncio.AbstractEventLoop | None] = [None]

    def callback(report: HealthReport) -> None:
        self._health_reports[child_id] = report

        # ... existing delegation cleanup ...
        # ... existing restarting guard ...
        # ... existing event.set() for errored/stopped/stopping ...

        # Notify HealthCog (existing)
        if self._on_health_change is not None and report.state in (...):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._on_health_change(report))
            except RuntimeError:
                pass

        # NEW: Route to PM event queue (PMRT-01, PMRT-04)
        if self._pm_event_sink is not None:
            try:
                loop = asyncio.get_running_loop()
                # PMRT-01: health_change event for any significant state change
                if report.state in ("errored", "running", "blocked", "stopped"):
                    loop.create_task(self._pm_event_sink({
                        "type": "health_change",
                        "agent_id": report.agent_id,
                        "state": report.state,
                        "inner_state": report.inner_state,
                        "error_count": report.error_count,
                    }))
                # PMRT-04: escalation event specifically for BLOCKED state
                if report.state == "blocked":
                    loop.create_task(self._pm_event_sink({
                        "type": "escalation",
                        "agent_id": report.agent_id,
                        "reason": report.blocked_reason or "unknown",
                    }))
            except RuntimeError:
                pass  # No running loop (test teardown)

    return callback
```

### Example 2: GSD transition hook in GsdAgent.advance_phase()
```python
# GsdAgent.__init__() — add:
self._on_phase_transition: Callable[[str, str, str], Awaitable[None]] | None = None

# GsdAgent.advance_phase() — extend:
async def advance_phase(self, phase: str) -> None:
    from_phase = self.inner_state or "idle"  # capture before transition
    # ... existing FSM transition ...
    await self._checkpoint_phase()
    if self._on_phase_transition is not None:
        await self._on_phase_transition(self.context.agent_id, from_phase, phase)
```

### Example 3: Briefing hook in ContinuousAgent.advance_cycle()
```python
# ContinuousAgent.__init__() — add:
self._on_briefing: Callable[[str, str], Awaitable[None]] | None = None

# ContinuousAgent.advance_cycle() — extend signature and body:
async def advance_cycle(self, phase: str, briefing_content: str = "") -> None:
    # ... existing FSM transition + checkpoint (unchanged) ...
    if phase == "report" and self._on_briefing is not None:
        await self._on_briefing(self.context.agent_id, briefing_content)
```

### Example 4: Wiring in VcoBot.on_ready()
```python
# After pm_container is identified (after the for-child loop):
if pm_container is not None:
    async def pm_sink(event: dict[str, Any]) -> None:
        await pm_container.post_event(event)

    # Wire health_change + escalation routing
    project_sup.set_pm_event_sink(pm_sink)

    # Wire GSD transition routing
    for child in project_sup.children.values():
        if isinstance(child, GsdAgent):
            def _make_gsd_cb(sink: ...) -> Callable:
                async def _cb(agent_id: str, from_p: str, to_p: str) -> None:
                    await sink({"type": "gsd_transition", "agent_id": agent_id,
                                "from_phase": from_p, "to_phase": to_p})
                return _cb
            child._on_phase_transition = _make_gsd_cb(pm_sink)
        elif isinstance(child, ContinuousAgent):
            def _make_briefing_cb(sink: ...) -> Callable:
                async def _cb(agent_id: str, content: str) -> None:
                    await sink({"type": "briefing", "agent_id": agent_id, "content": content})
                return _cb
            child._on_briefing = _make_briefing_cb(pm_sink)
```

### Example 5: New event handlers in FulltimeAgent._handle_event()
```python
elif event_type == "health_change":
    logger.info(
        "PM received health_change: agent=%s state=%s inner=%s",
        event.get("agent_id"), event.get("state"), event.get("inner_state"),
    )
elif event_type == "gsd_transition":
    logger.info(
        "PM received gsd_transition: agent=%s %s->%s",
        event.get("agent_id"), event.get("from_phase"), event.get("to_phase"),
    )
elif event_type == "briefing":
    logger.info(
        "PM received briefing from %s (content_len=%d)",
        event.get("agent_id"), len(event.get("content", "")),
    )
elif event_type == "escalation":
    logger.info(
        "PM received escalation: agent=%s reason=%s",
        event.get("agent_id"), event.get("reason"),
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Health changes only routed to Discord #alerts via AlertsCog | Health changes routed to both Discord (existing) and PM event queue (Phase 13) | Phase 13 | PM can observe and act on agent health, not just Discord |
| GSD phase transitions only checkpointed to SQLite | GSD phase transitions also routed to PM queue | Phase 13 | PM gains visibility into agent workflow progress |
| ContinuousAgent REPORT phase fires no external signal | REPORT phase fires PM briefing event | Phase 13 | PM can consume periodic agent reports |
| BLOCKED state visible only in health tree | BLOCKED state also generates PM escalation event | Phase 13 | PM can react to blocks, not just observe them in health tree |

## Open Questions

1. **Should health_change events be filtered to significant transitions only?**
   - What we know: `on_health_change` currently only fires for `errored`, `running`, `stopped`, `blocked`, `stopping`
   - What's unclear: Should `creating` and `sleeping` transitions produce health_change events for PM?
   - Recommendation: Match the existing `on_health_change` filter — only `errored`, `running`, `blocked`, `stopped`. This avoids event spam while covering the meaningful transitions.

2. **Who calls advance_cycle() with briefing_content?**
   - What we know: ContinuousAgent's actual GATHER/ANALYZE/ACT work logic is deferred to v3 (per REQUIREMENTS.md Out of Scope)
   - What's unclear: In v2.1, nothing calls `advance_cycle("report", content)` with real content
   - Recommendation: Wire the mechanism fully; content defaults to `""`. Tests verify the event is posted when `advance_cycle("report", "some content")` is called explicitly. Real content arrives in v3.

3. **Should pm_event_sink also be added to CompanyRoot for company-level agent events?**
   - What we know: CompanyRoot manages company agents (Strategist) separately from project supervisors; `on_health_change` is on CompanyRoot but project supervisor health routing goes through add_project()
   - What's unclear: Requirements say "agent health state changes" — does this include the Strategist CompanyAgent?
   - Recommendation: Wire on `ProjectSupervisor` (project agents) only — this covers GsdAgents and ContinuousAgents which are the ones with BLOCKED/ERRORED/GSD-transition events. Strategist events are a v3 concern.

## Environment Availability

Step 2.6: SKIPPED — Phase 13 is pure Python wiring of existing code. No external tools, services, databases, or CLI utilities beyond what is already installed.

## Validation Architecture

nyquist_validation is explicitly `false` in `.planning/config.json`. Skipping this section per config.

## Sources

### Primary (HIGH confidence)
- `src/vcompany/agent/fulltime_agent.py` — FulltimeAgent.post_event(), _handle_event(), _event_queue structure confirmed by direct read
- `src/vcompany/supervisor/supervisor.py` — _make_state_change_callback() pattern and on_health_change wiring confirmed by direct read
- `src/vcompany/container/container.py` — AgentContainer.block(), _on_state_change_cb(), _blocked_reason confirmed by direct read
- `src/vcompany/agent/gsd_agent.py` — advance_phase() call site confirmed; no existing PM notification
- `src/vcompany/agent/continuous_agent.py` — advance_cycle() call site confirmed; no existing briefing notification
- `src/vcompany/bot/client.py` — VcoBot.on_ready() wiring location, pm_container identification loop confirmed by direct read
- `src/vcompany/container/health.py` — HealthReport fields (state, inner_state, blocked_reason, error_count) confirmed
- `.planning/REQUIREMENTS.md` — PMRT-01..PMRT-04 requirements confirmed

### Secondary (MEDIUM confidence)
- `tests/test_company_agent.py`, `tests/test_gsd_agent.py` — existing test patterns and fixtures confirmed, establishing test conventions for Phase 13 tests

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — existing code confirmed by direct read; no new dependencies
- Architecture: HIGH — all injection points identified by tracing actual call paths through codebase
- Pitfalls: HIGH — derived from actual code patterns in supervisor.py and verified against existing test suite

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable internal architecture, no external dependencies)
