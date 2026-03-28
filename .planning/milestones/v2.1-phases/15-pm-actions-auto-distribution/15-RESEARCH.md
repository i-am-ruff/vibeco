# Phase 15: PM Actions & Auto Distribution - Research

**Researched:** 2026-03-28
**Domain:** PM proactive management — auto task distribution, integration triggers, agent lifecycle requests, Strategist escalation, stuck-agent detection
**Confidence:** HIGH

## Summary

Phase 15 activates the PM as a proactive actor rather than a passive event log. The infrastructure wired in Phases 11-14 (event queue, backlog, ProjectStateManager, review gates) already contains the raw primitives needed. What is missing is wiring those primitives to behaviors triggered by incoming events inside `FulltimeAgent._handle_event()`.

Currently `_handle_event()` has two categories of logic: (a) real task lifecycle operations (`task_completed`, `task_failed`, `request_assignment`, `add_backlog_item`) that actually call `ProjectStateManager`, and (b) stub logging handlers for `health_change`, `gsd_transition`, `briefing`, and `escalation` events that emit `logger.info` and do nothing further. Phase 15 replaces those stubs with real actions: automatic next-task assignment, integration review trigger, agent recruitment/removal via `ProjectSupervisor`, Strategist escalation via `StrategistCog`, and stuck-state intervention via Discord message.

The separation of concerns is clean. `FulltimeAgent` owns PM business logic; `ProjectSupervisor` owns the agent lifecycle (add/stop children); `StrategistCog` owns escalation to the Strategist conversation; `VcoBot.on_ready` owns wiring. No new classes are needed — this is pure method implementation and callback wiring.

The one new infrastructure piece is the stuck-agent detector (PMAC-05): a per-agent timestamp that records when each GsdAgent last changed its `inner_state`. A background `asyncio.Task` running inside `FulltimeAgent` polls these timestamps against a configurable threshold and sends a Discord message via `comm_port` or directly via a callback to the agent's channel when the threshold is exceeded.

**Primary recommendation:** Implement PMAC-01..05 as new methods on `FulltimeAgent` (or a `PMActions` helper class it delegates to), triggered from `_handle_event()`, wired from `VcoBot.on_ready`. Add a stuck-state tracker as a lightweight background loop inside `FulltimeAgent`.

## Project Constraints (from CLAUDE.md)

- Pure Python 3.12+; all async code uses `asyncio` (no threads for new code)
- No new external libraries — v2.1 is pure wiring of existing v2.0 code
- `asyncio.create_subprocess_exec` for subprocess calls in async contexts
- No GitPython; no SQLAlchemy; no Flask/FastAPI
- Use `pydantic` for any new config/model validation
- Filesystem state (YAML/Markdown) — no new database
- Discord is the only human interaction channel
- GSD compatibility: vCompany orchestrates, not replaces, GSD

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None — discuss phase was skipped. All decisions at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WORK-03 | When an agent completes its current backlog item, PM assigns the next one from BacklogQueue and the agent starts it automatically | `ProjectStateManager.assign_next_task()` already exists; `GsdAgent.set_assignment()` already exists; need to call `assign_next_task` inside `_handle_event("task_completed")` and send the assignment to the agent via tmux command |
| PMAC-01 | PM can trigger integration review through ProjectSupervisor | `ProjectSupervisor` is a `Supervisor` subclass; PM needs a reference to the project's supervisor; trigger = post a message to a designated review channel or call a callback on `VcoBot` |
| PMAC-02 | PM can inject milestones into BacklogQueue (insert_urgent, append) | `BacklogQueue.insert_urgent()` and `BacklogQueue.append()` already exist; PM already has `self.backlog`; needs an `add_backlog_item` event handler (partially wired) and a Discord slash command path |
| PMAC-03 | PM can request agent recruitment/removal through ProjectSupervisor | `ProjectSupervisor` inherits `_start_child()` and `stop()`; need `add_agent_spec()` / `remove_agent()` methods or PM action methods that call into the supervisor via a callback wired from `VcoBot` |
| PMAC-04 | PM can escalate decisions to Strategist | `StrategistCog.handle_pm_escalation()` already exists and is tested; PM needs a callback `_on_escalate_to_strategist` wired from `VcoBot.on_ready` that calls this method |
| PMAC-05 | PM detects agents stuck in the same GSD state beyond configurable threshold and intervenes via Discord message | Needs per-agent `inner_state` change timestamp tracking; background asyncio loop in `FulltimeAgent`; sends intervention message via existing Discord channel pattern |
</phase_requirements>

