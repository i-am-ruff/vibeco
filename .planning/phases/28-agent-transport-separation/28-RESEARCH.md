# Phase 28: Agent-Transport Separation Refactor - Research

**Researched:** 2026-03-31
**Domain:** Python Protocol-based handler abstraction, composition over inheritance
**Confidence:** HIGH

## Summary

Phase 28 extracts the three handler patterns (session, conversation, transient) from five agent subclasses into composable Protocol-based handlers orthogonal to the transport layer. The codebase already has the transport axis cleanly abstracted (Phase 25-27). This phase completes the other axis: HOW the agent thinks.

The current state shows five agent subclasses (GsdAgent, ContinuousAgent, CompanyAgent, FulltimeAgent, TaskAgent) that each duplicate `_send_discord()`, override `receive_discord_message()`, and bake handler-specific logic into the class hierarchy. Two of these (GsdAgent, TaskAgent) still reference `self._tmux` and `self._launch_tmux_session()` which no longer exist on the base AgentContainer -- these are dead code paths that would fail at runtime and must be fixed as part of extraction.

**Primary recommendation:** Define three handler Protocols (`SessionHandler`, `ConversationHandler`, `TransientHandler`), extract handler logic from subclasses into implementations, move `_send_discord()` to base AgentContainer, add `handler` field to AgentTypeConfig, and compose handler+transport in the factory. Agent subclasses become thin wrappers or are eliminated.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Three handler protocols using Python Protocol (structural typing): SessionHandler, ConversationHandler, TransientHandler
- **D-02:** Handlers are stateless protocols -- behavior, not state. Session state stays on AgentContainer or handler-specific state objects
- **D-03:** Handler injected into AgentContainer at creation time. Container delegates receive_discord_message() to handler. Container owns lifecycle, handler owns message processing
- **D-04:** `_send_discord()` moves to base AgentContainer -- no more duplicated implementations. Uses numeric channel_id
- **D-05:** Container stores primary channel_id at registration time (set by RuntimeAPI via MentionRouterCog)
- **D-06:** comm_port on containers is the real CommunicationPort (already partially wired)
- **D-07:** agent-types.yaml gains `handler` field: session, conversation, or transient. Factory reads and composes
- **D-08:** Factory handler registry: `{"session": SessionHandler, "conversation": ConversationHandler, "transient": TransientHandler}`
- **D-09:** Agent subclasses become thin wrappers or eliminated entirely
- **D-10:** Extract-then-deprecate migration strategy -- create abstractions AND migrate in this phase
- **D-11:** GsdAgent review gate logic becomes part of SessionHandler or GSD-specific state object
- **D-12:** FulltimeAgent prefix matching becomes TransientHandler's process_message() implementation
- **D-13:** CompanyAgent's StrategistConversation becomes ConversationHandler implementation

### Claude's Discretion
- Whether handler protocols need async methods or sync methods
- Internal state management approach for SessionHandler (idle tracking, task queue)
- Whether to keep agent subclasses as thin wrappers for backward compat during transition or remove immediately
- How the GSD lifecycle (gsd_phases.py, gsd_lifecycle.py) integrates with the extracted SessionHandler

### Deferred Ideas (OUT OF SCOPE)
- Network transport (v4)
- Per-agent handler overrides (conversation agent on Docker)
- Handler hot-swapping at runtime
- Lifecycle components as separate composable pieces (stuck-detector, review-gate as plugins)

</user_constraints>

<phase_requirements>

## Phase Requirements

Since no formal requirement IDs exist for this phase, requirements are derived from CONTEXT.md decisions:

