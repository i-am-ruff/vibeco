---
phase: 28-agent-transport-separation
verified: 2026-03-31T05:30:00Z
status: passed
score: 8/8 must-haves verified
gaps:
  - truth: "GsdAgent and TaskAgent dead code (self._tmux, self._launch_tmux_session) is removed"
    status: resolved
    reason: "Fixed inline — TaskAgent.start() now delegates to super().start(). Commit 0c82300."
    artifacts:
      - path: "src/vcompany/agent/task_agent.py"
        issue: "Lines 112-113: `if self._tmux is not None and self._needs_tmux_session:` + `await self._launch_tmux_session()`. Neither _tmux nor _launch_tmux_session exist on the base class any more, so the guard is always False but the stale reference remains."
    missing:
      - "Replace TaskAgent.start() body with `await super().start()` (the base container handles FSM start, memory open, handler on_start, and transport launch)"
      - "Remove the dead `_launch_tmux_session` reference from task_agent.py"
---

# Phase 28: Agent Transport Separation Verification Report

**Phase Goal:** Extract handler types (tmux session, resume-conversation, memory-based transient) from agent subclasses into composable pieces orthogonal to transport (native, Docker, network). Any handler type can run on any transport without new classes.
**Verified:** 2026-03-31T05:30:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Three handler protocols exist as @runtime_checkable Python Protocols with async handle_message/on_start/on_stop methods | VERIFIED | `protocol.py` defines SessionHandler, ConversationHandler, TransientHandler; isinstance checks pass at runtime |
| 2 | Base AgentContainer has a consolidated `_send_discord()` method using SendMessagePayload from daemon.comm | VERIFIED | `container.py` lines 391-403; no `_send_discord` in any subclass `__dict__` |
| 3 | Base AgentContainer stores `_channel_id` and delegates `receive_discord_message()` to injected `_handler` | VERIFIED | `container.py` lines 84-86, 405-424; MentionRouterCog.register_agent sets `container._channel_id` at registration |
| 4 | Base AgentContainer has compound state/inner_state handling (OrderedSet) in the base class, not duplicated in subclasses | VERIFIED | `container.py` lines 90-113; ContinuousAgent no longer overrides state/inner_state |
| 5 | Three concrete handler implementations exist satisfying their respective protocols | VERIFIED | GsdSessionHandler, StrategistConversationHandler, PMTransientHandler all pass isinstance checks |
| 6 | agent-types.yaml has a handler field on every agent type entry, factory has `_HANDLER_REGISTRY` and injects handler from config | VERIFIED | All 6 entries in agent-types.yaml have handler field; factory._HANDLER_REGISTRY has 3 entries; create_container injects via D-08 |
| 7 | Agent subclasses are thin wrappers (lifecycle FSM + domain methods only) — CompanyAgent, FulltimeAgent, GsdAgent, ContinuousAgent thinned | VERIFIED | No `_send_discord`, `state`, `inner_state`, or `receive_discord_message` in any of these 4 subclass `__dict__` |
| 8 | Dead code paths (self._tmux, _launch_tmux_session) removed from GsdAgent and TaskAgent | FAILED | GsdAgent start() correctly removed; TaskAgent.start() still contains `if self._tmux is not None and self._needs_tmux_session: await self._launch_tmux_session()` at lines 112-113 |

