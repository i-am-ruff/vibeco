# Phase 6: Resilience - Research

**Researched:** 2026-03-28
**Domain:** Rate-limited messaging, upstream outage detection, degraded mode for external service failure
**Confidence:** HIGH

## Summary

Phase 6 adds three resilience capabilities to the existing v2 supervision tree: (1) a rate-aware message queue between the system and Discord API, (2) upstream outage detection in supervisors so bulk failures trigger global backoff instead of per-agent restart storms, and (3) a degraded mode when Claude API is unreachable. All three are infrastructure-only changes layered onto existing code -- no new agent types, no new FSM states, no new Discord commands.

The codebase already has solid foundations: `AlertsCog._send_or_buffer()` demonstrates the buffer-on-disconnect pattern, `RestartTracker` provides sliding-window failure counting, and the `Supervisor._handle_child_failure()` method is the single entry point for failure handling. The v1 `CrashTracker` with its backoff schedule and circuit breaker is useful prior art but lives in the old orchestrator module and should not be imported -- the patterns should be reimplemented cleanly in the v2 supervisor layer.

**Primary recommendation:** Build a `MessageQueue` class with priority levels and rate-aware dispatch as the core new component. Extend `Supervisor._handle_child_failure()` with temporal correlation to detect bulk failures. Add a `DegradedModeManager` at `CompanyRoot` level that monitors Claude API health and controls dispatch gating.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
No locked decisions -- all implementation choices at Claude's discretion (pure infrastructure phase).

### Claude's Discretion
All implementation choices are at Claude's discretion. Key technical anchors from requirements:
- Rate-aware batching: health reports debounced, supervisor commands prioritized, exponential backoff on 429s (RESL-01)
- Upstream outage detection: all children failing simultaneously triggers global backoff, not per-agent restart loops (RESL-02)
- Degraded mode: Claude unreachable -> containers stay alive, no new dispatches, owner notified, auto-recovery (RESL-03)

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RESL-01 | Communication layer queues outbound Discord messages with rate-aware batching -- health reports debounced, supervisor commands prioritized over status updates, exponential backoff on 429s | MessageQueue with asyncio.PriorityQueue, priority enum, debounce timer for health, backoff on HTTPException 429 |
| RESL-02 | Supervisor distinguishes upstream outage (all children failing simultaneously within a short window) from individual agent failure -- bulk failure triggers global backoff instead of per-agent restart loops | BulkFailureDetector in Supervisor tracking failure timestamps, correlation window, global backoff state |
| RESL-03 | System enters degraded mode when Claude servers are unreachable -- existing containers stay alive, no new dispatches, owner notified, automatic recovery when service returns | DegradedModeManager at CompanyRoot level, health check probe, dispatch gate, owner notification |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Use httpx for HTTP clients (sync + async), not requests or aiohttp
- Use asyncio for all async orchestration
- No database -- state lives in files (YAML/Markdown) and per-agent SQLite
- No web framework -- Discord is the interface
- discord.py 2.7.x for all Discord interaction
- anthropic SDK 0.86.x for Claude API calls
- All agent communication flows through Discord (CONT-06)
- Pin libtmux tightly (0.55.x)

## Standard Stack

### Core (no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio (stdlib) | N/A | PriorityQueue, Event, Lock for message queue and coordination | Already used throughout; PriorityQueue is stdlib |
| discord.py | 2.7.x | Already handles most rate limits internally; catch HTTPException for 429s that slip through | Already installed |
| anthropic | 0.86.x | SDK has built-in retry (2x) with backoff for 429/5xx; catch APIConnectionError for outage detection | Already installed |
| httpx | 0.28.x | Health check probe for Claude API (lightweight HEAD/GET) | Already installed |

### No new packages needed
This phase requires zero new dependencies. All patterns are implementable with asyncio stdlib primitives (PriorityQueue, Event, Lock, asyncio.wait_for) plus the existing discord.py and anthropic SDK.

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
  resilience/
    __init__.py
    message_queue.py      # RESL-01: Priority message queue with rate limiting
    bulk_failure.py        # RESL-02: Bulk failure detection for supervisors
    degraded_mode.py       # RESL-03: Degraded mode manager
