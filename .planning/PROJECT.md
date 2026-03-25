# vCompany — Autonomous Multi-Agent Development System

## What This Is

vCompany is a project-agnostic orchestration system that coordinates multiple parallel Claude Code/GSD agents to build software products autonomously. A human owner provides strategic direction via Discord. A Claude-powered PM/Strategist bot handles product decisions. A Python CLI (`vco`) and Discord bot handle dispatch, monitoring, integration, and recovery. Give it a product blueprint and a milestone scope — it builds.

## Core Value

Agents run autonomously without hanging on terminal input, stay coordinated through contracts and status awareness, and produce integrated code that merges cleanly — all operable from Discord.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] vco CLI with init, clone, dispatch, monitor, integrate, standup, status, kill, relaunch, sync-context commands
- [ ] Agent isolation model — each agent gets its own repo clone with non-overlapping directory ownership
- [ ] GSD configuration injection per agent clone (yolo mode, assumptions discuss, agent system prompt)
- [ ] AskUserQuestion hook (ask_discord.py) — intercepts agent questions, routes through Discord, returns answers with 10-min timeout/fallback
- [ ] Plan gate — monitor detects new PLAN.md files, pauses agent, posts to #plan-review, waits for PM approval before execution proceeds
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
*Last updated: 2026-03-25 after initialization*
