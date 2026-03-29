# Phase 24: Discord Visibility - Research

**Researched:** 2026-03-29
**Domain:** Internal agent routing replacement with Discord-native communication
**Confidence:** HIGH

## Summary

Phase 24 replaces all internal Python-level agent-to-agent routing with Discord messages visible in channels. The codebase currently has two parallel communication paths: (1) Discord messages via CommunicationPort/SendMessagePayload for notifications, and (2) internal asyncio.Queue-based post_event() calls for PM/Strategist coordination. This phase eliminates path (2) entirely, making Discord the sole inter-agent communication channel.

The primary work involves: removing ~15 agent-specific routing methods from RuntimeAPI (pm_event_sink, relay_strategist_*, route_completion_to_pm, handle_pm_escalation, signal_workflow_stage, log_plan_decision), replacing FulltimeAgent/CompanyAgent's internal event queues with Discord @mention routing, adding Discord message emission to BacklogQueue mutations, and building a generic @mention-based message delivery system in the bot layer.

**Primary recommendation:** Build a single generic MentionRouter in the bot layer that watches all messages for @AgentHandle mentions and delivers them to the target agent's container via CommunicationPort. All agent coordination (PM events, Strategist escalations, task assignments) becomes Discord messages with @mentions. Remove the internal post_event() queues and the RuntimeAPI closure factory methods that feed them.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Discord is the ONLY agent-to-agent interaction point. No internal post_event() queues, no Python-level event routing between agents.
- **D-02:** Every agent subscribes to their Discord handle (@Strategist, @PMProjectX, @SomeResearcher). @mentioning routes messages to the target agent.
- **D-03:** Replies to an agent's messages route back to that agent with context (who replied, which message, reply content).
- **D-04:** Routing mechanism is generic -- not hardcoded per agent type. Bot watches @mentions and delivers via CommunicationPort.
- **D-05:** Events are plain text Discord messages, not structured embeds. Human-readable.
- **D-06:** Claude's discretion on pre-commit vs post-commit per event type.
- **D-07:** Events land in the most relevant channel. Task assignment -> agent channel, plan review -> #plan-review, phase complete -> #status.
- **D-08:** Backlog mutations posted to dedicated #backlog channel.
- **D-09:** Whether PM posts its own mutations or system posts on PM's behalf is Claude's discretion.
- **D-10:** Clean sweep -- remove all agent-specific internal routing in one pass.
- **D-11:** RuntimeAPI keeps infrastructure ops (hire, dispatch, kill, relaunch, new_project, remove_project, status, health_tree, checkin, standup, run_integration, resolve_review, verify_agent_execution, get_agent_states, get_container_info).
- **D-12:** Remove signal_workflow_stage() -- dead code, no callers.
- **D-13:** Remove log_plan_decision() -- replaced by Discord messages.
- **D-14:** Both PM and Strategist lose special post_event() paths. Both become normal agents through Discord only.
- **D-15:** Reply context includes reply text plus immediate parent message only, not full chain.

### Claude's Discretion
- Event timing (pre-commit vs post-commit) per event type
- Whether PM or system posts backlog mutation messages
- Message formatting conventions for different event types
- How CommunicationPort delivers @mention-routed messages to agent containers

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VIS-01 | Every inter-agent event produces a Discord message before taking effect | Requires Discord send_message before post_event/state mutation; all event paths mapped in RuntimeAPI Categories B/C/D/E |
| VIS-02 | PM backlog ops (add/remove/prioritize) posted to Discord | BacklogQueue.append/insert_urgent/reorder/cancel need Discord emission; new #backlog channel needed in channel_setup.py |
| VIS-03 | Plan review decisions posted to Discord before processing | PlanReviewCog already posts to #plan-review; need to ensure confidence+reasoning visible before internal resolve_review() |
| VIS-04 | RuntimeAPI has no agent-type-specific routing methods | Remove: _make_pm_event_sink, _make_gsd_cb, _make_briefing_cb, relay_strategist_message, relay_strategist_escalation_reply, _on_escalate_to_strategist, _on_strategist_response, route_completion_to_pm, handle_pm_escalation, signal_workflow_stage, log_plan_decision |
| VIS-05 | Agent coordination uses Discord channel subscriptions not post_event() | FulltimeAgent._event_queue and CompanyAgent._event_queue replaced by inbound Discord message handling |
| VIS-06 | Task assignment is Discord message in agent channel, not internal queue_task() | _on_assign_task currently calls child.set_assignment() directly; replace with Discord message to #agent-{id} |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **discord.py 2.7.x** is the only Discord library (no nextcord/disnake)
- **No database** -- state lives in filesystem (YAML/Markdown)
- **CommunicationPort protocol** for all outbound messaging from daemon layer
- **No discord.py imports** in daemon/runtime_api.py
- **httpx** for any HTTP needs, not requests/aiohttp
- **pydantic** for data validation models
- **asyncio** for all async orchestration
- **Nyquist validation disabled** per config -- no test infrastructure section needed

