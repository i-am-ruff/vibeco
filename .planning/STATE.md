---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Agent Container Architecture
status: Milestone complete
stopped_at: Completed 08.2-02-PLAN.md
last_updated: "2026-03-28T04:02:53.743Z"
progress:
  total_phases: 10
  completed_phases: 10
  total_plans: 26
  completed_plans: 26
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-27)

**Core value:** Agents run autonomously without hanging, stay coordinated through contracts and status awareness, and produce integrated code -- all operable from Discord.
**Current focus:** Phase 08.2 — deep-integration

## Current Position

Phase: 08.2
Plan: Not started

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 2min | 1 tasks | 10 files |
| Phase 01 P02 | 2min | 2 tasks | 5 files |
| Phase 01 P03 | 3min | 1 tasks | 3 files |
| Phase 02 P01 | 4min | 2 tasks | 7 files |
| Phase 02 P02 | 6min | 2 tasks | 5 files |
| Phase 03 P01 | 3min | 2 tasks | 4 files |
| Phase 03 P02 | 4min | 2 tasks | 3 files |
| Phase 04 P01 | 2min | 2 tasks | 3 files |
| Phase 04 P03 | 3min | 2 tasks | 7 files |
| Phase 04 P02 | 4min | 2 tasks | 6 files |
| Phase 04 P04 | 4min | 2 tasks | 4 files |
| Phase 05 P01 | 6min | 2 tasks | 4 files |
| Phase 05 P02 | 3min | 1 tasks | 3 files |
| Phase 06 P01 | 3min | 1 tasks | 3 files |
| Phase 06 P03 | 3min | 2 tasks | 4 files |
| Phase 06 P02 | 8min | 2 tasks | 4 files |
| Phase 07 P01 | 2min | 1 tasks | 3 files |
| Phase 07 P02 | 3min | 2 tasks | 4 files |
| Phase 07 P03 | 3min | 1 tasks | 4 files |
| Phase 08 P01 | 3min | 2 tasks | 4 files |
| Phase 08 P02 | 10min | 2 tasks | 6 files |
| Phase 08 P03 | 46min | 2 tasks | 25 files |
| Phase 08.1 P01 | 2min | 2 tasks | 2 files |
| Phase 08.1 P02 | 2min | 2 tasks | 2 files |
| Phase 08.2 P01 | 6min | 2 tasks | 10 files |
| Phase 08.2 P02 | 4min | 2 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap v2 rev2]: 8 phases (up from 5) for better risk isolation
- [Roadmap v2 rev2]: Supervision tree separated from GsdAgent -- supervision is pure new code, GsdAgent absorbs WorkflowOrchestrator (different risk profiles)
- [Roadmap v2 rev2]: Agent types separated from health tree -- 3 agent types + scheduler in Phase 4, health aggregation in Phase 5
- [Roadmap v2 rev2]: New resilience phase (Phase 6) for RESL-01/02/03 -- rate limiting, outage detection, degraded mode
- [Roadmap v2 rev2]: HLTH-01 (self-reporting) stays in Phase 1 with container base; HLTH-02/03/04 in Phase 5
- [Roadmap v2 rev2]: MIGR-* all in Phase 8 (last) -- v1 MonitorLoop stays as safety net until v2 passes regression tests
- [Phase 01]: Used current_state_value instead of deprecated current_state.id for python-statemachine 3.0.0
- [Phase 01]: CommunicationPort uses typing.Protocol with @runtime_checkable, Message is a dataclass
- [Phase 01]: MemoryStore uses assert for db open guard instead of custom exception
- [Phase 01]: ChildSpecRegistry is plain class (not Pydantic) - dict-based with no validation overhead
- [Phase 01]: Used state_field=_fsm_state to avoid property collision with python-statemachine model binding
- [Phase 02]: Supervisor is standalone class (not AgentContainer subclass) -- simpler, avoids unneeded memory store/FSM
- [Phase 02]: Restart intensity tracked per-supervisor (not per-child) following Erlang OTP semantics
- [Phase 02]: Event-driven monitoring via asyncio.Event + on_state_change callback (no polling)
- [Phase 02]: _restarting flag prevents cascade during all_for_one/rest_for_one supervisor-initiated stops
- [Phase 02]: CompanyRoot manages ProjectSupervisors dynamically via add/remove rather than static child_specs
- [Phase 02]: Override handle_child_escalation in CompanyRoot for dynamic project topology
- [Phase 03]: GsdLifecycle is standalone StateMachine (not subclass of ContainerLifecycle) -- compound states require fresh class definition
- [Phase 03]: HistoryState used for both sleep/wake and error/recover to preserve inner phase
- [Phase 03]: OrderedSet[0] for outer state, OrderedSet[1] for inner state when decomposing compound FSM state
- [Phase 03]: Checkpoint before sleep/error (not after) to capture phase state before exiting running
- [Phase 03]: Invalid checkpoint falls back silently to running.idle rather than raising
- [Phase 04]: Factory uses module-level _REGISTRY dict for agent type dispatch
- [Phase 04]: EventDrivenLifecycle is standalone StateMachine (not subclass) following GsdLifecycle compound state pattern
- [Phase 04]: Cross-project state uses xp: prefix in memory_store to namespace company-scoped keys
- [Phase 04]: Wake uses sleeping.to(running) for fresh cycle; recover uses errored.to(running.h) for mid-cycle resume
- [Phase 04]: Scheduler uses MemoryStore KV with JSON array for schedule persistence
- [Phase 04]: register_defaults() uses lazy imports to avoid circular deps between factory and agent modules
- [Phase 05]: Store HealthReport on every callback (before _restarting check) so tree always populated
- [Phase 05]: health_tree() iterates _child_specs for ordering, not _health_reports dict
- [Phase 05]: Notification uses loop.create_task for fire-and-forget async dispatch from sync callback
- [Phase 05]: Only errored/running/stopped trigger notifications (not creating)
- [Phase 05]: STATE_INDICATORS uses Unicode emoji for portability; notifications only for errored/running/stopped
- [Phase 06]: RateLimited custom exception instead of catching discord.HTTPException -- keeps MessageQueue Discord-agnostic
- [Phase 06]: Injectable send_func callable instead of bot reference -- makes MessageQueue testable without Discord mocks
- [Phase 06]: Injectable health_check callable decouples DegradedModeManager from anthropic SDK
- [Phase 06]: DegradedModeManager supports both active probing (background loop) and passive operational detection
- [Phase 06]: DegradedModeManager is optional in CompanyRoot -- graceful no-op when health_check not provided
- [Phase 06]: Check is_in_backoff before record_failure to prevent duplicate escalations during active backoff
- [Phase 06]: Bulk detector only created for supervisors with 2+ children
- [Phase 07]: BacklogQueue uses JSON array in single MemoryStore key for atomic persistence
- [Phase 07]: asyncio.Lock per BacklogQueue instance (not global) for concurrency safety
- [Phase 07]: DelegationTracker uses injectable clock for testable rate limiting
- [Phase 07]: Delegation cleanup in state change callback before _restarting check ensures terminated children always release capacity
- [Phase 07]: PM is single writer to backlog -- agents post events, never write to PM MemoryStore directly
- [Phase 08]: DiscordCommunicationPort uses structural subtyping (no Protocol inheritance) for v3 extensibility
- [Phase 08]: commands.when_mentioned replaces command_prefix='\!' to disable prefix commands
- [Phase 08]: WorkflowOrchestratorCog keeps v1 WorkflowStage/detect_stage_signal imports until plan 03 extracts to shared utility
- [Phase 08]: Gate reviews simplified to Discord events -- container FSM handles state transitions
- [Phase 08]: set_company_root() replaces set_orchestrator() -- CompanyRoot accessed via bot attribute
- [Phase 08]: Extracted WorkflowStage/detect_stage_signal to shared/workflow_types.py for cross-module reuse
- [Phase 08]: CLI commands use TmuxManager directly (independent of supervision tree/bot)
- [Phase 08.1]: Claude API health check uses minimal messages.create ping for DegradedModeManager
- [Phase 08.1]: PM found via isinstance iteration over project_sup.children after add_project()
- [Phase 08.2]: Agent subclasses use **kwargs to forward tmux params for extensibility
- [Phase 08.2]: is_tmux_alive() returns True when no tmux injected -- test containers work unchanged
- [Phase 08.2]: _needs_tmux_session True only for gsd/continuous types -- fulltime/company are event-driven
- [Phase 08.2]: TmuxManager created in on_ready and /new-project, injected into CompanyRoot
- [Phase 08.2]: /status removed entirely -- /health is the canonical replacement

### Pending Todos

None yet.

### Blockers/Concerns

- Research flags Phase 3 (GsdAgent) as highest-risk: map every WorkflowOrchestrator callback before implementation
- Research flags Phase 8 (CompanyRoot wiring) as high integration risk: audit all VcoBot.on_ready() wiring before implementation
- python-statemachine 3.0.x and aiosqlite 0.21.x are new dependencies -- verify versions at implementation time
- 10-minute restart windows (not 60s) needed for slow Claude Code bootstrap -- must configure in Phase 2

## Session Continuity

Last session: 2026-03-28T03:57:32.668Z
Stopped at: Completed 08.2-02-PLAN.md
Resume file: None
