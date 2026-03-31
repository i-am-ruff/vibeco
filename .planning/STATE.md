---
gsd_state_version: 1.0
milestone: v4.0
milestone_name: Distributed Agent Runtime
status: Ready to plan
stopped_at: Completed 32-02-PLAN.md
last_updated: "2026-03-31T16:36:15.320Z"
progress:
  total_phases: 6
  completed_phases: 4
  total_plans: 9
  completed_plans: 9
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-31)

**Core value:** Agents run autonomously without hanging on terminal input, stay coordinated through contracts and status awareness, and produce integrated code that merges cleanly -- all operable from Discord.
**Current focus:** Phase 32 — transport-channel-implementations

## Current Position

Phase: 33
Plan: Not started

## Performance Metrics

**Velocity:**

- Total plans completed: 0 (v4.0 milestone)
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Prior milestone (v3.1): 5 phases, 18 plans completed
- Trend: Stable

*Updated after each plan completion*
| Phase 29 P01 | 2min | 1 tasks | 4 files |
| Phase 30 P01 | 2min | 2 tasks | 11 files |
| Phase 30 P02 | 4min | 2 tasks | 15 files |
| Phase 30 P03 | 2min | 1 tasks | 4 files |
| Phase 31 P01 | 2min | 2 tasks | 4 files |
| Phase 31 P02 | 5min | 2 tasks | 2 files |
| Phase 31 P03 | 2min | 2 tasks | 2 files |
| Phase 32 P01 | 2min | 2 tasks | 3 files |
| Phase 32 P02 | 2min | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v3.1]: AgentTransport protocol separates WHERE from HOW
- [v3.1]: Handler extraction makes session/conversation/transient orthogonal to transport
- [v4.0]: Containers run INSIDE transports, not as daemon-side Python objects
- [v4.0]: vco splits into vco-head (orchestration) and vco-worker (container runtime)
- [v4.0]: Transport channel is the ONLY communication between head and worker
- [v4.0]: vco-worker must be installable standalone -- no discord.py, no bot code, no orchestration
- [Phase 29]: StrEnum discriminators for channel protocol messages -- human-readable JSON type fields
- [Phase 29]: Separate TypeAdapter per direction -- decode_head/decode_worker enforce type-level direction safety
- [Phase 30]: Duplicate channel protocol files verbatim into worker package for zero vcompany dependency
- [Phase 30]: Handler registry uses lazy string-based imports so it can be defined before handler classes exist
- [Phase 30]: HealthReport stripped of head-side fields (transport_type, docker_container_id, docker_image) -- worker reports status, head adds metadata
- [Phase 30]: WorkerConversationHandler uses relay mode when no conversation subprocess wired -- avoids anthropic SDK dependency
- [Phase 30]: StdioWriter uses sync stdout.buffer.write instead of private asyncio StreamWriter APIs
- [Phase 30]: run_worker accepts duck-typed writer for testable I/O -- any object with write(bytes) + drain()
- [Phase 31]: AgentHandle uses PrivateAttr for runtime state -- process and health cache excluded from serialization
- [Phase 31]: RoutingState persists as JSON -- filesystem-first, no database, human-readable
- [Phase 31]: channel_id passed as parameter to CompanyRoot.hire() for routing persistence correctness
- [Phase 31]: add_company_agent() kept on container path for Strategist backward compat until worker port
- [Phase 31]: isinstance dispatch for AgentHandle vs AgentContainer in MentionRouterCog _deliver_to_agent()
- [Phase 32]: ChannelTransport uses typing.Protocol with @runtime_checkable, DockerChannelTransport uses subprocess docker run -i instead of docker-py SDK
- [Phase 32]: Lazy transport instantiation cached in _transports dict for reuse across hire() calls

### Roadmap Evolution

- Phase 29-34 created: v4.0 Distributed Agent Runtime -- 6 phases derived from 17 requirements

### Blockers/Concerns

- [Tech debt]: Test suite needs cleanup (asyncio patterns, Click 8.3 compat) -- carried from v3.1
- [Architecture]: Current daemon-side container objects must coexist with new worker until Phase 34 removes them

### Pending Todos

None yet.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260328-tzg | Fix PM review gate: modify/clarify loop + all-stage review | 2026-03-28 | 25a1136 | [260328-tzg](./quick/260328-tzg-fix-pm-review-gate-make-modify-clarify-l/) |

## Session Continuity

Last session: 2026-03-31T16:28:30.194Z
Stopped at: Completed 32-02-PLAN.md
Resume file: None