## Architecture Patterns

### Current Architecture (What Exists)

There are two CommunicationPort protocols in the codebase:
1. **`daemon/comm.py`** -- Used by RuntimeAPI for outbound Discord messaging (SendMessagePayload, CreateChannelPayload, etc.). This is the active, battle-tested one.
2. **`container/communication.py`** -- Original container-level protocol with send_message(target, content) and receive_message(). Stub/noop only. Defined for future use.

Current agent-to-agent routing is all internal Python:
```
Supervisor health_change -> pm_event_sink -> PM.post_event(asyncio.Queue)
GSD phase transition -> _make_gsd_cb -> pm_event_sink -> PM.post_event()
PM escalation -> _on_escalate_to_strategist -> CompanyAgent.post_event()
Strategist response -> _on_response callback -> send_message to Discord
Task assignment -> _on_assign_task -> child.set_assignment() directly
Phase completion -> route_completion_to_pm -> PM.post_event()
```

### Target Architecture (What to Build)

```
Agent completes phase -> sends Discord message to #agent-{id}: "Phase X complete, @PMProjectX"
                      -> Bot sees @PMProjectX mention -> routes to PM container

PM decides task -> sends Discord message to #agent-{gsd-id}: "@agent-{id} assigned: {task}"
               -> Bot sees @agent-{id} mention -> routes to GSD container

PM escalates -> sends Discord message to #strategist: "@Strategist {question}"
             -> Bot sees @Strategist mention -> routes to Strategist container
```

### Recommended Project Structure Changes

```
src/vcompany/
├── bot/
│   ├── routing.py               # MODIFY: Extend route_message to handle all @agent mentions
│   ├── channel_setup.py         # MODIFY: Add #backlog channel to project channels
│   └── cogs/
│       └── mention_router.py    # NEW: Generic cog that watches @mentions, delivers to containers
├── daemon/
│   ├── runtime_api.py           # MODIFY: Remove ~15 agent-specific routing methods
│   └── comm.py                  # KEEP: CommunicationPort protocol unchanged
├── agent/
│   ├── fulltime_agent.py        # MODIFY: Remove post_event/event_queue, add Discord message handler
│   ├── company_agent.py         # MODIFY: Remove post_event/event_queue, add Discord message handler
│   └── gsd_agent.py             # MODIFY: Remove _on_phase_transition callback, emit Discord messages
├── autonomy/
│   └── backlog.py               # MODIFY: Add Discord notification on mutations
└── supervisor/
    └── supervisor.py            # MODIFY: Remove pm_event_sink wiring
```

### Pattern 1: Generic @Mention Routing

**What:** A single bot Cog watches all messages across all channels. When a message contains @AgentHandle, the Cog delivers the message content to that agent's container via a generic delivery mechanism.

**When to use:** All inter-agent communication.

**Implementation approach:**
```python
# New: MentionRouterCog
class MentionRouterCog(commands.Cog):
    """Watches all messages for @agent mentions and delivers to target containers."""

    def __init__(self, bot: VcoBot):
        self.bot = bot
        # Registry: handle_name -> (container, channel_id)
        self._agent_handles: dict[str, AgentHandle] = {}

    def register_agent(self, handle: str, container: AgentContainer, channel_id: str):
        """Register an agent handle for @mention routing."""
        self._agent_handles[handle] = AgentHandle(container=container, channel_id=channel_id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        # Check for @mentions in message content
        for handle, agent in self._agent_handles.items():
            if f"@{handle}" in message.content:
                await self._deliver_to_agent(agent, message)

    async def _deliver_to_agent(self, agent: AgentHandle, message: discord.Message):
        """Deliver message to agent container with context."""
        # Build context: who sent it, which channel, reply-to if applicable
        context = MessageContext(
            sender=message.author.display_name,
            channel=message.channel.name,
            content=message.content,
            reply_to=message.reference.message_id if message.reference else None,
        )
        # Deliver via container's receive method (new generic interface)
        await agent.container.receive_discord_message(context)
```

