# vCompany — Autonomous Multi-Agent Development System

## What This Is

vCompany is a project-agnostic orchestration system that coordinates multiple parallel Claude Code/GSD agents to build software products autonomously. A human owner provides strategic direction via Discord. A Claude-powered PM/Strategist bot handles product decisions. A Python CLI (`vco`) and Discord bot handle dispatch, monitoring, integration, and recovery. Give it a product blueprint and a milestone scope — it builds.

Every agent runs inside an Erlang-style supervision tree with lifecycle state machines, real tmux session bridging, self-reported health, and priority-queued Discord communication.

## Core Value

Agents run autonomously without hanging on terminal input, stay coordinated through contracts and status awareness, and produce integrated code that merges cleanly — all operable from Discord.

## Current Milestone: v4.0 Distributed Agent Runtime

**Goal:** Agent containers run inside transports as autonomous processes. Split vco into vco-head (orchestration) and vco-worker (container runtime). All communication through transport channel. Dead code from daemon-side container architecture ripped out.

**Target features:**
- vco-worker package — lightweight runtime (report/ask/send-file/signal), runs inside Docker/native/network
- vco-head — daemon stripped to orchestration + transport handles only, no agent Python objects
- Transport channel protocol — replaces Unix socket mounts, bidirectional head↔worker messaging
- Container bootstrapping — head sends config blob through transport, worker self-configures and starts agent
- Agent state inside container — conversations, checkpoints, memory all behind transport boundary
- Docker containers run vco-worker only — no socket mount, no daemon filesystem access
- Rip out daemon-side container objects, handler injection from factory, StrategistConversation managed from daemon side, all v3.1 shims
- Network transport stub — TCP/WebSocket interface ready for remote agents

## Current State

**v4.0 in progress (2026-03-31).** Phase 29 complete — transport channel protocol with typed Pydantic v2 message models and NDJSON framing. v3.1 complete — transport abstraction, Docker runtime, agent-types config, handler extraction done.

## Previously Shipped

**v3.1 Container Runtime Abstraction (2026-03-31):** Transport abstraction (AgentTransport protocol, LocalTransport, DockerTransport), Docker runtime (Dockerfile, auto-build, parametric setup), agent-types.yaml config system, handler extraction (SessionHandler, ConversationHandler, TransientHandler), communication abstraction (all agent comms through daemon socket), MentionRouterCog unified routing, StrategistCog removed — 5 phases, 15 plans, 44 requirements
**v3.0 CLI-First Architecture Rewrite (2026-03-29):** Runtime daemon, Unix socket API (NDJSON), CommunicationPort abstraction, RuntimeAPI gateway (600+ lines), CompanyRoot extraction, 6 CLI commands, bot cogs as pure I/O adapters, Strategist CLI autonomy — 6 phases, 15 plans, 36 requirements
**v2.1 Behavioral Integration (2026-03-28):** Work initiation, PM review gates, auto work distribution, PM event routing, stuck-agent detection, health tree rendering
**v2.0 Agent Container Architecture (2026-03-28):** 8-state lifecycle FSM, supervision tree, 4 agent types, health tree, resilience, PM autonomy
**v1.0 MVP (2026-03-27):** CLI orchestration, Discord bot, plan review, AI decision system, integration pipeline
**Stack:** Python 3.12, discord.py 2.7, anthropic SDK, libtmux, pydantic v2, click, uv

## Requirements

### Validated

<details>
<summary>v1.0 MVP (62 requirements) — shipped 2026-03-27</summary>

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
- Discord commands — slash commands for new-project, dispatch, kill, relaunch, standup, integrate — Phase 4
- Role-based access — Owner (vco-owner) + Viewer tiers — Phase 4
- Channel auto-setup — category per project with standard + per-agent channels — Phase 4
- Alert system — AlertsCog with buffer/flush, sync-to-async callback bridge to monitor — Phase 4
- AskUserQuestion hook — stdlib-only PreToolUse hook with webhook posting, file-based answer polling — Phase 5
- Plan gate — PlanReviewCog with approve/reject buttons, safety table validation — Phase 5
- Two-tier AI decision system — Strategist (Opus) + PM (heuristic confidence) — Phase 6
- PM tier — heuristic confidence scoring, three-check plan review, auto-approve on HIGH — Phase 6
- Strategist persistent conversation — AsyncAnthropic streaming, token tracking, Knowledge Transfer — Phase 6
- Integration pipeline — IntegrationPipeline with interlock model, N+1 test attribution, AI conflict resolution — Phase 7
- Standup/checkin rituals — blocking interlock with per-agent threads, Release button — Phase 7

</details>

- ✓ AgentContainer base — lifecycle state machine, health reporting, context management, communication — v2.0
- ✓ Supervision tree — CompanyRoot → ProjectSupervisor → agents, Erlang-style restart policies — v2.0
- ✓ GsdAgent type — phase-driven lifecycle with compound FSM, checkpoint crash recovery — v2.0
- ✓ ContinuousAgent type — scheduled wake/sleep cycles with persistent memory — v2.0
- ✓ FulltimeAgent type (PM) — event-driven, reacts to state transitions/health/escalations — v2.0
- ✓ CompanyAgent type (Strategist) — event-driven, alive for company duration, cross-project state — v2.0
- ✓ Health tree — self-reported HealthReport per container, tree rendering, Discord /health, state-change push — v2.0
- ✓ Living milestone backlog — PM-managed mutable queue with 8 async operations — v2.0
- ✓ Delegation protocol — continuous agents request task spawns through supervisor with caps/rate limits — v2.0
- ✓ Decoupled lifecycles — project state owned by PM, crash never corrupts project state — v2.0
- ✓ Scheduler — timer within CompanyRoot triggers WAKE on sleeping containers — v2.0
- ✓ Agent memory_store — async SQLite per-agent KV store, checkpoints at state transitions — v2.0
- ✓ Container tmux bridge — start/stop/liveness bridged to real tmux sessions — v2.0
- ✓ Priority message queue — rate-limit backoff, priority ordering for all notifications — v2.0
- ✓ Bulk failure detection — upstream outage suppression, global backoff — v2.0
- ✓ Degraded mode — auto-detection, gated dispatches, auto-recovery — v2.0
- ✓ Config-driven agent types — AgentConfig.type routes to correct container subclass — v2.0
- ✓ PM event dispatch — GsdAgent completion events routed to PM — v2.0
- ✓ v1 module removal — MonitorLoop, CrashTracker, WorkflowOrchestrator, AgentManager deleted — v2.0

