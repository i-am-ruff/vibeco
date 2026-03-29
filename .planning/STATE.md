---
gsd_state_version: 1.0
milestone: v3.1
milestone_name: Container Runtime Abstraction
status: Milestone complete
stopped_at: Completed 27-04-PLAN.md
last_updated: "2026-03-29T23:30:16.927Z"
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 14
  completed_plans: 14
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-29)

**Core value:** Agents run autonomously without hanging on terminal input, stay coordinated through contracts and status awareness, and produce integrated code that merges cleanly -- all operable from Discord.
**Current focus:** Phase 27 — docker-integration-wiring

## Current Position

Phase: 27
Plan: Not started

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v3.1 scope]: Phase 24 first — surface all hidden inter-agent communication to Discord before transport abstraction
- [v3.1 scope]: No agent-specific hardcoding in RuntimeAPI — PM is just an agent with rules, not special Python
- [v3.1 scope]: AgentTransport protocol for local/Docker/network execution environments
- [v3.1 scope]: Socket-based agent signaling replaces sentinel temp files
- [v3.1 scope]: State persistence deferred to v3.2+
- [v3.1 scope]: Nyquist validation disabled — focus on implementation quality over test ceremony
- [Phase 24]: Injected async callback pattern for BacklogQueue mutation notifications -- decoupled from Discord/CommunicationPort
- [Phase 24]: Generic handle-based @mention routing (no agent-type checks) via MentionRouterCog
- [Phase 24]: Prefix-based message dispatch pattern for Discord agent communication
- [Phase 24]: escalate_to_strategist changed from request-response to fire-and-forget Discord message
- [Phase 24]: Strategist container accessed via company_root instead of stored ref; PM handle as PM{project}; BacklogQueue on_mutation via CommunicationPort
- [Phase 24]: Kept RuntimeAPI SendMessagePayload notifications alongside [Review] messages -- different purposes
- [Phase 25]: AgentTransport uses @runtime_checkable Protocol (structural subtyping, same as CommunicationPort)
- [Phase 25]: LocalTransport accepts optional TmuxManager via constructor injection for testability
- [Phase 25]: Unix socket for signal HTTP server (avoids TCP port conflicts)
- [Phase 25]: Silent failure in vco signal when daemon unreachable (hooks must not block agents)
- [Phase 25]: ChildSpec gets transport field for factory lookup; factory creates new transport per container from transport_deps
- [Phase 26]: docker_image is a plain optional string with no validator -- factory validates at runtime
- [Phase 26]: Container naming uses vco-{project}-{agent_id} for deterministic reuse
- [Phase 26]: Volume-based file I/O for DockerTransport read_file/write_file (not docker cp)
- [Phase 27]: Separate async/sync Docker build interfaces: ensure_docker_image for hire-flow, build_image_sync for CLI
- [Phase 27]: Factory resolves per-transport deps from agent type config instead of passing global dict (D-01)
- [Phase 27]: Module-level set/get pattern for agent types config avoids threading through constructors
- [Phase 27]: hasattr duck typing over isinstance for method guards (resolve_review, initialize_conversation, backlog)
- [Phase 27]: Dual registry by type string and class name enables docker-gsd -> GsdAgent mapping via container_class config
- [Phase 27]: Auto-build placed in company_root.hire() not factory -- factory is sync, ensure_docker_image is async
- [Phase 27]: Transport type detection in health_report uses hasattr duck typing on _image attribute

### Roadmap Evolution

- Phase 27 added: Docker Integration Wiring — per-transport deps, docker_image flow, auto-build, parametric setup, remove hardcoded type checks, e2e Docker agent via Discord

### Blockers/Concerns

- [Architecture]: PM currently receives events via internal post_event() asyncio.Queue — invisible on Discord
- [Architecture]: RuntimeAPI has PM-specific methods (_on_phase_complete, pm_event_sink) — hardcoded agent routing
- [Architecture]: BacklogQueue operations are silent internal state changes — not visible on Discord
- [Architecture]: Plan review decisions (approve/reject) routed internally, not through Discord channels

### Pending Todos

None yet.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260328-tzg | Fix PM review gate: modify/clarify loop + all-stage review | 2026-03-28 | 25a1136 | [260328-tzg](./quick/260328-tzg-fix-pm-review-gate-make-modify-clarify-l/) |

## Session Continuity

Last session: 2026-03-29T23:25:24.276Z
Stopped at: Completed 27-04-PLAN.md
Resume file: None
