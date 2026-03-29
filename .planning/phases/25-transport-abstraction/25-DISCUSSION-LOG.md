# Phase 25: Transport Abstraction - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 25-transport-abstraction
**Areas discussed:** Protocol surface area, Signal mechanism, Strategist subprocess handling, Factory injection

---

## Protocol Surface Area

| Option | Description | Selected |
|--------|-------------|----------|
| Thin transport | Transport handles raw execution primitives only: setup env, teardown env, exec command, check alive, read/write files. Container keeps task queueing, idle gating, signal interpretation. | ✓ |
| Fat transport | Transport owns full agent lifecycle including task queue, signal watching, idle state. Container becomes thin coordinator. | |
| You decide | Claude's discretion based on Docker transport needs. | |

**User's choice:** Thin transport
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Include read_file/write_file now | Define on protocol even though LocalTransport delegates to pathlib. Docker-ready from day one. | ✓ |
| Defer to Docker phase | Skip file ops. Add when Docker actually needs them. | |
| You decide | Claude's discretion. | |

**User's choice:** Include now
**Notes:** None

---

## Signal Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Unix domain socket | vco signal writes to daemon's existing Unix socket. | |
| HTTP endpoint on daemon | Daemon exposes local HTTP endpoint. vco signal uses httpx to POST. More discoverable, easier to debug with curl. | ✓ |
| You decide | Claude's discretion. | |

**User's choice:** HTTP endpoint on daemon
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Full implementation | Build HTTP endpoint, implement vco signal CLI, update hooks. Sentinel files fully removed. | ✓ |
| Protocol + local shim | Define signal protocol but LocalTransport still uses temp files under the hood. | |
| You decide | Claude's discretion. | |

**User's choice:** Full implementation
**Notes:** None

---

## Strategist Subprocess Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, unify under transport | Strategist becomes a proper transport-managed agent. All subprocess invocations go through AgentTransport. | ✓ |
| No, Strategist stays internal | Strategist's piped subprocess calls stay as internal implementation detail. | |
| You decide | Claude's discretion. | |

**User's choice:** Yes, unify under transport
**Notes:** User clarified the core architecture: "Business Logic → Transport Layer → Agent Implementation. Business logic doesn't care how to send messages and how to receive them. Transport layer doesn't care where the agent is located or how it operates. It manages the lifecycle of the container transparently. The agent container can live on the network, in docker, or locally." Nothing stays internal — the Strategist is not special.

---

## Factory Injection

| Option | Description | Selected |
|--------|-------------|----------|
| Simple registry dict | Factory has a dict mapping transport name to class. New transports = add one line. | ✓ |
| Plugin discovery | Entry points or importlib-based discovery. More extensible but overkill. | |
| You decide | Claude's discretion. | |

**User's choice:** Simple registry dict
**Notes:** None

## Claude's Discretion

- How LocalTransport internally decides between tmux session and subprocess based on agent type/config
- HTTP endpoint path and payload format for signal delivery
- Whether AgentTransport is a Protocol or ABC
- How to migrate existing Claude Code hooks from temp file writes to HTTP calls

## Deferred Ideas

None — discussion stayed within phase scope
