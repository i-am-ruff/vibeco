# Requirements: vCompany

**Defined:** 2026-03-28
**Core Value:** Agents run autonomously without hanging, stay coordinated through contracts and status awareness, and produce integrated code — all operable from Discord.

## v2.1 Requirements

Requirements for v2.1 Behavioral Integration. Each maps to roadmap phases.

### Work Initiation

- [ ] **WORK-01**: After container starts and tmux launches Claude Code, the system sends a GSD command (`/gsd:discuss-phase N`) to the agent's tmux pane — agent begins working autonomously
- [ ] **WORK-02**: Container detects Claude Code readiness (prompt available) before sending the GSD command — no blind timing-based waits
- [ ] **WORK-03**: When an agent completes its current backlog item, PM assigns the next one from BacklogQueue and the agent starts it automatically

### PM Review Gates

- [ ] **GATE-01**: Agent stops after each GSD stage transition (discuss→plan, plan→execute, etc.) and posts to its Discord channel: `[agent-id] @PM, finished [stage], need your review` with key file attachments
- [ ] **GATE-02**: PM reads attached files, reviews against project context/memory, and responds with approve/modify/clarify in the agent's channel
- [ ] **GATE-03**: Multi-turn conversation: PM and agent discuss until PM is satisfied — agent only advances when PM approves
- [ ] **GATE-04**: Agent reads PM's response, understands approve vs modify vs clarify, and acts accordingly (continue / fix / explain)
- [ ] **GATE-05**: Message throttling: maximum 1 message per 30 seconds per agent to keep Discord rate limits happy

### PM Event Routing

- [ ] **PMRT-01**: Agent health state changes (RUNNING→ERRORED, etc.) are routed to PM's event queue, not just Discord #alerts
- [ ] **PMRT-02**: GSD state transitions (DISCUSS→PLAN, PLAN→EXECUTE, etc.) are routed to PM's event queue
- [ ] **PMRT-03**: Briefings from ContinuousAgents are routed to PM's event queue
- [ ] **PMRT-04**: Escalations (agent BLOCKED) are routed to PM's event queue

### PM Actions

- [ ] **PMAC-01**: PM can trigger integration review through ProjectSupervisor
- [ ] **PMAC-02**: PM can inject milestones into BacklogQueue (insert_urgent, append)
- [ ] **PMAC-03**: PM can request agent recruitment/removal through ProjectSupervisor
- [ ] **PMAC-04**: PM can escalate decisions to Strategist
- [ ] **PMAC-05**: PM detects agents stuck in the same GSD state beyond a configurable threshold and intervenes via Discord message

### Container Architecture

- [ ] **ARCH-01**: Strategist operates through CompanyAgent container event handler — StrategistCog becomes a thin Discord adapter
- [ ] **ARCH-02**: Strategist is a direct child of CompanyRoot, peer to ProjectSupervisors — not under ProjectSupervisor
- [ ] **ARCH-03**: BLOCKED is a real FSM state (not a bool) — visible in health tree with reason
- [ ] **ARCH-04**: CommunicationPort is wired during container creation — agents use comm_port for structured messaging

### Health & Monitoring

- [ ] **HLTH-05**: Health tree shows CompanyRoot at top with its state, Strategist/CompanyAgents as children, then ProjectSupervisors with their agents
- [ ] **HLTH-06**: Health tree shows inner_state, uptime, and last_activity per agent matching the architecture doc's example format

### Agent Completeness

- [ ] **AGNT-01**: ContinuousAgent has a `request_task()` method that delegates work through supervisor via DelegationTracker
- [ ] **AGNT-02**: ContinuousAgent persists seen_items, pending_actions, briefing_log, config to memory_store (not just cycle_count)
- [ ] **AGNT-03**: GsdAgent restores full work context on restart — current phase, task, and assignment from ProjectStateManager, not just FSM state

### Lifecycle

- [ ] **LIFE-01**: STOPPING is a transitional FSM state before STOPPED — visible in health tree during graceful shutdown

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
| WORK-01 | Phase 12 | Pending |
| WORK-02 | Phase 12 | Pending |
| WORK-03 | Phase 15 | Pending |
| GATE-01 | Phase 14 | Pending |
| GATE-02 | Phase 14 | Pending |
| GATE-03 | Phase 14 | Pending |
| GATE-04 | Phase 14 | Pending |
| GATE-05 | Phase 14 | Pending |
| PMRT-01 | Phase 13 | Pending |
| PMRT-02 | Phase 13 | Pending |
| PMRT-03 | Phase 13 | Pending |
| PMRT-04 | Phase 13 | Pending |
| PMAC-01 | Phase 15 | Pending |
| PMAC-02 | Phase 15 | Pending |
| PMAC-03 | Phase 15 | Pending |
| PMAC-04 | Phase 15 | Pending |
| PMAC-05 | Phase 15 | Pending |
| ARCH-01 | Phase 16 | Pending |
| ARCH-02 | Phase 11 | Pending |
| ARCH-03 | Phase 11 | Pending |
| ARCH-04 | Phase 11 | Pending |
| HLTH-05 | Phase 17 | Pending |
| HLTH-06 | Phase 17 | Pending |
| AGNT-01 | Phase 16 | Pending |
| AGNT-02 | Phase 16 | Pending |
| AGNT-03 | Phase 16 | Pending |
| LIFE-01 | Phase 11 | Pending |

**Coverage:**
- v2.1 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0

---
*Requirements defined: 2026-03-28*
