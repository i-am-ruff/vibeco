# Phase 10: MessageQueue Notification Routing - Research

**Researched:** 2026-03-28
**Domain:** Discord notification routing through priority message queue
**Confidence:** HIGH

## Summary

Phase 10 closes the last v2 requirement gap (RESL-01). The MessageQueue infrastructure is fully built and running (Phase 6), but all 6 notification call sites bypass it with direct `channel.send()` calls. The fix is a straightforward rewiring: replace direct Discord sends in notification callbacks with `message_queue.enqueue(QueuedMessage(...))` calls, and update tests to verify queue routing instead of direct sends.

There are exactly 4 notification paths that need rewiring: (1) `HealthCog._notify_state_change()` in `health.py`, (2) `on_escalation` callback in `client.py`, (3) `on_degraded` callback in `client.py`, and (4) `on_recovered` callback in `client.py`. Additionally, the `/new-project` command in `commands.py` defines its own `on_escalation` callback that also bypasses the queue. The `_send_boot_notifications` in client.py are one-time startup messages and can be considered out of scope (they fire before the supervision tree is active).

**Primary recommendation:** Rewire the 4 notification callbacks to use `self.message_queue.enqueue()` with appropriate `MessagePriority` levels, then update tests to assert enqueue calls rather than channel.send calls.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion (infrastructure/gap-closure phase).

### Claude's Discretion
All implementation choices are at Claude's discretion. Key constraints from milestone audit:
- HealthCog._notify_state_change() must use message_queue.enqueue(QueuedMessage(...)) instead of channel.send()
- on_escalation, on_degraded, on_recovered callbacks in client.py must route through message_queue.enqueue()
- No direct channel.send() calls should remain in notification paths
- Escalations must have higher priority than health state change notifications
- Old direct-send code paths must be fully removed

### Deferred Ideas (OUT OF SCOPE)
None -- gap closure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RESL-01 | Communication layer queues outbound Discord messages with rate-aware batching -- health reports debounced, supervisor commands prioritized over status updates, exponential backoff on 429s | MessageQueue already implements all of this (priority queue, debounce, backoff). The gap is that notification call sites bypass it. This phase wires them through. |
</phase_requirements>

## Architecture Patterns

### Current State: Direct Send Paths (to be removed)

There are 4 notification callback sites that bypass MessageQueue:

**1. `HealthCog._notify_state_change()` in `src/vcompany/bot/cogs/health.py:94`**
```python
# CURRENT (direct send -- must change)
await alerts_channel.send(msg)
```

**2. `on_escalation` callback in `src/vcompany/bot/client.py:191-194`**
```python
# CURRENT (direct send -- must change)
async def on_escalation(msg: str) -> None:
    alerts_ch = self._system_channels.get("alerts")
    if alerts_ch:
        await alerts_ch.send(f"ESCALATION: {msg}")
```

**3. `on_degraded` callback in `src/vcompany/bot/client.py:216-222`**
```python
# CURRENT (direct send -- must change)
async def on_degraded() -> None:
    alerts_ch = self._system_channels.get("alerts")
    if alerts_ch:
        await alerts_ch.send("WARNING: System entered degraded mode...")
```

**4. `on_recovered` callback in `src/vcompany/bot/client.py:224-230`**
```python
# CURRENT (direct send -- must change)
async def on_recovered() -> None:
    alerts_ch = self._system_channels.get("alerts")
    if alerts_ch:
        await alerts_ch.send("RECOVERED: System recovered...")
```

**5. `/new-project` `on_escalation` in `src/vcompany/bot/cogs/commands.py:174-177`**
```python
# CURRENT (direct send -- must change)
async def on_escalation(msg: str) -> None:
    alerts_ch = self.bot._system_channels.get("alerts")
    if alerts_ch:
        await alerts_ch.send(f"ESCALATION: {msg}")
```

### Target State: Queue-Routed Paths

**Pattern 1: Rewiring HealthCog._notify_state_change()**

The HealthCog needs access to the bot's `message_queue`. Since `HealthCog.__init__` receives `bot` (a VcoBot instance), it can access `self.bot.message_queue`. The challenge: the alerts channel ID must be resolved at send time (not at init time, since channels may not be ready).