```

### Pattern 1: Priority Message Queue (RESL-01)

**What:** An async message queue that sits between system components (supervisors, health cog, containers) and Discord API sends. Messages have priority levels; the queue drains at a rate-limited pace; health reports are debounced.

**When to use:** All outbound Discord messages route through this queue.

**Design:**
```python
import asyncio
from dataclasses import dataclass, field
from enum import IntEnum
from datetime import datetime, timezone

class MessagePriority(IntEnum):
    """Lower number = higher priority (asyncio.PriorityQueue pops lowest first)."""
    ESCALATION = 0      # Owner alerts, circuit breaker
    SUPERVISOR = 1      # Restart notifications, state changes
    STATUS = 2          # Health reports, routine updates
    HEALTH_DEBOUNCED = 3 # Debounced health batch

@dataclass(order=True)
class QueuedMessage:
    priority: int
    timestamp: float = field(compare=True)
    # Non-compared fields
    channel_id: int = field(compare=False)
    content: str | None = field(default=None, compare=False)
    embed: object | None = field(default=None, compare=False)

class MessageQueue:
    """Rate-aware priority message queue for Discord sends.

    - asyncio.PriorityQueue for ordering
    - Token bucket or simple interval for rate limiting
    - Exponential backoff on 429s
    - Debounce timer for health reports (coalesce within window)
    - Background drain task
    """

    def __init__(
        self,
        bot,  # VcoBot reference for actual sends
        max_rate: float = 5.0,  # messages per second (conservative)
        debounce_seconds: float = 5.0,  # health report debounce
    ):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._bot = bot
        self._interval = 1.0 / max_rate
        self._debounce_seconds = debounce_seconds
        self._backoff: float = 0.0
        self._drain_task: asyncio.Task | None = None
        self._health_buffer: dict[int, QueuedMessage] = {}
        self._health_timer: asyncio.TimerHandle | None = None

    async def enqueue(self, msg: QueuedMessage) -> None:
        """Add message to priority queue."""
        await self._queue.put(msg)

    async def _drain_loop(self) -> None:
        """Background task: pull from queue, send, respect rate limits."""
        while True:
            msg = await self._queue.get()
            if self._backoff > 0:
                await asyncio.sleep(self._backoff)
            try:
                await self._send(msg)
                self._backoff = 0.0  # Reset on success
            except discord.HTTPException as e:
                if e.status == 429:
                    self._backoff = min(
                        (self._backoff or 1.0) * 2,
                        60.0  # Cap at 60 seconds
                    )
                    # Re-enqueue the message
                    await self._queue.put(msg)
                    await asyncio.sleep(self._backoff)
            await asyncio.sleep(self._interval)
```

**Key design decisions:**
- `asyncio.PriorityQueue` uses `(priority, timestamp)` ordering -- lower priority number wins, ties broken by timestamp (FIFO within priority)
- `@dataclass(order=True)` with field comparison control makes items sortable
- Backoff doubles on 429 up to 60s cap, resets on success
- Health debouncing: health reports for the same channel coalesce within a window, only the latest is sent
- discord.py handles most rate limits internally; this catches the edge cases that slip through (bulk sends, webhook calls)

### Pattern 2: Bulk Failure Detection (RESL-02)

**What:** The supervisor tracks failure timestamps across children. When multiple children fail within a short correlation window (e.g., 30 seconds), it switches from per-agent restart to global backoff.

**When to use:** In `Supervisor._handle_child_failure()` before dispatching to restart strategy.

**Design:**
```python
from collections import deque
from datetime import datetime, timezone

