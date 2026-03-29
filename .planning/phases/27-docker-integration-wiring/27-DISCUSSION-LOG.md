# Phase 27: Docker Integration Wiring - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-30
**Phase:** 27-docker-integration-wiring
**Areas discussed:** Per-agent transport deps, Auto-build strategy, Parametric agent setup, Type-check elimination, E2E hire-to-health flow, Agent-types file format, New type extensibility

---

## Per-Agent Transport Deps

| Option | Description | Selected |
|--------|-------------|----------|
| Factory extracts from spec | Factory reads docker_image from ChildSpec, merges with global transport_deps, passes to constructor. Daemon stays simple. | ✓ |
| Daemon builds per-agent deps | Daemon iterates agents and builds per-agent transport_deps dict. Factory stays dumb. | |
| Transport self-resolves | Pass full ChildSpec/context to transport constructor. Each transport extracts what it needs. | |

**User's choice:** Factory extracts from spec
**Notes:** User clarified that `vco hire <type> <name>` should know nothing about what to pass — all resolution lives in config. The caller just names a type and agent name.

---

## Auto-Build Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-build inline | Hire detects missing image, builds automatically, then continues. First hire takes longer but "just works." | ✓ |
| Fail with guidance | Hire fails with message to run `vco build` first. | |
| Both — auto + explicit | Auto-builds on hire AND provides `vco build` for explicit builds. | |

**User's choice:** Auto-build inline

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, add vco build | Explicit command for rebuilding after Dockerfile changes, CI, pre-warming. | ✓ |
| Not now | Auto-build covers the need, add later. | |

**User's choice:** Yes, add vco build

---

## Parametric Agent Setup

| Option | Description | Selected |
|--------|-------------|----------|
| Type-level config map | Config section maps agent types to parameters (tweakcc profile, settings). Type determines what gets injected. | ✓ |
| Per-agent in agents.yaml | Each agent entry specifies tweakcc_profile and settings directly. | |
| You decide | Claude picks based on existing patterns. | |

**User's choice:** Type-level config map

| Option | Description | Selected |
|--------|-------------|----------|
| At container start | setup() copies profile and settings into container after start, before launching Claude Code. | ✓ |
| You decide | Claude picks injection timing. | |

**User's choice:** At container start

| Option | Description | Selected |
|--------|-------------|----------|
| In agents.yaml | Add agent_types section to existing agents.yaml. | |
| Separate config file | New dedicated file for agent type definitions. | ✓ |
| You decide | Claude picks based on existing patterns. | |

**User's choice:** Separate config file
**Notes:** User emphasized this must be a **single source of truth for ALL agent types** — both Docker and non-Docker. `vco hire` lookups resolve from this file. Designed for drastic extensibility later.

---

## Type-Check Elimination

| Option | Description | Selected |
|--------|-------------|----------|
| Config-derived capabilities | Agent type config declares capabilities (gsd_driven, event_driven, etc.). Runtime checks capabilities, not type strings. | ✓ |
| You decide | Claude audits existing checks and picks best replacement per case. | |

**User's choice:** Config-derived capabilities

---

## E2E Hire-to-Health Flow

| Option | Description | Selected |
|--------|-------------|----------|
| Same checks, container layer added | Health = container running + agent alive. Same as DockerTransport.is_alive(). | |
| Docker status in health tree | Show Docker-specific info (container ID, image, uptime) alongside standard health. | |
| You decide | Claude determines useful health info from existing patterns. | ✓ |

**User's choice:** You decide

---

## Agent-Types Config File Format

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal viable | Start with what Phase 27 needs, extend later. | |
| Full schema upfront | Define complete schema now including future-facing fields. | ✓ |
| You decide | Claude designs minimal extensible schema. | |

**User's choice:** Full schema upfront

| Option | Description | Selected |
|--------|-------------|----------|
| Resource limits | CPU/memory limits for Docker containers. | |
| Environment variables | Per-type env vars injected into containers. | ✓ |
| Volume overrides | Additional volume mounts beyond standard. | ✓ |
| Network mode | Docker network mode per type. | |

**User's choice:** Environment variables, Volume overrides (resource limits and network mode deferred)

---

## New Type Extensibility

| Option | Description | Selected |
|--------|-------------|----------|
| Config points to class | agent-types.yaml has container_class field, factory has class registry. | ✓ |
| Convention-based discovery | Factory auto-discovers subclasses by scanning package. | |
| You decide | Claude picks registration mechanism. | |

**User's choice:** Config points to class

---

## Claude's Discretion

- Docker-specific health info in health tree
- Implementation details of factory dep extraction
- ChildSpec field additions for docker_image flow
- Capability check structure in runtime code
- Default values for agent-types config fields

## Deferred Ideas

None — discussion stayed within phase scope
