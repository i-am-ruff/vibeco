# Phase 28: Agent-Transport Separation Refactor - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Extract the three handler patterns (tmux session, resume-conversation, memory-based transient) from agent subclasses into composable pieces. The handler dimension (HOW the agent thinks) becomes orthogonal to the transport dimension (WHERE it runs). Any handler type can run on any transport without writing new classes.

Current state: 5 agent subclasses each hardcode their handler pattern + duplicate `_send_discord` logic. Transport abstraction (Phase 25-27) is clean — this phase completes the other axis.

</domain>

<decisions>
## Implementation Decisions

### Handler Abstraction (the "HOW it thinks" axis)
- **D-01:** Three handler protocols, each a Python Protocol (structural typing — consistent with AgentTransport from Phase 25):
  - `SessionHandler` — manages an interactive Claude Code session (tmux send_keys, idle/ready signals). Used by current GsdAgent, TaskAgent, ContinuousAgent.
  - `ConversationHandler` — request-response via `transport.exec()` with piped stdin/stdout, session persists via `--resume`. Used by current CompanyAgent (Strategist).
  - `TransientHandler` — in-memory Python logic, no Claude session. Processes structured messages via prefix matching or state machine. Used by current FulltimeAgent (PM).
- **D-02:** Handlers are stateless protocols — they define behavior, not state. Session state (idle tracking, task queue, review gates) stays on AgentContainer or in handler-specific state objects passed in.
- **D-03:** Handler is injected into AgentContainer at creation time. Container delegates `receive_discord_message()` to its handler. Container owns lifecycle, handler owns message processing.

### Message I/O (fixing the response path)
- **D-04:** `_send_discord()` moves to base AgentContainer — no more duplicated implementations across 5 subclasses. Uses numeric channel_id (already on MessageContext from MentionRouterCog), not channel names.
- **D-05:** Container stores its primary channel_id at registration time (set by RuntimeAPI when registering with MentionRouterCog). All outbound messages use this stored channel_id.
- **D-06:** comm_port on containers is the real CommunicationPort (already wired in this session — CompanyRoot now receives it from daemon). No more NoopCommunicationPort in production.

### Composition via Config
- **D-07:** agent-types.yaml gains a `handler` field: `session`, `conversation`, or `transient`. Factory reads this and composes the right handler + transport + container. Example:
  ```yaml
  gsd:
    handler: session
    transport: local
    capabilities: [gsd_driven, uses_tmux]

  docker-gsd:
    handler: session
    transport: docker
    docker_image: "vco-agent:latest"

  strategist:
    handler: conversation
    transport: local

  pm:
    handler: transient
    transport: local
  ```
- **D-08:** Factory handler registry: `{"session": SessionHandler, "conversation": ConversationHandler, "transient": TransientHandler}`. Same pattern as transport registry (D-07 from Phase 25). New handler type = add one line.
- **D-09:** Agent subclasses (CompanyAgent, FulltimeAgent, GsdAgent, etc.) become thin wrappers or are eliminated entirely. Handler-specific logic (review gates, prefix matching, conversation management) moves into handler implementations.

### Migration Strategy
- **D-10:** Extract-then-deprecate. Phase 28 creates the handler abstractions AND migrates existing subclasses. By end of phase, the factory composes handler + transport from config without needing agent subclasses.
- **D-11:** GsdAgent's review gate logic (pending_review Future, advance_phase) becomes part of SessionHandler or a GSD-specific state object. The handler protocol doesn't change — the state management is handler-internal.
- **D-12:** FulltimeAgent's prefix matching (Phase Complete, Task Assigned, etc.) becomes the TransientHandler's `process_message()` implementation. The PM's stuck-detector background task becomes a composable lifecycle component.
- **D-13:** CompanyAgent's StrategistConversation becomes the ConversationHandler implementation. It already uses transport.exec() — it just needs to be extracted from the class hierarchy.

### Claude's Discretion
- Whether handler protocols need async methods or sync methods
- Internal state management approach for SessionHandler (idle tracking, task queue)
- Whether to keep agent subclasses as thin wrappers for backward compat during transition or remove immediately
- How the GSD lifecycle (gsd_phases.py, gsd_lifecycle.py) integrates with the extracted SessionHandler

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `.planning/architecture-notes/agent-transport-separation.md` — The container type vs transport matrix that defines this refactor
- `.planning/phases/25-transport-abstraction/25-CONTEXT.md` — D-01 (thin transport), D-05 (Strategist through transport), D-06 (both modes), D-07 (registry pattern)

### Current Agent Subclasses (to be refactored)
- `src/vcompany/agent/company_agent.py` — CompanyAgent (resume-conversation handler)
- `src/vcompany/agent/fulltime_agent.py` — FulltimeAgent (transient handler)
- `src/vcompany/agent/gsd_agent.py` — GsdAgent (session handler)
- `src/vcompany/agent/continuous_agent.py` — ContinuousAgent (session handler variant)
- `src/vcompany/agent/task_agent.py` — TaskAgent (session handler variant)

### Transport Layer (already abstracted — reference only)
- `src/vcompany/transport/protocol.py` — AgentTransport protocol
- `src/vcompany/transport/local.py` — LocalTransport
- `src/vcompany/transport/docker.py` — DockerTransport

### Container & Factory
- `src/vcompany/container/container.py` — AgentContainer base class
- `src/vcompany/container/factory.py` — Container factory with transport registry
- `agent-types.yaml` — Agent type config (gains handler field)

### Communication
- `src/vcompany/daemon/comm.py` — CommunicationPort protocol
- `src/vcompany/bot/cogs/mention_router.py` — MentionRouterCog (channel-based + @mention routing)
- `src/vcompany/models/messages.py` — MessageContext (has channel_id)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AgentTransport` protocol — clean, handler-agnostic, ready to compose
- `_TRANSPORT_REGISTRY` in factory.py — exact same pattern needed for handler registry
- `_CONTAINER_REGISTRY` in factory.py — already maps type names to classes
- `MentionRouterCog` — already does channel-based routing with channel_id

### Established Patterns
- Protocol-based typing (AgentTransport) — use same for handlers
- Registry dict in factory — proven for transport, reuse for handlers
- agent-types.yaml as single source of truth — extend with handler field
- `receive_discord_message(context)` — uniform entry point on all agents

### Integration Points
- `factory.create_container()` — needs to compose handler based on config
- `RuntimeAPI.create_strategist()` — hardcodes CompanyAgent, needs to use factory
- `CompanyRoot.add_company_agent()` — passes comm_port to containers
- `MentionRouterCog.register_agent()` — sets channel_id for routing

</code_context>

<specifics>
## Specific Ideas

- The user explicitly described the mental model: "Agent containers: tmux session handler (normal), memory-based transient handler (PM), resume-conversation handler (strategist). Transport is where this agent container runs: Docker container, Native, Network (later)."
- Handler + Transport are a matrix — any combination should work without new code
- The comm_port wiring (real DiscordCommunicationPort, not Noop) is already partially fixed in this session and should be fully resolved

</specifics>

<deferred>
## Deferred Ideas

- Network transport (v4) — remote agents on different machines
- Per-agent handler overrides (run a Strategist-style conversation agent on Docker)
- Handler hot-swapping at runtime (change from session to conversation without restart)
- Lifecycle components as separate composable pieces (stuck-detector, review-gate as plugins)

</deferred>

---

*Phase: 28-agent-transport-separation*
*Context gathered: 2026-03-31 via auto mode*
