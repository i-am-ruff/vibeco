---
gsd_state_version: 1.0
milestone: v3.0
milestone_name: CLI-First Architecture Rewrite
status: Ready to execute
stopped_at: Completed 20-03-PLAN.md
last_updated: "2026-03-29T03:26:43.657Z"
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 9
  completed_plans: 8
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-29)

**Core value:** Agents run autonomously without hanging on terminal input, stay coordinated through contracts and status awareness, and produce integrated code that merges cleanly -- all operable from Discord.
**Current focus:** Phase 20 — CompanyRoot Extraction

## Current Position

Phase: 20 (CompanyRoot Extraction) — EXECUTING
Plan: 4 of 4

## Performance Metrics

**Velocity:**

- Total plans completed: 0 (v3.0)
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans (v2.1): 15s, 12s, 3s, 4s, 525603s
- Trend: Variable

*Updated after each plan completion*
| Phase 18 P01 | 77s | 1 tasks | 4 files |
| Phase 18 P02 | 194s | 2 tasks | 4 files |
| Phase 18 P03 | 167 | 2 tasks | 5 files |
| Phase 19 P01 | 140 | 2 tasks | 3 files |
| Phase 19 P02 | 137 | 2 tasks | 3 files |
| Phase 20 P01 | 150 | 2 tasks | 4 files |
| Phase 20 P02 | 177 | 2 tasks | 2 files |
| Phase 20 P03 | 329 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v3.0 start]: Daemon runs bot in-process via `bot.start()` not `bot.run()` -- avoids two-event-loop conflict
- [v3.0 start]: Zero new runtime deps -- stdlib asyncio for socket, existing aiosqlite/pydantic/click/discord.py
- [v3.0 start]: State persistence deferred to v3.1 -- daemon restart loses state for now
- [v3.0 start]: NDJSON over Unix socket -- simpler than JSON-RPC, debuggable with socat
- [v3.0 roadmap]: COMM requirements split -- protocol definition (Phase 19) before extraction (Phase 20) uses it
- [v3.0 roadmap]: COMM-04/05/06 grouped with EXTRACT phase since they move logic into daemon using the protocol
- [Phase 18]: JSON-RPC 2.0 message structure for daemon NDJSON protocol
- [Phase 18]: Signal handlers set asyncio.Event only -- no async work in signal context
- [Phase 18]: Bot typed as object in Daemon to avoid discord.py import coupling
- [Phase 18]: DaemonClient uses stdlib sync socket -- CLI commands are blocking, no async needed
- [Phase 18]: vco down uses PID polling not socket shutdown -- works even if socket is broken
- [Phase 19]: NoopCommunicationPort lives in comm.py alongside protocol for single-import convenience
- [Phase 19]: CommunicationPort uses runtime_checkable for isinstance validation in set_comm_port
- [Phase 19]: Daemon setter/property injection: set_comm_port raises TypeError, comm_port raises RuntimeError
- [Phase 19]: DiscordCommunicationPort uses _resolve_channel helper with TextChannel isinstance check
- [Phase 19]: _comm_registered flag prevents double registration on Discord reconnects
- [Phase 20]: RuntimeAPI uses lazy comm_port_getter callable for late-bound CommunicationPort
- [Phase 20]: RuntimeAPI.hire() creates channel via CommunicationPort before CompanyRoot.hire() -- no guild param needed
- [Phase 20]: Callback methods use CommunicationPort send_message for all notifications -- consistent platform-agnostic messaging
- [Phase 20]: Inbound relay methods decouple bot cogs from container internals -- bot calls RuntimeAPI not containers
- [Phase 20]: Bot is now a pure Discord I/O adapter -- all CompanyRoot/container/agent imports removed from client.py
- [Phase 20]: Daemon waits for _bot_ready_event before initializing CompanyRoot with crash-before-ready detection
- [Phase 20]: PlanReviewer/PMTier NOT injected into cogs -- deferred to Phase 22 via RuntimeAPI

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 20]: on_ready() has 15+ callback closures needing audit before extraction -- plan first task of Phase 20 as audit
- [Phase 20]: Wiring order constraints in on_ready() (PM event sink must be last) -- respect during RuntimeAPI design

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260328-tzg | Fix PM review gate: modify/clarify loop + all-stage review | 2026-03-28 | 25a1136 | [260328-tzg](./quick/260328-tzg-fix-pm-review-gate-make-modify-clarify-l/) |

## Session Continuity

Last session: 2026-03-29T03:26:43.654Z
Stopped at: Completed 20-03-PLAN.md
Resume file: None
