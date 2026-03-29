# Phase 20: CompanyRoot Extraction - Research

**Researched:** 2026-03-29
**Domain:** Architecture extraction -- moving supervision tree and business logic from Discord bot into daemon process
**Confidence:** HIGH

## Summary

Phase 20 is the most complex phase in v3.0. It moves CompanyRoot, the supervision tree, StrategistConversation, PM review flow, and channel creation from VcoBot.on_ready() into the daemon process. The daemon (Phase 18) already owns the event loop and bot lifecycle. CommunicationPort (Phase 19) provides the platform-agnostic messaging bridge. This phase connects those two foundations.

The core challenge is the **22 callback closures** in `on_ready()` (lines 113-627 of client.py). Each closure captures Discord-specific references (`self.get_channel()`, `self.get_cog()`, `guild`, `self.message_queue`) that must be replaced with RuntimeAPI method calls or CommunicationPort sends. The wiring has ordering constraints -- PM event sink must be set LAST after all agent callbacks are wired, to prevent events arriving before handlers are ready.

**Primary recommendation:** Create a RuntimeAPI class in `src/vcompany/daemon/runtime_api.py` that wraps CompanyRoot operations with typed methods. The daemon owns RuntimeAPI. Bot accesses CompanyRoot exclusively through RuntimeAPI. All Discord-touching callbacks route through CommunicationPort.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked -- all implementation choices at Claude's discretion per CONTEXT.md.

### Claude's Discretion
All implementation choices are at Claude's discretion -- architecture extraction phase. Key decisions and concerns from STATE.md:
- on_ready() has 15+ callback closures needing audit before extraction -- plan first task as audit
- Wiring order constraints in on_ready() (PM event sink must be last) -- respect during RuntimeAPI design
- Daemon runs bot in-process via bot.start() -- CompanyRoot initializes in daemon, not in on_ready
- CommunicationPort (Phase 19) is the bridge -- daemon sends through it, Discord adapter in bot receives

### Deferred Ideas (OUT OF SCOPE)
None -- extraction phase with clear scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXTRACT-01 | CompanyRoot and supervision tree run inside daemon process, not bot | RuntimeAPI owns CompanyRoot; daemon initializes it during startup (after bot.on_ready registers CommunicationPort) |
| EXTRACT-02 | RuntimeAPI gateway class provides typed methods for all CompanyRoot operations | RuntimeAPI class with hire(), give_task(), dismiss(), status(), health_tree(), new_project(), plus internal wiring methods |
| EXTRACT-03 | All callback closures from on_ready() replaced with RuntimeAPI calls or event subscriptions | 22 closures audited; each maps to either a RuntimeAPI method or CommunicationPort.send_message() call |
| EXTRACT-04 | Bot accesses CompanyRoot exclusively through RuntimeAPI (no direct imports) | Bot imports RuntimeAPI only; CompanyRoot, Supervisor, container modules not imported by bot |
| COMM-04 | StrategistConversation runs in daemon, sends/receives through CommunicationPort | StrategistConversation stays in CompanyAgent, which runs in daemon; responses sent via CommunicationPort.send_message() instead of channel.send() |
| COMM-05 | PM review flow state machine runs in daemon, review requests/responses through CommunicationPort | PM review dispatch, approval, rejection all in daemon; CommunicationPort sends review embeds and receives responses via event subscription |
| COMM-06 | Channel creation requested by daemon through CommunicationPort | New CommunicationPort methods (create_category, create_channel) or extend send_message with structured payloads |
</phase_requirements>

## Architecture Patterns

### Current Architecture (Pre-Phase 20)
```
VcoBot.on_ready()
  |-- Creates CompanyRoot with 10+ callback closures
  |-- Creates StrategistConversation via CompanyAgent
  |-- Wires 12+ PM/agent event callbacks
  |-- Starts MessageQueue
  |-- All callbacks capture Discord objects directly

Daemon
  |-- Owns PID, signals, socket server, bot lifecycle
  |-- Has CommunicationPort reference (set by bot on_ready)
  |-- Does NOT own CompanyRoot
```

