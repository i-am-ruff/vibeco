# Phase 33: Container Autonomy - Research

**Researched:** 2026-03-31
**Domain:** Agent state isolation, transport duplication, daemon restart survival
**Confidence:** HIGH

## Summary

Phase 33 requires three changes to the existing vco-head/vco-worker architecture: (1) agent state files must live inside the worker's execution environment rather than at daemon-specified paths, (2) duplicating a transport and sending a new config blob must produce a fully independent agent with zero shared state, and (3) workers must continue running when the daemon restarts, with the head reconstructing routing from persisted state and reconnecting to surviving worker processes.

The existing codebase is well-positioned. WorkerContainer already composes MemoryStore, lifecycle FSM, checkpoints, and handler -- all inside the worker process. The main gaps are: the `data_dir` default points to `/tmp/vco-worker/data` which is daemon-controlled, RoutingState does not persist `transport_type` (needed for reconnection), there is no reconnection protocol in the channel messages, and the NativeTransport stdin/stdout pipe model does not survive daemon process death. The native transport will need a different I/O mechanism (Unix domain socket or named pipe) so workers can outlive the daemon process.

**Primary recommendation:** Use per-worker Unix domain sockets as the channel I/O mechanism (replacing stdin/stdout pipes for native transport), persist transport_type in RoutingState, add a reconnect message to the channel protocol, and make data_dir default to a worker-local path derived from cwd.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked -- all implementation choices at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key constraints:
- Containers run INSIDE transports, not as daemon-side Python objects
- Transport channel is the ONLY communication between head and worker
- Agent state must live inside the worker's execution environment filesystem
- Duplicating a transport + config blob creates a fully independent agent (no shared state)
- Workers must survive daemon restarts and reconnect via transport channel
- Worker sends current state on reconnection, head reconstructs routing
- Phase 30 vco-worker already has MemoryStore, checkpoint/restore, lifecycle FSM
- Phase 31 AgentHandle + routing state persistence supports daemon restart recovery
- Phase 32 NativeTransport/DockerChannelTransport spawn workers via subprocess

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTO-01 | Agent state (conversations, checkpoints, memory, session files) lives inside the execution environment -- not on the daemon side | WorkerConfig.data_dir change + WorkerContainer path derivation |
| AUTO-02 | Duplicating a transport creates a fully independent agent -- no shared daemon-side state between agents of the same type | Audit of shared state in hire() flow + data_dir isolation |
| AUTO-03 | Container survives daemon restart -- worker continues running, reconnects via transport channel when head comes back | Unix socket channel, reconnect protocol message, RoutingState transport_type persistence |
</phase_requirements>

## Architecture Patterns

### Current Architecture (What Exists)

```
Daemon (vco-head)
  CompanyRoot
    hire() -> Transport.spawn() -> subprocess with stdin/stdout pipes
    _channel_reader() -> reads worker stdout line by line
    AgentHandle -> writes to worker stdin
    RoutingState -> JSON file (agent_id, channel_id, agent_type, handler_type, config, capabilities)

Worker (vco-worker)
  main.py -> reads stdin, writes stdout (NDJSON)
  WorkerContainer
    MemoryStore -> aiosqlite at Path(config.data_dir) / agent_id / "memory.db"
    lifecycle FSM, handler, task queue, health reporting
```

### Problem 1: State Path is Daemon-Controlled (AUTO-01)

**Current:** `WorkerConfig.data_dir` defaults to `/tmp/vco-worker/data`. The head sends this in the config blob via `StartMessage`. The worker then creates `data_dir / agent_id / memory.db`.

**Issue:** The path `/tmp/vco-worker/data` is a shared filesystem location. If the head sends the same default to two workers, they could collide. More importantly, for Docker containers the state should live INSIDE the container filesystem, not on a host mount.

**Fix:** Worker should derive its own data_dir from its working directory (cwd). The head should NOT send data_dir in the config blob at all -- or if it does, the worker should treat it as a suggestion and prefer its own local path. The pattern is:

```python
# In WorkerContainer.__init__:
# Use cwd-relative path instead of config.data_dir
data_dir = Path.cwd() / ".vco-state" / agent_id
```

For Docker containers, cwd is `/workspace` (set by `-w /workspace` in DockerChannelTransport). For native, cwd is the agent's scratch working directory (set by NativeTransport spawn `cwd=working_dir`). Either way, state is local to the execution environment.

