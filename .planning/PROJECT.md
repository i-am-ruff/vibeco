# vCompany — Autonomous Multi-Agent Development System

## What This Is

vCompany is a project-agnostic orchestration system that coordinates multiple parallel Claude Code/GSD agents to build software products autonomously. A human owner provides strategic direction via Discord. A Claude-powered PM/Strategist bot handles product decisions. A Python CLI (`vco`) and Discord bot handle dispatch, monitoring, integration, and recovery. Give it a product blueprint and a milestone scope — it builds.

## Core Value

Agents run autonomously without hanging on terminal input, stay coordinated through contracts and status awareness, and produce integrated code that merges cleanly — all operable from Discord.

## Requirements

### Validated

- agents.yaml configuration — Pydantic-validated agent roster with overlap detection — Phase 1
- vco init + clone — project scaffolding and per-agent clone deployment with all artifacts — Phase 1
- Agent isolation model — each agent gets its own repo clone with non-overlapping directory ownership — Phase 1
- GSD configuration injection per agent clone (yolo mode, system prompt, hook config) — Phase 1
- vco dispatch/kill/relaunch — agent lifecycle management with crash recovery — Phase 2
- Crash recovery — classification, exponential backoff, circuit breaker with callback hook — Phase 2
- Pre-flight test suite — validates Claude Code headless behavior, determines monitor strategy — Phase 2
- Monitor loop — 60s async cycle with liveness, stuck detection, plan gate, status generation — Phase 3
- PROJECT-STATUS.md — auto-generated cross-agent status, distributed to all clones every cycle — Phase 3
- INTERFACES.md contract system — change request logging, sync-context distribution — Phase 3
- INTERACTIONS.md — 8 documented concurrent interaction patterns with safety analysis — Phase 3
- Discord bot with Cog architecture — VcoBot client, 4 Cogs loaded, auto-reconnect — Phase 4
- Discord commands — !new-project, !dispatch, !status, !kill, !relaunch, !standup, !integrate — Phase 4
- Role-based access — Owner (vco-owner) + Viewer tiers with is_owner decorator — Phase 4
- Channel auto-setup — category per project with standard + per-agent channels — Phase 4
- Alert system — AlertsCog with buffer/flush, sync-to-async callback bridge to monitor — Phase 4
- AskUserQuestion hook (ask_discord.py) — stdlib-only PreToolUse hook with webhook posting, file-based answer polling, configurable timeout (block/continue) — Phase 5
- Plan gate — PlanReviewCog with approve/reject buttons, safety table validation, plan gate state tracking, execution triggering — Phase 5
- Interaction safety tables — validator enforces 6-column markdown tables in PLAN.md, configurable strictness (warn/block) — Phase 5
- QuestionHandlerCog — answer delivery via atomic file write to /tmp/vco-answers/, webhook question detection — Phase 5
- Two-tier AI decision system — persistent Strategist (Opus 1M, CEO-friend) + stateless PM (heuristic confidence) — Phase 6
- PM tier — heuristic confidence scoring (context coverage + prior decisions), three-check plan review (scope/dependency/duplicate), auto-approve on HIGH — Phase 6
- Strategist persistent conversation — AsyncAnthropic streaming, token tracking, Knowledge Transfer handoff at ~800K tokens, asyncio.Lock — Phase 6
- Three-tier escalation chain — PM → Strategist → Owner with indefinite wait for LOW confidence — Phase 6
- Decision logging — all PM/Strategist decisions to #decisions channel + append-only JSONL — Phase 6
- vco new-milestone — milestone infrastructure (scope update, agent reset, re-dispatch) — Phase 6
- PM-CONTEXT.md — renamed from STRATEGIST-PROMPT.md, assembled from blueprint+interfaces+scope+status+decisions — Phase 6
- Integration pipeline — IntegrationPipeline with interlock model, N+1 test attribution, AI conflict resolution via PM, auto PR creation — Phase 7
- Fix dispatch — auto-dispatch /gsd:quick to responsible agent on test failure — Phase 7
- Checkin ritual — auto-post phase completion status to #agent-{id} after each phase — Phase 7
- Standup ritual — blocking interlock with per-agent threads, Release button, full owner control, no timeout — Phase 7
- Interaction regression tests — 9 tests from INTERACTIONS.md patterns, @pytest.mark.integration — Phase 7

