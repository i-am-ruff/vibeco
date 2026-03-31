---
phase: 33-container-autonomy
verified: 2026-03-31T16:59:48Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 33: Container Autonomy Verification Report

**Phase Goal:** Agent containers are fully autonomous -- state lives inside, duplicating a transport creates independent agents, and workers survive daemon restarts
**Verified:** 2026-03-31T16:59:48Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Worker derives data_dir from cwd, not from daemon-specified config path | VERIFIED | `Path.cwd() / ".vco-state" / agent_id` at container.py:54; WorkerConfig.data_dir defaults to None (config.py:21) |
| 2 | Worker can listen on a Unix domain socket for head connections | VERIFIED | `socket_server.py` exports `start_socket_server` backed by `asyncio.start_unix_server`; main.py `_run_socket` wires it |
| 3 | Worker has a ReconnectMessage type in its channel protocol | VERIFIED | `RECONNECT = "reconnect"` in `HeadMessageType` (worker messages.py:27); `ReconnectMessage` class at line 84; included in `HeadMessage` union at line 143 |
| 4 | Worker responds to ReconnectMessage with HealthReportMessage | VERIFIED | main.py:88 handles `isinstance(msg, ReconnectMessage)` in stdio mode; main.py:212 handles it in socket mode -- both send `HealthReportMessage` back |
| 5 | NativeTransport spawns workers with --socket flag and connects via Unix domain socket | VERIFIED | native.py:54 builds cmd with `--socket str(socket_path)`; `start_new_session=True` and `stdin=DEVNULL` at lines 66-71; `open_unix_connection` at line 92 |
| 6 | DockerChannelTransport runs containers in detached mode without --rm or -i | VERIFIED | docker_channel.py:63 has `"docker", "run", "-d"`; no `--rm` or `-i` flag in cmd construction; socket dir mounted at `/var/run/vco` |
| 7 | AgentHandle can send messages through a socket writer, not just process stdin | VERIFIED | agent_handle.py:60-63 `attach_socket` stores reader/writer; send() at line 72 uses socket writer first, falls back to process stdin |
| 8 | RoutingState persists transport_type for each agent | VERIFIED | routing_state.py:25 `transport_type: str = "native"`; company_root.py:527 writes it in `_save_routing` |
| 9 | Daemon reconstructs routing from RoutingState and reconnects to surviving workers on startup | VERIFIED | `reconnect_agents()` at company_root.py:541; called from `start()` at line 608; uses `transport.connect()` per routing.transport_type, `attach_socket`, sends `ReconnectMessage`, starts channel reader |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `packages/vco-worker/src/vco_worker/channel/socket_server.py` | Unix domain socket listener for worker side | VERIFIED | Exists, exports `start_socket_server`, `asyncio.start_unix_server`, stale socket cleanup with `unlink` |
| `packages/vco-worker/src/vco_worker/channel/messages.py` | ReconnectMessage added, RECONNECT in HeadMessageType, HeadMessage union updated | VERIFIED | RECONNECT at line 27, ReconnectMessage class at 84, union at 143 |
| `packages/vco-worker/src/vco_worker/container/container.py` | cwd-relative data_dir | VERIFIED | `Path.cwd() / ".vco-state" / agent_id` at line 54 |
| `packages/vco-worker/src/vco_worker/main.py` | Socket mode with --socket flag, ReconnectMessage handling | VERIFIED | `_run_socket` at line 157, `--socket` arg at 305, `isinstance(msg, ReconnectMessage)` at 88 and 212 |
| `src/vcompany/transport/channel/messages.py` | Identical ReconnectMessage addition (head-side copy) | VERIFIED | RECONNECT at line 27, ReconnectMessage at 84, union at 143 -- identical to worker copy |
| `src/vcompany/transport/channel_transport.py` | Protocol with spawn returning tuple and connect() method | VERIFIED | `async def spawn` returns `tuple[asyncio.StreamReader, asyncio.StreamWriter]`, `async def connect` at line 56 |
| `src/vcompany/transport/native.py` | Socket-based NativeTransport with spawn, connect | VERIFIED | `open_unix_connection`, `start_new_session=True`, `DEVNULL` stdin, `--socket` arg, `async def connect` |
| `src/vcompany/transport/docker_channel.py` | Detached Docker with socket mount | VERIFIED | `"docker", "run", "-d"`, `/var/run/vco` mount, no `--rm`/`-i`, `async def connect` |
| `src/vcompany/daemon/agent_handle.py` | attach_socket, reader property, socket-aware send/is_alive/stop | VERIFIED | `attach_socket` at line 60, `reader` property at 82, `is_closing()` checks at 138 and 156 |
| `src/vcompany/daemon/routing_state.py` | AgentRouting with transport_type field | VERIFIED | `transport_type: str = "native"` at line 25 |
| `src/vcompany/supervisor/company_root.py` | reconnect_agents(), socket hire() flow, handle.reader in _channel_reader | VERIFIED | `reconnect_agents` at line 541, called from `start()` at 608; `attach_socket` at 305 and 568; `handle.reader` at 324; no `handle._process.stdout` or `handle._process = process` references |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `main.py` | `socket_server.py` | `from vco_worker.channel.socket_server import start_socket_server` | WIRED | main.py:163 imports within `_run_socket`, called at line 262 |
| `main.py` | ReconnectMessage handling | `isinstance(msg, ReconnectMessage)` | WIRED | main.py:25 imports ReconnectMessage; handled at lines 88 and 212 |
| `native.py` | vco-worker `--socket` | subprocess spawn with `--socket` argument | WIRED | native.py:54 `cmd` includes `"--socket", str(socket_path)` |
| `agent_handle.py` | asyncio.StreamWriter | `attach_socket` stores reader/writer pair | WIRED | `_socket_reader`/`_socket_writer` PrivateAttrs; `attach_socket` populates them; `send()` uses `_socket_writer` |
| `company_root.py` | `routing_state.py` | `RoutingState.load() + AgentRouting.transport_type` | WIRED | line 557 `routing.transport_type` passed to `_get_transport`; line 527 `transport_type=transport_name` persisted |
| `company_root.py` | `native.py` | `transport.connect()` for reconnection | WIRED | line 558 `transport.connect(agent_id)` called inside `reconnect_agents` |
| `company_root.py` | `agent_handle.py` | `handle.attach_socket()` and `handle.reader` | WIRED | lines 305, 568 (`attach_socket`); line 324 (`handle.reader`) |

