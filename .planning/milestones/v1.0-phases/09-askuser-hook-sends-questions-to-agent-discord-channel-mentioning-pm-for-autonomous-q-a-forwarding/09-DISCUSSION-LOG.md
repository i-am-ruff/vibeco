# Phase 9: AskUser Hook → Agent Discord Channel + PM Mention - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 09-askuser-hook-sends-questions-to-agent-discord-channel-mentioning-pm-for-autonomous-q-a-forwarding
**Areas discussed:** Question routing, PM mention & auto-answer, Hook rewrite scope, Visibility & audit trail

---

## Question Routing

### Where should agent questions land initially?

| Option | Description | Selected |
|--------|-------------|----------|
| Always #agent-{id} | Every AskUserQuestion posts to the agent's own channel. PM picks it up from there. Escalations to Strategist/Owner get cross-posted or threaded in #strategist. | ✓ |
| Split by confidence | PM evaluates first (before posting to Discord). HIGH confidence questions answered silently. MEDIUM/LOW questions posted to #agent-{id}. | |
| Always #strategist | Keep current routing. Phase 9 only adds PM @mention. | |

**User's choice:** Always #agent-{id}
**Notes:** None

### When PM escalates to Strategist or Owner, how should that appear?

| Option | Description | Selected |
|--------|-------------|----------|
| Cross-post to #strategist | Escalated question appears in both #agent-{id} and #strategist. | |
| Thread in #agent-{id} | Escalation stays in the agent channel. Owner gets @mentioned there. No cross-posting. | ✓ |
| Move to #strategist | Original stays in agent channel, active discussion moves to #strategist. | |

**User's choice:** Thread in #agent-{id}
**Notes:** None

### Should the hook resolve the agent's channel ID, or post to a generic endpoint?

| Option | Description | Selected |
|--------|-------------|----------|
| Hook resolves channel | Hook uses DISCORD_BOT_TOKEN + DISCORD_GUILD_ID to look up #agent-{id} channel by name, then posts directly. | ✓ |
| Bot-side routing | Hook posts to a single endpoint. Bot re-routes to the correct channel. | |
| Env var per agent | Dispatch sets DISCORD_AGENT_CHANNEL_ID per agent. Hook posts directly to that channel ID. | |

**User's choice:** Hook resolves channel
**Notes:** None

---

## PM Mention & Auto-Answer

### How should the PM be notified to evaluate a new question?

| Option | Description | Selected |
|--------|-------------|----------|
| Bot-internal event | QuestionHandlerCog listens for messages in all #agent-{id} channels. | |
| @PM role mention in message | Hook includes @mention for vco-pm role. | |
| Both: internal + visible mention | Bot triggers PM internally AND visible @PM mention. | |

**User's choice:** Other (free text)
**Notes:** All communication goes through Discord. Each system component gets a visible identity prefix. Introduced explicit interaction rules: reply-based routing (only the entity whose message is replied to processes it), @mention-based routing, and channel-owner defaults. Strategist ignores messages not addressed to it.

### Escalation pattern: PM replies with escalation, or non-reply mention?

| Option | Description | Selected |
|--------|-------------|----------|
| Pattern A: PM replies with escalation | PM replies to question with @Strategist in the reply. Messy — hook sees non-answer reply. | |
| Pattern B: Non-reply mention | PM posts separate non-reply message with @mention. Only final resolver replies to the original question. | ✓ |

**User's choice:** Pattern B — non-reply mentions for escalation
**Notes:** First reply to the question message IS the answer. Simple and unambiguous.

### How should auto-answered questions appear?

| Option | Description | Selected |
|--------|-------------|----------|
| PM replies with answer | PM replies to the agent's question with the answer. | |
| PM replies + reaction | Same plus a checkmark reaction. | |
| Silent + log only | PM answers silently, only logged to #decisions. | |

**User's choice:** Other (free text)
**Notes:** NO file writes. PM answers directly in Discord as a reply. This is what gets sent as an answer to the hook. Discord IS the IPC layer.

### Discord-only IPC confirmation

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, Discord-only IPC | Hook posts to Discord, polls for reply messages. No filesystem intermediary. | ✓ |
| Adjust | Different mechanism. | |

**User's choice:** Yes, Discord-only IPC
**Notes:** Hook polls Discord API for replies to its posted message.

### Hook dependency approach (stdlib vs httpx)

**User's choice:** "Decide yourself"
**Notes:** Claude's discretion — leaning stdlib-only to preserve self-contained design.

---

## Hook Rewrite Scope

### In-place rewrite or fresh replacement?

| Option | Description | Selected |
|--------|-------------|----------|
| In-place rewrite | Same file (tools/ask_discord.py), rewritten internals. | ✓ |
| New file, deprecate old | New ask_discord_v2.py, update templates. | |
| Refactor into modules | Split into entry point + discord_client module. | |

**User's choice:** In-place rewrite
**Notes:** None

### Bot-side Cog changes

| Option | Description | Selected |
|--------|-------------|----------|
| Rework QuestionHandlerCog | Repurpose to monitor #agent-{id} channels. | |
| Replace with PM routing | Absorbed into PM tier logic. | |
| You decide | Claude decides. | ✓ |

**User's choice:** You decide
**Notes:** Claude's discretion on Cog architecture.

### Routing framework scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full routing framework | General message dispatcher for all Cogs. Reply detection, @mention parsing, channel-owner defaults. | ✓ |
| Q&A routing only | Hardcode just enough for AskUserQuestion flow. | |
| Framework + Q&A as first consumer | Build reusable module, wire Q&A as first consumer. | |

**User's choice:** Full routing framework
**Notes:** None

---

## Visibility & Audit Trail

### Should PM auto-answers be logged to #decisions?

| Option | Description | Selected |
|--------|-------------|----------|
| Agent channel is enough | Visible Q&A in #agent-{id} is the audit trail. | |
| Log everything to #decisions | Every PM auto-answer also posted to #decisions. | |
| Log escalations only | #decisions gets entries only for PM→Strategist or PM→Owner escalations. | ✓ |

**User's choice:** Log escalations only
**Notes:** None

### Visual treatment of questions in agent channels

| Option | Description | Selected |
|--------|-------------|----------|
| Rich embed for questions | Discord embeds with color coding. | |
| Plain text with prefix | Consistent with prefix system. | |
| You decide | Claude decides. | ✓ |

**User's choice:** You decide
**Notes:** Claude's discretion.

### Timeout policy changes

| Option | Description | Selected |
|--------|-------------|----------|
| Keep same timeout policy | 10min timeout, continue/block mode. | |
| Longer timeout | 30min for owner escalations. | |
| No timeout for escalations | PM auto-answers: 10min. Owner escalations: wait indefinitely. | ✓ |

**User's choice:** No timeout for escalations
**Notes:** Matches Phase 6 D-07 pattern.

---

## Claude's Discretion

- Bot-side Cog architecture for question detection and PM routing
- Hook dependency approach (stdlib vs httpx)
- Visual treatment of questions in agent channels

## Deferred Ideas

None — discussion stayed within phase scope
