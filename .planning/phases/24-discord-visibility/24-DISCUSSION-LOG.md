# Phase 24: Discord Visibility - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 24-discord-visibility
**Areas discussed:** Event-to-Discord mapping, PM event replacement, Backlog mutation visibility, RuntimeAPI cleanup

---

## Event-to-Discord Mapping

### Event Format

| Option | Description | Selected |
|--------|-------------|----------|
| Structured embeds | Events as Discord embeds with typed fields. Machine-readable + human-readable. | |
| Plain messages | Events as human-readable text. Agents parse conventions. | ✓ |
| Hybrid | Embeds for machine events, plain for human-facing. | |

**User's choice:** Plain messages
**Notes:** None

### Event Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Before (pre-commit) | Discord message before internal state changes | |
| After (notification) | Action first, Discord after | |
| Configurable per event type | Some pre, some post | |

**User's choice:** Not important — Claude's discretion
**Notes:** User said "Not sure what it changes. Not important"

### Channel Routing

| Option | Description | Selected |
|--------|-------------|----------|
| Agent channels | Events in channel most relevant to agent involved | ✓ |
| Single events channel | One #events channel for everything | |
| You decide | Claude picks per event type | |

**User's choice:** Agent channels
**Notes:** None

---

## PM Event Replacement

### Agent Listening Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Discord subscription | PM subscribes to relevant Discord channels via CommunicationPort | |
| Bot forwards to PM | Bot routes relevant messages to PM | |
| PM polls channels | PM periodically checks channels | |

**User's choice:** Custom — @mention-based routing (see below)
**Notes:** User provided detailed vision: All agents subscribe to their handle (@Strategist, @PMProjectX, @SomeResearcher). @mentioning routes the message with context (who, where, ability to reply). Replies to agent messages also route back. Human owner can reply to any agent's message. Not hardcoded for any agent type.

### Routing Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Bot routes @mentions | Single bot watches messages, delivers @mentions to agents via CommunicationPort | ✓ |
| Webhook per agent | Each agent has a Discord webhook identity | |
| Separate bot users | Each agent runs own Discord bot token | |

**User's choice:** Bot routes @mentions
**Notes:** None

### Reply Context Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Immediate parent + context | Reply text plus original message being replied to | ✓ |
| Full chain | Entire reply chain up to original | |
| You decide | Claude picks | |

**User's choice:** Immediate parent + context
**Notes:** None

### Strategist Too?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, both | PM and Strategist both lose special post_event() paths | ✓ |
| PM only for now | Tackle Strategist separately | |

**User's choice:** Yes, both
**Notes:** None

---

## Backlog Mutation Visibility

### Channel

| Option | Description | Selected |
|--------|-------------|----------|
| PM's channel | Mutations in PM's channel | |
| Dedicated #backlog | Separate channel for backlog operations | ✓ |
| You decide | Claude picks | |

**User's choice:** Dedicated #backlog
**Notes:** None

### Who Posts

| Option | Description | Selected |
|--------|-------------|----------|
| PM posts its own actions | PM sends message before mutating | |
| System posts on PM behalf | BacklogQueue emits event, system formats | |
| You decide | Claude picks | ✓ |

**User's choice:** You decide
**Notes:** None

---

## RuntimeAPI Cleanup

### Migration Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Clean sweep | Remove all post_event() paths in one pass | ✓ |
| Incremental redirect | One method at a time | |
| You decide | Claude picks | |

**User's choice:** Clean sweep
**Notes:** None

### RuntimeAPI Role After Cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| Keep infra, remove routing | Keep lifecycle/project/workflow ops, remove agent-specific routing | ✓ |
| Minimal — just CLI gateway | Only socket API handler | |
| You decide | Claude determines boundary | |

**User's choice:** Keep infra, remove routing
**Notes:** User asked about checkin/standup/run_integration/verify_agent_execution status. Investigation showed all are implemented and called from slash commands (infra ops that stay). signal_workflow_stage is dead code. log_plan_decision reaches into strategist internals.

### Dead Code / Internal Wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Remove both | Delete signal_workflow_stage (dead), replace log_plan_decision with Discord message | ✓ |
| Keep log_plan_decision | Refactor but keep concept | |
| You decide | Claude determines | |

**User's choice:** Remove both
**Notes:** None

---

## Claude's Discretion

- Event timing (pre-commit vs post-commit) per event type
- Whether PM or system posts backlog mutation messages
- Message formatting conventions
- CommunicationPort delivery mechanism for @mention routing

## Deferred Ideas

None — discussion stayed within phase scope
