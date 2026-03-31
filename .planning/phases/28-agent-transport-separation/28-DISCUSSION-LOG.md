# Phase 28: Agent-Transport Separation Refactor - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-31
**Phase:** 28-agent-transport-separation
**Areas discussed:** Handler abstraction, Message I/O, Composition mechanism, Migration strategy
**Mode:** auto (all areas auto-selected with recommended defaults)

---

## Handler Abstraction

| Option | Description | Selected |
|--------|-------------|----------|
| Protocol per handler type | Three Python Protocols (SessionHandler, ConversationHandler, TransientHandler) | ✓ |
| ABC base classes | Abstract base classes with enforced method signatures | |
| Duck typing only | No formal interface, just convention | |

**User's choice:** Protocol per handler type (auto-selected — consistent with AgentTransport from Phase 25)
**Notes:** User explicitly described the three handler types in conversation. This is the core insight driving the refactor.

---

## Message I/O Pattern

| Option | Description | Selected |
|--------|-------------|----------|
| Container has channel_id, uses comm_port | Store numeric channel_id on container, base class _send_discord | ✓ |
| Each handler manages its own I/O | Handlers call comm_port directly | |
| Route all responses through daemon socket | Containers use vco report for everything | |

**User's choice:** Container has channel_id, uses comm_port (auto-selected)
**Notes:** This fixes the current bug where _send_discord passes channel names instead of numeric IDs. Base class implementation eliminates duplication across 5 subclasses.

---

## Composition Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Factory composes from config | agent-types.yaml gains handler field, factory builds handler+transport+container | ✓ |
| Subclass per combination | Keep inheritance hierarchy, one class per handler×transport | |
| Runtime mixin injection | Compose at runtime via multiple inheritance | |

**User's choice:** Factory composes from config (auto-selected — extends existing factory pattern)
**Notes:** Follows the same registry pattern already used for transports (Phase 25 D-07) and container classes (Phase 27 D-13).

---

## Migration Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Extract then deprecate | Create handlers, migrate subclasses, remove old classes | ✓ |
| Big bang rewrite | Replace everything at once | |
| Parallel implementation | New system alongside old, switch over gradually | |

**User's choice:** Extract then deprecate (auto-selected)
**Notes:** Safest approach — each subclass can be migrated independently.

---

## Claude's Discretion

- Whether handler protocols need async methods or sync methods
- Internal state management approach for SessionHandler
- Whether to keep agent subclasses as thin wrappers during transition
- How GSD lifecycle integrates with extracted SessionHandler

## Deferred Ideas

- Network transport (v4)
- Per-agent handler overrides
- Handler hot-swapping at runtime
- Lifecycle components as composable plugins