## Standard Stack

### Core (no new packages — pure wiring)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio (stdlib) | N/A | Background stuck-detection loop; event routing | Already the async backbone of all agents and bot code |
| discord.py | 2.7.x | Sending intervention messages to agent channels; Strategist escalation | Already wired; `PlanReviewCog._post_throttled()` establishes the Discord message pattern |
| pydantic | 2.11.x | Validating any new config models (e.g., stuck threshold config) | Already used for `BacklogItem`, `ContainerContext`, etc. |

**Installation:** No new packages required. Phase 15 is pure wiring of existing infrastructure.

## Architecture Patterns

### Recommended Project Structure (new files)

```
src/vcompany/
├── agent/
│   └── fulltime_agent.py          # PRIMARY: new action methods, stuck tracker
├── bot/
│   └── client.py                  # Wire new PM action callbacks in on_ready
└── supervisor/
    └── project_supervisor.py      # Add add_agent / remove_agent helpers if needed
```

No new modules required unless PM action logic becomes large enough to warrant a `pm_actions.py` helper (at Claude's discretion).

### Pattern 1: PM Action Methods on FulltimeAgent

**What:** New async methods on `FulltimeAgent` that implement each PM action. Called from `_handle_event()` dispatch or from callbacks wired by `VcoBot`.

**When to use:** When a PM event arrives and the PM must do something beyond logging.

**Example — WORK-03 auto-assignment after task completion:**

```python
# In FulltimeAgent._handle_event(), task_completed branch:
elif event_type == "task_completed" and self._project_state is not None:
    await self._project_state.handle_task_completed(
        event["agent_id"], event["item_id"]
    )
    # WORK-03: immediately assign next task to the same agent
    await self._auto_assign_next(event["agent_id"])

async def _auto_assign_next(self, agent_id: str) -> None:
    """Claim next PENDING item and notify agent via callback."""
    if self._project_state is None:
        return
    item = await self._project_state.assign_next_task(agent_id)
    if item is None:
        logger.info("No pending backlog items for %s -- agent goes idle", agent_id)
        return
    logger.info("Auto-assigned %s to agent %s", item.item_id, agent_id)
    if self._on_assign_task is not None:
        await self._on_assign_task(agent_id, item)
```

The `_on_assign_task` callback is wired from `VcoBot.on_ready` to call a method that sends the assignment to the agent's tmux pane (via the existing `_send_tmux_command` pattern in `PlanReviewCog`).

### Pattern 2: Stuck-State Detector as Background asyncio Task

**What:** A background `asyncio.Task` running inside `FulltimeAgent` that polls per-agent state timestamps and triggers an intervention message when the threshold is exceeded.

**When to use:** PMAC-05 — any time a GSD agent remains in the same `inner_state` for longer than the configured threshold.

**Design:**

```python
# FulltimeAgent.__init__ additions:
self._agent_state_timestamps: dict[str, tuple[str, float]] = {}
# Maps agent_id -> (inner_state_at_last_transition, monotonic_time)
self._stuck_threshold_seconds: int = 1800  # 30 min default, configurable
self._stuck_check_interval: int = 60       # poll every 60s
self._stuck_detected_agents: set[str] = set()  # avoid repeated alerts
self._stuck_detector_task: asyncio.Task | None = None
self._on_send_intervention: Callable[[str, str], Awaitable[None]] | None = None
# Args: agent_id, message

# In FulltimeAgent.start():
self._stuck_detector_task = asyncio.create_task(self._run_stuck_detector())

# In FulltimeAgent.stop() (new override):
if self._stuck_detector_task is not None:
    self._stuck_detector_task.cancel()
    try:
        await self._stuck_detector_task
    except asyncio.CancelledError:
        pass
```

The detector loop checks timestamps every `_stuck_check_interval` seconds. When it detects an agent stuck past the threshold, it calls `_on_send_intervention` (a callback wired to post a Discord message to the agent's channel). The `_stuck_detected_agents` set prevents repeated alerts within the same stuck window — cleared when the agent transitions to a new state.

### Pattern 3: State Transition Updates for Stuck Detector

When a `gsd_transition` event arrives in `_handle_event()`, update the timestamp:

```python
elif event_type == "gsd_transition":
    agent_id = event.get("agent_id", "")
    to_phase = event.get("to_phase", "")
    # Update stuck-detection timestamp
    self._agent_state_timestamps[agent_id] = (to_phase, asyncio.get_event_loop().time())
    # Clear alert suppression since agent is progressing
    self._stuck_detected_agents.discard(agent_id)
    # Existing GATE-02 callback
    if self._on_gsd_review is not None:
        await self._on_gsd_review(agent_id, to_phase)
```

### Pattern 4: PMAC-04 Escalation to Strategist

The `StrategistCog.handle_pm_escalation()` method already exists and accepts `(agent_id, question, confidence_score)`. The PM needs a wired callback:

```python
# FulltimeAgent.__init__ addition:
self._on_escalate_to_strategist: Callable[[str, str, float], Awaitable[str | None]] | None = None

# In _handle_event(), escalation branch:
elif event_type == "escalation":
    reason = event.get("reason", "unknown")
    if self._on_escalate_to_strategist is not None:
        response = await self._on_escalate_to_strategist(
            event.get("agent_id", ""), reason, 0.0
        )
        logger.info("Strategist escalation response for %s: %s", event.get("agent_id"), response)
```

Wired in `VcoBot.on_ready` after `StrategistCog` is initialized:

```python
strategist_cog = self.get_cog("StrategistCog")
if pm_container is not None and strategist_cog is not None:
    async def _escalate_to_strategist(agent_id: str, question: str, score: float) -> str | None:
        return await strategist_cog.handle_pm_escalation(agent_id, question, score)
    pm_container._on_escalate_to_strategist = _escalate_to_strategist
```

### Pattern 5: PMAC-01 Integration Review Trigger

Integration review = PM tells `ProjectSupervisor` to pause new work and run an integration check. Since `ProjectSupervisor` has no integration review method yet, the simplest v2.1 approach is a callback that posts an integration review request to a Discord channel (e.g., `#alerts`) for the owner, and/or calls a `on_integration_review` callback that `VcoBot` wires to whatever action is needed.

```python
# FulltimeAgent.__init__ addition:
self._on_trigger_integration_review: Callable[[], Awaitable[None]] | None = None

# Callable from _handle_event or from a new "trigger_integration" event type:
async def trigger_integration_review(self) -> None:
    """PM requests integration review through ProjectSupervisor."""
    logger.info("PM triggering integration review")
    if self._on_trigger_integration_review is not None:
        await self._on_trigger_integration_review()
```

The `VcoBot` wires `_on_trigger_integration_review` to post a message to `#alerts` or a designated integration channel with context about the review request.

### Pattern 6: PMAC-03 Agent Recruitment/Removal

`ProjectSupervisor` inherits `_start_child()` from `Supervisor` and has `stop()` for removal. For recruitment, the PM needs to call `_start_child(spec)` with a new `ChildSpec`; for removal, it needs to call `child.stop()` on the specific agent.

The cleanest approach: add `add_child_spec(spec: ChildSpec)` and `remove_child(child_id: str)` public helpers to `ProjectSupervisor` (since `_start_child` is private), then wire a PM callback.

```python
# ProjectSupervisor addition:
async def add_child_spec(self, spec: ChildSpec) -> None:
    """Add and start a new agent child spec."""
    self._child_specs.append(spec)
    await self._start_child(spec)

async def remove_child(self, child_id: str) -> None:
    """Stop and deregister a child agent."""
    child = self._children.get(child_id)
    if child is not None and child.state not in ("stopped", "destroyed", "stopping"):
        await child.stop()
    self._child_specs = [s for s in self._child_specs if s.child_id != child_id]
```

PM callback wired from `VcoBot.on_ready`:

```python
# FulltimeAgent.__init__ addition:
self._on_recruit_agent: Callable[[ChildSpec], Awaitable[None]] | None = None
self._on_remove_agent: Callable[[str], Awaitable[None]] | None = None
```

### Pattern 7: WORK-03 Auto-Dispatch of New Assignment to Agent via tmux

When the PM assigns the next task, it must send the assignment to the agent's GSD session. The agent reads from `GsdAgent.get_assignment()` (which reads its own `MemoryStore`). So the dispatch sequence is:

1. `ProjectStateManager.assign_next_task(agent_id)` — claims item from backlog, writes to PM memory under `assignment:{agent_id}`
2. PM writes assignment to agent's own MemoryStore via `GsdAgent.set_assignment(item.model_dump())`
3. PM sends a GSD command via tmux: `/gsd:discuss-phase 1` or the agent's configured `gsd_command` from `ContainerContext`

The bot's `_send_tmux_command` pattern (in `PlanReviewCog`) is the reference: look up the agent in the supervision tree, send the command to its tmux pane. The PM needs access to this mechanism via a callback.

```python
# FulltimeAgent.__init__ addition:
self._on_assign_task: Callable[[str, BacklogItem], Awaitable[None]] | None = None
```

Wired from `VcoBot.on_ready`:

```python
async def _on_assign_task(agent_id: str, item: BacklogItem) -> None:
    container = await self.company_root._find_container(agent_id)
    if isinstance(container, GsdAgent):
        await container.set_assignment(item.model_dump())
    plan_review_cog = self.get_cog("PlanReviewCog")
    if plan_review_cog is not None:
        gsd_command = "/gsd:discuss-phase 1"  # or from container.context.gsd_command
        await plan_review_cog._send_tmux_command(agent_id, gsd_command)
```

### Anti-Patterns to Avoid

- **Importing discord.py inside FulltimeAgent:** The agent container layer must not import discord. All Discord interaction happens via callbacks wired from `VcoBot.on_ready`. The `_on_*` callback pattern established in Phases 13-14 is the right approach.
- **Repeated stuck-agent alerts:** Without a `_stuck_detected_agents` suppression set, the detector loop fires every 60 seconds once an agent is stuck. Track detected agents and only alert once per stuck window.
- **Writing to PM's MemoryStore from GsdAgent:** Only the PM writes to PM's MemoryStore. GsdAgents write to their own MemoryStore. Assignment communication flows: PM assigns via `ProjectStateManager` (PM memory) + `GsdAgent.set_assignment()` (agent memory). Never cross the memory boundary.
- **Calling `_start_child` directly:** It's private. Add `add_child_spec()` and `remove_child()` as public helpers on `ProjectSupervisor`.
- **Blocking the event loop in stuck detector:** The stuck detector loop uses `asyncio.sleep(interval)` between polls, not a synchronous `time.sleep()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Task assignment state tracking | Custom assignment DB | `ProjectStateManager` + `BacklogQueue` | Already built, tested, and persisted in MemoryStore |
| Discord message delivery to agent | New Discord client | `PlanReviewCog._send_tmux_command()` + `_post_throttled()` patterns | Established pattern; includes throttling and logging |
| Strategist conversation | New LLM call plumbing | `StrategistCog.handle_pm_escalation()` | Already built with confidence scoring, decision logging |
| Stuck detection | Full monitoring daemon | Lightweight `asyncio.Task` in `FulltimeAgent` | Monitor checks.py already has git-commit-based stuck detection; this is FSM-state based |
| Agent process lifecycle | Custom process manager | `ProjectSupervisor.add_child_spec()` / `.remove_child()` | Extends existing supervisor infrastructure |

## Common Pitfalls

### Pitfall 1: Missing Task Assignment Write-Back to GsdAgent MemoryStore
**What goes wrong:** PM calls `ProjectStateManager.assign_next_task(agent_id)` which writes to PM's MemoryStore under `assignment:{agent_id}`. But `GsdAgent.get_assignment()` reads from the **agent's own** MemoryStore under `current_assignment`. These are different stores.
**Why it happens:** Both stores use the same key names, creating an illusion of shared state.
**How to avoid:** After `assign_next_task()` returns an item, also call `GsdAgent.set_assignment(item.model_dump())` on the specific GsdAgent container (accessible via `company_root._find_container(agent_id)`).
**Warning signs:** `assign_next_task()` succeeds but the agent's tmux session has no assignment to work from.

### Pitfall 2: Stuck Detector Firing Indefinitely
**What goes wrong:** Once an agent is detected stuck, the 60-second poll loop fires the intervention callback every cycle.
**Why it happens:** No suppression after first alert.
**How to avoid:** Track alerted agents in `_stuck_detected_agents: set[str]`. Clear when `gsd_transition` event arrives for that agent.

### Pitfall 3: Callback Not Wired Before PM Starts Processing Events
**What goes wrong:** `FulltimeAgent` starts before `VcoBot.on_ready` finishes wiring `_on_assign_task`, `_on_escalate_to_strategist`, etc. An early event arrives and the callback is None — silently skipped.
**Why it happens:** The supervision tree starts in `on_ready` before all callback wiring happens.
**How to avoid:** Wire all callbacks before calling `project_sup.set_pm_event_sink()`. The event sink should only be set after all action callbacks are in place. Alternatively, make `_handle_event` queue events that arrived before wiring was complete (but this adds complexity; wiring order is simpler).

### Pitfall 4: Stuck Detector Uses Wall Clock Time for asyncio Context
**What goes wrong:** `datetime.now()` is used to record state transition times. `asyncio` timing uses `loop.time()` (monotonic). Mixing the two causes drift in long-running sessions.
**How to avoid:** Use `asyncio.get_event_loop().time()` (monotonic float) for stuck-detection timestamps. Never use `time.time()` or `datetime.now()` for async timeout calculations.

### Pitfall 5: PMAC-01 Integration Review Without a Real Handler
**What goes wrong:** PM calls `_on_trigger_integration_review()` but the callback is None because no handler was wired. Review silently dropped.
**Why it happens:** PMAC-01 is a new capability with no pre-existing wiring.
**How to avoid:** Log a warning when the callback fires and is None. In `VcoBot.on_ready`, always wire a baseline handler that at minimum posts to `#alerts`.

### Pitfall 6: PMAC-03 Recruitment Adds Agent to ChildSpecs But Not to PM Event Sink
**What goes wrong:** New agent starts but its `_on_phase_transition` callback is not wired to the PM event sink.
**Why it happens:** The wiring loop in `VcoBot.on_ready` only runs once at startup.
**How to avoid:** `add_child_spec()` must also wire `_on_phase_transition` and `_on_review_request` on the new `GsdAgent` before calling `_start_child()`. Extract the wiring logic from `on_ready` into a helper function that can be called for both initial and dynamically added agents.

## Code Examples

Verified patterns from existing codebase:

### Existing: post_event to PM queue (Phase 13 pattern)
```python
# From VcoBot.on_ready (bot/client.py)
async def pm_event_sink(event: dict[str, Any]) -> None:
    await pm_container.post_event(event)
project_sup.set_pm_event_sink(pm_event_sink)
```

### Existing: send tmux command to agent (PlanReviewCog pattern)
```python
# From PlanReviewCog._send_tmux_command() (bot/cogs/plan_review.py)
registry = AgentsRegistry.model_validate_json(...)
entry = registry.agents.get(agent_id)
tmux = TmuxManager()
sent = await asyncio.to_thread(tmux.send_command, entry.pane_id, command)
```

### Existing: Strategist escalation entry point
```python
# StrategistCog.handle_pm_escalation(agent_id, question, confidence_score)
# Returns: str (response) or None (owner escalation needed)
full_response = await strategist_cog.handle_pm_escalation(
    agent_id="gsd-agent-1",
    question="Should we defer phase 3 to v2.2?",
    confidence_score=0.2,
)
```

### Existing: ProjectStateManager assign_next_task
```python
# From autonomy/project_state.py
item = await self._project_state.assign_next_task(agent_id)
# Returns BacklogItem or None if no PENDING items
if item is not None:
    logger.info("Assigned %s to agent %s", item.item_id, agent_id)
```

### Existing: GsdAgent assignment write-back
```python
# From agent/gsd_agent.py
await container.set_assignment(item.model_dump())  # writes to agent's own MemoryStore
```

### Existing: BacklogQueue insert_urgent / append
```python
# From autonomy/backlog.py
await self.backlog.insert_urgent(BacklogItem(title="Urgent: Fix auth bug", priority=10))
await self.backlog.append(BacklogItem(title="New feature: webhooks"))
```

### Existing: Background asyncio task pattern (Scheduler reference)
```python
# From supervisor/scheduler.py (existing pattern for background loops)
self._scheduler_task = asyncio.create_task(self._scheduler.run())
# Cancelled in stop():
self._scheduler_task.cancel()
try:
    await self._scheduler_task
except asyncio.CancelledError:
    pass
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PM only logs events | PM logs + takes actions | Phase 15 | PM becomes proactive actor |
| Agent stays idle after task completion | PM auto-assigns next task | Phase 15 (WORK-03) | Continuous agent throughput without human dispatch |
| Stuck detection via git commits (monitor/checks.py) | Stuck detection via GSD inner_state timestamp | Phase 15 (PMAC-05) | More accurate for GSD agents where stuck = frozen phase, not frozen git |

**Note:** The existing `check_stuck()` in `monitor/checks.py` uses git commit timestamps. PMAC-05 uses a different signal: FSM inner_state last-changed timestamp. Both can coexist — they detect different failure modes.

## Open Questions

1. **PMAC-01: What does "trigger integration review" actually do in v2.1?**
   - What we know: `ProjectSupervisor` exists; the requirement says "through ProjectSupervisor"
   - What's unclear: No integration review pipeline exists yet. Is this just posting a message to `#alerts` + pausing new assignment? Or does it call `vco integrate`?
   - Recommendation: Implement as a callback that posts to `#alerts` with a "PM requests integration review for project X" message. The actual integration pipeline is a future phase concern. Log the request as an event in PM memory.

2. **PMAC-05: What is the configurable threshold stored in?**
   - What we know: `ContainerContext` is immutable once created. `FulltimeAgent.memory` is a `MemoryStore`.
   - What's unclear: Should the threshold be in `agents.yaml` (project config), an env var, or PM's MemoryStore?
   - Recommendation: Add `stuck_threshold_minutes: int = 30` to `FulltimeAgent.__init__` as a constructor parameter; `VcoBot.on_ready` can pass it from `ProjectConfig` or default to 30. This keeps it configurable without adding complexity.

3. **WORK-03: What GSD command should the auto-assigned agent receive?**
   - What we know: `ContainerContext.gsd_command` stores the agent's configured command (`/gsd:discuss-phase 1`). `GsdAgent.inner_state` shows current phase.
   - What's unclear: If the agent was in `ship` phase when its previous task completed, should it restart at `discuss` or at its current phase?
   - Recommendation: Always use the agent's `context.gsd_command` (e.g., `/gsd:discuss-phase 1`) for a fresh task start. The agent's FSM will be in `idle` state after the previous task completes, so `discuss` is the correct entry point.

## Environment Availability

Step 2.6: SKIPPED (no external dependencies identified — Phase 15 is pure wiring of existing Python code and bot infrastructure, no new tools or services required).

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection of `src/vcompany/agent/fulltime_agent.py` — confirmed `_handle_event()` stub handlers and existing action dispatch
- Direct codebase inspection of `src/vcompany/autonomy/project_state.py` — confirmed `assign_next_task()`, `handle_task_completed()`, `handle_task_failed()`
- Direct codebase inspection of `src/vcompany/autonomy/backlog.py` — confirmed `insert_urgent()`, `append()`, `claim_next()`
- Direct codebase inspection of `src/vcompany/agent/gsd_agent.py` — confirmed `set_assignment()`, `make_completion_event()`, `inner_state` property
- Direct codebase inspection of `src/vcompany/bot/cogs/strategist.py` — confirmed `handle_pm_escalation()`, `post_owner_escalation()`
- Direct codebase inspection of `src/vcompany/bot/cogs/plan_review.py` — confirmed `_send_tmux_command()`, `_post_throttled()`, `dispatch_pm_review()`
- Direct codebase inspection of `src/vcompany/bot/client.py` — confirmed callback wiring pattern in `on_ready` for Phases 13-14
- Direct codebase inspection of `src/vcompany/supervisor/project_supervisor.py` — confirmed no `add_child_spec` / `remove_child` public methods yet
- Direct codebase inspection of `src/vcompany/supervisor/supervisor.py` — confirmed `_start_child()` is private; `handle_delegation_request()` shows dynamic child spawning pattern
- Direct codebase inspection of `src/vcompany/monitor/checks.py` — confirmed existing `check_stuck()` uses git commit timestamps (different signal from PMAC-05)

### Secondary (MEDIUM confidence)
- `.planning/phases/14-pm-review-gates/14-RESEARCH.md` — Phase 14 decisions documented: Future gate pattern, throttle tracker, PM event routing wiring
- `.planning/STATE.md` accumulated decisions: Phase 14 deferred "Full PMTier integration for non-plan stages" to Phase 15 (see `plan_review.py` comment line 703)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all existing code inspected directly
- Architecture: HIGH — all integration points found in source; patterns verified in codebase
- Pitfalls: HIGH — derived from direct code inspection of boundary conditions (memory isolation, callback wiring order)
- Open questions: MEDIUM — questions are judgment calls, not unknowns about existing code

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable internal codebase; no external dependencies)
