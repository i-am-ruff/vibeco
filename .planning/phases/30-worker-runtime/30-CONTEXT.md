# Phase 30: Worker Runtime - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

vco-worker is a separate installable Python package that runs inside any execution environment, accepts a config blob, starts the right agent process, and communicates exclusively through the transport channel. It contains the complete agent container runtime — handler logic (session/conversation/transient), lifecycle FSM, task queue, idle tracking, memory store, checkpoint/restore — previously daemon-side capabilities now self-managed.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Key constraints from project context:
- Containers run INSIDE transports, not as daemon-side Python objects
- Transport channel is the ONLY communication between head and worker
- vco-worker must be installable standalone — no discord.py, no bot code, no orchestration dependencies
- Worker accepts a config blob at startup (handler type, capabilities, gsd_command, persona, env vars)
- Worker manages full agent lifecycle: start, health reporting, graceful stop
- Must contain handler logic (session/conversation/transient), lifecycle FSM, task queue, idle tracking, memory store, checkpoint/restore
- Use Pydantic v2 models (project standard)
- Phase 29's channel protocol (src/vcompany/transport/channel/) is the communication layer

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/vcompany/transport/channel/` — Phase 29 channel protocol (messages.py, framing.py) — the communication layer worker will use
- `src/vcompany/container/container.py` — AgentContainer base class with lifecycle, health, context management
- `src/vcompany/container/state_machine.py` — ContainerLifecycle FSM
- `src/vcompany/container/context.py` — ContainerContext Pydantic model
- `src/vcompany/agent/gsd_agent.py` — GsdAgent (phase FSM, checkpoint recovery)
- `src/vcompany/agent/continuous_agent.py` — ContinuousAgent (cycle FSM)
- `src/vcompany/agent/fulltime_agent.py` — FulltimeAgent (event-driven)
- `src/vcompany/agent/company_agent.py` — CompanyAgent (cross-project)
- `src/vcompany/handler/session.py` — GsdSessionHandler
- `src/vcompany/handler/conversation.py` — StrategistConversationHandler
- `src/vcompany/handler/transient.py` — PMTransientHandler
- `src/vcompany/handler/protocol.py` — SessionHandler, ConversationHandler, TransientHandler protocols

### Established Patterns
- Erlang-style supervision tree with lifecycle state machines (statemachine library)
- @runtime_checkable Protocol pattern for interfaces
- Pydantic BaseModel for all config/data contracts
- Agent types configured via agent-types.yaml

### Integration Points
- Channel protocol (Phase 29) — worker sends WorkerMessages, receives HeadMessages
- Current AgentContainer/handler code lives daemon-side — needs to be extracted/moved to worker package
- pyproject.toml — new package definition needed for vco-worker

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