- ✓ Runtime daemon with Unix socket API — v3.0
- ✓ CommunicationPort protocol + DiscordCommunicationPort adapter — v3.0
- ✓ CompanyRoot extracted to daemon with RuntimeAPI gateway — v3.0
- ✓ CLI commands as API clients (hire, give-task, dismiss, status, health, new-project) — v3.0
- ✓ `vco new-project` composite command using hire internally — v3.0
- ✓ Bot refactored to thin relay (slash commands → RuntimeAPI) — v3.0
- ✓ Strategist Bash-based autonomy (vco hire/give-task/dismiss) — v3.0

- ✓ All inter-agent communication surfaced through Discord (no hidden event routing) — v3.1
- ✓ AgentTransport protocol abstracting execution environment — v3.1
- ✓ Socket-based agent signaling (replaces sentinel temp files) — v3.1
- ✓ DockerTransport for isolated agent runtimes — v3.1

### Active

- [ ] vco-worker package — lightweight container-side runtime
- [ ] vco-head — daemon as pure orchestrator with transport handles only
- ✓ Transport channel protocol — typed Pydantic v2 message models, NDJSON framing, round-trip tested — v4.0 Phase 29
- [ ] Container bootstrapping via transport
- [ ] Agent state inside container (conversations, checkpoints, memory)
- [ ] Docker containers without socket mount
- [ ] Dead code removal (daemon-side containers, handler factory injection, shims)
- [ ] Network transport stub

### Out of Scope

- Any specific product implementation — vCompany is project-agnostic, products are inputs
- Mobile app or web UI for vCompany itself — Discord is the interface
- Full multi-machine production deployment — network transport is a stub/foundation in v4
- Clone disk space optimization — noted, not solving yet
- CI/CD pipeline integration — agents build and test locally

## Context

- Runs on local machine (Xubuntu 24.04 LTS)
- Python 3.12 for all tooling (vco CLI, Discord bot, hooks)
- Depends on: Claude Code, GSD (globally installed), Node.js 22 LTS, tmux, Git, GitHub CLI
- Discord server configured with bot, webhooks, channel structure
- v3.1 shipped: Phase 26 complete — DockerTransport, Dockerfile, transport abstraction, socket-based signaling, Discord visibility
- v3.0 shipped: daemon architecture, RuntimeAPI (600+ lines), 6 CLI commands, bot as thin relay, 17k LOC Python
- Known tech debt: test suite needs cleanup (asyncio patterns, Click 8.3 compat, missing Phase 23 verification)

## Constraints

- **Project-agnostic**: No hardcoded assumptions about what agents build — everything comes from blueprint + agents.yaml
- **Agent isolation**: Agents never share working directories, never write outside owned paths
- **CLI-first, Discord-second**: CLI is primary interface, Discord is a relay adapter
- **GSD compatibility**: Agents run standard GSD pipelines — vCompany orchestrates, not replaces, GSD
- **Transport-agnostic**: Agent containers work behind any transport (native, Docker, network)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python for all tooling | Ecosystem fit (discord.py, anthropic SDK, click) | ✓ Good |
| Discord as sole interface | Owner wants to dispatch and monitor from Discord, not terminal | ✓ Good |
| Erlang-style supervision tree | Self-supervising containers eliminate single-point-of-failure monitor | ✓ Good |
| In-place refactor for v2 | New modules alongside existing, reuse Discord bot/CLI/git/tmux, delete as replaced | ✓ Good |
| Agent type abstractions | GsdAgent, ContinuousAgent, FulltimeAgent, CompanyAgent — different lifecycles | ✓ Good |
| Async SQLite for agent memory | WAL mode, per-agent isolation, crash-safe checkpoints | ✓ Good |
| Priority message queue for notifications | Rate-limit backoff, escalation priority over health updates | ✓ Good |
| Real tmux bridge in containers | AgentContainer.start() creates actual tmux sessions, 30s liveness monitoring | ✓ Good |
| Config-driven agent types | AgentConfig.type field routes to factory — clean, extensible | ✓ Good |
| Daemon owns event loop | bot.start() as coroutine within daemon's asyncio.run() | ✓ Good |
| NDJSON over Unix socket | Simpler than JSON-RPC, debuggable with socat, zero new deps | ✓ Good |
| CommunicationPort as Protocol | typing.Protocol for structural subtyping, not ABC | ✓ Good |
| RuntimeAPI gateway pattern | Single typed class wrapping all CompanyRoot operations | ✓ Good |
| Bot as thin I/O adapter | Zero container/supervisor/agent imports in cog modules | ✓ Good |
| Strategist uses vco CLI | Bash tool runs vco commands instead of [CMD:] action tags | ✓ Good |

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
*Last updated: 2026-03-31 after Phase 29 completion*
