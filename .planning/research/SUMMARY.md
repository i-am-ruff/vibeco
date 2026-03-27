# Project Research Summary

**Project:** vCompany — Autonomous Multi-Agent Development System (v2.0 Container Architecture)
**Domain:** Supervision trees, agent container lifecycle, self-healing orchestration
**Researched:** 2026-03-27
**Confidence:** HIGH

## Executive Summary

vCompany v2.0 is a migration from a flat, externally-monitored agent model to a self-supervising container hierarchy modeled on Erlang/OTP supervision trees. The v1 system relies on three loosely-coupled externals — `MonitorLoop` (60s poll watchdog), `CrashTracker` (backoff/circuit breaker), and `WorkflowOrchestrator` (phase state machine) — that operate in parallel without a single authority. v2 replaces this with a tree where each agent is an `AgentContainer` (lifecycle state machine + self-reported health + persistent memory), supervisors own restart policy, and a two-level hierarchy (`CompanyRoot` -> `ProjectSupervisor` -> agents) scopes restart blast radius correctly. The pattern is well-understood from Erlang, Kubernetes, and systemd, and maps cleanly to Python asyncio. The entire container tree runs as asyncio Tasks inside the existing VcoBot process, keeping inter-container communication zero-cost and the system single-process.

The recommended approach adds only two new PyPI dependencies (`python-statemachine 3.0.x` for declarative state machines, `aiosqlite 0.21.x` for per-agent persistent memory) on top of the existing validated stack. All scheduling and event communication use stdlib asyncio primitives — no scheduler library, no event bus library. The existing modules (`MonitorLoop`, `CrashTracker`, `WorkflowOrchestrator`) are absorbed incrementally with a mandatory coexistence period before deletion, making this a safe in-place migration rather than a risky rewrite.

The primary risk is migration complexity: three existing state machines simultaneously tracking the same agent will diverge (split-brain), the 30-60 second Claude Code bootstrap time breaks Erlang's instant-process-creation assumption and will trigger false circuit-breakers, and the existing callback chain in `VcoBot.on_ready()` is wired directly between Cogs and services with no abstraction — inserting the supervision tree silently breaks these wires. The mitigation is strict sequencing: establish single state ownership in Phase 1, build supervision before integrating with the bot, and run ALL existing Phase 7 interaction regression tests after every migration step. The v1 MonitorLoop runs alongside v2 as a safety net until v2 supervision passes integration tests.

## Key Findings

### Recommended Stack

The existing stack requires only two additions for v2. `python-statemachine 3.0.0` (released Feb 2026, zero runtime dependencies, native async, SCXML compound states) replaces hand-rolled enums for the five distinct state machine types needed. `aiosqlite 0.21.x` wraps stdlib `sqlite3` for non-blocking async access to per-agent memory stores — each agent gets its own `.db` file in its clone directory, preserving v1's isolation model while gaining ACID guarantees for checkpoint writes. APScheduler and event bus libraries are explicitly rejected as overkill for single-machine interval-based wake and tree-shaped (not pub/sub) communication. Full rationale in [STACK.md](.planning/research/STACK.md).