### Target Architecture (Post-Phase 20)
```
Daemon
  |-- Owns PID, signals, socket server, bot lifecycle
  |-- Owns RuntimeAPI (wraps CompanyRoot)
  |-- Owns CompanyRoot + supervision tree
  |-- All business logic callbacks stay within daemon
  |-- Uses CommunicationPort for all outbound messaging

VcoBot.on_ready()
  |-- Creates DiscordCommunicationPort, registers with daemon
  |-- Creates vco-owner role (Discord-only concern)
  |-- Sets up system channels (Discord-only concern)
  |-- DOES NOT create CompanyRoot
  |-- DOES NOT wire callbacks

Cogs
  |-- Thin adapters: Discord events -> RuntimeAPI calls
  |-- No container module imports
```

### Recommended Project Structure
```
src/vcompany/daemon/
  daemon.py          # Modified: owns RuntimeAPI + CompanyRoot init
  runtime_api.py     # NEW: typed gateway to CompanyRoot operations
  comm.py            # Existing: CommunicationPort protocol
  server.py          # Existing: socket server
src/vcompany/bot/
  client.py          # Modified: gutted on_ready, delegates to daemon
  comm_adapter.py    # Modified: extended with channel creation methods
  cogs/
    strategist.py    # Modified: thin adapter calling RuntimeAPI
    commands.py      # Modified: calls RuntimeAPI (Phase 22 completes this)
    plan_review.py   # Modified: PM review logic extracted to daemon
```

### Pattern 1: RuntimeAPI as Typed Gateway
**What:** A class with typed async methods that wraps all CompanyRoot operations. Lives in daemon layer, no discord.py imports.
**When to use:** Any operation that bot cogs currently do by calling CompanyRoot directly.
**Example:**
```python
# src/vcompany/daemon/runtime_api.py
class RuntimeAPI:
    """Typed gateway to CompanyRoot operations.

    All methods are async. No discord.py imports. Uses CommunicationPort
    for any outbound messaging.
    """

    def __init__(
        self,
        company_root: CompanyRoot,
        comm_port_getter: Callable[[], CommunicationPort],
    ) -> None:
        self._root = company_root
        self._get_comm = comm_port_getter  # lazy -- comm_port set after bot connects

    async def hire(self, agent_id: str, template: str = "generic") -> str:
        """Hire a company-level agent. Returns agent_id."""
        # Channel creation via CommunicationPort instead of guild.create_text_channel
        await self._get_comm().send_message(
            SendMessagePayload(channel_id=..., content=...)
        )
        container = await self._root.hire(agent_id, template=template)
        return container.context.agent_id

    async def give_task(self, agent_id: str, task: str) -> None:
        container = await self._root._find_container(agent_id)
        if container is not None:
            await container.give_task(task)

    async def dismiss(self, agent_id: str) -> None:
        await self._root.dismiss(agent_id)

    async def health_tree(self) -> dict:
        tree = self._root.health_tree()
        return tree.model_dump()  # or custom serialization

    async def new_project(self, project_id: str, config: ProjectConfig) -> None:
        # Full project setup: specs, supervision tree, PM wiring
        ...
```

### Pattern 2: Callback-to-CommunicationPort Replacement
**What:** Every closure that calls `channel.send()` or `self.get_channel()` gets replaced with `CommunicationPort.send_message()`.
**When to use:** All 22 closures in on_ready() that touch Discord.
**Example:**
```python
# BEFORE (in on_ready, captures self):
async def on_escalation(msg: str) -> None:
    alerts_ch = self._system_channels.get("alerts")
    if alerts_ch and self.message_queue:
        await self.message_queue.enqueue(QueuedMessage(
            priority=MessagePriority.ESCALATION,
            timestamp=time.monotonic(),
            channel_id=alerts_ch.id,
            content=f"ESCALATION: {msg}",
        ))

# AFTER (in RuntimeAPI, uses CommunicationPort):
async def _on_escalation(self, msg: str) -> None:
    alerts_id = self._channel_registry.get("alerts")
    if alerts_id:
        await self._get_comm().send_message(
            SendMessagePayload(channel_id=alerts_id, content=f"ESCALATION: {msg}")
        )
```

