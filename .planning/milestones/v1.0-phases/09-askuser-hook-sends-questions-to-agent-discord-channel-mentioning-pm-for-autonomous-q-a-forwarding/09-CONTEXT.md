# Phase 9: AskUser Hook → Agent Discord Channel + PM Mention - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Reroute the AskUserQuestion hook to post agent questions to `#agent-{id}` channels (instead of #strategist), implement a Discord message routing framework with reply-based and @mention-based interaction rules, enable PM auto-answering via Discord replies, and replace file-based IPC with Discord-only answer delivery. The hook polls Discord API for replies instead of polling local answer files.

</domain>

<decisions>
## Implementation Decisions

### Question Routing
- **D-01:** All AskUserQuestion questions post to `#agent-{id}` channel (the agent's own channel). No questions go to #strategist directly.
- **D-02:** Hook uses `DISCORD_BOT_TOKEN` + `DISCORD_GUILD_ID` to resolve the `#agent-{id}` channel by name, then posts directly via Discord REST API. Aligns with VO1 direct-posting pattern.
- **D-03:** Escalation stays in `#agent-{id}`. Owner gets @mentioned there. No cross-posting to #strategist.

### Discord Message Routing Framework
- **D-04:** All inter-component communication happens through Discord messages. Discord is the universal communication bus, not just UI.
- **D-05:** Each entity has a visible identity prefix when speaking: `[PM]`, `[agent-frontend]`, `[agent-backend]`, etc. The Strategist is the exception — speaks naturally with no prefix.
- **D-06:** Message routing rules (strict):
  - **Reply-based:** Only the entity whose message is being replied to processes the reply. If PM replies to a Strategist message, only Strategist processes it. The reply target determines who responds, not the sender.
  - **@mention-based:** If a message starts with `@entity`, that entity processes it.
  - **Channel-owner default:** In `#agent-{id}`, unaddressed owner messages (no reply, no @mention) go to the channel-owning agent.
  - **#strategist default:** In #strategist, unaddressed owner messages go to the Strategist.
- **D-07:** Strategist ignores messages that aren't: (a) replies to its own messages, (b) owner talking in #strategist without reply/mention, or (c) @mentions directed at it.
- **D-08:** This is a full routing framework, not Q&A-specific. All Cogs use it. Phase 9 builds it, Phase 10+ reuses it.

### PM Auto-Answer Flow (AskUserQuestion)
- **D-09:** Flow: Hook posts question as `[agent-x]` in `#agent-x` → PM monitors for question embeds, evaluates → Only the final answering entity **replies** to the original question message.
- **D-10:** PM escalation uses Pattern B (non-reply mentions): PM posts a separate non-reply message with @Strategist mention. Strategist escalation to Owner is also a non-reply @Owner mention. Only the resolver replies to the original question. This keeps the hook's answer detection simple: first reply = the answer.
- **D-11:** PM replies as `[PM]` with the answer directly in Discord. No file writes. Discord IS the IPC layer.

### Discord-Only IPC (Replaces File-Based)
- **D-12:** Hook posts question to Discord API, gets message ID back. Then polls Discord API for replies to that message. First reply to the question message IS the answer.
- **D-13:** No more `/tmp/vco-answers/{request-id}.json` file-based polling. Discord messages are the single source of truth for Q&A.
- **D-14:** Hook remains a blocking PreToolUse hook — intercept → post question → poll for reply → return answer → Claude continues.

### Hook Rewrite
- **D-15:** In-place rewrite of `tools/ask_discord.py`. Same file path keeps settings.json.j2 unchanged. Agents don't need reconfiguration.
- **D-16:** Env vars change: `DISCORD_AGENT_WEBHOOK_URL` replaced by `DISCORD_BOT_TOKEN` + `DISCORD_GUILD_ID` + `VCO_AGENT_ID` (already set by dispatch).

### Timeout Policy
- **D-17:** PM auto-answers: 10-minute timeout with continue/block mode from config (unchanged from Phase 5 D-06).
- **D-18:** Owner escalations: wait indefinitely, matching Phase 6 D-07 pattern. If PM and Strategist both can't answer, the agent blocks until the owner responds.

### Visibility & Audit Trail
- **D-19:** #decisions channel logs escalated decisions only (PM→Strategist or PM→Owner). Routine PM auto-answers stay in agent channels only.
- **D-20:** Agent channel IS the audit trail for routine Q&A. Owner can browse any `#agent-{id}` to see full history.

### Claude's Discretion
- Bot-side Cog architecture for question detection and PM routing (rework QuestionHandlerCog vs absorb into PM tier)
- Hook dependency approach (stdlib-only vs httpx — leaning stdlib to preserve self-contained design)
- Visual treatment of questions in agent channels (embeds vs plain text with prefix system)
- Poll interval and backoff strategy for Discord API reply polling
- How the routing framework is structured as a module (dispatcher class, middleware pattern, etc.)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Hook Implementation
- `tools/ask_discord.py` — Current hook to be rewritten in-place
- `src/vcompany/templates/settings.json.j2` — Hook path configuration (unchanged)

### Bot / Cog Architecture
- `src/vcompany/bot/cogs/question_handler.py` — Current QuestionHandlerCog (to be reworked or replaced)
- `src/vcompany/bot/cogs/strategist.py` — StrategistCog with persistent conversation and escalation handling
- `src/vcompany/bot/cogs/commands.py` — CommandsCog for reference on Cog patterns
- `src/vcompany/bot/client.py` — VcoBot with Cog loading and callback injection
- `src/vcompany/bot/channel_setup.py` — Channel creation and lookup patterns

### PM / Strategist
- `src/vcompany/strategist/pm.py` — PM tier with confidence scoring
- `src/vcompany/strategist/conversation.py` — Claude CLI conversation manager

### Agent Dispatch (env var setup)
- `src/vcompany/orchestrator/agent_manager.py` — Sets env vars during dispatch (DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, VCO_AGENT_ID)

### Prior Phase Context
- `.planning/phases/05-hooks-and-plan-gate/05-CONTEXT.md` — Original hook design (D-01 through D-06), timeout policy
- `.planning/phases/06-pm-strategist-and-milestones/06-CONTEXT.md` — PM/Strategist escalation chain (D-05 through D-07), confidence scoring
- `.planning/phases/04-discord-bot-core/04-CONTEXT.md` — Channel structure (D-16/D-17), Cog architecture (D-12)

### Quick Task Reference
- `.planning/quick/260326-vo1-direct-discord-reporting-monitor-advisor/260326-vo1-PLAN.md` — VO1 direct Discord posting pattern (bot token + guild ID approach)

### Requirements
- `.planning/REQUIREMENTS.md` §Hooks and Plan Gate — HOOK-01 through HOOK-07

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **ask_discord.py** (`tools/ask_discord.py`): Full hook structure with stdin parsing, fallback handling, timeout policy — rewrite internals, keep structure
- **QuestionHandlerCog** (`src/vcompany/bot/cogs/question_handler.py`): Webhook listener, PM intercept, button views — rework for new channel-based flow
- **PM tier** (`src/vcompany/strategist/pm.py`): Confidence scoring, evaluate_question — reuse for auto-answer evaluation
- **StrategistCog** (`src/vcompany/bot/cogs/strategist.py`): handle_pm_escalation, post_owner_escalation — adapt for new reply-based pattern
- **channel_setup.py** (`src/vcompany/bot/channel_setup.py`): Channel lookup by name — reuse for hook's channel resolution
- **report_cmd.py** (`src/vcompany/cli/report_cmd.py`): Direct Discord posting pattern from VO1 — reference for hook's API calls

### Established Patterns
- **Direct Discord API posting**: VO1 established bot token + guild ID approach (replaces webhooks)
- **Entity prefixes**: VO1 introduced `[system]` prefix — extend to `[PM]`, `[agent-x]`, etc.
- **asyncio.to_thread()**: All blocking operations wrapped for async safety
- **Atomic file writes**: write_atomic pattern — no longer needed for answer delivery but still used elsewhere

### Integration Points
- **Hook → Discord API**: Hook posts to #agent-{id} channel via REST API, polls for replies
- **QuestionHandlerCog → PM tier**: Detects question embeds in agent channels, triggers PM evaluation
- **PM → Discord**: PM posts answer as reply (auto-answer) or posts non-reply @mention (escalation)
- **Strategist/Owner → Discord**: Final resolver replies to original question message
- **Message routing framework**: New module that all Cogs use for reply-based and @mention-based dispatch

</code_context>

<specifics>
## Specific Ideas

- Discord is the universal communication bus — not just UI, but the IPC layer between all components
- Entity identity is explicit: every component has a prefix (`[PM]`, `[agent-x]`) except Strategist who speaks naturally
- The "only the resolver replies" pattern (Pattern B) keeps answer detection trivial for the hook: first reply = the answer
- The interaction rules (reply-target processes, @mention processes, channel-owner default) are a general framework, not Q&A-specific — designed for reuse across all bot interactions
- The message routing framework should enforce that entities don't process messages they shouldn't (e.g., Strategist ignores other agents' messages unless explicitly addressed)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-askuser-hook-sends-questions-to-agent-discord-channel-mentioning-pm-for-autonomous-q-a-forwarding*
*Context gathered: 2026-03-27*