### Data-Flow Trace (Level 4)

State data (container memory) flows from worker cwd to `MemoryStore`. Channel data (messages) flows from socket reader through `_channel_reader` to handlers.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `container.py` | `data_dir` (memory path) | `Path.cwd() / ".vco-state" / agent_id` | Yes -- derives from process cwd at runtime | FLOWING |
| `agent_handle.py` | `_socket_reader` / `_socket_writer` | `attach_socket()` populated from `transport.spawn()` or `transport.connect()` | Yes -- asyncio.StreamReader/Writer connected to live Unix socket | FLOWING |
| `company_root._channel_reader` | `reader` (from `handle.reader`) | Socket reader attached in hire() or reconnect_agents() | Yes -- reads from live socket connection | FLOWING |
| `routing_state.py` | `transport_type` | Written by `_save_routing(handle, transport_name=...)` at hire time | Yes -- persisted to disk via `RoutingState.save()` | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| ReconnectMessage round-trips through framing | `uv run python -c "from vco_worker.channel.messages import ReconnectMessage; rm = ReconnectMessage(agent_id='test'); print(rm.type)"` | `reconnect` | PASS |
| WorkerConfig.data_dir defaults to None | `uv run python -c "from vco_worker.config import WorkerConfig; print(WorkerConfig(handler_type='s').data_dir)"` | `None` | PASS |
| AgentRouting.transport_type defaults to native | `uv run python -c "from vcompany.daemon.routing_state import AgentRouting; print(AgentRouting(agent_id='x').transport_type)"` | `native` | PASS |
| NativeTransport.transport_type returns native | `uv run python -c "from vcompany.transport.native import NativeTransport; print(NativeTransport().transport_type)"` | `native` | PASS |
| DockerChannelTransport.transport_type returns docker | `uv run python -c "from vcompany.transport.docker_channel import DockerChannelTransport; print(DockerChannelTransport().transport_type)"` | `docker` | PASS |
| start_socket_server importable | `uv run python -c "from vco_worker.channel.socket_server import start_socket_server; print(type(start_socket_server))"` | `<class 'function'>` | PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| AUTO-01 | 33-01, 33-03 | Agent state lives inside the execution environment -- not on the daemon side | SATISFIED | `WorkerContainer` uses `Path.cwd() / ".vco-state" / agent_id`; config.data_dir deprecated (None); state path is local to wherever cwd is set (container /workspace or native scratch dir) |
| AUTO-02 | 33-02, 33-03 | Duplicating a transport creates a fully independent agent -- no shared daemon-side state | SATISFIED | `NativeTransport._processes` and `DockerChannelTransport._containers` are per-instance dicts initialized in `__init__`; no module-level singletons; each `NativeTransport()` or `DockerChannelTransport()` instance tracks only its own agents; socket paths keyed by agent_id prevent collisions |
| AUTO-03 | 33-01, 33-02, 33-03 | Container survives daemon restart -- worker continues running, reconnects via transport channel | SATISFIED | Workers spawned with `start_new_session=True` and `stdin=DEVNULL` (no pipe dependency); Docker containers run detached (`-d`); `reconnect_agents()` called in `start()` loads RoutingState, calls `transport.connect(agent_id)`, sends `ReconnectMessage`, and resumes channel reading; stale entries cleaned if socket is gone |

