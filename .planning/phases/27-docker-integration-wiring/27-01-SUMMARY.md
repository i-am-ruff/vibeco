---
phase: 27-docker-integration-wiring
plan: 01
subsystem: infra
tags: [pydantic, yaml, agent-types, factory, transport, docker]

# Dependency graph
requires:
  - phase: 26-docker-transport
    provides: DockerTransport class, AgentTransport protocol, ChildSpec.transport field
provides:
  - AgentTypeConfig and AgentTypesConfig Pydantic models
  - agent-types.yaml single source of truth for agent type definitions
  - Factory smart per-transport dep resolution via _resolve_transport_deps()
  - Daemon loads agent-types config at startup and injects into factory
affects: [27-02, 27-03, 27-04]

# Tech tracking
tech-stack:
  added: []
  patterns: [module-level config injection via set/get pattern, per-transport dep resolution]

key-files:
  created:
    - src/vcompany/models/agent_types.py
    - agent-types.yaml
  modified:
    - src/vcompany/container/factory.py
    - src/vcompany/daemon/daemon.py

key-decisions:
  - "Factory resolves per-transport deps from agent type config instead of passing global dict"
  - "Built-in defaults ensure system works without agent-types.yaml file on disk"
  - "Module-level set/get pattern for agent types config avoids threading it through constructors"

patterns-established:
  - "Agent type config pattern: Pydantic model + YAML file + built-in defaults fallback"
  - "Per-transport dep resolution: factory partitions global deps by transport name"

requirements-completed: [WIRE-01, WIRE-02, WIRE-07]

# Metrics
duration: 3min
completed: 2026-03-29
---

# Phase 27 Plan 01: Agent Types Config and Factory Wiring Summary

**AgentTypeConfig Pydantic models with agent-types.yaml as single source of truth, factory smart per-transport dep resolution routing docker_image to DockerTransport and tmux_manager to LocalTransport**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-29T23:11:58Z
- **Completed:** 2026-03-29T23:14:37Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- AgentTypeConfig and AgentTypesConfig models with full schema (transport, docker_image, capabilities, gsd_command, env, volumes)
- agent-types.yaml at repo root with all 5 existing agent types plus docker-gsd type
- Factory _resolve_transport_deps() correctly partitions deps: LocalTransport gets tmux_manager, DockerTransport gets docker_image + project_name
- Daemon loads agent-types config at startup with built-in defaults fallback

## Task Commits

Each task was committed atomically:

1. **Task 1: Create AgentTypeConfig model, loader, and default agent-types.yaml** - `0bcca66` (feat)
2. **Task 2: Wire factory smart dep resolution and daemon config loading** - `a89f4a9` (feat)

## Files Created/Modified
- `src/vcompany/models/agent_types.py` - AgentTypeConfig/AgentTypesConfig Pydantic models, load_agent_types(), get_default_config(), _BUILTIN_DEFAULTS
- `agent-types.yaml` - Default agent type definitions for all types including docker-gsd
- `src/vcompany/container/factory.py` - _resolve_transport_deps(), set/get_agent_types_config(), updated create_container() to use smart resolution
- `src/vcompany/daemon/daemon.py` - Loads agent-types.yaml at startup, adds project_name to transport_deps

## Decisions Made
- Factory resolves per-transport deps from agent type config instead of passing a single global dict (D-01)
- Built-in defaults match current hardcoded behavior so system works without agent-types.yaml
- Module-level set/get pattern for config avoids threading it through 4 layers of constructors

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Agent types config system is the foundation for all remaining Phase 27 plans
- Plan 02 (auto-build), Plan 03 (parametric setup), and Plan 04 (e2e wiring) can proceed
- Factory correctly resolves deps for both local and docker transports

---
*Phase: 27-docker-integration-wiring*
*Completed: 2026-03-29*