**Score:** 7/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/vcompany/handler/__init__.py` | Package init re-exporting 6 names (3 protocols + 3 impls) | VERIFIED | Exports all 6 names; `__all__` correct |
| `src/vcompany/handler/protocol.py` | SessionHandler, ConversationHandler, TransientHandler @runtime_checkable | VERIFIED | All three defined with `@runtime_checkable`; async handle_message/on_start/on_stop |
| `src/vcompany/handler/session.py` | GsdSessionHandler satisfying SessionHandler protocol | VERIFIED | `isinstance(GsdSessionHandler(), SessionHandler)` passes; handles [Review Decision] + [Task Assigned] |
| `src/vcompany/handler/conversation.py` | StrategistConversationHandler satisfying ConversationHandler protocol | VERIFIED | `isinstance(StrategistConversationHandler(), ConversationHandler)` passes; calls container._conversation.send() |
| `src/vcompany/handler/transient.py` | PMTransientHandler satisfying TransientHandler protocol | VERIFIED | `isinstance(PMTransientHandler(), TransientHandler)` passes; dispatches [Phase Complete], [Task Completed], [Task Failed], [Request Assignment], [Health Change] |
| `src/vcompany/container/container.py` | Consolidated _send_discord, _channel_id, _handler, OrderedSet state | VERIFIED | All four present; handler hooks in start()/stop() |
| `src/vcompany/models/agent_types.py` | AgentTypeConfig with `handler: str | None = None` field and _BUILTIN_DEFAULTS | VERIFIED | Field present; all 5 builtin entries have handler values |
| `agent-types.yaml` | All entries have handler field | VERIFIED | All 6 entries (gsd, continuous, fulltime, company, task, docker-gsd) have handler field |
| `src/vcompany/container/factory.py` | _HANDLER_REGISTRY + handler injection in create_container | VERIFIED | Registry has 3 entries; create_container injects via lines 179-194 |
| `src/vcompany/agent/gsd_agent.py` | Thin wrapper: no _send_discord, state, inner_state, receive_discord_message | VERIFIED | None of the four methods in GsdAgent.__dict__ |
| `src/vcompany/agent/company_agent.py` | Thin wrapper: no _send_discord, state, inner_state, receive_discord_message | VERIFIED | None of the four methods in CompanyAgent.__dict__ |
| `src/vcompany/agent/fulltime_agent.py` | Thin wrapper: no _send_discord, state, inner_state, receive_discord_message, _run_stuck_detector, _auto_assign_next | VERIFIED | None of the six methods in FulltimeAgent.__dict__ |
| `src/vcompany/agent/continuous_agent.py` | No state, inner_state overrides | VERIFIED | Comment "# state/inner_state inherited from base container" at line 77 |
| `src/vcompany/agent/task_agent.py` | No dead _tmux/_launch_tmux_session references in start() | FAILED | Lines 112-113 still reference self._tmux and self._launch_tmux_session |
| `src/vcompany/bot/cogs/mention_router.py` | register_agent sets container._channel_id | VERIFIED | Line 73: `container._channel_id = channel_id`; unregister_agent clears it at line 88 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `handler/protocol.py` | `container/container.py` | `AgentContainer._handler` typed as Any, checked via Protocol | VERIFIED | container.py line 84: `self._handler: Any = None`; receive_discord_message delegates to handler |
| `container/container.py` | `daemon/comm.py` | `_send_discord` imports `SendMessagePayload` | VERIFIED | Lazy import inside method body at line 400 |
| `handler/session.py` | `container/container.py` | handle_message accesses container._pending_review, container._current_assignment | VERIFIED | Lines 74-97 in session.py |
| `handler/conversation.py` | `strategist/conversation.py` | handle_message calls `container._conversation.send()` | VERIFIED | Line 47 in conversation.py |
| `handler/transient.py` | `container/container.py` | handle_message calls container._send_discord for PM actions | VERIFIED | Lines 173, 199 in transient.py |
| `container/factory.py` | `handler/__init__.py` | `_HANDLER_REGISTRY` maps strings to handler classes | VERIFIED | factory.py lines 40-44 |
| `container/factory.py` | `container/container.py` | `container_instance._handler = handler_cls()` | VERIFIED | factory.py line 190 |
| `agent-types.yaml` | `models/agent_types.py` | handler field parsed by AgentTypeConfig | VERIFIED | AgentTypeConfig.handler field; load_agent_types tested |
| `bot/cogs/mention_router.py` | `container/container.py` | register_agent sets container._channel_id at registration | VERIFIED | mention_router.py line 73 |
| `agent/gsd_agent.py` | `handler/session.py` | GsdAgent.start() calls self._handler.on_start(self) | VERIFIED | gsd_agent.py lines 288-289 |

### Data-Flow Trace (Level 4)

Not applicable — this phase produces infrastructure abstractions (protocols, handlers, factory wiring), not components that render dynamic data from external sources.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Handler protocols importable and isinstance checks pass | `uv run python -c "from vcompany.handler.protocol import ...; isinstance checks"` | All three isinstance checks passed | PASS |
| Handler registry contains 3 entries | `uv run python -c "from vcompany.container.factory import get_handler_registry; ..."` | session->GsdSessionHandler, conversation->StrategistConversationHandler, transient->PMTransientHandler | PASS |
| AgentContainer has _handler, _channel_id, OrderedSet state | `uv run python -c "from vcompany.container.container import AgentContainer; ..."` | All fields present, OrderedSet round-trip verified | PASS |
| AgentTypeConfig handler field and agent-types.yaml | `uv run python -c "from vcompany.models.agent_types import ...; load_agent_types(...)"` | All builtin defaults and YAML entries have correct handler values | PASS |
| Subclass thinning | `uv run python -c "from vcompany.agent.gsd_agent import GsdAgent; ..."` | GsdAgent, CompanyAgent, FulltimeAgent, ContinuousAgent pass; TaskAgent has dead _tmux reference | PARTIAL |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| HSEP-01 | 28-01 | Three @runtime_checkable handler Protocols | SATISFIED | protocol.py verified; isinstance checks pass |
| HSEP-02 | 28-01 | _send_discord consolidated in base, no duplicates | SATISFIED | No _send_discord in any subclass __dict__ |
| HSEP-03 | 28-01 | Base delegates receive_discord_message to handler, stores _channel_id | SATISFIED | container.py lines 84-86, 405-424; mention_router wires _channel_id |
| HSEP-04 | 28-03 | agent-types.yaml has handler field on every entry | SATISFIED | All 6 entries verified |
| HSEP-05 | 28-03 | Factory has _HANDLER_REGISTRY and injects handler from config | SATISFIED | factory.py lines 40-44, 179-194 |
| HSEP-06 | 28-02 + 28-04 | Agent subclasses are thin wrappers (lifecycle FSM + domain methods) | SATISFIED for 4/5 | GsdAgent, CompanyAgent, FulltimeAgent, ContinuousAgent thinned; TaskAgent has dead code but not in receive_discord_message |
| HSEP-07 | 28-04 | Dead code (self._tmux, _launch_tmux_session) removed from GsdAgent and TaskAgent | BLOCKED | GsdAgent: DONE. TaskAgent.start() lines 112-113 still reference self._tmux and self._launch_tmux_session |
| HSEP-08 | 28-01 | Base AgentContainer handles OrderedSet compound state/inner_state | SATISFIED | container.py lines 90-113; no duplicate overrides in subclasses |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/vcompany/agent/task_agent.py` | 112-113 | Dead `self._tmux` and `self._launch_tmux_session()` references after base class removed both | Warning | Non-blocking: the `if self._tmux is not None` guard is always False since `_tmux` no longer exists on the base. Code never executes but violates HSEP-07 contract. The task agent bypasses the transport-based start flow that the base implements. |