### Problem 2: Shared State Between Same-Type Agents (AUTO-02)

**Current shared state audit of `hire()` flow:**

| State | Location | Shared? | Fix |
|-------|----------|---------|-----|
| `MemoryStore` db | `data_dir / agent_id / memory.db` | No (agent_id scoped) | Move to cwd-relative |
| Working directory | `TASKS_DIR / agent_id` | No (agent_id scoped) | Already isolated |
| `_company_agents` dict | Daemon memory | By-ref, not shared | OK as-is |
| `RoutingState` JSON | Daemon filesystem | Index, not agent state | OK as-is |
| Transport process cache | `NativeTransport._processes` | By-ref, not shared | OK as-is |
| `AGENT_TEMPLATES` | Class constant | Read-only | OK as-is |

**Finding:** There is no shared daemon-side mutable state between agents of the same type. Each agent gets its own AgentHandle, its own subprocess, its own working directory, and its own MemoryStore database. The only change needed is ensuring the MemoryStore path is inside the worker's execution environment (Problem 1 fix covers this).

**Duplication test:** To duplicate a transport and create an independent agent, the head calls `hire()` with a different `agent_id`. This creates a fresh working directory, spawns a new subprocess, sends a new StartMessage with a new config blob. No state is shared. Once data_dir is cwd-relative, duplication produces fully independent agents.

### Problem 3: Worker Survival Across Daemon Restart (AUTO-03)

This is the hardest requirement. Currently:

1. **NativeTransport** uses `asyncio.create_subprocess_exec` with `stdin=PIPE, stdout=PIPE`. When the daemon process dies, these pipes break (EOF on the worker's stdin, broken pipe on stdout). The worker's `run_worker` loop exits on EOF. Worker dies.

2. **DockerChannelTransport** uses `docker run -i` with piped stdin/stdout. Same problem -- daemon death closes the `docker run` process's stdin pipe, Docker sends EOF to the container, worker exits.

3. **RoutingState** already persists to disk and is loaded on daemon startup. But there's no mechanism to reconnect to existing workers.

**Solution architecture:**

For native transport, replace stdin/stdout pipes with Unix domain sockets:
- Each worker listens on a well-known socket path (e.g., `/tmp/vco-worker-{agent_id}.sock`)
- The head connects to this socket after spawn (or on reconnect)
- When the daemon dies, the socket disconnects but the worker keeps running
- On daemon restart, the head loads RoutingState, finds persisted agents, connects to their sockets

For Docker transport, the approach is similar but uses `docker exec` or a socket forwarded into the container. However, Docker containers with `--rm` and `-i` will exit when stdin closes. Fix: remove `-i` and `--rm`, use a persistent container with a socket.

**Channel protocol addition:** Add a `ReconnectMessage` (head-to-worker) that tells the worker "I'm back, send me your current state":

```python
class ReconnectMessage(BaseModel):
    type: Literal["reconnect"] = "reconnect"
    agent_id: str
```

Worker responds with a `HealthReportMessage` (already exists) containing its current state.

### Recommended Architecture

```
Native Transport (revised):
  1. hire() -> spawn subprocess (worker runs as daemon, not piped child)
  2. Worker opens Unix domain socket at /tmp/vco-worker-{agent_id}.sock
  3. Head connects to socket, sends StartMessage
  4. Channel protocol flows over socket instead of stdin/stdout
  5. On daemon death: socket disconnects, worker enters "disconnected" state
  6. On daemon restart: head loads RoutingState, connects to socket, sends ReconnectMessage
  7. Worker responds with HealthReportMessage

Docker Transport (revised):
  1. hire() -> docker run -d (detached, no -i, no --rm)
  2. Worker inside container opens socket (either exposed port or volume-mounted socket)
  3. Same reconnect protocol
  4. Container persists across daemon restarts (no --rm)
```

### Recommended Project Structure Changes

```
packages/vco-worker/src/vco_worker/
  channel/
    socket_server.py    # NEW: Unix domain socket listener for worker side
  main.py              # MODIFIED: add socket mode alongside stdio mode
  config.py            # MODIFIED: remove data_dir, add socket_path

src/vcompany/
  transport/
    native.py          # MODIFIED: connect via socket instead of pipes
    docker_channel.py   # MODIFIED: detached mode + socket connection
  transport/channel/
    messages.py         # MODIFIED: add ReconnectMessage
  daemon/
    routing_state.py    # MODIFIED: add transport_type field to AgentRouting
  supervisor/
    company_root.py     # MODIFIED: add reconnect_agents() called on start()
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unix domain socket server | Raw socket code | `asyncio.start_unix_server` / `asyncio.open_unix_connection` | stdlib asyncio has first-class Unix socket support with StreamReader/StreamWriter -- identical API to what the NDJSON framing already uses |
| Process daemonization | Double-fork, setsid | `subprocess.Popen` with `start_new_session=True` | Python subprocess already supports detaching child processes from parent process group |
| Socket path management | Custom path logic | Well-known path pattern `/tmp/vco-worker-{agent_id}.sock` | Simple, deterministic, no registry needed |

## Common Pitfalls

### Pitfall 1: Stdin/Stdout Pipes Die With Parent Process
**What goes wrong:** Worker process spawned with piped stdin/stdout exits when daemon dies because pipe EOF triggers run_worker loop exit.
**Why it happens:** OS closes pipe file descriptors when the parent process exits.
**How to avoid:** Use Unix domain sockets instead of pipes. Worker listens on a socket, head connects. Socket disconnect is detectable but non-fatal.
**Warning signs:** Worker processes disappearing from `ps` after daemon restart.

### Pitfall 2: Docker `--rm` and `-i` Flags Kill Container on Daemon Death
**What goes wrong:** Docker container exits when stdin closes (because of `-i` flag) and is auto-removed (because of `--rm`).
**Why it happens:** `-i` keeps stdin open; when the `docker run` parent process dies, stdin closes, container exits. `--rm` deletes it.
**How to avoid:** Use `docker run -d` (detached) instead of `-i`. Remove `--rm`. Use `docker exec` or socket for communication.
**Warning signs:** `docker ps` shows no containers after daemon restart.

### Pitfall 3: Socket File Left Behind After Crash
**What goes wrong:** Worker crashes without cleaning up its socket file. Next spawn fails with "Address already in use".
**Why it happens:** Unix domain socket files persist on filesystem after process death.
**How to avoid:** Worker should `unlink()` the socket path before binding. Also check if the socket is active (connect attempt) before unlinking -- don't delete a live worker's socket.
**Warning signs:** `OSError: [Errno 98] Address already in use` on worker spawn.

### Pitfall 4: Race Between Daemon Startup and Worker Reconnect
**What goes wrong:** Daemon starts, loads RoutingState, tries to connect to workers that haven't finished starting yet (or are in the middle of handling a disconnection).
**Why it happens:** Workers may need time to detect disconnection and re-enter listening state.
**How to avoid:** Retry connection with exponential backoff. Mark workers as "reconnecting" in health tree until connection succeeds.
**Warning signs:** Connection refused errors during daemon startup.

### Pitfall 5: data_dir Collision in /tmp
**What goes wrong:** Two agents with similar IDs get overlapping state directories.
**Why it happens:** If data_dir is still derived from a shared `/tmp` path.
**How to avoid:** Derive data_dir from worker's cwd (which is always unique per agent via `TASKS_DIR / agent_id`).
**Warning signs:** Unexpected data in MemoryStore, checkpoint corruption.

## Code Examples

### Unix Domain Socket Worker Server

```python
# packages/vco-worker/src/vco_worker/channel/socket_server.py
import asyncio
from pathlib import Path

async def start_socket_server(
    socket_path: Path,
    on_connected: callable,  # async (reader, writer) -> None
) -> asyncio.Server:
    """Start Unix domain socket server for channel protocol.

    Worker listens for head connections. When head connects,
    on_connected is called with the reader/writer pair.
    Socket file is cleaned up before binding.
    """
    # Clean up stale socket file
    if socket_path.exists():
        socket_path.unlink()

    server = await asyncio.start_unix_server(
        on_connected,
        path=str(socket_path),
    )
    return server
```

### Head Reconnection on Startup

```python
# In CompanyRoot.start() after loading RoutingState:
async def reconnect_agents(self) -> None:
    """Reconnect to surviving workers after daemon restart."""
    for agent_id, routing in self._routing_state.agents.items():
        socket_path = Path(f"/tmp/vco-worker-{agent_id}.sock")
        if not socket_path.exists():
            logger.info("Worker %s not running (no socket)", agent_id)
            self._routing_state.remove_agent(agent_id)
            continue
        try:
            reader, writer = await asyncio.open_unix_connection(str(socket_path))
            handle = AgentHandle(
                agent_id=routing.agent_id,
                agent_type=routing.agent_type,
                channel_id=routing.channel_id,
                handler_type=routing.handler_type,
                config=routing.config,
                capabilities=routing.capabilities,
            )
            # Attach socket-based process proxy
            handle.attach_socket(reader, writer)
            # Send reconnect message
            await handle.send(ReconnectMessage(agent_id=agent_id))
            # Start channel reader
            handle._reader_task = asyncio.create_task(
                self._channel_reader(handle),
            )
            self._company_agents[agent_id] = handle
            logger.info("Reconnected to worker %s", agent_id)
        except (ConnectionRefusedError, FileNotFoundError):
            logger.warning("Failed to reconnect to worker %s", agent_id)
            self._routing_state.remove_agent(agent_id)
```

### Worker-Local State Path

```python
# In WorkerContainer.__init__:
# State lives inside the execution environment, not at daemon-specified path
data_dir = Path.cwd() / ".vco-state" / agent_id
self.memory = MemoryStore(data_dir / "memory.db")
```

### ReconnectMessage Addition

```python
# In messages.py, add to HeadMessageType:
RECONNECT = "reconnect"

# New message:
class ReconnectMessage(BaseModel):
    type: Literal[HeadMessageType.RECONNECT] = HeadMessageType.RECONNECT
    agent_id: str
```

### AgentRouting with transport_type

```python
# In routing_state.py:
class AgentRouting(BaseModel):
    agent_id: str
    channel_id: str | None = None
    category_id: str | None = None
    agent_type: str = "task"
    handler_type: str = "session"
    config: dict = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    transport_type: str = "native"  # NEW: needed for reconnection
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Stdin/stdout pipes for IPC | Unix domain sockets for persistent IPC | This phase | Workers survive parent death |
| Daemon-specified data_dir | Worker-local cwd-relative data_dir | This phase | True state isolation |
| No reconnection protocol | ReconnectMessage + HealthReport response | This phase | Daemon restart recovery |
| Docker `-i --rm` | Docker `-d` + socket | This phase | Containers survive daemon death |

## Open Questions

1. **AgentHandle Refactoring for Sockets**
   - What we know: AgentHandle currently uses `_process.stdin.write()` to send messages. With sockets, it needs a `writer.write()` path instead.
   - What's unclear: Best abstraction -- should AgentHandle hold a generic "writer" callable, or should it switch between process mode and socket mode?
   - Recommendation: Add `attach_socket(reader, writer)` method alongside existing `attach_process()`. The `send()` method checks which is attached. Clean, minimal change.

2. **Worker Discovery on Reconnect**
   - What we know: Socket path is deterministic (`/tmp/vco-worker-{agent_id}.sock`). RoutingState lists all known agents.
   - What's unclear: Should the head try to reconnect to ALL persisted agents, or only those whose socket files exist?
   - Recommendation: Check socket file existence first (fast), then attempt connection. Remove stale entries from RoutingState.

3. **Docker Container Persistence**
   - What we know: Current DockerChannelTransport uses `--rm` and `-i`. Both must change for survival.
   - What's unclear: How to expose the Unix domain socket from inside the Docker container to the host.
   - Recommendation: Mount a small host directory for the socket file (e.g., `-v /tmp/vco-sockets:/var/run/vco`). Worker writes socket inside container at mounted path. Minimal filesystem sharing -- just the socket, not state.

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `packages/vco-worker/src/vco_worker/` -- all worker runtime code
- Codebase inspection: `src/vcompany/daemon/` -- AgentHandle, RoutingState, CompanyRoot
- Codebase inspection: `src/vcompany/transport/` -- NativeTransport, DockerChannelTransport, ChannelTransport protocol
- Python asyncio docs: `asyncio.start_unix_server` and `asyncio.open_unix_connection` are stable stdlib APIs

### Secondary (MEDIUM confidence)
- Unix domain socket survival semantics: socket file persists on filesystem after process death, but listening socket is closed. Connection attempts to dead socket get ECONNREFUSED.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all changes use existing Python stdlib (asyncio Unix sockets) and existing project patterns (Pydantic models, NDJSON framing)
- Architecture: HIGH - three clear problems with clear solutions, all verified against codebase
- Pitfalls: HIGH - pipe death on parent exit is well-documented OS behavior; Docker flag semantics are well-documented

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable domain, no external dependency changes)