### Pattern 2: Discord-First Event Emission

**What:** Before any internal state mutation, emit a Discord message describing the action. The message IS the event -- agents watching the channel react to it.

**When to use:** All events that were previously internal post_event() calls.

**Implementation approach:**
```python
# In BacklogQueue -- wrap mutations with Discord emission
async def append(self, item: BacklogItem) -> None:
    """Add item to end of queue and notify Discord."""
    async with self._lock:
        self._items.append(item)
        await self._persist()
    # Emit to #backlog channel (after persist to avoid partial state)
    if self._on_mutation:
        await self._on_mutation(f"Backlog: added '{item.title}' (priority {item.priority})")
```

### Pattern 3: Reply Context Delivery (D-15)

**What:** When an agent receives a reply, it gets the reply text plus the immediate parent message content. Not the full chain.

**When to use:** All reply-based routing.

**Implementation approach:**
```python
# In MentionRouterCog
if message.reference and message.reference.message_id:
    try:
        parent = await message.channel.fetch_message(message.reference.message_id)
        context.parent_message = parent.content
    except discord.NotFound:
        context.parent_message = None
```

### Anti-Patterns to Avoid
- **Post-event queues for inter-agent communication:** The entire point of this phase is eliminating asyncio.Queue-based event routing between agents. Never add new post_event() paths.
- **Agent-type-specific routing in RuntimeAPI:** No `if isinstance(container, FulltimeAgent)` routing logic. The MentionRouter is generic.
- **Structured embeds for events:** D-05 says plain text. Don't use discord.Embed for inter-agent events.
- **Direct container method calls for coordination:** Don't call `container.set_assignment()` directly. Send a Discord message that the agent receives.

## Methods to Remove from RuntimeAPI

These methods must be removed per D-10/D-11/D-14:

| Method | Category | Replacement |
|--------|----------|-------------|
| `_make_pm_event_sink()` | C: PM routing | Discord @PM mentions |
| `_make_gsd_cb()` | C: PM routing | GSD agent sends Discord message on phase transition |
| `_make_briefing_cb()` | C: PM routing | Continuous agent sends briefing as Discord message |
| `_on_escalate_to_strategist()` | E: PM action | PM sends @Strategist message in #strategist |
| `_on_strategist_response()` | B: Strategist | Strategist posts reply in Discord channel directly |
| `_on_assign_task()` | E: PM action | PM sends task message to #agent-{id} |
| `_on_recruit_agent()` | E: PM action | Keep as infrastructure op? Or Discord message |
| `_on_remove_agent()` | E: PM action | Keep as infrastructure op? Or Discord message |
| `relay_strategist_message()` | F: Inbound relay | Bot routes @Strategist mentions via generic router |
| `relay_strategist_escalation_reply()` | F: Inbound relay | Bot routes replies via generic router |
| `route_completion_to_pm()` | G: Delegation | Agent sends completion message to Discord |
| `handle_pm_escalation()` | H: Bot support | PM sends @Strategist in Discord |
| `signal_workflow_stage()` | Dead code | Remove entirely (D-12) |
| `log_plan_decision()` | Dead code | Remove -- replaced by Discord message (D-13) |
| `_dispatch_pm_review()` | D: Review gate | PM review happens through Discord message flow |
| `_post_review_request()` | D: Review gate | Agent posts review request as Discord message |