No orphaned requirements: REQUIREMENTS.md maps AUTO-01, AUTO-02, AUTO-03 exclusively to Phase 33, and all three are claimed and satisfied by plans 33-01 through 33-03.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | -- | -- | -- | No anti-patterns found across modified files |

No TODOs, FIXMEs, placeholders, or stub patterns found in any of the 11 files modified by this phase.

### Human Verification Required

#### 1. Worker Survival After Daemon Kill

**Test:** Start a worker with `vco-worker --socket /tmp/test-worker.sock`, then kill the daemon process. Verify the socket file persists and a new daemon process can connect to it.
**Expected:** Worker process continues running; socket file exists; new connection accepted; HealthReport returned in response to ReconnectMessage.
**Why human:** Requires running live processes; cannot verify socket persistence behavior with static code analysis.

#### 2. Docker Container Detached Survival

**Test:** Run `docker run -d` via DockerChannelTransport, then stop the vco daemon. Verify container is still running via `docker ps`.
**Expected:** Docker container listed in `docker ps`; no auto-removal; socket mount still accessible on host.
**Why human:** Requires Docker daemon and a built `vco-agent` image; cannot verify at rest.

#### 3. State Path Independence Across Containers

**Test:** Spawn two workers with different agent_ids from the same NativeTransport. Confirm their `.vco-state/` directories are at their respective cwds and do not overlap.
**Expected:** Each worker writes to its own `{cwd}/.vco-state/{agent_id}/memory.db`.
**Why human:** cwd is set at spawn time; static analysis cannot prove two different cwds are used.

### Gaps Summary

No gaps found. All 9 observable truths are verified. All 11 artifacts exist, are substantive, and are wired. All 3 requirements (AUTO-01, AUTO-02, AUTO-03) are satisfied with direct implementation evidence. No blocker anti-patterns were found.

---

_Verified: 2026-03-31T16:59:48Z_
_Verifier: Claude (gsd-verifier)_