class BulkFailureDetector:
    """Detect correlated failures indicating upstream outage.

    Tracks failure timestamps in a sliding window. When failures
    exceed a threshold within the correlation window, declares an
    upstream outage and enters global backoff.
    """

    def __init__(
        self,
        child_count: int,
        correlation_window: float = 30.0,  # seconds
        threshold_ratio: float = 0.5,  # 50% of children
        backoff_seconds: float = 120.0,  # initial backoff
        max_backoff: float = 600.0,  # 10 min cap
    ):
        self._child_count = child_count
        self._correlation_window = correlation_window
        self._threshold = max(2, int(child_count * threshold_ratio))
        self._backoff_seconds = backoff_seconds
        self._max_backoff = max_backoff
        self._failure_times: deque[datetime] = deque()
        self._in_backoff = False
        self._current_backoff = backoff_seconds

    def record_failure(self) -> bool:
        """Record a failure. Returns True if upstream outage detected."""
        now = datetime.now(timezone.utc)
        self._purge_old(now)
        self._failure_times.append(now)

        if len(self._failure_times) >= self._threshold:
            self._in_backoff = True
            return True
        return False

    @property
    def is_in_backoff(self) -> bool:
        return self._in_backoff
```

**Integration with Supervisor:**
- Add `_bulk_failure_detector` to `Supervisor.__init__()`
- In `_handle_child_failure()`, call `detector.record_failure()` before the restart policy check
- If bulk failure detected: skip per-agent restart, enter global backoff, notify owner
- After backoff expires: attempt one child restart as a probe; if it succeeds, resume normal operation

### Pattern 3: Degraded Mode Manager (RESL-03)

**What:** Monitors Claude API reachability. When unreachable, enters degraded mode: existing containers stay alive (no kills), new dispatches are blocked, owner is notified. When service returns, auto-recovers.

**When to use:** At `CompanyRoot` level as a singleton service.

**Design:**
```python
import asyncio
import anthropic

class DegradedModeManager:
    """Manages system state when Claude API is unreachable.

    Runs a periodic health check. Transitions:
    - NORMAL -> DEGRADED: Claude unreachable for N consecutive checks
    - DEGRADED -> NORMAL: Claude reachable for M consecutive checks
    """

    NORMAL = "normal"
    DEGRADED = "degraded"

    def __init__(
        self,
        check_interval: float = 60.0,  # seconds between checks
        failure_threshold: int = 3,  # consecutive failures to enter degraded
        recovery_threshold: int = 2,  # consecutive successes to exit degraded
        on_degraded: Callable | None = None,  # callback: owner notification
        on_recovered: Callable | None = None,
    ):
        self._state = self.NORMAL
        self._check_interval = check_interval
        self._failure_threshold = failure_threshold
        self._recovery_threshold = recovery_threshold
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._on_degraded = on_degraded
        self._on_recovered = on_recovered
        self._task: asyncio.Task | None = None

    @property
    def is_degraded(self) -> bool:
        return self._state == self.DEGRADED

    async def _check_claude(self) -> bool:
        """Lightweight probe of Claude API availability."""
        try:
            # Use anthropic SDK with minimal request
            # Or use httpx to HEAD the API endpoint
            client = anthropic.AsyncAnthropic()
            # A minimal models list call or similar lightweight endpoint
            # Alternatively, catch connection errors during normal operation
            return True
        except (anthropic.APIConnectionError, anthropic.APITimeoutError):
            return False
        except anthropic.APIStatusError as e:
            # 5xx = service issue, 4xx (except 429) = our problem
            return e.status_code < 500
