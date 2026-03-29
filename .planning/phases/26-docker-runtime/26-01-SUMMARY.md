---
phase: 26-docker-runtime
plan: 01
subsystem: infra
tags: [docker, docker-py, dockerfile, claude-code, tweakcc, pydantic]

# Dependency graph
requires:
  - phase: 25-transport-abstraction
    provides: AgentTransport protocol, AgentConfig.transport field
provides:
  - Docker agent image definition (Dockerfile)
  - Default Claude Code settings for containers (settings.json)
  - AgentConfig.docker_image field for image selection
  - docker-py SDK as project dependency
affects: [26-02-docker-transport]

# Tech tracking
tech-stack:
  added: [docker-py 7.1.0]
  patterns: [optional pydantic field for transport-specific config]

key-files:
  created:
    - docker/Dockerfile
    - docker/settings.json
  modified:
    - src/vcompany/models/config.py
    - pyproject.toml

key-decisions:
  - "docker_image is a plain optional string with no validator -- factory validates at runtime"
  - "Dockerfile uses python3/python3-venv/python3-pip packages (Debian naming) rather than python3.12 specifics"

patterns-established:
  - "Transport-specific config fields as optional on AgentConfig (None when not applicable)"

requirements-completed: [DOCK-02, DOCK-05]

# Metrics
duration: 1min
completed: 2026-03-29
---

# Phase 26 Plan 01: Docker Image Infrastructure Summary

**Docker agent Dockerfile (node:22-slim + Claude Code + tweakcc), settings.json for container permissions, docker-py SDK dependency, and AgentConfig.docker_image field**

## Performance

- **Duration:** 1 min 25s
- **Started:** 2026-03-29T21:13:16Z
- **Completed:** 2026-03-29T21:14:41Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added docker-py 7.1.0 SDK as project dependency for DockerTransport implementation
- Added docker_image: str | None = None field to AgentConfig model for per-agent image selection
- Created Dockerfile defining universal Claude Code agent image (node:22-slim base, Python 3.12, git, tmux, uv, Claude Code, tweakcc patches)
- Created settings.json granting full Claude Code tool permissions inside containers

## Task Commits

Each task was committed atomically:

1. **Task 1: Add docker-py dependency and AgentConfig.docker_image field** - `3fdf8d6` (feat)
2. **Task 2: Create Dockerfile and default settings.json** - `d048416` (feat)

## Files Created/Modified
- `docker/Dockerfile` - Universal Claude Code agent image build definition
- `docker/settings.json` - Default Claude Code permissions baked into image
- `src/vcompany/models/config.py` - AgentConfig with docker_image optional field
- `pyproject.toml` - docker>=7.1,<8 dependency added

## Decisions Made
- docker_image field has no Pydantic validator -- runtime validation in factory when transport is "docker"
- Dockerfile uses Debian package names (python3, python3-venv) rather than version-specific (python3.12) for compatibility with node:22-slim base

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Dockerfile and settings.json ready for docker build (not built in this plan -- build tested in integration)
- AgentConfig.docker_image field ready for DockerTransport to consume in plan 26-02
- docker-py SDK available for DockerTransport implementation

## Self-Check: PASSED

All files exist. All commits verified.

---
*Phase: 26-docker-runtime*
*Completed: 2026-03-29*