| ID | Description | Research Support |
|----|-------------|------------------|
| HSEP-01 | Three handler Protocols defined (SessionHandler, ConversationHandler, TransientHandler) | Protocol pattern from AgentTransport; structural typing consistent with codebase |
| HSEP-02 | `_send_discord()` consolidated into base AgentContainer with channel_id | Three identical implementations found in company_agent.py, fulltime_agent.py, gsd_agent.py |
| HSEP-03 | Container delegates `receive_discord_message()` to injected handler | Base container already has no-op receive_discord_message(); handler replaces subclass overrides |
| HSEP-04 | agent-types.yaml extended with `handler` field | AgentTypeConfig model needs one new field; factory needs handler registry |
| HSEP-05 | Factory composes handler + transport from config | Factory already has _TRANSPORT_REGISTRY pattern; replicate for handlers |
| HSEP-06 | Agent subclasses eliminated or reduced to thin wrappers | Five subclasses analyzed; each has extractable handler logic + duplicated _send_discord |
| HSEP-07 | Dead code paths (`self._tmux`, `_launch_tmux_session`) cleaned up in GsdAgent and TaskAgent | These reference methods that no longer exist on base container |
| HSEP-08 | Container stores primary channel_id for outbound Discord messages | MentionRouterCog already provides channel_id at registration |

</phase_requirements>

## Architecture Patterns

### Current Class Hierarchy (to be refactored)

```
AgentContainer (base)
  +-- _send_discord() [NOT here -- duplicated in subclasses]
  +-- receive_discord_message() [no-op in base]
  +-- _launch_agent() [transport-based launch]
  +-- give_task() [idle-gated task queue]
  |
  +-- GsdAgent
  |     +-- _send_discord() [DUPLICATE]
  |     +-- receive_discord_message() [review decision, task assignment]
  |     +-- advance_phase() / resolve_review() [review gate]
  |     +-- GsdLifecycle FSM [compound running state]
  |     +-- checkpoint/restore [memory-based persistence]
  |     +-- self._tmux / _launch_tmux_session() [DEAD CODE - references removed methods]
  |
  +-- ContinuousAgent
  |     +-- [no _send_discord -- doesn't send messages directly]
  |     +-- ContinuousLifecycle FSM [cycle phases]
  |     +-- checkpoint/restore
  |
  +-- TaskAgent
  |     +-- [no _send_discord or receive_discord_message override]
  |     +-- working_dir / system_prompt_path overrides
  |     +-- self._tmux / _launch_tmux_session() [DEAD CODE]
  |
  +-- CompanyAgent
  |     +-- _send_discord() [DUPLICATE]
  |     +-- receive_discord_message() [forwards to StrategistConversation]
  |     +-- initialize_conversation() [wires StrategistConversation]
  |     +-- EventDrivenLifecycle FSM
  |
  +-- FulltimeAgent
        +-- _send_discord() [DUPLICATE]
        +-- receive_discord_message() [prefix-based dispatch]
        +-- backlog operations, stuck detector
        +-- EventDrivenLifecycle FSM
```

### Target Architecture (after refactor)

```
AgentContainer (base)
  +-- _send_discord(channel_id, content) [CONSOLIDATED HERE]
  +-- _channel_id: str [stored at registration time]
  +-- _handler: Handler protocol [injected at creation]
  +-- receive_discord_message() [delegates to self._handler.handle()]

Handler Protocols (composable, injected):
  SessionHandler     -- interactive tmux session, idle tracking, task queue
  ConversationHandler -- piped claude -p --resume, request-response
  TransientHandler   -- pure Python logic, prefix matching, state machine

Factory composes: handler (from config) + transport (from config) + container
```

### Recommended Project Structure for New Code

```
src/vcompany/handler/
  +-- __init__.py
  +-- protocol.py          # SessionHandler, ConversationHandler, TransientHandler protocols
  +-- session.py            # SessionHandler implementation (from GsdAgent/ContinuousAgent/TaskAgent)
  +-- conversation.py       # ConversationHandler implementation (from CompanyAgent)
  +-- transient.py          # TransientHandler implementation (from FulltimeAgent)
```

### Pattern: Handler Protocol Definition

All three handlers share a common message-handling interface but differ in HOW they process messages. Use Protocol with async methods (consistent with the async-native codebase -- discord.py, transport.exec(), etc.).

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class SessionHandler(Protocol):
    """Handles messages by sending to interactive Claude session (tmux)."""

    async def handle_message(
        self, container: AgentContainer, context: MessageContext
    ) -> None:
        """Process a Discord message for a session-based agent."""
        ...

    async def on_start(self, container: AgentContainer) -> None:
        """Called when container starts -- launch session, restore state."""
        ...

    async def on_stop(self, container: AgentContainer) -> None:
        """Called when container stops -- checkpoint state."""
        ...
