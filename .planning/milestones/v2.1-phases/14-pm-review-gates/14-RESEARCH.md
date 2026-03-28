# Phase 14: PM Review Gates - Research

**Researched:** 2026-03-28
**Domain:** Agent-PM conversational gate protocol over Discord
**Confidence:** HIGH

## Summary

Phase 14 adds the core behavioral intelligence of v2.1: agents must stop after each GSD stage transition, request PM review via their Discord channel, and only advance when the PM explicitly approves. The foundation is entirely in place from phases 11-13. The event pipeline is wired (Phase 13), the GSD lifecycle FSM has the right phase states (Phase 11), and `DiscordCommunicationPort` already routes messages. What is missing is the blocking primitive and the review protocol on both ends.

The architecture has a clear seam. When a GsdAgent calls `advance_phase()`, it fires `_on_phase_transition` which posts a `gsd_transition` event to the PM. But `advance_phase()` returns immediately — there is no await-for-approval pattern. Phase 14 must add an async gate: after stage completion, the agent posts a review request to its Discord channel and suspends in a pending state until the PM replies with approve/modify/clarify. The PM side (`FulltimeAgent._handle_event`) currently does only `logger.info` for `gsd_transition` events — Phase 14 replaces those stubs with real Discord reply logic.

The agent's "stopping at a gate" mechanism should NOT use the existing `block()`/`unblock()` FSM transitions because BLOCKED has separate semantics (agent cannot continue due to external obstacle). Instead, a gate is an expected, normal pause — the inner state can stay in the phase it just entered (e.g., `plan`) while a `_pending_review: asyncio.Future` attribute holds the gate open. Message throttling (GATE-05, max 1 msg/30s per agent) fits cleanly into the existing `MessageQueue` with a per-agent timestamp tracker.

**Primary recommendation:** Add `_pending_review: asyncio.Future | None` to GsdAgent; gate fires after each `advance_phase()` call; PM's `gsd_transition` handler posts a review request to the agent's Discord channel and stores the Future; agent waits on it; PM's `on_message` handler resolves it with approve/modify/clarify based on the reply content.

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
| GATE-01 | Agent stops after each GSD stage transition and posts to its Discord channel: `[agent-id] @PM, finished [stage], need your review` with key file attachments | GsdAgent.advance_phase() is the call site; `_on_phase_transition` callback fires there; need asyncio.Future gate after the callback fires |
| GATE-02 | PM reads attached files, reviews against project context/memory, and responds with approve/modify/clarify — not a rubber stamp | FulltimeAgent._handle_event `gsd_transition` branch is the entry point; Claude CLI (`claude -p`) already used by PMTier for plan review; same pattern applies |
| GATE-03 | Multi-turn conversation: PM and agent discuss until PM is satisfied — agent only advances when PM approves | asyncio.Future gate in GsdAgent resolved by bot's on_message; multi-turn = multiple round-trips before Future is resolved; Future stays open through clarify exchanges |
| GATE-04 | Agent reads PM response (approve/modify/clarify) and acts accordingly | Future result carries the decision string; GsdAgent.advance_phase() must inspect result and either proceed, re-run stage, or enter clarify loop |
| GATE-05 | Message throttling: max 1 message per 30 seconds per agent to keep Discord rate limits happy | New per-agent timestamp dict in PlanReviewCog or a dedicated GateThrottle helper; asyncio.sleep() used to defer if within window |
</phase_requirements>

## Standard Stack

### Core (no new packages needed — pure wiring)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.7.x | Message listening in agent channels, sending review requests, file attachments | Already in use; `on_message` listener in PlanReviewCog is the pattern to follow |
| asyncio (stdlib) | N/A | `asyncio.Future` for gate synchronization; `asyncio.sleep` for throttle | Agent lifecycle is already async; Future is the lightest correct primitive |
| python-statemachine | 3.0.x | GsdLifecycle FSM already owns inner phase states | Block/unblock are already FSM transitions; gate does not add new FSM states |
| anthropic / Claude CLI | 0.86.x / via subprocess | PM calls `claude -p` to review stage artifacts | PMTier._answer_directly() and PlanReviewer.review_plan() establish this pattern |