### Human Verification Required

None — all relevant checks were programmatically verifiable.

### Gaps Summary

One gap blocks full HSEP-07 compliance: `TaskAgent.start()` was not updated to remove the dead `_tmux` references. The Plan 04 summary claims this was done ("Task 1: Fix container.start() handler hook ordering, wire _channel_id, thin GsdAgent + TaskAgent — 977c42c") but the actual file at lines 108-113 still contains the old code pattern:

```python
async def start(self) -> None:
    """Start the task agent in tmux."""
    self._lifecycle.start()
    await self.memory.open()
    if self._tmux is not None and self._needs_tmux_session:
        await self._launch_tmux_session()
```

The plan specified replacing this with `await super().start()`. The guard `if self._tmux is not None` is permanently False because `_tmux` no longer exists on the base class (the base switched to `_transport` in a prior phase). The code is inert but is the exact dead code HSEP-07 required removing.

**Root cause:** The plan execution for Plan 04 Task 1 thinned GsdAgent correctly (removing _send_discord, state, inner_state, receive_discord_message) but missed the TaskAgent start() body replacement.

**Fix:** Replace TaskAgent.start() with:
```python
async def start(self) -> None:
    """Start the task agent via base container transport."""
    await super().start()
```

All other 7 requirements are fully satisfied. The handler composition architecture is operational: handlers inject cleanly, protocol isinstance checks work, factory wires handlers from config, and all agent subclasses delegate message handling through the base container to the injected handler.

---

_Verified: 2026-03-31T05:30:00Z_
_Verifier: Claude (gsd-verifier)_