```

**Recommendation on async vs sync:** Use async methods. Every handler will call `_send_discord()` (async), access `transport.exec()` (async), or interact with the memory store (async). Making handlers sync would require wrapping every call.

### Pattern: Handler Injection in Factory

```python
_HANDLER_REGISTRY: dict[str, type] = {
    "session": GsdSessionHandler,
    "conversation": StrategistConversationHandler,
    "transient": PMTransientHandler,
}

# In create_container():
handler_name = type_config.handler if type_config else "session"
handler_cls = _HANDLER_REGISTRY.get(handler_name)
handler = handler_cls() if handler_cls else None
container._handler = handler
```

### Anti-Patterns to Avoid

- **Over-abstracting the handler protocol:** Don't create a single unified Handler protocol that all three types implement. The three handler types have fundamentally different interfaces (session has idle tracking, conversation has send/stream, transient has prefix dispatch). Keep them as separate Protocols.
- **Moving lifecycle FSMs into handlers:** The FSMs (GsdLifecycle, EventDrivenLifecycle, ContinuousLifecycle) are container-level concerns, not handler concerns. Handlers define message processing; FSMs define container state. Keep FSMs on the container.
- **Breaking the hasattr duck-typing pattern:** The codebase already uses `hasattr` for method detection (resolve_review, initialize_conversation, make_completion_event). Don't break this pattern -- instead, make handlers expose these methods so hasattr checks still work.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Protocol definition | ABC classes with @abstractmethod | `typing.Protocol` with `@runtime_checkable` | Consistent with AgentTransport and CommunicationPort patterns in codebase |
| Registry pattern | Complex plugin system | Dict registry like `_TRANSPORT_REGISTRY` | Already proven in factory.py; simple, debuggable |
| State management for handlers | Handler-internal state dicts | Container-owned state objects passed to handlers | D-02 says handlers are stateless protocols |

## Common Pitfalls

### Pitfall 1: GsdAgent's `start()` method has complex checkpoint-restore logic

**What goes wrong:** Extracting GsdAgent's handler logic without also extracting the start() override that does checkpoint restore, phase-aware command resolution, and assignment restoration.
**Why it happens:** GsdAgent.start() is tightly coupled to both lifecycle AND handler concerns -- it restores checkpoints (lifecycle), resolves GSD commands (handler), and launches tmux (transport).
**How to avoid:** The SessionHandler.on_start() hook should handle checkpoint restore and command resolution. The container's start() should call handler.on_start() after FSM transition and before transport launch.
**Warning signs:** Tests pass but agents don't restore from checkpoints after restart.

### Pitfall 2: Dead code in GsdAgent and TaskAgent

**What goes wrong:** Both GsdAgent.start() and TaskAgent.start() reference `self._tmux` and `self._launch_tmux_session()` which don't exist on the base AgentContainer anymore (removed during Phase 25 transport abstraction). This is dead code that would crash at runtime.
**Why it happens:** Phase 25 replaced `_tmux` with `_transport` on the base class but the subclass overrides of start() weren't updated.
**How to avoid:** The extraction must fix these references. The base container's start() already calls `_launch_agent()` correctly via transport. GsdAgent and TaskAgent's start() methods should delegate to super().start() after doing their own pre-launch work (checkpoint restore, etc.).
**Warning signs:** `AttributeError: 'GsdAgent' object has no attribute '_tmux'` at runtime.

### Pitfall 3: Three separate `_send_discord()` implementations with subtle differences

**What goes wrong:** The three implementations import SendMessagePayload from different modules (`vcompany.daemon.comm` in CompanyAgent vs `vcompany.container.communication` in FulltimeAgent and GsdAgent).
**Why it happens:** Copy-paste across phases with different import conventions.
**How to avoid:** Consolidate into base AgentContainer using the canonical import from `vcompany.daemon.comm` (which is where the protocol and payloads are defined). The `communication` module in container/ appears to be a re-export.
**Warning signs:** ImportError at runtime if the wrong module is used.

### Pitfall 4: hasattr-based duck typing in RuntimeAPI will break

**What goes wrong:** RuntimeAPI uses `hasattr(container, 'resolve_review')`, `hasattr(container, 'initialize_conversation')`, and `hasattr(container, 'make_completion_event')` to detect agent capabilities. If handlers own these methods instead of the container, hasattr checks fail.
**Why it happens:** Methods move from container subclasses to handler implementations, but callers still check the container.
**How to avoid:** Either (a) keep these methods on the container as thin delegates to the handler, or (b) update RuntimeAPI to check `hasattr(container._handler, 'method')`. Option (a) is simpler and preserves backward compat.
**Warning signs:** Review decisions silently dropped, strategist conversation never initialized.

### Pitfall 5: EventDrivenLifecycle coupling

**What goes wrong:** Both CompanyAgent and FulltimeAgent override the parent's `ContainerLifecycle` with `EventDrivenLifecycle` in their `__init__`. The compound state (listening/processing) and the state/inner_state property overrides are baked into these subclasses.
**Why it happens:** The FSM type is a container concern (what lifecycle states exist), not a handler concern (how messages are processed). But the current code bundles them together.
**How to avoid:** The factory should set the lifecycle FSM based on the handler type. When handler is "conversation" or "transient", use EventDrivenLifecycle. When handler is "session", use GsdLifecycle (for GSD agents) or ContainerLifecycle (for TaskAgent/ContinuousAgent). The state/inner_state property overrides need to move to the container level based on lifecycle type.
**Warning signs:** `state` and `inner_state` properties return wrong values because the FSM type doesn't match.

### Pitfall 6: FulltimeAgent has background tasks (stuck detector)

**What goes wrong:** The stuck detector `_run_stuck_detector()` is an asyncio background task started in FulltimeAgent.start() and cancelled in FulltimeAgent.stop(). If the FulltimeAgent subclass is eliminated, this lifecycle management must move somewhere.
**Why it happens:** Background tasks are lifecycle concerns, not handler concerns, but they live on the subclass.
**How to avoid:** The TransientHandler could expose start/stop hooks for background tasks, or the stuck detector could become a lifecycle component on the container. Given "lifecycle components as plugins" is explicitly deferred, the simplest approach is to keep it in the TransientHandler implementation's on_start/on_stop hooks.

## Code Examples

### Current _send_discord duplication (verified in codebase)

All three implementations are functionally identical:

```python
# CompanyAgent (imports from vcompany.daemon.comm)
async def _send_discord(self, channel_name: str, content: str) -> None:
    if self.comm_port is None:
        return
    from vcompany.daemon.comm import SendMessagePayload
    payload = SendMessagePayload(channel_id=channel_name, content=content)
    await self.comm_port.send_message(payload)

