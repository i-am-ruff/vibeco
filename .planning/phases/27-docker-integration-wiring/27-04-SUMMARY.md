---
phase: 27-docker-integration-wiring
plan: 04
subsystem: infra
tags: [docker, transport, auto-build, tweakcc, health, hire-flow]

# Dependency graph
requires:
  - phase: 27-02
    provides: Docker build utilities (ensure_docker_image)
  - phase: 27-03
    provides: Factory per-transport deps resolution, agent-types config module-level set/get
provides:
  - DockerTransport parametric setup (tweakcc profile and settings injection)
  - Auto-build in hire flow for Docker agents
  - Full e2e Docker agent hire path (CLI -> RuntimeAPI -> CompanyRoot -> factory -> DockerTransport)
  - Transport-specific health reporting fields
affects: [docker-agents, health-tree-rendering, hire-workflow]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "docker cp for host-to-container profile copying in async context"
    - "duck-typed transport inspection in health_report() via hasattr"
    - "agent_type parameter threaded from CLI through RuntimeAPI to CompanyRoot"

key-files:
  created: []
  modified:
    - src/vcompany/transport/docker.py
    - src/vcompany/container/factory.py
    - src/vcompany/container/container.py
    - src/vcompany/supervisor/company_root.py
    - src/vcompany/daemon/runtime_api.py
    - src/vcompany/cli/hire_cmd.py
    - src/vcompany/container/health.py

key-decisions:
  - "Auto-build placed in company_root.hire() not factory -- factory is sync, ensure_docker_image is async, build once per hire not per restart"
  - "hire_cmd passes TYPE as both template and agent_type -- graceful fallback for template-only types"
  - "Transport type detection in health_report uses hasattr duck typing on _image attribute"

patterns-established:
  - "agent_type param threaded through full hire chain: CLI -> daemon socket -> RuntimeAPI -> CompanyRoot"
  - "Transport-specific health fields as optional on HealthReport (backward compatible)"

requirements-completed: [WIRE-04, WIRE-06]

# Metrics
duration: 3min
completed: 2026-03-29
---

# Phase 27 Plan 04: Docker Integration Wiring Summary

**Parametric DockerTransport setup with tweakcc/settings injection, auto-build in hire flow, and transport-aware health reporting**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-29T23:21:11Z
- **Completed:** 2026-03-29T23:24:35Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- DockerTransport.setup() applies tweakcc profile and custom settings.json at container start time (D-06, WIRE-04)
- Auto-build triggers via ensure_docker_image() when Docker agent is hired and image is missing (D-03)
- Full e2e hire path wired: vco hire TYPE NAME -> daemon -> RuntimeAPI -> CompanyRoot (config lookup, auto-build, ChildSpec with transport) -> factory -> DockerTransport (WIRE-06)
- HealthReport includes transport_type, docker_container_id, and docker_image for Docker agents

## Task Commits

Each task was committed atomically:

1. **Task 1: Add parametric setup to DockerTransport and pass setup kwargs through container** - `c5b9820` (feat)
2. **Task 2: Wire auto-build into hire flow, update company_root.hire for Docker, add transport info to health** - `9a197e9` (feat)

## Files Created/Modified
- `src/vcompany/transport/docker.py` - Added _apply_tweakcc_profile() and _apply_settings() methods, parametric kwargs in setup()
- `src/vcompany/container/factory.py` - Extracts tweakcc_profile/settings_json from agent type config, sets _transport_setup_kwargs on container
- `src/vcompany/container/container.py` - Added _transport_setup_kwargs attribute, spreads into transport.setup(); health_report() populates transport info
- `src/vcompany/supervisor/company_root.py` - hire() accepts agent_type, does config lookup, calls ensure_docker_image for Docker, uses config for ChildSpec
- `src/vcompany/daemon/runtime_api.py` - hire() accepts and passes agent_type to CompanyRoot
- `src/vcompany/cli/hire_cmd.py` - Passes TYPE as agent_type in hire call
- `src/vcompany/container/health.py` - HealthReport gains transport_type, docker_container_id, docker_image optional fields

## Decisions Made
- Auto-build placed in company_root.hire() not factory -- factory is sync, ensure_docker_image is async, build should happen once per hire not on every container restart
- hire_cmd passes TYPE as both template and agent_type -- graceful fallback for template-only types like "generic" or "researcher"
- Transport type detection in health_report uses hasattr duck typing on _image attribute (consistent with Phase 27 decision on duck typing)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 27 (Docker Integration Wiring) is now complete -- all 4 plans executed
- Full Docker agent lifecycle wired end-to-end: agent-types config -> factory deps -> auto-build -> DockerTransport with parametric setup -> health reporting
- Ready for milestone validation or next milestone planning

---
*Phase: 27-docker-integration-wiring*
*Completed: 2026-03-29*