### Pattern 3: Daemon CompanyRoot Initialization Sequence
**What:** CompanyRoot must wait for bot to connect before initializing (needs CommunicationPort registered). Two-phase init.
**When to use:** Daemon startup.
**Critical ordering:**
1. Daemon starts socket server
2. Daemon starts bot via `bot.start(token)`
3. Bot connects to Discord, on_ready fires
4. on_ready registers DiscordCommunicationPort with daemon
5. Daemon detects CommunicationPort registration, initializes CompanyRoot
6. OR: CompanyRoot starts with NoopCommunicationPort, swaps to Discord adapter when available

**Recommended approach:** Start CompanyRoot immediately with NoopCommunicationPort. When DiscordCommunicationPort registers, swap it in. This avoids blocking and handles reconnects gracefully. CompanyRoot already uses NoopCommunicationPort as default.

### Pattern 4: Channel Registry for Daemon
**What:** Daemon needs channel IDs to send messages but cannot resolve channel names (that's Discord-specific). Bot registers channel IDs during on_ready.
**When to use:** Every CommunicationPort.send_message() call from the daemon.
**Example:**
```python
# In daemon/runtime_api.py
class RuntimeAPI:
    def __init__(self, ...):
        self._channel_ids: dict[str, str] = {}  # name -> id

    def register_channels(self, channels: dict[str, str]) -> None:
        """Called by bot after system channels are created."""
        self._channel_ids.update(channels)
```

### Anti-Patterns to Avoid

- **Passing guild objects to daemon:** The daemon must never hold a reference to discord.Guild, discord.TextChannel, or any discord.py type. Use string channel IDs only.
- **Lazy import of discord.py in daemon:** Do not use `import discord` anywhere in the daemon package, even inside functions. This is COMM-02.
- **Re-implementing MessageQueue in daemon:** The existing MessageQueue with priority/debounce is valuable but currently Discord-coupled. Either extract it to use CommunicationPort, or accept that CommunicationPort handles rate limiting at the adapter level.
- **Breaking the PM event sink ordering:** The PM event sink MUST be wired LAST, after all agent callbacks are set. Research Pitfall 3 from the original code documents this race condition.

## Complete on_ready() Closure Audit

22 closures identified in `src/vcompany/bot/client.py` lines 113-627:

### Category A: Alert/Notification Callbacks (move to RuntimeAPI, use CommunicationPort)
| # | Closure | Lines | Captures | RuntimeAPI Method |
|---|---------|-------|----------|-------------------|
| 1 | `on_escalation` | 209-217 | self._system_channels, self.message_queue | `_on_escalation(msg)` -> CommunicationPort |
| 2 | `on_degraded` | 239-249 | self._system_channels, self.message_queue | `_on_degraded()` -> CommunicationPort |
| 3 | `on_recovered` | 251-260 | self._system_channels, self.message_queue | `_on_recovered()` -> CommunicationPort |
| 4 | `_on_trigger_integration_review` | 485-498 | self._system_channels, self.message_queue, self.project_config | `_on_trigger_integration()` -> CommunicationPort |
| 5 | `_on_send_intervention` | 547-568 | self.message_queue, guild | `_on_send_intervention(agent_id, msg)` -> CommunicationPort |

### Category B: Strategist Callbacks (stay in daemon via CompanyAgent)
| # | Closure | Lines | Captures | Destination |
|---|---------|-------|----------|-------------|
| 6 | `_on_strategist_response` | 300-308 | self.get_channel | CompanyAgent sends via CommunicationPort |
| 7 | `_on_hire` | 320-323 | self.get_guild, self.company_root | RuntimeAPI.hire() -- guild replaced by CommunicationPort channel creation |
| 8 | `_on_give_task` | 326-331 | self.company_root | RuntimeAPI.give_task() -- pure business logic, no Discord |
| 9 | `_on_dismiss` | 333-334 | self.company_root | RuntimeAPI.dismiss() -- pure business logic, no Discord |

### Category C: PM Event Routing (stay in daemon, callbacks are internal)
| # | Closure | Lines | Captures | Destination |
|---|---------|-------|----------|-------------|
| 10 | `pm_event_sink` | 403-404 | pm_container | Internal daemon wiring -- no Discord |
| 11 | `_make_gsd_cb` (factory) | 408-416 | sink | Internal daemon wiring -- no Discord |
| 12 | `_make_briefing_cb` (factory) | 418-425 | sink | Internal daemon wiring -- no Discord |

### Category D: Review Gate Callbacks (move to daemon, CommunicationPort for review posts)
| # | Closure | Lines | Captures | Destination |
|---|---------|-------|----------|-------------|
| 13 | `_make_review_cb` | 448-452 | plan_review_cog | Daemon posts review via CommunicationPort |
| 14 | `_make_gsd_review_cb` | 456-459 | plan_review_cog | PM review logic in daemon |

### Category E: PM Action Callbacks (move to daemon)
| # | Closure | Lines | Captures | Destination |
|---|---------|-------|----------|-------------|
| 15 | `_on_assign_task` | 468-481 | project_sup, plan_review_cog_for_assign | RuntimeAPI -- tmux command via container, no Discord |
| 16 | `_on_recruit_agent` | 501-511 | project_sup, pm_event_sink, plan_review_cog | RuntimeAPI -- internal supervisor operation |
| 17 | `_on_remove_agent` | 513-514 | project_sup | RuntimeAPI -- internal supervisor operation |
| 18 | `_on_escalate_to_strategist` | 522-533 | strategist_container | Internal daemon wiring -- CompanyAgent event |
| 19 | `_on_escalate_to_strategist_fallback` | 539-544 | strategist_cog_ref2 | Remove -- fallback path eliminated when daemon owns conversation |

### Category F: Infrastructure Callbacks (move to RuntimeAPI)
| # | Closure | Lines | Captures | Destination |
|---|---------|-------|----------|-------------|
| 20 | `on_health_change` | 221 | health_cog | RuntimeAPI emits health events; bot subscribes via socket/event |
| 21 | `claude_health_check` | 224-236 | anthropic | Stays as-is -- pure API call, no Discord dependency |
| 22 | `_send_message` (MessageQueue) | 343-356 | self.get_channel, discord.HTTPException | Replace: CommunicationPort handles sending |

### Remaining on_ready() Code (not closures, but also needs extraction)
- **vco-owner role creation** (lines 133-142): Stays in bot -- pure Discord concern
- **System channel setup** (lines 145-152): Stays in bot, but registers channel IDs with daemon
- **Strategist channel init** (lines 156-182): StrategistCog.initialize() stays, but conversation owned by daemon
- **WorkflowMaster init** (lines 184-195): Stays in bot for now (out of scope)
- **Project detection** (lines 198-202): Moves to daemon -- daemon detects projects, not bot
- **Child specs build** (lines 362-376): Moves to daemon -- RuntimeAPI.new_project()
- **PM/PlanReviewer init** (lines 586-614): PM tier owned by daemon, PlanReviewer remains bot-side (review UI) but review dispatch moves to daemon
- **CommunicationPort registration** (lines 619-623): Stays in bot -- bot creates adapter, registers with daemon
- **Boot notifications** (lines 630): Move to daemon using CommunicationPort

## CommunicationPort Extensions Needed

The current CommunicationPort protocol (Phase 19) has 4 methods:
- `send_message(SendMessagePayload)`
- `send_embed(SendEmbedPayload)`
- `create_thread(CreateThreadPayload)`
- `subscribe_to_channel(SubscribePayload)`

Phase 20 needs additional capabilities:

| Need | Current Support | Extension Required |
|------|----------------|-------------------|
| Send plain message | send_message | Sufficient |
| Send rich embed | send_embed | Sufficient |
| Create thread | create_thread | Sufficient |
| Create category channel | None | **New: create_category method or structured payload** |
| Create text channel under category | None | **New: create_channel method** |
| Resolve channel by name | None | **New: Bot registers channel name->ID map with daemon** |
| Edit existing message | None | **New: edit_message method (for "Thinking..." placeholder)** |
| Add reaction to message | None | Not needed for Phase 20 |

**Recommendation:** Extend CommunicationPort with:
```python
class CreateChannelPayload(BaseModel):
    category_name: str
    channel_name: str

class CreateChannelResult(BaseModel):
    channel_id: str
    name: str

class EditMessagePayload(BaseModel):
    channel_id: str
    message_id: str
    content: str

# Add to CommunicationPort protocol:
async def create_channel(self, payload: CreateChannelPayload) -> CreateChannelResult | None: ...
async def edit_message(self, payload: EditMessagePayload) -> bool: ...
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Channel ID resolution in daemon | Custom daemon-side Discord channel cache | Channel registry dict populated by bot on_ready | Daemon must not import discord.py; bot knows channels |
| Message priority/debounce in daemon | New queue system | Either adapt MessageQueue to use CommunicationPort, or rely on CommunicationPort adapter for rate limiting | MessageQueue already handles priority, debounce, rate limiting |
| Supervision tree in daemon | New supervisor patterns | Existing CompanyRoot + Supervisor + ProjectSupervisor | All logic exists, just needs to be constructed in daemon instead of on_ready |
| Event-driven agent lifecycle | New event system | Existing CompanyAgent + EventDrivenLifecycle | Already implemented, just need to wire through RuntimeAPI |

## Common Pitfalls

### Pitfall 1: CommunicationPort Not Ready When CompanyRoot Starts
**What goes wrong:** CompanyRoot starts in daemon before bot connects. First escalation/notification goes to NoopCommunicationPort and is silently dropped.
**Why it happens:** Daemon starts before bot, CommunicationPort registered in on_ready.
**How to avoid:** Start CompanyRoot with NoopCommunicationPort (already the default). When DiscordCommunicationPort registers, swap it into CompanyRoot and all ProjectSupervisors. Log a warning on the first real message sent while still using Noop.
**Warning signs:** Escalation messages not appearing in Discord after bot restart.

### Pitfall 2: PM Event Sink Ordering Race
**What goes wrong:** PM event sink set before all agent callbacks are wired. Events arrive, handlers not ready, events silently dropped.
**Why it happens:** This exact bug is documented in the original code comment at line 577-578.
**How to avoid:** RuntimeAPI.new_project() must wire ALL agent callbacks before calling `project_sup.set_pm_event_sink()`. Preserve exact same ordering as current on_ready().
**Warning signs:** PM not responding to agent transitions, health changes.

### Pitfall 3: Bot Still Importing Container Modules
**What goes wrong:** EXTRACT-04 violated. Bot cog imports CompanyRoot or container types for isinstance checks.
**Why it happens:** Incremental refactoring leaves stale imports.
**How to avoid:** After extraction, grep bot/ directory for imports from `vcompany.supervisor`, `vcompany.container`, `vcompany.agent` (except models). Should find zero.
**Warning signs:** Circular import errors, or test failures when container internals change.

### Pitfall 4: Channel ID Types (int vs str)
**What goes wrong:** Discord channel IDs are integers in discord.py but strings in CommunicationPort payloads. Type mismatch causes lookup failures.
**Why it happens:** CommunicationPort uses `channel_id: str` (correct for platform agnostic), but bot code uses `int`.
**How to avoid:** DiscordCommunicationPort._resolve_channel already handles str->int conversion. Daemon must always use string IDs. Channel registry stores strings.
**Warning signs:** "channel not found" warnings in logs after extraction.

### Pitfall 5: CompanyRoot.hire() Takes guild Parameter
**What goes wrong:** `CompanyRoot.hire(agent_id, template, guild=guild)` currently receives a discord.Guild for channel creation. Post-extraction, daemon cannot pass guild.
**Why it happens:** hire() was designed when bot owned CompanyRoot.
**How to avoid:** Remove guild parameter from hire(). Channel creation happens via CommunicationPort.create_channel() inside RuntimeAPI.hire(), not inside CompanyRoot.hire().
**Warning signs:** TypeError on hire() call from daemon.

### Pitfall 6: /new-project Duplicated CompanyRoot Creation
**What goes wrong:** CommandsCog.new_project() (lines 173-218) has its own CompanyRoot creation path, duplicating on_ready() logic.
**Why it happens:** Was needed for the case where no project detected on startup.
**How to avoid:** /new-project must go through RuntimeAPI.new_project(). The duplicated creation logic in CommandsCog must be removed.
**Warning signs:** Two CompanyRoot instances, or missing callback wiring on dynamically created projects.

## Extraction Sequencing

The extraction must happen in a specific order to maintain a working system at each step:

1. **Audit** -- Catalog all 22 closures with their Discord dependencies (this research)
2. **RuntimeAPI shell** -- Create RuntimeAPI class with stub methods, wire into Daemon
3. **CompanyRoot to daemon** -- Move CompanyRoot construction from on_ready() to Daemon._run(), guarded by CommunicationPort availability
4. **Alert callbacks** -- Replace Category A closures (5 callbacks) with CommunicationPort sends in RuntimeAPI
5. **Strategist extraction** -- Move StrategistConversation ownership fully into daemon; CompanyAgent._on_response sends via CommunicationPort
6. **PM flow extraction** -- Move PM event routing and review dispatch to daemon
7. **Channel creation via CommunicationPort** -- Extend CommunicationPort protocol, implement in adapter
8. **Bot gutting** -- Remove all container imports from bot cogs, replace with RuntimeAPI calls
9. **Verification** -- Grep for prohibited imports, run tests

## State of the Art

| Old Approach (current) | New Approach (Phase 20) | Impact |
|------------------------|-------------------------|--------|
| on_ready() creates CompanyRoot | Daemon creates CompanyRoot | Bot no longer owns business logic |
| Closures capture Discord objects | RuntimeAPI methods use CommunicationPort | Platform-agnostic operations |
| Bot imports container modules | Bot imports RuntimeAPI only | Clean dependency boundary |
| Strategist sends via channel.send() | Strategist sends via CommunicationPort | Portable to non-Discord |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pyproject.toml` (pytest section) |
| Quick run command | `uv run pytest tests/ -x --timeout=10 -q` |
| Full suite command | `uv run pytest tests/ --timeout=30` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXTRACT-01 | CompanyRoot initializes in daemon | unit | `uv run pytest tests/test_daemon.py -x -k runtime` | Wave 0 |
| EXTRACT-02 | RuntimeAPI typed methods | unit | `uv run pytest tests/test_runtime_api.py -x` | Wave 0 |
| EXTRACT-03 | on_ready callbacks replaced | integration | `uv run pytest tests/test_bot_client.py -x -k ready` | Existing (needs update) |
| EXTRACT-04 | Bot uses RuntimeAPI only | unit (import check) | `uv run pytest tests/test_import_boundary.py -x` | Wave 0 |
| COMM-04 | Strategist through CommunicationPort | unit | `uv run pytest tests/test_strategist_comm.py -x` | Wave 0 |
| COMM-05 | PM review through CommunicationPort | unit | `uv run pytest tests/test_pm_review_comm.py -x` | Wave 0 |
| COMM-06 | Channel creation through CommunicationPort | unit | `uv run pytest tests/test_discord_comm_adapter.py -x -k channel` | Existing (needs extension) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x --timeout=10 -q`
- **Per wave merge:** `uv run pytest tests/ --timeout=30`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_runtime_api.py` -- covers EXTRACT-02 (RuntimeAPI methods)
- [ ] `tests/test_import_boundary.py` -- covers EXTRACT-04 (no container imports in bot)
- [ ] `tests/test_strategist_comm.py` -- covers COMM-04 (Strategist via CommunicationPort)
- [ ] `tests/test_pm_review_comm.py` -- covers COMM-05 (PM review via CommunicationPort)
- [ ] Update `tests/test_daemon.py` -- covers EXTRACT-01 (CompanyRoot in daemon)
- [ ] Update `tests/test_discord_comm_adapter.py` -- covers COMM-06 (channel creation)
- [ ] Update `tests/test_bot_client.py` -- covers EXTRACT-03 (gutted on_ready)

## Open Questions

1. **MessageQueue fate**
   - What we know: MessageQueue provides priority/debounce/rate-limiting for outbound Discord messages. Currently Discord-coupled (captures `channel.send()`).
   - What's unclear: Should MessageQueue stay in bot (behind CommunicationPort), move to daemon (using CommunicationPort), or be eliminated (CommunicationPort adapter handles queueing)?
   - Recommendation: Keep MessageQueue in bot layer as part of DiscordCommunicationPort adapter. CommunicationPort.send_message() can internally use MessageQueue. Daemon doesn't need to know about queueing.

2. **PlanReviewCog scope**
   - What we know: PlanReviewCog has both UI logic (Discord buttons, embeds) and review logic (PM evaluation). PM evaluation should be in daemon.
   - What's unclear: How much of PlanReviewCog moves vs. stays.
   - Recommendation: Review dispatch/evaluation moves to daemon. PlanReviewCog becomes a thin adapter: receives Discord button clicks, forwards to RuntimeAPI, formats responses.

3. **Boot notification timing**
   - What we know: `_send_boot_notifications()` runs at end of on_ready(). Post-extraction, daemon owns CompanyRoot init which happens after on_ready.
   - What's unclear: When exactly do boot notifications fire?
   - Recommendation: Bot on_ready sends "connected" notification. Daemon sends "CompanyRoot ready" notification after supervision tree starts. Two separate notifications.

## Sources

### Primary (HIGH confidence)
- `src/vcompany/bot/client.py` -- 22 closures audited line by line
- `src/vcompany/daemon/daemon.py` -- current daemon structure (Phase 18)
- `src/vcompany/daemon/comm.py` -- CommunicationPort protocol (Phase 19)
- `src/vcompany/bot/comm_adapter.py` -- DiscordCommunicationPort (Phase 19)
- `src/vcompany/supervisor/company_root.py` -- CompanyRoot operations
- `src/vcompany/agent/company_agent.py` -- Strategist event handling
- `src/vcompany/bot/cogs/strategist.py` -- StrategistCog message routing
- `src/vcompany/bot/cogs/commands.py` -- CommandsCog including /new-project duplication
- `src/vcompany/bot/cogs/plan_review.py` -- PM review flow
- `src/vcompany/bot/channel_setup.py` -- channel creation functions

### Secondary (MEDIUM confidence)
- `.planning/STATE.md` -- PM event sink ordering constraint documented
- `.planning/REQUIREMENTS.md` -- requirement definitions

## Metadata

**Confidence breakdown:**
- Architecture patterns: HIGH -- based on direct code reading of all 7 affected modules
- Closure audit: HIGH -- line-by-line audit of 700+ line on_ready() method
- CommunicationPort extensions: HIGH -- clear gap analysis against existing protocol
- Extraction sequencing: HIGH -- dependency ordering derived from callback wiring analysis
- Pitfalls: HIGH -- each pitfall tied to specific code lines and existing comments

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (stable -- internal architecture, no external dependency changes)