**Installation:** No new packages required. Phase 14 is pure wiring of existing infrastructure.

## Architecture Patterns

### Existing Code to Reuse or Extend

**GsdAgent** (`src/vcompany/agent/gsd_agent.py`)
- `advance_phase()` — insert gate await here after `_on_phase_transition` fires
- `_on_phase_transition` — already wired by VcoBot.on_ready() to post `gsd_transition` events to PM
- Add `_pending_review: asyncio.Future | None = None` attribute

**FulltimeAgent** (`src/vcompany/agent/fulltime_agent.py`)
- `_handle_event()` `gsd_transition` branch — currently `logger.info` only; replace with real PM review dispatch

**PlanReviewCog** (`src/vcompany/bot/cogs/plan_review.py`)
- `on_message` already handles `@PM` mentions in agent channels; extend to handle review responses
- `_send_tmux_command()` is the right mechanism to advance agents after approval
- `_review_agent_plans()` has file attachment reading and PM knowledge doc patterns

**DiscordCommunicationPort** (`src/vcompany/container/discord_communication.py`)
- `send_message()` sends to `agent-{target}` channels — the agent's own comm_port can post to PM's channel (or PM can post directly to the agent's channel)
- `deliver_message()` / `receive_message()` are the inbox pathway

**MessageQueue** (`src/vcompany/resilience/message_queue.py`)
- Priority queue with rate-limited drain loop already handles outbound throttling
- GATE-05 per-agent 30-second throttle is a separate concern (inbound-trigger throttle, not outbound volume throttle); simplest correct implementation is a `dict[str, float]` tracking `last_review_request_time` per agent

### Recommended Design

#### Gate Flow (GATE-01 through GATE-04)

```
GsdAgent.advance_phase(phase)
  1. FSM transition (method())
  2. _checkpoint_phase()
  3. Fire _on_phase_transition callback → posts gsd_transition event to PM queue
  4. [NEW] If review gate enabled: create asyncio.Future, store as _pending_review
  5. [NEW] Post "[agent-id] @PM, finished [stage], need your review" + file attachments to #agent-{id}
  6. [NEW] await _pending_review  ← suspends here
  7. [NEW] Inspect result: "approve" → return normally
                          "modify"  → raise GateModifyRequired (caller re-runs stage)
                          "clarify" → remain suspended, new Future created for next exchange
```

**PM side (FulltimeAgent._handle_event or PlanReviewCog.on_message):**

```
on_message in #agent-{id}:
  if "[PM]" response to review request:
    parse approve / modify / clarify
    look up pending Future for agent_id
    if "approve": Future.set_result("approve")
    if "modify":  Future.set_result("modify")  + post guidance
    if "clarify": Future.set_result("clarify") + post question  + reset new Future
```

#### Where the Gate Lives

The gate Future must be accessible to both GsdAgent (which creates and awaits it) and the Discord bot's on_message handler (which resolves it). The two natural locations are:

Option A: `GsdAgent._pending_review` + a registry in VcoBot mapping `agent_id → GsdAgent`. Bot's on_message resolves `bot.company_root.find_agent(agent_id)._pending_review`.

Option B: A new `ReviewGateRegistry` in VcoBot that maps `agent_id → Future`. GsdAgent registers when it creates the Future; bot resolves via registry.

**Recommendation: Option A.** VcoBot already has `company_root.project_sup.children` dict. Add a helper `_find_gsd_agent(agent_id: str) -> GsdAgent | None` to VcoBot. No new registry class needed.

#### Review Request Message Format (GATE-01)

```
[agent-id] @PM, finished [stage], need your review
```

Plus file attachments — the relevant files per stage:
- `discuss` → `CONTEXT.md`
- `plan` → latest `*-PLAN.md` file(s)
- `execute` → latest `*-SUMMARY.md` file
- `uat` → `*-SUMMARY.md` with test results
- `ship` → git log / release notes if available

File discovery follows `PlanReviewCog._review_agent_plans()` pattern: scan `project_dir/clones/{agent_id}/.planning/phases/`.

#### PM Review Logic (GATE-02)

PM already has `PMTier.evaluate_question()` and `PlanReviewer.review_plan()`. For stage reviews:
- Reuse `PlanReviewer` for plan-stage reviews (already works)
- For discuss/execute/uat/ship stages: use `PMTier` with a stage-appropriate framing prompt
- PM response must include one of: "APPROVED", "NEEDS CHANGES: [feedback]", "CLARIFY: [question]"
- Use the same `pm-context.md` knowledge-accumulation pattern from `PlanReviewCog._append_pm_context()`

#### Throttle (GATE-05)

```python
_last_review_request: dict[str, float] = {}   # agent_id → monotonic timestamp
REVIEW_THROTTLE_SECONDS = 30.0

async def _throttled_post_review_request(agent_id, content, attachments):
    now = time.monotonic()
    last = _last_review_request.get(agent_id, 0.0)
    wait = REVIEW_THROTTLE_SECONDS - (now - last)
    if wait > 0:
        await asyncio.sleep(wait)
    _last_review_request[agent_id] = time.monotonic()
    await channel.send(content, files=attachments)
```

This lives in PlanReviewCog or a thin helper module alongside it.

### Anti-Patterns to Avoid

- **Using `block()`/`unblock()` for review gates:** BLOCKED is for unexpected obstacles (ARCH-03 semantics). Using it for planned review pauses would corrupt health reporting — health tree would show the agent as "stuck" when it is actually in a normal workflow gate. Use `asyncio.Future` instead.
- **Polling the agent channel:** Do not loop-check for PM replies. The `on_message` event fires synchronously within the discord.py event loop — use it to resolve the Future directly.
- **Storing the Future in memory_store / YAML:** Futures are not serializable. The Future lives in-process only. On restart, a gate in progress is lost — the agent restores its checkpoint phase but the Future is gone. The correct recovery behavior: agent reposts the review request on startup if inner_state is a non-idle phase with no pending Future. This is a crash-recovery edge case; log a warning and repost.
- **Running `claude -p` inside `FulltimeAgent._handle_event`:** FulltimeAgent processes events synchronously in a loop. Use `asyncio.to_thread()` (as PlanReviewCog already does) for the subprocess call.
- **Skipping throttle for "modify" re-submissions:** GATE-05 applies to all messages from an agent, including re-submissions after modify. The throttle dict must be checked before every post.
- **Hardcoding "approve"/"modify"/"clarify" parsing as exact strings:** PM responses are LLM-generated. Use case-insensitive substring matching (`"approved" in response.lower()`) with a fallback to "clarify" if none match.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File attachments in Discord | Custom base64 encoding or file upload helpers | `discord.File(fp=path)` (already used in PlanReviewCog.handle_new_plan) | discord.py handles multipart upload, chunking, and CDN URLs |
| Rate limiting outbound messages | Custom sleep loop | MessageQueue (already exists) for outbound; simple timestamp dict for per-agent gate throttle | MessageQueue has exponential backoff, priority queue, and debounce already tested |
| PM LLM calls | New Claude SDK integration | `asyncio.to_thread(plan_reviewer.review_plan, ...)` / `asyncio.to_thread(pm.evaluate_question, ...)` (existing PMTier + PlanReviewer pattern) | Already handles subprocess, JSON parsing, fallback on error |
| Agent lookup by ID | New registry class | `project_sup.children[agent_id]` (existing dict) | Supervisor already tracks children by ID; no new data structure needed |

**Key insight:** Phase 14 adds behavior to gaps explicitly left in Phase 13. Every mechanism (channels, message routing, comm ports, PM review, throttle queue, tmux command dispatch) exists — the work is connecting them into a sequential gate protocol.

## Common Pitfalls

### Pitfall 1: Future Lifetime and Crash Recovery

**What goes wrong:** GsdAgent creates a `asyncio.Future` and awaits it. Process restarts. The Future is gone but the agent's FSM checkpoint still shows `inner_state == "plan"`. On restart, `_restore_from_checkpoint()` restores the FSM state but `_pending_review` is None. Agent tries to call `advance_phase("execute")` immediately without waiting for PM approval.

**Why it happens:** Futures are in-process memory. Checkpoints only persist FSM state.

**How to avoid:** In `GsdAgent.start()` (after `_restore_from_checkpoint()`), check: if `inner_state` is not None and not "idle", and `_pending_review is None`, set a flag `_needs_review_repost = True`. The next caller of `advance_phase()` should detect this and repost the review request.

**Warning signs:** Agent advances from plan→execute without a review request visible in the Discord channel.

### Pitfall 2: `on_message` Fires for Bot's Own Messages

**What goes wrong:** The bot posts the review request (`[agent-id] @PM, finished plan...`) in `#agent-{id}`. The `on_message` listener fires for that message. If the listener checks for PM responses without filtering out bot-authored messages, it sees its own outbound message and incorrectly resolves the Future.

**Why it happens:** discord.py dispatches `on_message` for all messages including those the bot sends.

**How to avoid:** Add `if message.author.id == self.bot.user.id: return` at the top of the response-handling `on_message` branch. The existing `PlanReviewCog.on_message` already does `if message.author.id == self.bot.user.id: return` — follow that same guard.

### Pitfall 3: Multiple Cog Listeners All Firing

**What goes wrong:** Both `PlanReviewCog.on_message` and any new `GateReviewCog.on_message` fire for every message in `#agent-{id}`. If both check for `@PM` in content, they double-process the PM response and attempt to set the Future twice, raising `asyncio.InvalidStateError: Future already done`.

**Why it happens:** discord.py broadcasts `on_message` to all Cogs without any short-circuit mechanism.

**How to avoid:** Do not add a new Cog for Phase 14 gate responses. Extend `PlanReviewCog.on_message` with the gate response detection. Single listener owns the `#agent-{id}` @PM message handling. Guard Future with `if not future.done()` before `set_result()`.

### Pitfall 4: `advance_phase()` Called from Sync Context

**What goes wrong:** GsdAgent.advance_phase() is now async and awaits a Future. If anything calls it in a sync callback context (e.g., from a supervisor restart path), the await will fail.

**Why it happens:** The FSM and supervisor restart paths are sync in places (GsdLifecycle.send_event is sync).

**How to avoid:** `advance_phase()` is already `async` — all current call sites are async (tmux command dispatch goes through `_send_tmux_command` which runs in the discord.py event loop). Verify no sync callers exist before adding the gate await.

### Pitfall 5: The "modify" Loop Has No Termination

**What goes wrong:** PM keeps responding with "NEEDS CHANGES" and the agent keeps re-submitting. Without a maximum iteration count, this can spin indefinitely (eating Claude API tokens and clogging the channel).

**Why it happens:** LLMs can be inconsistent. PM might ask for a change the agent cannot make, then reject the revision again.

**How to avoid:** Track `_review_attempts: int` per gate invocation. After 3 modify iterations, escalate to owner via `StrategistCog.post_owner_escalation()`. Document the count in the review request message ("attempt 2/3").

### Pitfall 6: File Attachment Size Limits

**What goes wrong:** Discord free-tier allows file attachments up to 25MB. PLAN.md and SUMMARY.md files are typically < 100KB. However, if `CONTEXT.md` or research files are included, they could exceed this.

**Why it happens:** Not checking file size before attachment.

**How to avoid:** Check `path.stat().st_size` before attaching. If > 1MB, truncate content and send as message text instead. This is the same safe pattern PlanReviewCog uses for embed field truncation (`:2000` slicing on content).

## Code Examples

Verified patterns from existing codebase:

### Gate Future Pattern (new — follows asyncio standard)

```python
# In GsdAgent (src/vcompany/agent/gsd_agent.py)
# Source: stdlib asyncio.Future pattern

self._pending_review: asyncio.Future[str] | None = None

async def advance_phase(self, phase: str) -> str:
    """Returns gate decision: 'approve', 'modify', 'clarify'."""
    transitions = { ... }
    method = transitions.get(phase)
    if method is None:
        raise ValueError(f"Unknown phase: {phase}")
    from_phase = self.inner_state or "idle"
    method()
    await self._checkpoint_phase()
    if self._on_phase_transition is not None:
        await self._on_phase_transition(self.context.agent_id, from_phase, phase)
    # Gate: create Future and suspend
    loop = asyncio.get_running_loop()
    self._pending_review = loop.create_future()
    try:
        decision = await self._pending_review
    finally:
        self._pending_review = None
    return decision
```

### Resolve Gate from PlanReviewCog.on_message

```python
# In PlanReviewCog.on_message (src/vcompany/bot/cogs/plan_review.py)
# Source: existing pending_escalations pattern in StrategistCog

# After parsing PM response as "approve", "modify", or "clarify":
agent = self._find_gsd_agent(agent_id)  # new helper on VcoBot
if agent is not None and agent._pending_review is not None:
    if not agent._pending_review.done():
        agent._pending_review.set_result(decision)
```

### Find GsdAgent on VcoBot

```python
# In VcoBot (src/vcompany/bot/client.py)
# Source: existing company_root.project_sup.children pattern

def _find_gsd_agent(self, agent_id: str) -> "GsdAgent | None":
    if self.company_root is None:
        return None
    for sup in self.company_root._supervisors.values():
        child = sup.children.get(agent_id)
        if isinstance(child, GsdAgent):
            return child
    return None
```

### Per-Agent Throttle (GATE-05)

```python
# In PlanReviewCog (src/vcompany/bot/cogs/plan_review.py)
# Source: asyncio.sleep + time.monotonic pattern

import time

_REVIEW_THROTTLE_SECS = 30.0

# In __init__:
self._last_review_time: dict[str, float] = {}

async def _post_throttled(self, agent_id: str, channel, content: str, files=None) -> None:
    """Post review message respecting 1-per-30s throttle per agent."""
    now = time.monotonic()
    last = self._last_review_time.get(agent_id, 0.0)
    wait = _REVIEW_THROTTLE_SECS - (now - last)
    if wait > 0:
        await asyncio.sleep(wait)
    self._last_review_time[agent_id] = time.monotonic()
    kwargs = {"content": content}
    if files:
        kwargs["files"] = files
    await channel.send(**kwargs)
```

### File Attachment for Review Request (GATE-01)

```python
# Source: PlanReviewCog.handle_new_plan() pattern (already in codebase)

async def _build_review_attachments(
    self, agent_id: str, stage: str
) -> list[discord.File]:
    """Collect relevant files for a stage review request."""
    clone_dir = self.bot.project_dir / "clones" / agent_id
    files = []
    stage_files = {
        "discuss": [clone_dir / ".planning" / "phases" / "*" / "*-CONTEXT.md"],
        "plan":    [clone_dir / ".planning" / "phases" / "*" / "*-PLAN.md"],
        "execute": [clone_dir / ".planning" / "phases" / "*" / "*-SUMMARY.md"],
    }
    patterns = stage_files.get(stage, [])
    for pattern in patterns:
        matches = sorted(Path(clone_dir).glob(str(pattern.relative_to(clone_dir))))
        if matches:
            latest = matches[-1]
            if latest.stat().st_size < 1_000_000:  # 1MB guard
                files.append(discord.File(fp=str(latest), filename=latest.name))
    return files
```

### PM Review Logic Skeleton (GATE-02)

```python
# In FulltimeAgent._handle_event or dispatched from it
# Source: PMTier.evaluate_question() + PlanReviewer.review_plan() patterns

async def _review_stage(self, agent_id: str, stage: str, context: str) -> str:
    """Returns 'APPROVED', 'NEEDS CHANGES: ...', or 'CLARIFY: ...'"""
    if stage == "plan" and self._plan_reviewer:
        result = await asyncio.to_thread(
            self._plan_reviewer.review_plan, agent_id, context
        )
        if result.confidence.level == "HIGH":
            return "APPROVED"
        return f"NEEDS CHANGES: {result.note}"
    # Other stages: use PMTier
    if self._pm:
        decision = await self._pm.evaluate_question(
            f"Review {stage} stage for agent {agent_id}: {context}", agent_id
        )
        return decision.answer or "CLARIFY: Unable to evaluate, please clarify"
    return "APPROVED"  # Fallback when no PM configured
```

## Environment Availability

Step 2.6: SKIPPED (no external dependencies identified — Phase 14 is pure Python code wiring with no new tools, services, or CLIs beyond what is already installed and verified in phases 11-13).

## Open Questions

1. **Who owns the gate Future — GsdAgent or VcoBot?**
   - What we know: GsdAgent creates and awaits the Future; on_message (in bot cog) must resolve it. VcoBot has access to company_root.
   - What's unclear: The exact lookup path through CompanyRoot → ProjectSupervisor → children. Need to verify `_supervisors` dict API on CompanyRoot.
   - Recommendation: Read `src/vcompany/supervisor/company_root.py` during planning to confirm the traversal. The pattern is straightforward — children is a dict on each supervisor.

2. **Should FulltimeAgent._handle_event own review dispatch or PlanReviewCog?**
   - What we know: FulltimeAgent._handle_event receives gsd_transition events. PlanReviewCog.on_message already has PM review logic and Discord send patterns.
   - What's unclear: Threading the review request post through FulltimeAgent._handle_event means FulltimeAgent needs a reference to the Discord bot/channel — that's currently not wired.
   - Recommendation: Keep Discord interactions in PlanReviewCog (it already has bot reference, channel resolution, file attachment, and tmux command dispatch). FulltimeAgent._handle_event can route gsd_transition events to PlanReviewCog via a callback injected by VcoBot.on_ready (same pattern as pm_event_sink).

3. **How does an agent "re-run" a stage after "modify"?**
   - What we know: The agent is in tmux. After advance_phase() returns "modify", the correct action is to send a tmux command instructing the agent to re-do the current stage.
   - What's unclear: Does the agent need a new GSD command (e.g., `/gsd:plan-phase N` re-run) or just a feedback message in the channel?
   - Recommendation: Send feedback as a tmux command text (same as PlanReviewCog._handle_rejection does) + send a channel message with the modification guidance. The GSD workflow is already set up to receive correction instructions via the terminal.

## Sources

### Primary (HIGH confidence)
- `src/vcompany/agent/gsd_agent.py` - advance_phase(), _on_phase_transition hook, FSM state structure
- `src/vcompany/agent/fulltime_agent.py` - _handle_event stubs for gsd_transition, briefing, escalation
- `src/vcompany/bot/cogs/plan_review.py` - existing PM review flow, file attachment, tmux command dispatch, per-agent throttle pattern
- `src/vcompany/bot/cogs/strategist.py` - asyncio.Future pattern for pending_escalations resolution
- `src/vcompany/container/discord_communication.py` - send_message(), deliver_message(), inbox queue
- `src/vcompany/bot/routing.py` - route_message(), @PM detection logic
- `src/vcompany/resilience/message_queue.py` - MessageQueue rate limiting (existing outbound throttle)
- `.planning/phases/13-pm-event-routing/13-01-SUMMARY.md` - exact wiring completed, confirmed FulltimeAgent handlers are log-only stubs awaiting Phase 14

### Secondary (MEDIUM confidence)
- `src/vcompany/bot/client.py` - VcoBot.on_ready() wiring pattern confirms factory-closure and set_pm_event_sink() patterns
- REQUIREMENTS.md GATE-01 through GATE-05 — authoritative requirement text

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all libraries already in use
- Architecture: HIGH — seams are clearly visible in code; patterns from Phase 13 directly applicable
- Pitfalls: HIGH — derived from actual code patterns (bot.user.id filter, Future lifetime, Cog multi-listener behavior)

**Research date:** 2026-03-28
**Valid until:** Stable — purely internal implementation against frozen codebase. Remains valid until Phase 14 implementation begins.