**Methods to KEEP (infrastructure ops per D-11):**
- `hire()`, `give_task()`, `dismiss()`
- `dispatch()`, `kill()`, `relaunch()`
- `new_project()`, `new_project_from_name()`, `remove_project()`
- `status()`, `health_tree()`, `get_agent_states()`, `get_container_info()`
- `checkin()`, `standup()`, `run_integration()`
- `resolve_review()`, `verify_agent_execution()`
- `relay_channel_message()` (tmux relay -- infrastructure, not agent routing)
- `register_channels()`, `get_channel_id()`
- Alert callbacks: `_on_escalation()`, `_on_degraded()`, `_on_recovered()` (system notifications, not agent routing)

## Wiring Points to Update

### Supervisor (supervisor.py)
- Remove `pm_event_sink` parameter from `__init__`
- Remove `set_pm_event_sink()` method
- Remove `_pm_event_sink` usage in `_make_state_change_callback()` (lines 281-306)
- Health change events should become Discord messages to agent channels instead

### RuntimeAPI.new_project() (the big wiring method)
- Remove PM event sink creation and wiring (step 6)
- Remove GSD transition callback wiring (step 3, `_make_gsd_cb`)
- Remove briefing callback wiring (step 3, `_make_briefing_cb`)
- Remove PM action callback wiring (step 5, `_on_assign_task`, `_on_escalate_to_strategist`, etc.)
- Remove review gate callback wiring (step 4, `_on_review_request`)
- Instead: Register agent handles with MentionRouterCog

### FulltimeAgent (fulltime_agent.py)
- Remove `_event_queue`, `post_event()`, `process_next_event()`, `_handle_event()`
- Remove callback fields: `_on_gsd_review`, `_on_assign_task`, `_on_trigger_integration_review`, `_on_recruit_agent`, `_on_remove_agent`, `_on_escalate_to_strategist`, `_on_send_intervention`
- Add: `receive_discord_message()` method that parses Discord messages and dispatches PM actions
- Keep: `backlog`, `_project_state` (BacklogQueue and ProjectStateManager are state management, not routing)

### CompanyAgent (company_agent.py)
- Remove `_event_queue`, `post_event()`, `process_next_event()`, `_handle_event()`, `_drain_events()`
- Remove callback fields: `_on_response`, `_on_hire`, `_on_give_task`, `_on_dismiss`
- Add: `receive_discord_message()` that parses Discord messages and dispatches Strategist actions
- Keep: `_conversation` (StrategistConversation is the LLM backend, not routing)

### GsdAgent (gsd_agent.py)
- Remove `_on_phase_transition` callback
- Remove `_on_review_request` callback
- Phase transitions: agent sends Discord message to its channel instead of callback
- Review requests: agent sends "@PM" message in its channel instead of callback

### BacklogQueue (backlog.py)
- Add mutation callback (`_on_mutation`) parameter
- Each mutation method (append, insert_urgent, reorder, cancel, claim_next, mark_completed, mark_pending) calls the callback with a human-readable description

### Channel Setup (channel_setup.py)
- Add `"backlog"` to `_PROJECT_CHANNELS` list
- Consider adding `"status"` channel if it doesn't exist for phase completion events

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Message routing | Custom if/elif routing chains per agent type | Generic @mention-based routing with handle registry |
| Discord rate limiting | Custom rate limiter for event messages | discord.py's built-in rate limiting (handles it internally) |
| Message parsing | Regex-heavy message content parsing | Simple prefix/mention detection already in routing.py |
| Event ordering | Custom ordering/sequencing for events | Discord message timestamps + channel-based ordering (good enough for v1) |

## Common Pitfalls

### Pitfall 1: Circular Message Loops
**What goes wrong:** Agent A sends a message mentioning @AgentB. AgentB processes it and replies mentioning @AgentA. This creates an infinite loop.
**Why it happens:** Both agents are Discord message handlers, and the bot processes all messages.
**How to avoid:** The MentionRouter must skip bot-authored messages (already standard in discord.py cogs). Agents' outbound messages are sent via CommunicationPort (the bot's own user), so they'll have `message.author.bot = True` and be filtered out. Additionally, agent handles use @-prefix text patterns (not real Discord user mentions), so the bot won't trigger on its own messages.
**Warning signs:** Rapid message flooding in a channel between two agents.