```python
# TARGET pattern for health.py
async def _notify_state_change(self, report: HealthReport) -> None:
    try:
        if report.state not in ("errored", "running", "stopped"):
            return
        if self.bot.message_queue is None:
            return  # queue not started yet

        if not self.bot.guilds:
            return
        guild = self.bot.guilds[0]
        alerts_channel = discord.utils.get(guild.text_channels, name="alerts")
        if alerts_channel is None:
            return

        emoji = STATE_INDICATORS.get(report.state, "")
        inner = f" ({report.inner_state})" if report.inner_state else ""
        msg_text = f"{emoji} **{report.agent_id}** -> {report.state}{inner}"

        await self.bot.message_queue.enqueue(QueuedMessage(
            priority=MessagePriority.STATUS,
            timestamp=time.monotonic(),
            channel_id=alerts_channel.id,
            content=msg_text,
        ))
    except Exception:
        logger.exception("Failed to enqueue state-change notification for %s", report.agent_id)
```

**Pattern 2: Rewiring on_escalation callback**

Escalation callback already has access to `self` (VcoBot) via closure. Route through queue with `MessagePriority.ESCALATION`.

```python
# TARGET pattern for client.py on_escalation
async def on_escalation(msg: str) -> None:
    alerts_ch = self._system_channels.get("alerts")
    if alerts_ch and self.message_queue:
        await self.message_queue.enqueue(QueuedMessage(
            priority=MessagePriority.ESCALATION,
            timestamp=time.monotonic(),
            channel_id=alerts_ch.id,
            content=f"ESCALATION: {msg}",
        ))
```

**Pattern 3: Rewiring on_degraded/on_recovered callbacks**

Same pattern as escalation. Use `MessagePriority.SUPERVISOR` (higher than STATUS, lower than ESCALATION).

```python
# TARGET pattern for client.py on_degraded
async def on_degraded() -> None:
    alerts_ch = self._system_channels.get("alerts")
    if alerts_ch and self.message_queue:
        await self.message_queue.enqueue(QueuedMessage(
            priority=MessagePriority.SUPERVISOR,
            timestamp=time.monotonic(),
            channel_id=alerts_ch.id,
            content="WARNING: System entered degraded mode...",
        ))
```

**Pattern 4: /new-project on_escalation in commands.py**

The `/new-project` command creates its own CompanyRoot when none exists. Its `on_escalation` callback must also route through the queue. Access via `self.bot.message_queue`.

### Priority Mapping

| Notification Type | MessagePriority | Rationale |
|-------------------|-----------------|-----------|
| Escalation (restart budget exceeded) | ESCALATION (0) | Highest -- owner needs immediate attention |
| Degraded mode enter/exit | SUPERVISOR (1) | System-level alerts, critical but not agent-specific |
| Health state change (errored/running/stopped) | STATUS (2) | Routine state transitions, important but frequent |

### Ordering Constraint

MessagePriority.ESCALATION (0) < MessagePriority.SUPERVISOR (1) < MessagePriority.STATUS (2) < MessagePriority.HEALTH_DEBOUNCED (3). Lower value = higher priority in `asyncio.PriorityQueue`. This ordering is already defined in the existing `MessagePriority` enum. No changes needed to the enum.

### Timing Constraint: MessageQueue Availability

The `on_escalation`, `on_degraded`, `on_recovered` callbacks are defined BEFORE `self.message_queue` is created in `on_ready()`. This is fine because:
1. The callbacks are closures that capture `self` (the VcoBot instance)
2. They access `self.message_queue` at call time, not definition time
3. A `None` guard (`if self.message_queue`) handles the case where the queue isn't started yet

The HealthCog similarly accesses `self.bot.message_queue` at call time.

### Boot Notifications: OUT OF SCOPE

`_send_boot_notifications()` in `client.py:386-420` fires at the end of `on_ready`, immediately after `MessageQueue.start()`. These are one-time startup messages (not health/escalation/degraded notifications). They are NOT part of the notification paths specified in the success criteria and should be left as direct sends. The audit identifies them for completeness but they are not in scope.

Similarly, `AlertsCog._send_or_buffer()` in `alerts.py` handles v1-era alerts (agent_dead, agent_stuck, circuit_open, hook_timeout, plan_detected). These are buffered alerts from the old monitor system, not v2 supervision callbacks. They are NOT in the notification paths specified by RESL-01 success criteria.

### Files to Modify

