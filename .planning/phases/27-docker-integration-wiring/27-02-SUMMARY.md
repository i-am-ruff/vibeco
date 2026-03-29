---
phase: 27-docker-integration-wiring
plan: 02
subsystem: infra
tags: [docker, docker-py, asyncio, click, cli]

# Dependency graph
requires:
  - phase: 26-docker-transport
    provides: DockerTransport using docker-py SDK, docker/Dockerfile
provides:
  - ensure_docker_image() async auto-build utility
  - build_image_sync() sync build for CLI
  - vco build CLI command with --force and --dockerfile-dir options
affects: [27-03, 27-04, hire-flow, docker-agent-lifecycle]

# Tech tracking
tech-stack:
  added: []
  patterns: [asyncio.to_thread for blocking docker-py calls, click command with Rich console output]

key-files:
  created:
    - src/vcompany/docker/__init__.py
    - src/vcompany/docker/build.py
    - src/vcompany/cli/build_cmd.py
  modified:
    - src/vcompany/cli/main.py

key-decisions:
  - "Reuse docker.from_env() pattern from DockerTransport for consistency"
  - "Separate async (ensure_docker_image) and sync (build_image_sync) interfaces for hire-flow vs CLI"

patterns-established:
  - "Docker utility module at src/vcompany/docker/ for build/image management"
  - "asyncio.to_thread wrapping for all blocking docker-py SDK calls"

requirements-completed: [WIRE-03]

# Metrics
duration: 1min
completed: 2026-03-29
---

# Phase 27 Plan 02: Docker Build & CLI Summary

**Async Docker image auto-build utility and vco build CLI command using docker-py SDK with asyncio.to_thread wrapping**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-29T23:12:07Z
- **Completed:** 2026-03-29T23:13:22Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Created ensure_docker_image() async function that checks for existing image before building, wrapped in asyncio.to_thread to avoid blocking the event loop
- Created build_image_sync() for CLI with force-rebuild support
- Added vco build CLI command with IMAGE argument, --force flag, and --dockerfile-dir option
- Registered build command in CLI group

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Docker build utility module** - `52251d7` (feat)
2. **Task 2: Create vco build CLI command** - `ce35a32` (feat)

## Files Created/Modified
- `src/vcompany/docker/__init__.py` - Docker module package init
- `src/vcompany/docker/build.py` - ensure_docker_image() async + build_image_sync() sync utilities
- `src/vcompany/cli/build_cmd.py` - vco build click command with Rich console output
- `src/vcompany/cli/main.py` - Added build command registration

## Decisions Made
- Reused docker.from_env() pattern from DockerTransport for consistency across codebase
- Separated async and sync build interfaces: ensure_docker_image for hire-flow integration, build_image_sync for CLI

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ensure_docker_image() ready to wire into hire flow (Plan 03)
- vco build command available for explicit pre-builds
- Docker module at src/vcompany/docker/ established for future utilities

---
*Phase: 27-docker-integration-wiring*
*Completed: 2026-03-29*
