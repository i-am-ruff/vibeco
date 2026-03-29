# Phase 22: Bot Thin Relay - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

All Discord slash commands delegate to RuntimeAPI with zero container module imports, and the bot acts as a pure I/O adapter between Discord and the daemon. Covers BOT-01 (slash commands via RuntimeAPI), BOT-02 (zero prohibited imports in cog modules), BOT-03 (daemon event formatting as embeds/threads/reactions), BOT-04 (message relay via CommunicationPort), BOT-05 (subscribe_to_channel for inbound channel messages).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure refactoring phase. Key patterns:
- Phase 20 already gutted on_ready and rewired CommandsCog/StrategistCog/PlanReviewCog through RuntimeAPI
- Phase 21 added CLI equivalents for all management commands
- This phase completes the remaining cog cleanup and adds event formatting + message relay
- test_import_boundary.py already exists with PROHIBITED_PREFIXES — extend coverage to all cog modules

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/daemon/runtime_api.py` — RuntimeAPI with all business methods
- `src/vcompany/daemon/comm.py` — CommunicationPort with subscribe_to_channel method
- `src/vcompany/bot/comm_adapter.py` — DiscordCommunicationPort adapter
- `src/vcompany/bot/cogs/` — existing cogs (commands.py, strategist.py, plan_review.py, alerts.py, task_relay.py)
- `tests/test_import_boundary.py` — existing import boundary enforcement test

### Established Patterns
- Cogs access daemon via `self.bot._daemon.runtime_api` (established in Phase 20)
- CommunicationPort.subscribe_to_channel() for inbound message delivery
- Event subscription over socket (SOCK-05) for daemon→bot notifications
- Rich embeds for Discord formatting (existing patterns in cogs)

### Integration Points
- Remaining cog imports that violate boundary (check all cogs)
- Event flow: daemon emits events → bot subscribes → formats as Discord messages
- Message relay: Discord on_message → CommunicationPort → daemon

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure refactoring phase.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
