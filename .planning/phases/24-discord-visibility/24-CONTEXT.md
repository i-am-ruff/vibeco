# Phase 24: Discord Visibility - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Surface all hidden inter-agent communication through Discord channels. Discord (or any external platform via CommunicationPort) becomes the ONLY agent-to-agent interaction point. No internal Python routing (post_event, pm_event_sink, relay_strategist_*) survives. Every event that affects an agent is a Discord message that agent receives via @mention or reply routing.

Requirements: VIS-01, VIS-02, VIS-03, VIS-04, VIS-05, VIS-06

</domain>

<decisions>
## Implementation Decisions

### Core Architecture: Discord as ONLY Interaction Channel
- **D-01:** This is NOT just "visibility" — Discord is the ONLY agent-to-agent interaction point. No internal post_event() queues, no Python-level event routing between agents. All coordination happens through Discord messages.
- **D-02:** Every agent (PM, Strategist, GSD agents, company agents) subscribes to their Discord handle (@Strategist, @PMProjectX, @SomeResearcher). @mentioning an agent routes the message to that agent with full context (who sent it, which channel, message content).
- **D-03:** Replies to an agent's messages also route back to that agent with context of which message was replied to and with what. This enables conversational agent interaction (PM replies to dev agent's message, dev agent sees the reply in context).
- **D-04:** The routing mechanism is generic — not hardcoded per agent type. The bot watches for @mentions and delivers them to the mentioned agent via CommunicationPort.

### Event Format
- **D-05:** Events are plain text Discord messages, not structured embeds. Human-readable.

### Event Timing
- **D-06:** Claude's discretion — pre-commit vs post-commit per event type.

### Channel Routing
- **D-07:** Events land in the channel most relevant to the agent involved. Task assignment goes to the agent's channel, plan review to #plan-review, phase complete to #status. Matches existing channel-per-agent pattern.

### Backlog Mutation Visibility
- **D-08:** Backlog mutations (add/remove/prioritize) are posted to a dedicated #backlog channel.
- **D-09:** Whether PM posts its own mutation messages or the system posts on PM's behalf is Claude's discretion.

### RuntimeAPI Cleanup
- **D-10:** Clean sweep — remove all agent-specific internal routing in one pass (pm_event_sink, _make_gsd_cb, _make_briefing_cb, relay_strategist_*, route_completion_to_pm, handle_pm_escalation). Replace with generic @mention-based Discord routing.
- **D-11:** RuntimeAPI keeps infrastructure ops (hire, dispatch, kill, relaunch, new_project, remove_project, status, health_tree, checkin, standup, run_integration, resolve_review, verify_agent_execution, get_agent_states, get_container_info). These are CLI/slash-command backends, not agent-routing.
- **D-12:** Remove `signal_workflow_stage()` — dead code, no callers.
- **D-13:** Remove `log_plan_decision()` — reaches into strategist container internals. Plan decisions become Discord messages instead.
- **D-14:** Both PM and Strategist lose their special post_event() paths. Both become normal agents interacting only through Discord. No agent-type-specific routing methods remain in RuntimeAPI (VIS-04).

### Reply Context
- **D-15:** When an agent receives a reply, it gets the reply text plus the immediate parent message being replied to. Not the full chain.

### Claude's Discretion
- Event timing (pre-commit vs post-commit) per event type
- Whether PM or system posts backlog mutation messages
- Message formatting conventions for different event types
- How CommunicationPort delivers @mention-routed messages to agent containers

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core Architecture
- `src/vcompany/daemon/runtime_api.py` — RuntimeAPI with all agent-specific routing to be removed (pm_event_sink, relay_strategist_*, route_completion_to_pm, handle_pm_escalation, signal_workflow_stage, log_plan_decision)
- `src/vcompany/agent/fulltime_agent.py` — FulltimeAgent.post_event() internal queue to be replaced
- `src/vcompany/agent/company_agent.py` — CompanyAgent (Strategist) post_event() path to be replaced

### Communication Layer
- `src/vcompany/bot/cogs/commands.py` — Slash commands calling checkin/standup/run_integration (these STAY)
- `src/vcompany/bot/cogs/plan_review.py` — PlanReviewCog calling verify_agent_execution and log_plan_decision
- `src/vcompany/autonomy/backlog.py` — BacklogQueue with silent mutations that need Discord visibility

### Supervisor
- `src/vcompany/supervisor/supervisor.py` — Supervisor with pm_event_sink wiring

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `CommunicationPort` protocol (Phase 19) — send_message, send_embed, subscribe_to_channel already exists
- `RuntimeAPI._get_comm().send_message()` — already used for many Discord notifications, pattern to extend
- `register_channels()` / `get_channel_id()` — channel routing infrastructure already in place

### Established Patterns
- Bot watches messages and routes to RuntimeAPI methods — extend to @mention routing
- Channel-per-agent pattern already exists in channel_setup.py
- Pydantic models for data validation throughout

### Integration Points
- RuntimeAPI agent-specific methods (~15 methods to remove/replace)
- FulltimeAgent.post_event() and CompanyAgent.post_event() — internal queues to eliminate
- BacklogQueue — needs to emit Discord messages on mutation
- PlanReviewCog — needs log_plan_decision replaced with Discord message
- Supervisor.set_pm_event_sink() — wiring to remove

### Dead Code to Remove
- `signal_workflow_stage()` — no callers outside RuntimeAPI
- `log_plan_decision()` — replaced by Discord message to #decisions

</code_context>

<specifics>
## Specific Ideas

- Agent handles follow naming convention: @Strategist, @PMProjectX, @SomeResearcher — role-based, not separate Discord users
- Single bot watches all messages and routes @mentions to the correct agent via CommunicationPort
- The human owner can reply to any agent's message, which routes to that agent with context — same mechanism as agent-to-agent
- This is the foundation that makes Phase 25 (Transport Abstraction) and Phase 26 (Docker Runtime) possible — agents interact only through an external channel, so the execution environment becomes irrelevant

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 24-discord-visibility*
*Context gathered: 2026-03-29*