**Core new technologies:**
- `python-statemachine 3.0.x`: Declarative state machines for all container types — covers compound states (GsdAgent's inner phase machine nested inside RUNNING), auto-detected async callbacks, validated transitions. Zero transitive dependencies.
- `aiosqlite 0.21.x`: Non-blocking async wrapper for per-agent SQLite memory stores. Schema is two tables (`memory`, `checkpoints`). One file per agent in the agent's clone directory. Not a shared database.
- `asyncio (stdlib)`: All scheduling (`asyncio.sleep` loops owned by CompanyRoot) and all event communication (tree-shaped `asyncio.Queue` + method calls, not pub/sub fan-out).

### Expected Features

The feature set follows a strict dependency chain documented in [FEATURES.md](.planning/research/FEATURES.md): nothing works without `AgentContainer` base, supervision tree requires containers to supervise, agent types require the base class, health reporting requires self-reporting containers.

**Must have (table stakes — Phases 1-2):**
- `AgentContainer` base with lifecycle state machine (CREATING -> RUNNING -> SLEEPING -> ERRORED -> STOPPED -> DESTROYED) — without this, no container architecture exists
- State transition validation — prevents impossible states, enables trustworthy supervision
- Context management per container — centralizes config currently scattered across dispatch, agents.yaml parsing, and clone commands
- Two-level supervision hierarchy (CompanyRoot -> ProjectSupervisor -> agents) — scopes restart blast radius so a crashed BACKEND agent does not restart the Strategist
- `one_for_one` restart strategy — covers 80% of agent crash scenarios
- Max restart intensity at supervisor level — circuit breaker to prevent crash loops, must use {3, 600} windows (10 min) not {3, 60} (Erlang default) due to slow Claude Code bootstrap
- `GsdAgent` type with internal phase FSM absorbing WorkflowOrchestrator — makes agent self-authoritative for phase state
- Self-reported `HealthReport` per container — replaces external 60s polling with instant state-change events

**Should have (differentiators — Phases 3-5):**
- `ContinuousAgent` with scheduled wake/sleep cycles — enables QA monitor as a first-class agent, not a hack on top of GsdAgent
- `FulltimeAgent` (PM) as event-driven container — PM becomes part of the supervision tree, not bolted to the Discord bot
- Health tree aggregation + Discord `!health` command — "docker ps" view of the full system
- Living milestone backlog (PM-managed mutable queue) — dynamic work ordering without stopping agents
- Delegation protocol (ContinuousAgent requests task spawns through supervisor) — self-healing beyond process restarts
- Decoupled project/agent lifecycles with cascade termination guarantees

**Defer to v3+:**
- Hot agent replacement (live reconfiguration without container destroy/recreate)
- Graceful degradation hardening (explicit test suite; implicit in design)
- Agent performance metrics and historical query dashboards
- Dynamic auto-scaling (anti-feature on single machine with API cost constraints)
- Agent-to-agent direct messaging (anti-feature: hidden coupling, breaks debug/replay)
- Distributed supervision across multiple machines

### Architecture Approach

The v2 architecture inserts a supervision tree between `VcoBot` and the raw tmux/Claude Code layer. Containers are asyncio Tasks (not OS processes) inside the existing VcoBot process — no IPC, shared discord.py client reference, simple lifecycle via task cancel. Each container owns its tmux pane, self-reports health on every state transition, and checkpoints to a per-agent SQLite file. Supervisors manage children via `asyncio.Task` done callbacks, applying Erlang-style restart policies with 150-200 lines of asyncio code (no library needed). The `MonitorLoop` is demoted from health authority to thin HealthTree poller during migration, then removed after v2 passes regression tests. Full component map, data flow diagrams, and 8-phase build order in [ARCHITECTURE.md](.planning/research/ARCHITECTURE.md).

**Major components:**
1. `containers/base.py` (AgentContainer) — lifecycle state machine, health reporting, memory store, event inbox
2. `containers/gsd_agent.py` (GsdAgent) — absorbs WorkflowOrchestrator; phase FSM (IDLE->DISCUSS->PLAN->EXECUTE->VERIFY->SHIP) nested inside RUNNING
3. `containers/continuous_agent.py` (ContinuousAgent) — scheduled WAKE/GATHER/ANALYZE/ACT/REPORT/SLEEP cycles with persistent memory
4. `containers/fulltime_agent.py` (FulltimeAgent) — event-driven PM container; alive for project duration
5. `containers/company_agent.py` (CompanyAgent) — event-driven Strategist container; cross-project lifetime
6. `supervision/supervisor.py` (Supervisor) — asyncio.Task management, restart policies (one/all/rest_for_one), absorbed CrashTracker logic
7. `supervision/company_root.py` (CompanyRoot) — top-level supervisor; owns Scheduler + ProjectSupervisors + CompanyAgents
8. `supervision/project_supervisor.py` (ProjectSupervisor) — per-project supervisor; scopes restart blast radius
9. `health/tree.py` (HealthTree) — aggregates self-reported HealthReports; drives Discord `!health` embed
10. `coordination/backlog.py` (MilestoneBacklog) — PM-managed mutable work queue with Pydantic-validated mutations
11. `coordination/delegation.py` (DelegationProtocol) — mediated task spawn requests through supervisor with depth counter and caps

### Critical Pitfalls

Full analysis with phase-by-phase prevention strategies and a "looks done but isn't" checklist in [PITFALLS.md](.planning/research/PITFALLS.md). Top five for roadmap planning:

1. **Dual state tracking creates split-brain during migration** — Three existing systems (agents.json, AgentMonitorState, AgentWorkflowState) will conflict with the new container state machine if not explicitly resolved. Prevent by declaring `AgentContainer.state` as the single source of truth from the start of Phase 1 and building a `ContainerRegistry` adapter that translates old/new representations. Delete the old representations only after all consumers are migrated.

2. **Supervisor cascade from slow Claude Code bootstrap** — Erlang assumes process creation takes microseconds. vCompany agent restart takes 30-60 seconds. Standard Erlang restart intensity limits ({3, 60}) will trigger false circuit-breakers after one crash. Use {3, 600} windows (10 minutes), track intensity at restart *completion* not initiation, and add a `RESTARTING` state visible in health reports.

3. **Broken callback wiring when supervision tree inserts between VcoBot and Cogs** — AlertsCog, PlanReviewCog, and WorkflowOrchestratorCog are wired via direct function references from MonitorLoop. Inserting the supervision tree silently breaks these chains. Prevent by running ALL existing Phase 7 interaction regression tests after every migration step. Zero regressions allowed.

4. **Triple state machine confusion** — Three machines tracking the same agent phase (outer container RUNNING/ERRORED, inner GsdAgent DISCUSS/PLAN/EXECUTE, separate WorkflowOrchestrator tracking) will diverge. Prevent by absorbing WorkflowOrchestrator state tracking INTO GsdAgent during Phase 2. Expose `lifecycle_state` vs `work_state` as orthogonal dimensions, not competing authorities.

5. **ContinuousAgent scheduled wakes lost on bot restart** — `asyncio.sleep()` is not persistent; asyncio tasks cancel on event loop shutdown. Prevent by persisting scheduled wake times to a JSON file, and using a `discord.ext.tasks.loop(seconds=60)` that checks the schedule file rather than long per-agent sleeps.

## Implications for Roadmap

Based on the dependency chain from FEATURES.md and the 8-phase build order from ARCHITECTURE.md, the suggested phase structure is:

### Phase 1: Container Foundation
**Rationale:** The single most critical phase. Everything else depends on this, and state ownership must be resolved here or split-brain (Pitfall 1) corrupts every subsequent phase. Zero v1 dependencies — pure new code with no integration risk. Tests are pure unit tests.
**Delivers:** `AgentContainer` base class, `ContainerState` enum, `ContainerEvent` types, `AgentMemoryStore` (SQLite per-agent, WAL mode), `HealthReport` Pydantic model, `ContainerRegistry` adapter declaring container state as the single source of truth.
**Addresses:** AgentContainer base abstraction, state transition validation, context management, memory_store (FEATURES.md table stakes Phase 1)
**Avoids:** Split-brain state (Pitfall 1) — establishes single truth source before anything else touches agent state

### Phase 2: Supervisor Foundation + GsdAgent
**Rationale:** Supervisors need containers to supervise (Phase 1 dependency). GsdAgent is the highest-priority agent type and the riskiest absorption target (WorkflowOrchestrator). Combining supervisor foundation with GsdAgent means restart policy can be immediately tested against a real agent type. `python-statemachine 3.0.x` compound states make the nested FSM (outer RUNNING contains inner DISCUSS/PLAN/EXECUTE) clean.
**Delivers:** `Supervisor` base with `one_for_one`, `all_for_one`, `rest_for_one` strategies and absorbed CrashTracker backoff/circuit breaker logic, `GsdAgent` with nested phase FSM, checkpoint-based crash recovery from `memory_store`, supervisor-level circuit breaker with {3, 600} restart intensity windows.
**Uses:** `python-statemachine 3.0.x` for compound state machines
**Avoids:** Triple state machine confusion (Pitfall 5), cascade restart from slow bootstrap (Pitfall 2 — configure intensity windows in the supervisor base, not per agent type)

### Phase 3: Remaining Agent Types + Health Tree
**Rationale:** With containers and supervisor running, health reporting can be wired end-to-end. Remaining agent types (FulltimeAgent PM, ContinuousAgent, CompanyAgent Strategist) are independent of each other and lower integration risk than GsdAgent. Scheduler and health tree can be built and tested in isolation.
**Delivers:** `HealthTree` aggregation with staggered-interval collection, Discord `!health` embed with color-coded status, `FulltimeAgent` (PM as container), `ContinuousAgent` (scheduled cycles with persistent schedule file), `CompanyAgent` (Strategist as container), `Scheduler` in CompanyRoot using ext.tasks loop pattern.
**Avoids:** Thundering herd health aggregation (Pitfall 3 — stagger report intervals with jitter, debounce Discord pushes to 30s batches), lost scheduled wakes on bot restart (Pitfall 8 — persist schedule to disk, use ext.tasks loop not bare asyncio.sleep)

### Phase 4: CompanyRoot + ProjectSupervisor Integration
**Rationale:** The highest integration-risk phase — modifies `VcoBot.on_ready()` entry point and requires v1/v2 coexistence. Comes after all container types are working and health tree is proven. The v1 MonitorLoop must continue running as safety net during this phase.
**Delivers:** `CompanyRoot` (top-level supervisor), `ProjectSupervisor` (per-project), modified `VcoBot.on_ready()` creating CompanyRoot instead of flat component wiring. MonitorLoop demoted to HealthTree poller (safety net, no longer health authority). CLI dispatch commands route through CompanyRoot.
**Avoids:** Broken callback wiring (Pitfall 4 — run ALL Phase 7 interaction regression tests before this phase lands; keep MonitorLoop safety net running)

### Phase 5: Autonomy Features (Delegation + Living Backlog)
**Rationale:** Highest-value differentiators but require the full supervision hierarchy and all agent types to be operational. Delegation without supervisor mediation would create uncontrolled spawning. Cap enforcement and depth counters must be in the protocol from the start.
**Delivers:** `DelegationProtocol` (ContinuousAgent -> Supervisor -> spawn GsdAgent, with max_concurrent_agents cap from agents.yaml, depth counter rejecting depth >= 2), `MilestoneBacklog` (PM-managed with Pydantic-validated mutations, backlog diffs posted to #decisions), decoupled project/agent lifecycles with cascade termination (ProjectSupervisor.destroy() cascades to tmux panes, not just Python objects).
**Avoids:** Unbounded agent spawning (Pitfall 6 — hard cap enforced at supervisor, PM-approval for cap+1 spawns), orphaned agents on teardown (Pitfall 7 — cascade destroy verified with `tmux list-panes` check in tests)

### Phase 6: Event Bus + Callback Migration
**Rationale:** Formalizes the event communication pattern that v1 callback chains need. The direct-reference callback pattern is already strained after Phase 4 integration; this phase replaces it cleanly. PROJECT-STATUS.md derivation from HealthTree eliminates status drift.
**Delivers:** `ContainerEvent` typed event bus replacing MonitorLoop callbacks. AlertsCog, PlanReviewCog, WorkflowOrchestratorCog converted to event subscribers. PROJECT-STATUS.md derived from HealthTree (single source, multiple renderers — Discord embed, markdown file, CLI table).
**Avoids:** Broken callback wiring (Pitfall 4, full resolution), triple state machine (Pitfall 5, full elimination of regex-based signal detection in WorkflowOrchestrator)

### Phase 7: Discord UX Polish
**Rationale:** All backend behavior is working by this phase. UX refinements are low-risk, high-visibility, and can be developed incrementally. Alert deduplication and three-tier delegation approval are needed before calling v2 "complete" from a usability standpoint.
**Delivers:** Color-coded health embeds (green/yellow/red, collapsible per supervisor), single-alert-with-message-edits pattern for restart lifecycle events, three-tier delegation approval (auto-approve up to cap / PM-approve for cap+1 to cap+3 / owner-approve beyond), backlog diff notifications to #decisions.
**Avoids:** Health tree Discord dump as unreadable raw text (UX pitfall), alert flooding from supervision events (UX pitfall)

### Phase 8: Migration Cleanup
**Rationale:** Delete v1 modules fully absorbed by v2, only after all integration tests pass for v2 equivalents. Low risk if previous phases have coverage; high risk without it.
**Delivers:** Deletion of `orchestrator/workflow_orchestrator.py` (absorbed by GsdAgent), `orchestrator/crash_tracker.py` (absorbed by Supervisor), removal or simplification of `monitor/loop.py`. Full regression suite passing with zero v1 fallbacks active.

### Phase Ordering Rationale

- The FEATURES.md dependency chain dictates Phases 1-3: AgentContainer base first, supervisor + GsdAgent together (each is useless without the other), then specialized agent types.
- Phase 4 (VcoBot integration) is deliberately placed after all container types are proven, maximizing coexistence time with v1. The safety net (MonitorLoop) should not be removed until v2 has survived real crashes.
- Phases 5-7 are autonomy and polish — they require the full tree to be working but add no foundational dependencies on each other.
- Phase 8 (cleanup) is always last. Deleting v1 before v2 is proven is the primary risk in any in-place migration.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (GsdAgent + Supervisor):** WorkflowOrchestrator absorption is the highest-risk module boundary. Before implementation, map every state transition and callback in `orchestrator/workflow_orchestrator.py` to its GsdAgent equivalent. Walk the codebase to identify all consumers of WorkflowOrchestrator state.
- **Phase 4 (CompanyRoot + Bot Integration):** `VcoBot.on_ready()` callback wiring is complex. Before implementation, audit every callback registered in `on_ready()` and trace its consumers. Missing one callback causes silent failures with no error in logs.
- **Phase 5 (Delegation + Backlog):** The PM confidence scoring thresholds for auto-approve vs PM-approve vs owner-approve are not specified in existing code. Needs design work before implementation.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Container Foundation):** Pure new code, no integration. asyncio.Queue patterns and per-agent SQLite are well-understood patterns with no ambiguity.
- **Phase 3 (Health Tree):** Additive feature. HealthReport as Pydantic model + Rich terminal rendering + discord.py embed is standard and well-documented.
- **Phase 7 (Discord UX):** discord.py embed patterns are established. UX decisions are product design, not technical research.
- **Phase 8 (Cleanup):** Deletion is straightforward given integration tests. No research needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | python-statemachine 3.0.0 verified (released Feb 2026, zero deps). aiosqlite 0.21.0 MEDIUM confidence on exact version (from training data — verify at implementation). All other additions are stdlib. Existing stack unchanged. |
| Features | HIGH | Dependency graph is complete and grounded in existing codebase analysis. Four-phase MVP roadmap maps directly to the dependency chain. Anti-features are correctly identified with specific rationale. |
| Architecture | HIGH | Component map is specific (named files, named classes, named methods). Build order grounded in dependency chains. Patterns are direct translations of Erlang/OTP to asyncio with concrete code examples. |
| Pitfalls | HIGH | Pitfalls reference specific existing class/method names from the v1 codebase (not generic). Prevention strategies are concrete, phased, and include a "looks done but isn't" verification checklist. |

**Overall confidence:** HIGH

### Gaps to Address

- **Restart intensity defaults per agent type:** PITFALLS.md correctly identifies that GsdAgent (30-60s restart) and CompanyAgent (fast restart) need different `max_restart_intensity` configurations. Exact defaults not specified. Validate during Phase 2 planning by measuring actual Claude Code bootstrap time in the target environment.
- **PM confidence scoring thresholds for delegation approval:** The three-tier approval system is conceptually specified but threshold values (what is "high confidence" for an auto-approve?) need design during Phase 5 planning.
- **Scheduler persistence format and location:** PITFALLS.md recommends a JSON file for scheduled wake persistence but does not specify the schema or location (alongside agents.yaml? inside each agent's clone dir?). Decide during Phase 3 planning.
- **aiosqlite current version:** STACK.md rates aiosqlite 0.21.0 as MEDIUM confidence (from training data). Verify with `pip index versions aiosqlite` at implementation time.

## Sources

### Primary (HIGH confidence)
- [python-statemachine PyPI](https://pypi.org/project/python-statemachine/) — version 3.0.0, zero deps, async support, StateChart compound states
- [python-statemachine docs](https://python-statemachine.readthedocs.io/) — async auto-detection, compound states, SCXML compliance
- [python-statemachine GitHub](https://github.com/fgmacedo/python-statemachine) — 3.0 release Feb 2026 confirmed
- [Erlang OTP Design Principles](https://www.erlang.org/doc/system/design_principles.html) — supervision tree restart strategies, one_for_one/all_for_one/rest_for_one
- [Learn You Some Erlang: Supervisors](https://learnyousomeerlang.com/supervisors) — restart intensity, escalation patterns, anti-patterns
- [Elixir Supervisor documentation](https://hexdocs.pm/elixir/1.12/Supervisor.html) — strategy definitions and max_restarts semantics
- [Kubernetes Health Probe patterns](https://www.oreilly.com/library/view/kubernetes-patterns-2nd/9781098131678/ch04.html) — self-reported liveness/readiness probes
- Existing vCompany codebase — `bot/client.py`, `orchestrator/`, `monitor/`, `models/` (authoritative v1 baseline, HIGH confidence)
- `VCO-ARCHITECTURE.md` — v1 design reference (HIGH confidence)
- `.planning/PROJECT.md` — v2 milestone requirements (HIGH confidence)
- Python asyncio stdlib — Task management, Queue, create_task patterns (HIGH confidence)

### Secondary (MEDIUM confidence)
- [Adopting Erlang: Supervision Trees](https://adoptingerlang.org/docs/development/supervision_trees/) — practical restart strategy guidance
- [AI Agent Delegation Patterns](https://fast.io/resources/ai-agent-delegation-patterns/) — supervisor-worker delegation architectures
- [Scheduling Agent Supervisor Pattern](https://www.geeksforgeeks.org/system-design/scheduling-agent-supervisor-pattern-system-design/) — scheduler + agent + supervisor coordination
- [aiosqlite PyPI](https://pypi.org/project/aiosqlite/) — version 0.21.0 (training data; verify at implementation)
- [httpx vs aiohttp comparison](https://www.speakeasy.com/blog/python-http-clients-requests-vs-httpx-vs-aiohttp) — dual sync/async capability

### Tertiary (LOW confidence)
- [bubus GitHub](https://github.com/browser-use/bubus) — reviewed and rejected as event bus option
- [mode GitHub](https://github.com/ask/mode) — reviewed and rejected as supervision library (241 stars, unclear maintenance)

---
*Research completed: 2026-03-27*
*Ready for roadmap: yes*