| File | Change | Lines |
|------|--------|-------|
| `src/vcompany/bot/cogs/health.py` | Replace `alerts_channel.send(msg)` with `message_queue.enqueue(QueuedMessage(...))` | ~94 |
| `src/vcompany/bot/client.py` | Rewire `on_escalation`, `on_degraded`, `on_recovered` closures | ~191-230 |
| `src/vcompany/bot/cogs/commands.py` | Rewire `/new-project` `on_escalation` closure | ~174-177 |
| `tests/test_health_cog.py` | Update `TestNotifyStateChange` to verify enqueue instead of channel.send | ~249-385 |
| `tests/test_bot_client.py` | Update callback tests to verify queue routing | ~265-329 |

### New Imports Needed

**health.py** needs:
```python
import time
from vcompany.resilience.message_queue import MessagePriority, QueuedMessage
```

**commands.py** needs:
```python
import time
from vcompany.resilience.message_queue import MessagePriority, QueuedMessage
```

**client.py** already imports `MessageQueue, MessagePriority, QueuedMessage, RateLimited`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Priority ordering | Custom priority logic | Existing `MessagePriority` enum + `asyncio.PriorityQueue` | Already built and tested in Phase 6 |
| Rate limiting | Per-callback rate limiting | Existing `MessageQueue` drain loop with backoff | Centralizes all rate-limit handling |
| Health debounce | Per-caller debounce timer | Existing `MessageQueue.enqueue_health()` | Already handles channel-keyed deduplication |

## Common Pitfalls

### Pitfall 1: MessageQueue is None at callback time
**What goes wrong:** `on_escalation` fires before `MessageQueue` is created/started.
**Why it happens:** CompanyRoot is created before MessageQueue in `on_ready()`. An early escalation (during agent startup) would hit a None queue.
**How to avoid:** Always guard with `if self.message_queue is not None`. Fall back to direct send or log warning if queue unavailable.
**Warning signs:** `AttributeError: NoneType has no attribute 'enqueue'` during startup.

### Pitfall 2: Channel ID resolution at definition time
**What goes wrong:** Storing `alerts_ch.id` in the closure at definition time, but the channel might not exist yet.
**Why it happens:** System channels are set up in `on_ready` before callbacks are used, but the `/new-project` path may have different timing.
**How to avoid:** Resolve channel at call time (inside the callback body), not at definition time.
**Warning signs:** `channel_id=0` in QueuedMessage, messages dropped by `_send_message`.

### Pitfall 3: Forgetting the /new-project path
**What goes wrong:** Only rewiring `client.py` callbacks but leaving `commands.py:174-177` as direct sends.
**Why it happens:** The `/new-project` command duplicates the `on_escalation` callback for the case where CompanyRoot doesn't exist yet.
**How to avoid:** Search for ALL `on_escalation` definitions, not just the one in `client.py`.
**Warning signs:** Grep for `channel.send.*ESCALATION` still finds hits after rewiring.

### Pitfall 4: Tests still mocking channel.send
**What goes wrong:** Tests pass but don't verify queue routing.
**Why it happens:** Old tests mock `alerts_channel.send` directly. After rewiring, the mock is never called.
**How to avoid:** Tests must mock `bot.message_queue.enqueue` (or provide a real queue with mock send_func) and verify QueuedMessage contents.
**Warning signs:** Tests that pass trivially (no assertions firing).

### Pitfall 5: MessageQueue not created in /new-project path
**What goes wrong:** `/new-project` creates CompanyRoot but not MessageQueue when `self.bot.message_queue` is None.
**Why it happens:** The `/new-project` code path (commands.py:173-195) creates CompanyRoot but does NOT create a MessageQueue.
**How to avoid:** Either (a) create MessageQueue in `/new-project` if it doesn't exist, or (b) guard with None check and fall back gracefully. Option (b) is simpler since `/new-project` is typically called after `on_ready` has already started the queue.
**Warning signs:** Queue-routed escalation silently dropped because `self.bot.message_queue is None`.

## Code Examples

### QueuedMessage construction (from existing codebase)
```python
# Source: src/vcompany/resilience/message_queue.py
QueuedMessage(
    priority=MessagePriority.ESCALATION,  # int 0
    timestamp=time.monotonic(),
    channel_id=alerts_channel.id,  # int
    content="ESCALATION: restart budget exceeded for project-alpha",
)
```