# FulltimeAgent (imports from vcompany.container.communication)
# GsdAgent (imports from vcompany.container.communication)
# Both identical except import path
```

### Consolidated _send_discord on base container

```python
# On AgentContainer:
async def _send_discord(self, channel_id: str, content: str) -> None:
    """Send a message to Discord via CommunicationPort."""
    if self.comm_port is None:
        logger.warning("Cannot send Discord message -- no comm_port wired")
        return
    from vcompany.daemon.comm import SendMessagePayload
    payload = SendMessagePayload(channel_id=channel_id, content=content)
    await self.comm_port.send_message(payload)
```

### Handler protocol example

```python
# src/vcompany/handler/protocol.py
from __future__ import annotations
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from vcompany.container.container import AgentContainer
    from vcompany.models.messages import MessageContext

@runtime_checkable
class AgentHandler(Protocol):
    """Base handler protocol -- all handlers must implement handle_message."""

    async def handle_message(
        self, container: AgentContainer, context: MessageContext
    ) -> None: ...

    async def on_start(self, container: AgentContainer) -> None: ...

    async def on_stop(self, container: AgentContainer) -> None: ...
```

### Factory handler composition

```python
# In factory.py create_container():
handler_name = type_config.handler if type_config else None
if handler_name:
    handler_cls = _HANDLER_REGISTRY.get(handler_name)
    if handler_cls:
        container_instance._handler = handler_cls()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Direct tmux calls (self._tmux) | Transport abstraction (self._transport) | Phase 25 (2026-03-29) | GsdAgent and TaskAgent still have dead _tmux references |
