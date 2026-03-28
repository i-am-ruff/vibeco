# Requirements: vCompany

**Defined:** 2026-03-27
**Core Value:** Agents run autonomously without hanging, stay coordinated through contracts and status awareness, and produce integrated code -- all operable from Discord.

## v2 Requirements

Requirements for v2.0 Agent Container Architecture. Each maps to roadmap phases.

### Container Foundation

- [x] **CONT-01**: Every agent is wrapped in an AgentContainer with a validated lifecycle state machine (CREATING→RUNNING→SLEEPING→ERRORED→STOPPED→DESTROYED)
- [x] **CONT-02**: State transitions are validated — impossible transitions (e.g., STOPPED→RUNNING) are rejected with errors
- [x] **CONT-03**: Each container carries its own context (agent_id, type, parent_id, project_id, owned dirs, GSD mode, system prompt)
- [x] **CONT-04**: Each agent has a persistent memory_store (per-agent SQLite file) for checkpoints, seen items, decisions, and config
- [x] **CONT-05**: Child specification registry declares how to create each container (type, config, restart policy) — supervisors read specs to spawn children
- [x] **CONT-06**: All container communication flows through Discord — no hidden file-based IPC, no in-memory callbacks between agents

### Supervision

- [x] **SUPV-01**: Two-level supervision hierarchy: CompanyRoot → ProjectSupervisor → agent containers
- [x] **SUPV-02**: `one_for_one` restart strategy — only restart the failed child (covers independent agents)
- [x] **SUPV-03**: `all_for_one` restart strategy — restart all children when one fails (coupled agents)
- [x] **SUPV-04**: `rest_for_one` restart strategy — restart failed child and all children started after it (ordered deps)
- [x] **SUPV-05**: Max restart intensity at supervisor level with 10-minute windows (not 60s) to account for slow Claude Code bootstrap
- [x] **SUPV-06**: When max restarts exceeded, supervisor escalates to parent (ProjectSupervisor → CompanyRoot → Owner alert)

### Agent Types

- [x] **TYPE-01**: GsdAgent with internal phase FSM (IDLE→DISCUSS→PLAN→EXECUTE→UAT→SHIP) absorbing WorkflowOrchestrator
- [x] **TYPE-02**: GsdAgent saves checkpoint to memory_store after each state transition — crash recovery resumes from last completed state
- [x] **TYPE-03**: ContinuousAgent with scheduled wake/sleep cycles (WAKE→GATHER→ANALYZE→ACT→REPORT→SLEEP) and persistent memory_store
- [ ] **TYPE-04**: FulltimeAgent (PM) is event-driven — reacts to agent state transitions, health changes, escalations, briefings, milestone completion
- [ ] **TYPE-05**: CompanyAgent (Strategist) is event-driven, alive for company duration, holds cross-project state, survives project restarts

### Health Reporting

- [x] **HLTH-01**: Each container self-reports a HealthReport (state, inner_state, uptime, last_heartbeat, error_count, last_activity)
- [x] **HLTH-02**: Supervisors aggregate children's health into a tree — queryable at any level (company-wide, project, individual)
- [x] **HLTH-03**: Discord slash command `/health` renders the full status tree with state indicators
- [x] **HLTH-04**: State transitions (RUNNING→ERRORED, etc.) push notifications to Discord automatically

### Autonomy

- [x] **AUTO-01**: Living milestone backlog — PM-managed mutable queue (append, insert_after, insert_urgent, reorder, cancel)
- [x] **AUTO-02**: GSD state machine consumes milestones from the living queue, not a static list
- [x] **AUTO-03**: Delegation protocol — ContinuousAgent requests task spawns through supervisor with hard caps and rate limits
- [x] **AUTO-04**: Supervisor validates delegation requests, enforces policy, spawns short-lived task agents
- [ ] **AUTO-05**: Project state owned by PM — agents read assignments and write completions. Agent crash never corrupts project state
- [x] **AUTO-06**: Scheduler in CompanyRoot triggers WAKE on sleeping ContinuousAgents per their configured schedule

### Resilience

- [ ] **RESL-01**: Communication layer queues outbound Discord messages with rate-aware batching — health reports debounced, supervisor commands prioritized over status updates, exponential backoff on 429s
- [x] **RESL-02**: Supervisor distinguishes upstream outage (all children failing simultaneously within a short window) from individual agent failure — bulk failure triggers global backoff instead of per-agent restart loops
- [x] **RESL-03**: System enters degraded mode when Claude servers are unreachable — existing containers stay alive, no new dispatches, owner notified, automatic recovery when service returns