### MessageQueue.enqueue() (from existing codebase)
```python
# Source: src/vcompany/resilience/message_queue.py:114
async def enqueue(self, msg: QueuedMessage) -> None:
    """Add a message to the priority queue."""
    await self._queue.put(msg)
```

### Test pattern: verify enqueue was called
```python
# Pattern for updated tests
from unittest.mock import AsyncMock, MagicMock
import time
from vcompany.resilience.message_queue import MessagePriority, QueuedMessage

mock_queue = AsyncMock()
bot.message_queue = mock_queue

# ... trigger notification ...

mock_queue.enqueue.assert_called_once()
queued_msg = mock_queue.enqueue.call_args[0][0]
assert queued_msg.priority == MessagePriority.ESCALATION
assert "ESCALATION" in queued_msg.content
assert queued_msg.channel_id == expected_channel_id
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio |
| Config file | pyproject.toml |
| Quick run command | `python3 -m pytest tests/test_message_queue.py tests/test_health_cog.py -x` |
| Full suite command | `python3 -m pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RESL-01a | HealthCog._notify_state_change routes through queue | unit | `python3 -m pytest tests/test_health_cog.py::TestNotifyStateChange -x` | Exists (needs update) |
| RESL-01b | on_escalation routes through queue with ESCALATION priority | unit | `python3 -m pytest tests/test_bot_client.py -x -k escalation` | Exists (needs update) |
| RESL-01c | on_degraded/on_recovered route through queue | unit | `python3 -m pytest tests/test_bot_client.py -x -k degraded` | Exists (needs update) |
| RESL-01d | No direct channel.send in notification paths | integration | grep audit (no test file needed) | N/A |
| RESL-01e | Escalations have higher priority than health notifications | unit | `python3 -m pytest tests/test_message_queue.py::test_priority_ordering -x` | Exists (already passes) |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_message_queue.py tests/test_health_cog.py tests/test_bot_client.py -x`
- **Per wave merge:** `python3 -m pytest tests/ -x`
- **Phase gate:** Full suite green + grep audit for residual `channel.send()` in notification paths

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. Tests need updates (not creation).

## Open Questions

1. **Should health state changes use `enqueue_health()` (debounced) or `enqueue()` (immediate)?**
   - What we know: `enqueue_health()` debounces by channel_id with a 5s window. `enqueue()` is immediate with priority ordering.
   - What's unclear: Health state changes (errored/running/stopped) are relatively rare and significant. Debouncing might suppress important state transitions.
   - Recommendation: Use `enqueue()` with `MessagePriority.STATUS` for state change notifications. Reserve `enqueue_health()` for periodic health report updates (if added later). State transitions are discrete events, not periodic reports.

2. **Should /new-project create MessageQueue if one doesn't exist?**
   - What we know: `/new-project` creates CompanyRoot but not MessageQueue. Normal flow: `on_ready` creates both.
   - What's unclear: Whether `/new-project` can be called before `on_ready` completes.
   - Recommendation: Guard with `None` check only. `/new-project` is a slash command, which requires `on_ready` to have completed (commands are synced in `setup_hook`). The queue will exist by the time `/new-project` runs.

## Sources

### Primary (HIGH confidence)
- `src/vcompany/resilience/message_queue.py` -- full MessageQueue implementation, QueuedMessage dataclass, MessagePriority enum
- `src/vcompany/bot/client.py` -- on_ready wiring, callback definitions, MessageQueue creation
- `src/vcompany/bot/cogs/health.py` -- _notify_state_change implementation
- `src/vcompany/bot/cogs/commands.py` -- /new-project on_escalation callback
- `src/vcompany/bot/cogs/alerts.py` -- AlertsCog (out of scope, v1 alert system)
- `tests/test_health_cog.py` -- existing notification tests (need updating)
- `tests/test_bot_client.py` -- existing wiring tests (need updating)
- `tests/test_message_queue.py` -- existing queue tests (already sufficient)

### Secondary (MEDIUM confidence)
- `.planning/v2.0-MILESTONE-AUDIT.md` -- gap identification and severity assessment

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, pure internal rewiring
- Architecture: HIGH -- all target code read directly, patterns verified
- Pitfalls: HIGH -- all identified from actual code analysis, not speculation

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable -- internal refactoring, no external dependencies)
