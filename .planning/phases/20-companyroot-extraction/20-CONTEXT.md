# Phase 20: CompanyRoot Extraction - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

CompanyRoot, supervision tree, Strategist conversation, and PM review flow all run inside the daemon process, accessed exclusively through a RuntimeAPI gateway. Covers EXTRACT-01 (CompanyRoot in daemon), EXTRACT-02 (RuntimeAPI gateway), EXTRACT-03 (on_ready callbacks replaced), EXTRACT-04 (bot uses RuntimeAPI only), COMM-04 (Strategist through CommunicationPort), COMM-05 (PM review through CommunicationPort), COMM-06 (channel creation through CommunicationPort).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — architecture extraction phase. Key decisions and concerns from STATE.md:
- on_ready() has 15+ callback closures needing audit before extraction — plan first task as audit
- Wiring order constraints in on_ready() (PM event sink must be last) — respect during RuntimeAPI design
- Daemon runs bot in-process via bot.start() — CompanyRoot initializes in daemon, not in on_ready
- CommunicationPort (Phase 19) is the bridge — daemon sends through it, Discord adapter in bot receives

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/daemon/daemon.py` — Daemon class from Phase 18, owns event loop + bot
- `src/vcompany/daemon/comm.py` — CommunicationPort protocol from Phase 19
- `src/vcompany/bot/comm_adapter.py` — DiscordCommunicationPort from Phase 19
- `src/vcompany/supervisor/company_root.py` — CompanyRoot with start()/stop()
- `src/vcompany/supervisor/supervisor.py` — Supervisor base class
- `src/vcompany/strategist/conversation.py` — StrategistConversation
- `src/vcompany/bot/client.py` — VcoBot with on_ready() containing 15+ callback closures
- `src/vcompany/bot/cogs/strategist.py` — StrategistCog
- `src/vcompany/bot/cogs/commands.py` — CommandsCog with slash commands

### Established Patterns
- Daemon owns event loop, bot is a coroutine within it (Phase 18)
- CommunicationPort protocol for platform-agnostic messaging (Phase 19)
- CompanyRoot currently constructed in on_ready with injected callbacks
- Callback-based wiring (on_phase_complete, on_review_needed, etc.)
- TmuxManager injected into containers

### Integration Points
- on_ready() 15+ closures → RuntimeAPI methods
- StrategistCog message handling → CommunicationPort
- PM review flow in CommandsCog → CommunicationPort
- Channel creation in channel_setup.py → CommunicationPort
- Socket server methods need new RuntimeAPI endpoints

</code_context>

<specifics>
## Specific Ideas

No specific requirements — architecture extraction phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — extraction phase with clear scope.

</deferred>