```

**Integration with CompanyRoot:**
- CompanyRoot holds a `DegradedModeManager` instance
- Before any dispatch operation, check `manager.is_degraded`
- When degraded: keep containers alive (they just idle), block `add_project()` or new agent spawns
- Owner notification via existing `on_escalation` callback or health change callback

### Anti-Patterns to Avoid

- **Polling Discord API for rate limit status:** discord.py handles rate limiting internally via response headers. Do not pre-check rate limits -- instead, catch 429 HTTPException as a fallback.
- **Killing containers when Claude is down:** RESL-03 explicitly requires containers stay alive. Do not stop/restart agents just because the API is unreachable.
- **Per-agent backoff for correlated failures:** If 5 agents fail within 30 seconds, restarting each with individual backoff wastes resources. Detect the correlation first.
- **Hardcoding rate limits:** Discord rate limits vary by endpoint and change over time. Use response headers and backoff, not hardcoded limits.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Discord rate limit handling | Custom HTTP rate limiter | discord.py's built-in handler + catch 429 fallback | discord.py already tracks per-route rate limits via response headers; only add a queue for batching/prioritization |
| Claude API retry | Custom retry loop | anthropic SDK's built-in retry (2x with exponential backoff) | SDK retries 429, 5xx, connection errors automatically; extend only for outage detection |
| Priority queue | Custom sorted list | asyncio.PriorityQueue | Stdlib, thread-safe, async-native, handles blocking get() |
| Exponential backoff calculation | Manual doubling logic | Simple `min(base * 2**n, cap)` pattern | Trivial formula; no library needed but don't overcomplicate |

**Key insight:** discord.py and the anthropic SDK already handle transient errors. This phase adds system-level resilience (prioritization, correlation, degradation) on top of their per-request handling.

## Common Pitfalls

### Pitfall 1: discord.py Swallows 429s Silently
**What goes wrong:** discord.py retries 429s internally but occasionally raises HTTPException when the retry budget is exhausted or the rate limit is global.
**Why it happens:** Global rate limits (50 req/s) differ from per-route limits; discord.py handles per-route but can miss global.
**How to avoid:** Wrap all `channel.send()` calls through the MessageQueue, which catches HTTPException and applies its own backoff. Do not assume discord.py always succeeds.
**Warning signs:** Sporadic "429 Too Many Requests" in logs despite no obvious bulk sending.

### Pitfall 2: Health Report Flood During Restart Storm
**What goes wrong:** When a supervisor restarts multiple children (all_for_one or rest_for_one), each child emits state transitions (stopped -> creating -> running) generating a flood of health notifications.
**Why it happens:** The `_restarting` flag suppresses failure callbacks but health reports still fire on each transition.
**How to avoid:** Debounce health reports in the message queue. Coalesce multiple reports for the same agent within a 5-second window, sending only the latest.
**Warning signs:** Discord #alerts channel flooded with rapid-fire state change messages during supervisor restarts.

### Pitfall 3: Bulk Failure Detection False Positives
**What goes wrong:** Unrelated agent failures within the correlation window trigger upstream outage detection.
**Why it happens:** Correlation window too wide, or threshold too low for the number of children.
**How to avoid:** Set threshold to at least 50% of children (minimum 2). Use a tight correlation window (30s). Require failures to be from distinct children (not the same child failing twice).
**Warning signs:** System entering global backoff when only one agent has issues.

### Pitfall 4: Claude Health Check Creating API Costs
**What goes wrong:** Health check probe makes Claude API calls, incurring cost.
**Why it happens:** Using `messages.create()` as a health check.
**How to avoid:** Use a lightweight endpoint that does not consume tokens. The anthropic SDK's model listing (`client.models.list()`) is one option. Alternatively, catch errors from actual operational calls rather than probing -- passive health detection.
**Warning signs:** Unexpected API charges from health check calls.

### Pitfall 5: Deadlock Between Message Queue and Degraded Mode
**What goes wrong:** Degraded mode notification tries to go through the message queue, but the queue is blocked because it is trying to send to Discord which is also having issues.
**Why it happens:** Circular dependency between notification system and the thing being notified about.
**How to avoid:** Degraded mode owner notification should bypass the rate-limited queue or use a separate high-priority path that retries independently.
**Warning signs:** Owner never receives degraded mode notification.

## Code Examples

### Debounced Health Reports
```python
# In MessageQueue: coalesce health reports within debounce window
async def enqueue_health(self, channel_id: int, embed: discord.Embed) -> None:
    """Enqueue a health report with debouncing.

    Multiple health reports for the same channel within debounce_seconds
    are coalesced -- only the latest is sent.
    """
    self._health_buffer[channel_id] = QueuedMessage(
        priority=MessagePriority.HEALTH_DEBOUNCED,
        timestamp=datetime.now(timezone.utc).timestamp(),
        channel_id=channel_id,
        embed=embed,
    )
    # Reset debounce timer
    if self._health_timer is not None:
        self._health_timer.cancel()
    loop = asyncio.get_running_loop()
    self._health_timer = loop.call_later(
        self._debounce_seconds,
        lambda: asyncio.ensure_future(self._flush_health()),
    )