### Pitfall 2: Race Condition -- Message Sent But Not Delivered
**What goes wrong:** An event is emitted to Discord, but the target agent hasn't processed it yet when internal state changes.
**Why it happens:** Discord message delivery is asynchronous. The message may be in Discord but the bot hasn't processed the on_message event yet.
**How to avoid:** For most events, this is fine -- eventual consistency. For critical paths (like task assignment where the GSD agent needs the assignment data), the Discord message can be the trigger AND carry the payload. The agent doesn't need prior internal state -- the message IS the assignment.
**Warning signs:** Agent processes events out of order or misses events.

### Pitfall 3: Breaking PM Event Processing During Migration
**What goes wrong:** Removing post_event() before the Discord-based replacement is fully wired causes PM to stop processing events entirely.
**Why it happens:** The PM's _handle_event() dispatcher handles many event types. Removing it all at once without replacement breaks all PM functionality.
**How to avoid:** Plan the migration in waves: (1) Add Discord emission alongside existing internal routing, (2) Add Discord-based inbound handling, (3) Remove internal routing. The plan should NOT do steps 1-3 atomically.
**Warning signs:** PM stops assigning tasks, stops reviewing plans, stops detecting stuck agents.

### Pitfall 4: Two CommunicationPort Protocols
**What goes wrong:** Confusing `daemon/comm.py` CommunicationPort with `container/communication.py` CommunicationPort. They have different method signatures.
**Why it happens:** Both are named CommunicationPort. daemon/comm.py uses payload objects (SendMessagePayload). container/communication.py uses (target, content) args.
**How to avoid:** Use daemon/comm.py's CommunicationPort exclusively (it's the active one). The container/communication.py one is a stub that should either be aligned or removed.
**Warning signs:** Import errors, method signature mismatches.

### Pitfall 5: Channel ID Resolution Timing
**What goes wrong:** Trying to send a Discord message before channel IDs are registered in RuntimeAPI._channel_ids.
**Why it happens:** Channel registration happens during bot on_ready(). If events fire before that, channel lookups return None.
**How to avoid:** Ensure the MentionRouterCog registers agent handles after channel setup completes. Use defensive None checks on channel IDs (already the pattern in existing code).
**Warning signs:** "channel X not found" warnings in logs during startup.

### Pitfall 6: BacklogQueue Has No CommunicationPort Access
**What goes wrong:** BacklogQueue is a pure data structure with MemoryStore persistence. It has no reference to CommunicationPort or Discord.
**Why it happens:** BacklogQueue is deliberately simple -- just data + persistence.
**How to avoid:** Inject a mutation callback (`on_mutation: Callable[[str], Awaitable[None]]`) during wiring in new_project(). The callback posts to #backlog via CommunicationPort. BacklogQueue stays decoupled from Discord.
**Warning signs:** Trying to import discord.py or CommunicationPort into backlog.py.

## Discretion Recommendations

### Event Timing (D-06): Post-Commit for Most Events
**Recommendation:** Use post-commit (emit Discord message AFTER internal state change) for most events. This avoids the case where a Discord message says "task assigned" but the assignment failed internally.

**Exceptions -- use pre-commit for:**
- Plan review decisions (VIS-03 explicitly requires "before the approval/rejection is processed")
- Backlog mutations (VIS-02 requires "not silently mutated" -- but the message can be post-persist since the persist is the meaningful change)

