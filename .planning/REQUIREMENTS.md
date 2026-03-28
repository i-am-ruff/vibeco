# Requirements: vCompany

**Defined:** 2026-03-28
**Core Value:** Agents run autonomously without hanging, stay coordinated through contracts and status awareness, and produce integrated code — all operable from Discord.

## v2.1 Requirements

Requirements for v2.1 Behavioral Integration. Each maps to roadmap phases.

### Work Initiation

- [x] **WORK-01**: After container starts and tmux launches Claude Code, the system sends a GSD command (`/gsd:discuss-phase N`) to the agent's tmux pane — agent begins working autonomously
- [x] **WORK-02**: Container detects Claude Code readiness (prompt available) before sending the GSD command — no blind timing-based waits
- [x] **WORK-03**: When an agent completes its current backlog item, PM assigns the next one from BacklogQueue and the agent starts it automatically

### PM Review Gates

- [x] **GATE-01**: Agent stops after each GSD stage transition (discuss→plan, plan→execute, etc.) and posts to its Discord channel: `[agent-id] @PM, finished [stage], need your review` with key file attachments
- [x] **GATE-02**: PM reads attached files, reviews against project context/memory, and responds with approve/modify/clarify in the agent's channel
- [x] **GATE-03**: Multi-turn conversation: PM and agent discuss until PM is satisfied — agent only advances when PM approves
- [x] **GATE-04**: Agent reads PM's response, understands approve vs modify vs clarify, and acts accordingly (continue / fix / explain)
- [x] **GATE-05**: Message throttling: maximum 1 message per 30 seconds per agent to keep Discord rate limits happy

### PM Event Routing

- [x] **PMRT-01**: Agent health state changes (RUNNING→ERRORED, etc.) are routed to PM's event queue, not just Discord #alerts
- [x] **PMRT-02**: GSD state transitions (DISCUSS→PLAN, PLAN→EXECUTE, etc.) are routed to PM's event queue
- [x] **PMRT-03**: Briefings from ContinuousAgents are routed to PM's event queue
- [x] **PMRT-04**: Escalations (agent BLOCKED) are routed to PM's event queue

### PM Actions

- [x] **PMAC-01**: PM can trigger integration review through ProjectSupervisor
- [x] **PMAC-02**: PM can inject milestones into BacklogQueue (insert_urgent, append)
- [x] **PMAC-03**: PM can request agent recruitment/removal through ProjectSupervisor
- [x] **PMAC-04**: PM can escalate decisions to Strategist
- [x] **PMAC-05**: PM detects agents stuck in the same GSD state beyond a configurable threshold and intervenes via Discord message

### Container Architecture

- [ ] **ARCH-01**: Strategist operates through CompanyAgent container event handler — StrategistCog becomes a thin Discord adapter
- [x] **ARCH-02**: Strategist is a direct child of CompanyRoot, peer to ProjectSupervisors — not under ProjectSupervisor
- [x] **ARCH-03**: BLOCKED is a real FSM state (not a bool) — visible in health tree with reason
- [x] **ARCH-04**: CommunicationPort is wired during container creation — agents use comm_port for structured messaging

### Health & Monitoring

- [ ] **HLTH-05**: Health tree shows CompanyRoot at top with its state, Strategist/CompanyAgents as children, then ProjectSupervisors with their agents
- [ ] **HLTH-06**: Health tree shows inner_state, uptime, and last_activity per agent matching the architecture doc's example format

### Agent Completeness

- [x] **AGNT-01**: ContinuousAgent has a `request_task()` method that delegates work through supervisor via DelegationTracker
- [x] **AGNT-02**: ContinuousAgent persists seen_items, pending_actions, briefing_log, config to memory_store (not just cycle_count)
- [x] **AGNT-03**: GsdAgent restores full work context on restart — current phase, task, and assignment from ProjectStateManager, not just FSM state

### Lifecycle

- [x] **LIFE-01**: STOPPING is a transitional FSM state before STOPPED — visible in health tree during graceful shutdown

## Future Requirements

### v3 — Strategist as Mastermind
- Strategist decides when to create projects, which agents to use, when to dispatch
- No server commands except health/global config — Strategist operates everything
- Abstract interaction channels (Slack, Teamspeak)

### v4 — Decentralized Agents
- Agents can run on separate machines
- Supervision tree works across network boundaries

## Out of Scope

| Feature | Reason |
|---------|--------|
| Strategist decision-making logic (what to decide) | v3 scope — v2.1 wires the container, v3 fills the brain |
| ContinuousAgent external source gathering (GATHER implementation) | v3 scope — v2.1 wires delegation, v3 adds real sources |
| Multi-project support (multiple ProjectSupervisors) | v3 scope |
| Cross-project resource reallocation | v3 scope |
| New infrastructure or libraries | v2.1 is pure wiring of existing v2.0 code |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| WORK-01 | Phase 12 | Complete |
| WORK-02 | Phase 12 | Complete |
| WORK-03 | Phase 15 | Complete |
| GATE-01 | Phase 14 | Complete |
| GATE-02 | Phase 14 | Complete |
| GATE-03 | Phase 14 | Complete |
| GATE-04 | Phase 14 | Complete |
| GATE-05 | Phase 14 | Complete |
| PMRT-01 | Phase 13 | Complete |
| PMRT-02 | Phase 13 | Complete |
| PMRT-03 | Phase 13 | Complete |
| PMRT-04 | Phase 13 | Complete |
| PMAC-01 | Phase 15 | Complete |
| PMAC-02 | Phase 15 | Complete |
| PMAC-03 | Phase 15 | Complete |
| PMAC-04 | Phase 15 | Complete |
| PMAC-05 | Phase 15 | Complete |
| ARCH-01 | Phase 16 | Pending |
| ARCH-02 | Phase 11 | Complete |
| ARCH-03 | Phase 11 | Complete |
| ARCH-04 | Phase 11 | Complete |
| HLTH-05 | Phase 17 | Pending |
| HLTH-06 | Phase 17 | Pending |
| AGNT-01 | Phase 16 | Complete |
| AGNT-02 | Phase 16 | Complete |
| AGNT-03 | Phase 16 | Complete |
| LIFE-01 | Phase 11 | Complete |

**Coverage:**
- v2.1 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0

---
*Requirements defined: 2026-03-28*