async def _flush_health(self) -> None:
    """Flush debounced health reports into the priority queue."""
    for msg in self._health_buffer.values():
        await self._queue.put(msg)
    self._health_buffer.clear()
```

### Supervisor Bulk Failure Integration
```python
# In Supervisor._handle_child_failure() -- added before existing restart logic
async def _handle_child_failure(self, failed_id: str) -> None:
    # NEW: Check for bulk failure (RESL-02)
    if self._bulk_detector is not None:
        is_outage = self._bulk_detector.record_failure()
        if is_outage:
            logger.warning(
                "Supervisor %s detected upstream outage (bulk failure)",
                self.supervisor_id,
            )
            # Enter global backoff instead of per-agent restart
            await self._enter_global_backoff()
            return

    # EXISTING: per-agent restart logic continues unchanged
    spec = self._get_spec(failed_id)
    # ... rest of existing code ...
```

### Degraded Mode Dispatch Gate
```python
# In CompanyRoot -- gate new dispatches
async def add_project(self, project_id: str, ...) -> ProjectSupervisor:
    if self._degraded_mode is not None and self._degraded_mode.is_degraded:
        raise RuntimeError(
            f"System in degraded mode (Claude unreachable). "
            f"Cannot add project {project_id}. Will auto-recover."
        )
    # ... existing add_project logic ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| discord.py retry-only | Custom message queue + discord.py | This phase | Prioritized, debounced, rate-aware message delivery |
| Per-agent restart always | Bulk failure detection + global backoff | This phase | Prevents restart storms during upstream outages |
| No Claude outage handling | Degraded mode with auto-recovery | This phase | Graceful degradation instead of cascading failures |
| v1 CrashTracker backoff | v2 Supervisor-level backoff | Phase 2 -> Phase 6 | RestartTracker already exists; extend with temporal correlation |

**Prior art in this codebase:**
- `AlertsCog._send_or_buffer()` -- buffer-on-disconnect pattern (lines 52-63 of alerts.py)
- `CrashTracker.BACKOFF_SCHEDULE` -- [30, 120, 600] second backoff (v1, informational only)
- `RestartTracker` -- sliding window with max restarts per window (v2, extend this)
- `HealthCog._notify_state_change()` -- fire-and-forget async notification pattern

## Open Questions

1. **Claude API health check endpoint**
   - What we know: anthropic SDK raises `APIConnectionError` for network issues, `RateLimitError` for 429s, `InternalServerError` for 5xx
   - What's unclear: Whether `client.models.list()` is a zero-cost health check or if it counts against rate limits
   - Recommendation: Use passive detection -- track errors from actual operational calls (Strategist conversation sends) rather than probing. Only add active probing if passive detection proves insufficient.

2. **Exact debounce window for health reports**
   - What we know: Health notifications fire on every state transition (errored, running, stopped)
   - What's unclear: How many transitions per second are realistic in a restart storm
   - Recommendation: Start with 5 seconds debounce; make configurable. This means during a restart storm, at most one health update per agent per 5 seconds reaches Discord.