| Agent subclass per type | Handler protocol + composition | Phase 28 (this phase) | Eliminates class hierarchy, enables handler x transport matrix |
| Hardcoded agent routing in RuntimeAPI | hasattr duck typing | Phase 27 (2026-03-30) | Must preserve or update these checks during extraction |

## Open Questions

1. **Lifecycle FSM selection per handler type**
   - What we know: GsdAgent uses GsdLifecycle, CompanyAgent/FulltimeAgent use EventDrivenLifecycle, ContinuousAgent uses ContinuousLifecycle, TaskAgent uses base ContainerLifecycle
   - What's unclear: Should lifecycle FSM be driven by handler type, or should it be a separate config field in agent-types.yaml?
   - Recommendation: Drive by handler type initially (session -> ContainerLifecycle or GsdLifecycle, conversation -> EventDrivenLifecycle, transient -> EventDrivenLifecycle). GSD-specific lifecycle is a handler-internal concern, not a container concern. If needed, add a `lifecycle` config field later.

2. **state/inner_state property overrides**
   - What we know: Three subclasses (GsdAgent, CompanyAgent, FulltimeAgent) override `state` and `inner_state` with identical OrderedSet handling logic. ContinuousAgent does the same.
   - What's unclear: Should this logic move to the base container (detecting compound states generically) or stay handler-specific?
   - Recommendation: Move the OrderedSet compound state handling to base AgentContainer. All compound FSMs use the same pattern. One implementation, zero overrides.

3. **ContinuousAgent's unique position**
   - What we know: ContinuousAgent uses tmux (session handler) but has its own ContinuousLifecycle FSM with cycle phases rather than GSD phases. It doesn't override receive_discord_message().
   - What's unclear: Does ContinuousAgent become a SessionHandler variant, or does it need its own handler type?
   - Recommendation: ContinuousAgent maps to the session handler type. Its cycle FSM (ContinuousLifecycle) is a lifecycle concern, not a handler concern. The session handler's on_start/on_stop hooks handle checkpoint restore. The advance_cycle method stays on the container (or a GSD-like state object).

4. **Whether to keep backward-compat thin wrappers**
   - What we know: RuntimeAPI uses hasattr checks for resolve_review, initialize_conversation, make_completion_event. Supervisor uses hasattr for _handle_signal.
   - What's unclear: How many external touchpoints reference specific container subclass types?
   - Recommendation: Keep subclasses as thin wrappers initially. They delegate to handlers for message processing but expose the hasattr-checkable methods as pass-throughs. This is lower risk and can be removed in a follow-up.

## Sources

### Primary (HIGH confidence)
- `src/vcompany/container/container.py` -- base AgentContainer, transport bridge, lifecycle
- `src/vcompany/container/factory.py` -- registry pattern, transport resolution, create_container
- `src/vcompany/transport/protocol.py` -- AgentTransport Protocol pattern to replicate
- `src/vcompany/agent/gsd_agent.py` -- largest handler extraction target (491 lines)
- `src/vcompany/agent/fulltime_agent.py` -- transient handler extraction target (308 lines)
- `src/vcompany/agent/company_agent.py` -- conversation handler extraction target (178 lines)
- `src/vcompany/agent/continuous_agent.py` -- session handler variant (251 lines)
- `src/vcompany/agent/task_agent.py` -- session handler variant (119 lines)
- `src/vcompany/models/agent_types.py` -- AgentTypeConfig to extend with handler field
- `src/vcompany/daemon/runtime_api.py` -- hasattr duck typing touchpoints
- `agent-types.yaml` -- config file to extend

## Metadata

**Confidence breakdown:**
- Architecture: HIGH -- full codebase access, all five subclasses read and analyzed
- Patterns: HIGH -- existing Protocol and registry patterns are clear precedent
- Pitfalls: HIGH -- dead code paths, import discrepancies, and hasattr coupling verified in source

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable internal refactor, no external dependencies)
