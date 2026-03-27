# Requirements: vCompany

**Defined:** 2026-03-27
**Core Value:** Agents run autonomously without hanging, stay coordinated through contracts and status awareness, and produce integrated code — all operable from Discord.

## v2 Requirements

Requirements for v2.0 Agent Container Architecture. Each maps to roadmap phases.

### Container Foundation

- [ ] **CONT-01**: Every agent is wrapped in an AgentContainer with a validated lifecycle state machine (CREATING→RUNNING→SLEEPING→ERRORED→STOPPED→DESTROYED)
- [ ] **CONT-02**: State transitions are validated — impossible transitions (e.g., STOPPED→RUNNING) are rejected with errors
- [ ] **CONT-03**: Each container carries its own context (agent_id, type, parent_id, project_id, owned dirs, GSD mode, system prompt)
- [ ] **CONT-04**: Each agent has a persistent memory_store (per-agent SQLite file) for checkpoints, seen items, decisions, and config
- [ ] **CONT-05**: Child specification registry declares how to create each container (type, config, restart policy) — supervisors read specs to spawn children
- [ ] **CONT-06**: All container communication flows through Discord — no hidden file-based IPC, no in-memory callbacks between agents

### Supervision

- [ ] **SUPV-01**: Two-level supervision hierarchy: CompanyRoot → ProjectSupervisor → agent containers
- [ ] **SUPV-02**: `one_for_one` restart strategy — only restart the failed child (covers independent agents)
- [ ] **SUPV-03**: `all_for_one` restart strategy — restart all children when one fails (coupled agents)
- [ ] **SUPV-04**: `rest_for_one` restart strategy — restart failed child and all children started after it (ordered deps)
- [ ] **SUPV-05**: Max restart intensity at supervisor level with 10-minute windows (not 60s) to account for slow Claude Code bootstrap
- [ ] **SUPV-06**: When max restarts exceeded, supervisor escalates to parent (ProjectSupervisor → CompanyRoot → Owner alert)

### Agent Types

- [ ] **TYPE-01**: GsdAgent with internal phase FSM (IDLE→DISCUSS→PLAN→EXECUTE→UAT→SHIP) absorbing WorkflowOrchestrator
- [ ] **TYPE-02**: GsdAgent saves checkpoint to memory_store after each state transition — crash recovery resumes from last completed state
- [ ] **TYPE-03**: ContinuousAgent with scheduled wake/sleep cycles (WAKE→GATHER→ANALYZE→ACT→REPORT→SLEEP) and persistent memory_store
- [ ] **TYPE-04**: FulltimeAgent (PM) is event-driven — reacts to agent state transitions, health changes, escalations, briefings, milestone completion
- [ ] **TYPE-05**: CompanyAgent (Strategist) is event-driven, alive for company duration, holds cross-project state, survives project restarts

### Health Reporting

- [ ] **HLTH-01**: Each container self-reports a HealthReport (state, inner_state, uptime, last_heartbeat, error_count, last_activity)
- [ ] **HLTH-02**: Supervisors aggregate children's health into a tree — queryable at any level (company-wide, project, individual)
- [ ] **HLTH-03**: Discord slash command `/health` renders the full status tree with state indicators
- [ ] **HLTH-04**: State transitions (RUNNING→ERRORED, etc.) push notifications to Discord automatically

### Autonomy

- [ ] **AUTO-01**: Living milestone backlog — PM-managed mutable queue (append, insert_after, insert_urgent, reorder, cancel)
- [ ] **AUTO-02**: GSD state machine consumes milestones from the living queue, not a static list
- [ ] **AUTO-03**: Delegation protocol — ContinuousAgent requests task spawns through supervisor with hard caps and rate limits
- [ ] **AUTO-04**: Supervisor validates delegation requests, enforces policy, spawns short-lived task agents
- [ ] **AUTO-05**: Project state owned by PM — agents read assignments and write completions. Agent crash never corrupts project state
- [ ] **AUTO-06**: Scheduler in CompanyRoot triggers WAKE on sleeping ContinuousAgents per their configured schedule

### Integration & Migration

- [ ] **MIGR-01**: CompanyRoot replaces flat VcoBot.on_ready() — supervision tree initializes all containers
- [ ] **MIGR-02**: All Discord commands converted to slash commands (no more `!` prefix)
- [ ] **MIGR-03**: v1 modules fully removed after v2 passes regression tests (MonitorLoop, CrashTracker, WorkflowOrchestrator, AgentManager)
- [ ] **MIGR-04**: Communication layer designed with clean interface that Discord implements — preparing for v3 channel abstraction

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
| CONT-01 | — | Pending |
| CONT-02 | — | Pending |
| CONT-03 | — | Pending |
| CONT-04 | — | Pending |
| CONT-05 | — | Pending |
| CONT-06 | — | Pending |
| SUPV-01 | — | Pending |
| SUPV-02 | — | Pending |
| SUPV-03 | — | Pending |
| SUPV-04 | — | Pending |
| SUPV-05 | — | Pending |
| SUPV-06 | — | Pending |
| TYPE-01 | — | Pending |
| TYPE-02 | — | Pending |
| TYPE-03 | — | Pending |
| TYPE-04 | — | Pending |
| TYPE-05 | — | Pending |
| HLTH-01 | — | Pending |
| HLTH-02 | — | Pending |
| HLTH-03 | — | Pending |
| HLTH-04 | — | Pending |
| AUTO-01 | — | Pending |
| AUTO-02 | — | Pending |
| AUTO-03 | — | Pending |
| AUTO-04 | — | Pending |
| AUTO-05 | — | Pending |
| AUTO-06 | — | Pending |
| MIGR-01 | — | Pending |
| MIGR-02 | — | Pending |
| MIGR-03 | — | Pending |
| MIGR-04 | — | Pending |

**Coverage:**
- v2 requirements: 31 total
- Mapped to phases: 0
- Unmapped: 31 ⚠️

---
*Requirements defined: 2026-03-27*
*Last updated: 2026-03-27 after initial definition*