3. **Global backoff duration for bulk failure**
   - What we know: v1 used [30, 120, 600] second backoff schedule; v2 supervisor windows are 10 minutes
   - What's unclear: Optimal initial backoff for Claude outages (could be minutes to hours)
   - Recommendation: Start at 120 seconds, double on each failed probe, cap at 600 seconds. This matches v1 patterns and aligns with the 10-minute supervisor windows.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24.x |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/ -x -q --ignore=tests/test_container_integration.py` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RESL-01a | Messages queued by priority (escalation before status) | unit | `uv run pytest tests/test_message_queue.py::test_priority_ordering -x` | Wave 0 |
| RESL-01b | Health reports debounced within window | unit | `uv run pytest tests/test_message_queue.py::test_health_debounce -x` | Wave 0 |
| RESL-01c | Exponential backoff on 429 | unit | `uv run pytest tests/test_message_queue.py::test_429_backoff -x` | Wave 0 |
| RESL-01d | Backoff resets on successful send | unit | `uv run pytest tests/test_message_queue.py::test_backoff_reset -x` | Wave 0 |
| RESL-02a | Bulk failure detected when threshold exceeded | unit | `uv run pytest tests/test_bulk_failure.py::test_bulk_detection -x` | Wave 0 |
| RESL-02b | Individual failures do not trigger bulk detection | unit | `uv run pytest tests/test_bulk_failure.py::test_no_false_positive -x` | Wave 0 |
| RESL-02c | Supervisor enters global backoff on bulk failure | unit | `uv run pytest tests/test_bulk_failure.py::test_supervisor_global_backoff -x` | Wave 0 |
| RESL-03a | Degraded mode entered after consecutive failures | unit | `uv run pytest tests/test_degraded_mode.py::test_enter_degraded -x` | Wave 0 |
| RESL-03b | Containers stay alive in degraded mode | unit | `uv run pytest tests/test_degraded_mode.py::test_containers_alive -x` | Wave 0 |
| RESL-03c | New dispatches blocked in degraded mode | unit | `uv run pytest tests/test_degraded_mode.py::test_dispatch_blocked -x` | Wave 0 |
| RESL-03d | Auto-recovery when service returns | unit | `uv run pytest tests/test_degraded_mode.py::test_auto_recovery -x` | Wave 0 |
| RESL-03e | Owner notified on degraded entry | unit | `uv run pytest tests/test_degraded_mode.py::test_owner_notification -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_message_queue.py tests/test_bulk_failure.py tests/test_degraded_mode.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_message_queue.py` -- covers RESL-01a/b/c/d
- [ ] `tests/test_bulk_failure.py` -- covers RESL-02a/b/c
- [ ] `tests/test_degraded_mode.py` -- covers RESL-03a/b/c/d/e

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `src/vcompany/supervisor/supervisor.py` -- Supervisor._handle_child_failure() entry point
- Codebase analysis: `src/vcompany/supervisor/restart_tracker.py` -- RestartTracker sliding window
- Codebase analysis: `src/vcompany/bot/cogs/health.py` -- HealthCog notification pattern
- Codebase analysis: `src/vcompany/bot/cogs/alerts.py` -- AlertsCog buffer-on-disconnect pattern
- Codebase analysis: `src/vcompany/orchestrator/crash_tracker.py` -- v1 backoff schedule prior art
- [Python asyncio Queue docs](https://docs.python.org/3/library/asyncio-queue.html) -- PriorityQueue API
- [Discord Rate Limits docs](https://discord.com/developers/docs/topics/rate-limits) -- 50 req/s global, per-route limits

### Secondary (MEDIUM confidence)
- [anthropic-sdk-python README](https://github.com/anthropics/anthropic-sdk-python/blob/main/README.md) -- Error hierarchy, auto-retry behavior (2x default)
- [Anthropic API errors](https://docs.anthropic.com/en/api/errors) -- Error codes and status codes
- [discord.py rate limit issue #9418](https://github.com/Rapptz/discord.py/issues/9418) -- Edge cases where discord.py raises instead of retrying

### Tertiary (LOW confidence)
- None -- all findings verified against codebase and official documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies; all patterns use existing libs
- Architecture: HIGH -- extends existing Supervisor/CompanyRoot with well-understood patterns (priority queue, circuit breaker, health probe)
- Pitfalls: HIGH -- derived from actual codebase patterns and Discord API documentation

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable infrastructure patterns)
