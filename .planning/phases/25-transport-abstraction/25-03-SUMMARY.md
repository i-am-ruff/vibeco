---
phase: 25-transport-abstraction
plan: 03
subsystem: container
tags: [transport-abstraction, agent-transport, factory-registry, push-signals, strategist]

# Dependency graph
requires:
  - phase: 25-transport-abstraction plan 01
    provides: AgentTransport protocol, LocalTransport, NoopTransport, AgentConfig.transport field
  - phase: 25-transport-abstraction plan 02
    provides: SignalRouter, signal HTTP endpoint, vco signal CLI
provides:
  - Transport-abstracted AgentContainer (zero TmuxManager imports)
  - Transport registry in factory with AgentConfig.transport lookup (D-07)
  - Push-based signal delivery via _handle_signal callback
  - Transport-based StrategistConversation with subprocess fallback
  - Full transport_deps plumbing chain (Daemon -> CompanyRoot -> ProjectSupervisor -> Supervisor -> Factory -> Container)
affects: [docker-transport, future-transport-backends]

# Tech tracking
tech-stack:
  added: []
  patterns: [transport registry lookup in factory, transport_deps injection pattern, push-based signal callback]

key-files:
  created: []
  modified:
    - src/vcompany/container/container.py
    - src/vcompany/container/factory.py
    - src/vcompany/container/child_spec.py
    - src/vcompany/supervisor/supervisor.py
    - src/vcompany/supervisor/company_root.py
    - src/vcompany/supervisor/project_supervisor.py
    - src/vcompany/daemon/daemon.py
    - src/vcompany/strategist/conversation.py
    - src/vcompany/agent/company_agent.py
    - tests/test_container_tmux_bridge.py

key-decisions:
  - "ChildSpec gets transport field (default 'local') as cleanest path for factory to determine transport"
  - "Factory instantiates transport from registry per agent, not reusing a shared instance"
  - "StrategistConversation keeps subprocess fallback when no transport injected (backward compat)"
  - "Signal router passed through full supervisor chain for push-based delivery registration"

patterns-established:
  - "Transport registry pattern: _TRANSPORT_REGISTRY maps name -> class, factory instantiates with transport_deps"
  - "transport_deps injection: daemon passes raw deps, factory instantiates correct transport class"
  - "Push-based signal callback: container._handle_signal registered with daemon's SignalRouter"

requirements-completed: [TXPT-03, TXPT-04]

# Metrics
duration: 9min
completed: 2026-03-29
---

# Phase 25 Plan 03: Transport Integration Summary

**Complete transport abstraction: container, factory, supervisor chain, and strategist all use AgentTransport with push-based signals replacing sentinel file polling**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-29T18:41:47Z
- **Completed:** 2026-03-29T18:50:44Z
- **Tasks:** 3 (+ 1 deviation)
- **Files modified:** 10

## Accomplishments
- Rewired AgentContainer to use injected AgentTransport exclusively -- zero TmuxManager imports
- Removed all sentinel file logic (_SIGNAL_DIR, _read_signal, _clear_signal, _wait_for_signal, _watch_idle_signals)
- Added push-based _handle_signal callback replacing polling-based idle watcher
- Workspace trust acceptance uses transport.send_keys() instead of direct tmux pane access
- Added _TRANSPORT_REGISTRY to factory with "local" -> LocalTransport (D-07 pattern)
- Factory reads ChildSpec.transport and instantiates from registry with transport_deps
- Replaced tmux_manager parameter with transport_deps throughout full supervisor chain
- Wired signal_router through Daemon -> CompanyRoot -> ProjectSupervisor -> Supervisor
- StrategistConversation uses transport.exec() and transport.exec_streaming() with subprocess fallback
- Updated all 19 container tests to use transport-based API

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewire AgentContainer to use AgentTransport and push-based signals** - `db76d86` (feat)
2. **Task 2: Rewire factory with registry lookup, supervisor chain, and daemon** - `44f1c76` (feat)
3. **Task 3: Rewire StrategistConversation to use AgentTransport** - `769c9a3` (feat)
4. **[Rule 3 - Blocking] Update tests for transport abstraction** - `151e7dc` (test)

## Files Created/Modified
- `src/vcompany/container/container.py` - Transport-abstracted AgentContainer with push-based signals
- `src/vcompany/container/factory.py` - Transport registry and D-07 registry lookup
- `src/vcompany/container/child_spec.py` - Added transport field (default "local")
- `src/vcompany/supervisor/supervisor.py` - transport_deps + signal_router replacing tmux_manager
- `src/vcompany/supervisor/company_root.py` - transport_deps + signal_router plumbing
- `src/vcompany/supervisor/project_supervisor.py` - transport_deps + signal_router plumbing
- `src/vcompany/daemon/daemon.py` - Creates transport_deps dict, passes signal_router to CompanyRoot
- `src/vcompany/strategist/conversation.py` - Transport-based exec with subprocess fallback
- `src/vcompany/agent/company_agent.py` - Passes self._transport to StrategistConversation
- `tests/test_container_tmux_bridge.py` - Rewritten for transport-based API (19 tests passing)

## Decisions Made
- Added `transport: str = "local"` to ChildSpec as the cleanest path for factory transport lookup (vs modifying ContainerContext)
- Factory creates a new LocalTransport per container from transport_deps rather than sharing a single instance -- each transport tracks its own agent sessions
- StrategistConversation keeps original subprocess code as fallback when no transport is injected, enabling backward compatibility
- Signal router is passed through the full supervisor chain so containers at any level can register for push-based signal delivery

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated test suite for transport abstraction**
- **Found during:** Task 1 completion
- **Issue:** tests/test_container_tmux_bridge.py used old tmux_manager parameter and sentinel file APIs that no longer exist
- **Fix:** Rewrote all 19 tests to use MockTransport, added tests for _handle_signal and task queue drain
- **Files modified:** tests/test_container_tmux_bridge.py
- **Commit:** 151e7dc

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Transport abstraction is complete -- business logic never imports TmuxManager
- Adding new transport backends requires only adding one line to _TRANSPORT_REGISTRY
- DockerTransport (Phase 26) can be added to the registry without touching container/supervisor code
- Signal delivery is push-based end-to-end (daemon signal_router -> container._handle_signal)

## Self-Check: PASSED

All 10 modified files verified present. All 4 commit hashes verified in git log.

---
*Phase: 25-transport-abstraction*
*Completed: 2026-03-29*
