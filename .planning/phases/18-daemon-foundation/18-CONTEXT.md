# Phase 18: Daemon Foundation - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

User can start and stop a runtime daemon that listens on a Unix socket, with safe single-instance enforcement and graceful shutdown. Covers DAEMON-01..06 (lifecycle, PID file, signals, stale cleanup, vco down, bot co-start) and SOCK-01..06 (Unix socket, NDJSON protocol, request framing, error responses, event subscription, protocol version handshake).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key decisions already established in STATE.md:
- Daemon runs bot in-process via `bot.start()` not `bot.run()` — avoids two-event-loop conflict
- Zero new runtime deps — stdlib asyncio for socket, existing discord.py/pydantic/click
- State persistence deferred to v3.1 — daemon restart loses state for now
- NDJSON over Unix socket — simpler than JSON-RPC, debuggable with socat

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `VcoBot` (bot/client.py) — subclasses commands.Bot, has setup_hook/on_ready lifecycle
- `CompanyRoot` (supervisor/company_root.py) — supervision tree root, start()/stop() async methods
- `TmuxManager` — injected into containers, sync calls wrapped in asyncio.to_thread()
- Click CLI group at cli/main.py with existing `vco up` command (up_cmd.py)
- `AgentContainer` with lifecycle FSM, health reporting, context management

### Established Patterns
- discord.py's `bot.run()` currently owns the event loop — daemon needs `asyncio.run()` with `bot.start()` instead
- CompanyRoot is not coupled to bot — constructed in on_ready with injected callbacks, can be constructed independently
- All blocking tmux calls use `asyncio.to_thread()` — safe for async daemon
- Pydantic models for config validation (AgentConfig, etc.)
- Signal-based agent readiness via sentinel files in /tmp/

### Integration Points
- `vco up` command (up_cmd.py) — current startup flow, needs refactoring to daemon mode
- `bot.on_ready()` — 15+ callback closures wiring CompanyRoot to bot (audit needed in Phase 20)
- Click CLI group — new `vco down` command needed
- pyproject.toml — entry point `vco = "vcompany.cli.main:cli"`

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase with clear scope.

</deferred>
