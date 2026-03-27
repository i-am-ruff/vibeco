# Phase 4: Discord Bot Core - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 04-discord-bot-core
**Areas discussed:** Command UX, Role mapping, Bot architecture, Channel setup
**Mode:** Interactive

---

## Command UX — !new-project

| Option | Description | Selected |
|--------|-------------|----------|
| Attach files | User uploads agents.yaml + blueprint + interfaces | |
| Git repo URL | !new-project repo-url branch | |
| Both options | Support both | |
| Conversation (user-proposed) | !new-project starts a thread, owner describes product, PM synthesizes docs | ✓ |

**User's choice:** Conversation-based. "I don't like that we need to provide everything ourselves. The orchestrator, in cooperation with PM, should discuss it with me and plan the project mainly themselves."
**Notes:** Phase 4 scaffolds the thread/channel infrastructure. Phase 6 PM adds the conversation intelligence.

## Command UX — Confirmations

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, confirm | Reaction buttons for !kill, !integrate | ✓ |
| No, instant | Execute immediately | |
| Only !integrate | Confirm merges only | |

**User's choice:** Yes, confirm all destructive commands.

---

## Role Mapping

| Option | Description | Selected |
|--------|-------------|----------|
| Two tiers | Owner (all) + Viewer (read-only) | ✓ |
| Three tiers | Owner + Operator + Viewer | |
| Custom | User-defined | |

**User's choice:** Two tiers — simple Owner + Viewer.

---

## Bot Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Direct import | Bot imports vcompany library, same process | ✓ |
| Subprocess | Bot calls vco CLI via subprocess | |
| Hybrid | Direct for reads, subprocess for mutations | |

**User's choice:** "You decide which one is the cleanest architecturally." → Direct import selected (same process, type safety, asyncio composition).

---

## Channel Setup

| Option | Description | Selected |
|--------|-------------|----------|
| Category per project | Discord category 'vco-{project}' with channels inside | ✓ |
| Flat channels | All at server root with prefix | |
| Single project | No prefix, add later | |

**User's choice:** Category per project.

---

## Claude's Discretion

- Embed formatting for !status
- Error message wording
- !help command
- Alert message formatting
- Alert buffer during disconnect

## Deferred Ideas

None
