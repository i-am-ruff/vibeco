# Phase 19: Communication Abstraction - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

A formal CommunicationPort protocol exists that the daemon uses for all platform communication, with a Discord adapter implementing it in the bot layer. Covers COMM-01 (protocol definition with send_message, send_embed, create_thread, subscribe_to_channel), COMM-02 (daemon never imports discord.py), COMM-03 (DiscordCommunicationPort adapter in bot layer).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key architectural principles:
- CommunicationPort is a Python Protocol (typing.Protocol) — not an ABC — for structural subtyping
- Daemon module tree must have zero discord.py imports — enforced at import level
- DiscordCommunicationPort lives in bot layer (not daemon) — keeps the dependency boundary clean
- Adapter is registered with daemon on startup — injection pattern, not import
- Methods must be typed (Pydantic models for message payloads preferred over raw dicts)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/daemon/` — daemon package from Phase 18 (protocol.py, server.py, daemon.py)
- `src/vcompany/bot/client.py` — VcoBot with on_ready lifecycle, existing channel/message handling
- `src/vcompany/bot/cogs/` — existing cogs that send Discord messages (alerts, strategist, commands)
- `src/vcompany/container/container.py` — AgentContainer with existing notification patterns

### Established Patterns
- Daemon uses asyncio.start_unix_server with NDJSON protocol (Phase 18)
- Bot constructs CompanyRoot in on_ready with injected callbacks
- Message queue priority system for Discord notifications
- Pydantic models for data validation throughout

### Integration Points
- Daemon needs to call CommunicationPort methods without importing discord.py
- Bot registers DiscordCommunicationPort with daemon on startup (likely in on_ready)
- Existing bot notification callbacks need to route through CommunicationPort eventually (Phase 20+)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase with clear scope.

</deferred>