### Integration & Migration

- [x] **MIGR-01**: CompanyRoot replaces flat VcoBot.on_ready() — supervision tree initializes all containers
- [x] **MIGR-02**: All Discord commands converted to slash commands (no more `!` prefix)
- [x] **MIGR-03**: v1 modules fully removed after v2 passes regression tests (MonitorLoop, CrashTracker, WorkflowOrchestrator, AgentManager)
- [x] **MIGR-04**: Communication layer designed with clean interface that Discord implements — preparing for v3 channel abstraction

## v1 Requirements (Completed)

All 85 v1 requirements completed. See `.planning/milestones/v1.0-REQUIREMENTS.md` for full list.

## Future Requirements

### v3 — Abstract Interaction Channels

- **CHAN-01**: Interaction channel abstraction layer — Discord is one implementation
- **CHAN-02**: Pluggable channel backends (Slack, Teamspeak, etc.)
- **CHAN-03**: Agent communication works identically regardless of channel backend

### v4 — Decentralized Agents

- **DIST-01**: Agents can run on separate machines
- **DIST-02**: Agents are detachable and location-independent
- **DIST-03**: Supervision tree works across network boundaries

## Out of Scope

| Feature | Reason |
|---------|--------|
| Agent-to-agent direct messaging | Creates hidden coupling, breaks debug/replay — communicate through Discord and supervision tree |
| Dynamic agent auto-scaling | Single machine with API cost constraints — PM manages agent count explicitly |
| Real-time agent output streaming | Discord rate limits; checkins and standups are the right granularity |
| Web UI / dashboard | Discord is the interface for v2 |
| Multi-machine distributed agents | v4 scope — v2 is single-machine |
| Non-Discord interaction channels | v3 scope — v2 uses Discord exclusively |
| Generic plugin system for agent types | Four types cover all use cases; add new types as needed |
| Hot agent replacement | Useful but not critical for v2 — defer to v3+ |
| Centralized shared database | Per-agent SQLite files; no shared DB |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONT-01 | Phase 1 | Complete |
| CONT-02 | Phase 1 | Complete |
| CONT-03 | Phase 1 | Complete |
| CONT-04 | Phase 1 | Complete |
| CONT-05 | Phase 1 | Complete |
| CONT-06 | Phase 1 | Complete |
| HLTH-01 | Phase 1 | Complete |
| SUPV-01 | Phase 2 | Complete |
| SUPV-02 | Phase 2 | Complete |
| SUPV-03 | Phase 2 | Complete |
| SUPV-04 | Phase 2 | Complete |
| SUPV-05 | Phase 2 | Complete |
| SUPV-06 | Phase 2 | Complete |
| TYPE-01 | Phase 3 | Complete |
| TYPE-02 | Phase 3 | Complete |
| TYPE-03 | Phase 4 | Complete |
| TYPE-04 | Phase 9 | Pending |
| TYPE-05 | Phase 9 | Pending |
| AUTO-06 | Phase 4 | Complete |
| HLTH-02 | Phase 5 | Complete |
| HLTH-03 | Phase 5 | Complete |
| HLTH-04 | Phase 5 | Complete |
| RESL-01 | Phase 10 | Pending |
| RESL-02 | Phase 6 | Complete |
| RESL-03 | Phase 6 | Complete |
| AUTO-01 | Phase 7 | Complete |
| AUTO-02 | Phase 7 | Complete |
| AUTO-03 | Phase 7 | Complete |
| AUTO-04 | Phase 7 | Complete |
| AUTO-05 | Phase 9 | Pending |
| MIGR-01 | Phase 8 | Complete |
| MIGR-02 | Phase 8 | Complete |
| MIGR-03 | Phase 8 | Complete |
| MIGR-04 | Phase 8 | Complete |

**Coverage:**
- v2 requirements: 34 total
- Mapped to phases: 34
- Complete: 30
- Pending (gap closure): 4 (TYPE-04, TYPE-05, AUTO-05, RESL-01)
- Unmapped: 0

---
*Requirements defined: 2026-03-27*
*Last updated: 2026-03-27 after roadmap revision (8 phases)*