### Backlog Mutation Authorship (D-09): System Posts on PM's Behalf
**Recommendation:** Have the system (BacklogQueue's mutation callback) post messages to #backlog. This is simpler than having PM compose and send Discord messages for every mutation. Format: `"[Backlog] Added: '{title}' (priority {priority})"` or `"[Backlog] Completed: '{title}' by {agent_id}"`.

### Message Format Conventions
**Recommendation:** Use simple prefixed plain text:
- `"[Phase Complete] agent-alpha finished 'execute' phase for Phase 3"`
- `"[Task Assigned] @agent-beta: Build authentication module (item: abc123)"`
- `"[Backlog] Added: 'Fix login bug' (priority 1)"`
- `"[Review] Plan for agent-gamma: APPROVED (confidence: HIGH). Reasoning: ..."`
- `"[Escalation] @Strategist: agent-delta asks: Should we use REST or GraphQL?"`

### CommunicationPort Delivery to Containers (D-04)
**Recommendation:** Add a `receive_discord_message(context: MessageContext)` method to AgentContainer base class (or as a mixin). The MentionRouterCog calls this method when a message @mentions the agent. The container subclass (FulltimeAgent, CompanyAgent, GsdAgent) overrides it to handle the message appropriately. This replaces the per-type post_event() dispatch.

## New Channel Requirements

| Channel | Purpose | Category |
|---------|---------|----------|
| `#backlog` | Backlog mutation visibility (VIS-02) | Project channel (add to _PROJECT_CHANNELS) |
| `#status` | Phase completion and state change events | May already be served by #alerts; Claude's discretion |

Existing channels that gain new traffic:
- `#agent-{id}` -- Task assignments, phase completions, review requests
- `#plan-review` -- Plan review decisions with confidence/reasoning
- `#strategist` -- PM escalations, Strategist responses
- `#decisions` -- Already exists, could receive plan decision summaries

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| asyncio.Queue post_event() | Discord messages with @mentions | All agent events visible on Discord |
| RuntimeAPI closure factories | Generic MentionRouter Cog | No agent-type-specific routing |
| Direct container.set_assignment() | Discord message to agent channel | Assignments visible as messages |
| Internal pm_event_sink | Discord @PM mentions | PM coordination through Discord |

## Open Questions

1. **How do agents parse inbound Discord messages?**
   - What we know: Messages arrive as plain text with @mentions. Agents need to extract intent (task assignment, phase complete, review decision, escalation).
   - What's unclear: Whether agents should use regex parsing, keyword detection, or structured prefixes like `[Task Assigned]`.
   - Recommendation: Use structured prefixes (the format conventions above). Agents parse the prefix to determine message type. Simple, reliable, human-readable.

2. **What happens to the FulltimeAgent stuck detector?**
   - What we know: The stuck detector runs as a background loop checking _agent_state_timestamps. It relies on health_change and gsd_transition events arriving via post_event().
   - What's unclear: How the stuck detector gets its data when events are Discord messages.
   - Recommendation: The stuck detector can still watch for health_change data -- but it should receive it from the Supervisor's health reporting (which is infrastructure, not routing) or from watching Discord messages. Alternatively, the stuck detector is a PM-internal mechanism that reads agent states via RuntimeAPI.get_agent_states() on a timer.

3. **Should _on_recruit_agent and _on_remove_agent survive?**
   - What we know: D-11 says RuntimeAPI keeps infrastructure ops. Agent recruitment/removal is arguably infrastructure.
   - What's unclear: Whether PM should request recruitment via Discord message or via direct RuntimeAPI call.
   - Recommendation: Keep recruit/remove as RuntimeAPI infrastructure ops. PM can invoke them, but the invocation itself should be visible on Discord (PM posts "Recruiting agent X" before calling the API).

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all referenced canonical files
- `src/vcompany/daemon/runtime_api.py` -- Full method inventory, 1058 lines
- `src/vcompany/agent/fulltime_agent.py` -- PM event processing, 308 lines
- `src/vcompany/agent/company_agent.py` -- Strategist event processing, 286 lines
- `src/vcompany/agent/gsd_agent.py` -- Phase transition and review gate, 412 lines
- `src/vcompany/autonomy/backlog.py` -- BacklogQueue mutations, 187 lines
- `src/vcompany/bot/cogs/plan_review.py` -- Plan review workflow, 633 lines
- `src/vcompany/supervisor/supervisor.py` -- PM event sink wiring, 598 lines
- `src/vcompany/daemon/comm.py` -- CommunicationPort protocol (daemon), 143 lines
- `src/vcompany/container/communication.py` -- CommunicationPort protocol (container), 60 lines
- `src/vcompany/bot/routing.py` -- Message routing framework, 222 lines
- `src/vcompany/bot/comm_adapter.py` -- DiscordCommunicationPort, 174 lines
- `src/vcompany/bot/channel_setup.py` -- Channel creation, 243 lines

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions (user-validated architecture choices)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- No new libraries needed. Uses existing discord.py, CommunicationPort, pydantic.
- Architecture: HIGH -- All source files examined, all routing paths traced, clear removal/replacement plan.
- Pitfalls: HIGH -- Race conditions and migration risks identified from actual code analysis.

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (stable -- internal refactoring, no external dependencies)