### Active

- [ ] vco CLI with init, clone, dispatch, monitor, integrate, standup, status, kill, relaunch, sync-context commands
- [ ] Agent isolation model — each agent gets its own repo clone with non-overlapping directory ownership
- [ ] GSD configuration injection per agent clone (yolo mode, assumptions discuss, agent system prompt)
- [ ] PM/Strategist Discord bot — answers agent questions from project context, reviews plans against milestone scope, escalates low-confidence decisions to owner
- [ ] Strategist confidence scoring (high/medium/low) with automatic @Owner escalation
- [ ] PROJECT-STATUS.md auto-generation — monitor reads all clones' state, assembles cross-agent status, distributes to all clones
- [ ] INTERFACES.md contract system — single source of truth for agent boundaries, with change request flow (agent asks → PM approves → orchestrator distributes)
- [ ] /vco:checkin command deployed to agent clones — fire-and-forget status post after each phase ships
- [ ] /vco:standup command deployed to agent clones — interactive group standup with threaded owner feedback
- [ ] Discord bot commands: !new-project, !dispatch, !status, !standup, !kill, !relaunch, !integrate
- [ ] Role-based access control for Discord commands
- [ ] Integration pipeline — merge all agent branches, run tests, identify failures, dispatch fixes
- [ ] Crash recovery — auto-relaunch with /gsd:resume-work, max 3/hour, alert + stop on 4th crash
- [ ] Strategist context management — summarization strategy for large projects approaching context limits
- [ ] agents.yaml configuration — agent roster, owned directories, shared_readonly, gsd_mode, system prompts
- [ ] Per-agent Discord channels (#agent-{id}) for checkin logs
- [ ] Channel structure: #strategist, #plan-review, #standup, #agent-{id}, #alerts, #decisions
- [ ] Monitor loop (60s cycle): liveness check, stuck detection (30+ min no commits), plan gate trigger, status regeneration
- [ ] tmux session management — one pane per agent plus monitor pane

### Out of Scope

- Any specific product implementation — vCompany is project-agnostic, products are inputs
- Mobile app or web UI for vCompany itself — Discord is the interface
- Multi-machine distributed agents — runs on a single local machine
- Discord rate limit queuing — noted as known issue, address when it bites
- Clone disk space optimization — noted, not solving in v1
- CI/CD pipeline integration — agents build and test locally, no cloud CI in v1

## Context

- Runs on local machine (Xubuntu 24.04 LTS or similar Linux)
- Python 3.11+ for all tooling (vco CLI, Discord bot, hooks)
- Depends on: Claude Code, GSD (globally installed), Node.js 22 LTS, tmux, Git, GitHub CLI
- Discord server exists (empty) — needs bot creation, webhook setup, channel structure
- Discord.py for bot, Anthropic SDK for strategist, click for CLI, pyyaml for config
- Owner has a real product to test with but system must remain project-agnostic
- Architecture doc (VCO-ARCHITECTURE.md) is the authoritative design reference

## Constraints

- **Project-agnostic**: No hardcoded assumptions about what agents build — everything comes from blueprint + agents.yaml
- **Agent isolation**: Agents never share working directories, never write outside owned paths
- **Discord-first**: All human interaction happens through Discord, not terminal
- **GSD compatibility**: Agents run standard GSD pipelines — vCompany orchestrates, not replaces, GSD
- **Single machine**: All agents, monitor, and bot run on one machine for v1

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python for all tooling | Ecosystem fit (discord.py, anthropic SDK, click) | — Pending |
| Discord as sole interface | Owner wants to dispatch and monitor from Discord, not terminal | — Pending |
| Role-based access on Discord commands | Multi-user support from the start | — Pending |
| Crash recovery: alert + stop at 4th crash | Prevents infinite crash loops consuming resources | — Pending |
| Strategist context summarization | Large projects will exceed context limits without management | — Pending |
| AskUserQuestion hook returns deny + reason | Prevents terminal hang, carries answer back to Claude | — Pending |
| Plan gate is filesystem-level, not hook | Monitor detects PLAN.md, pauses externally, more reliable than in-session gating | — Pending |
| Interaction Safety Tables required per phase | Multi-agent systems have emergent timing/concurrency bugs — systematic analysis at design time catches what testing misses | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-25 after Phase 4 completion*
