# Phase 34: Cleanup and Network Stub - Research

**Researched:** 2026-03-31
**Domain:** Dead code removal, network transport protocol design
**Confidence:** HIGH

## Summary

Phase 34 has two distinct concerns: (1) removing all daemon-side container dead code that has been superseded by the vco-worker/ChannelTransport architecture, and (2) creating a NetworkTransport stub that defines the TCP/WebSocket contract for future remote agents.

The dead code removal is well-scoped. The CONTEXT.md and codebase analysis reveal a clear delineation: `src/vcompany/agent/`, `src/vcompany/container/`, `src/vcompany/handler/`, `src/vcompany/transport/protocol.py`, `src/vcompany/transport/local.py`, and `src/vcompany/transport/docker.py` are all dead code candidates. However, several modules have lingering live references that must be carefully untangled -- notably HealthReport, MemoryStore, ChildSpec, CompanyHealthTree, and CommunicationPort/NoopCommunicationPort which are still used by live daemon code. The Strategist agent currently uses `add_company_agent()` (container path) and `StrategistConversation` depends on the old `AgentTransport` protocol -- this is the most complex migration area.

**Primary recommendation:** Split into three plans: (1) extract still-needed types from container/ to daemon/ or shared/, port Strategist to subprocess-direct execution, remove dead code; (2) clean up transport/__init__.py, tests, and verify compilation; (3) create NetworkTransport stub implementing ChannelTransport protocol with TCP/WebSocket.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked -- auto-generated infrastructure phase.

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key constraints:
- Remove ALL daemon-side container dead code -- be thorough
- NetworkTransport stub must define the contract (not production-ready)
- All existing functionality must work after removal (hire, give-task, dismiss, health, status)
- Old AgentTransport protocol (v3.1) can be removed -- replaced by ChannelTransport
- Old LocalTransport, DockerTransport can be removed -- replaced by NativeTransport, DockerChannelTransport
- Keep the codebase compiling -- verify imports after deletion

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HEAD-04 | Dead code removed -- daemon-side GsdAgent/CompanyAgent/FulltimeAgent Python objects, handler factory injection, NoopCommunicationPort, StrategistConversation-from-daemon, all v3.1 shims | Dead code inventory below maps every file and reference that must be deleted or migrated |
| CHAN-04 | Network transport stub exists with TCP/WebSocket interface definition -- not full production impl, but the contract is defined and a basic implementation works | ChannelTransport protocol analysis below shows the contract to implement; NetworkTransport stub pattern documented |
</phase_requirements>

## Architecture Patterns

### Dead Code Inventory

Files to DELETE entirely (directories):

| Directory/File | Content | Why Dead |
|---|---|---|
| `src/vcompany/agent/` (entire directory) | GsdAgent, CompanyAgent, FulltimeAgent, ContinuousAgent, TaskAgent, lifecycles, phases | All agent logic now lives in vco-worker |
| `src/vcompany/handler/` (entire directory) | SessionHandler, ConversationHandler, TransientHandler, protocols | Handler logic now in vco-worker handler registry |
| `src/vcompany/transport/protocol.py` | AgentTransport protocol, NoopTransport | Replaced by ChannelTransport protocol |
| `src/vcompany/transport/local.py` | LocalTransport (tmux-based) | Replaced by NativeTransport (socket-based) |
| `src/vcompany/transport/docker.py` | DockerTransport (docker-py SDK) | Replaced by DockerChannelTransport (subprocess) |

Files in `src/vcompany/container/` -- mixed (some dead, some still needed):

| File | Status | Reason |
|---|---|---|
| `container.py` (AgentContainer) | DELETE | Replaced by vco-worker WorkerContainer |
| `state_machine.py` (ContainerLifecycle) | DELETE | Lifecycle FSM now in worker |
| `context.py` (ContainerContext) | DELETE | Worker derives context from config blob |
| `child_spec.py` (ChildSpec, ChildSpecRegistry) | MIGRATE | Still used by CompanyRoot, Supervisor, ProjectSupervisor, RuntimeAPI |
| `health.py` (HealthReport, HealthTree, CompanyHealthTree, HealthNode) | MIGRATE | Still used by AgentHandle, CompanyRoot.health_tree(), health cog |
| `memory_store.py` (MemoryStore) | MIGRATE | Still used by Scheduler, BacklogQueue, ProjectStateManager |
| `communication.py` (CommunicationPort, NoopCommunicationPort, Message) | CHECK | NoopCommunicationPort in container/ is dead (daemon/comm.py has its own); CommunicationPort protocol in container/ is dead (daemon/comm.py has its own) |
| `discord_communication.py` | CHECK | May still be imported by tests |
| `factory.py` | DELETE | Handler factory injection, create_container, register_defaults -- all dead |
| `__init__.py` | DELETE (rewrite if dir kept) | Re-exports dead types |

### Critical Migration: Types Still In Use

These types currently live in `src/vcompany/container/` but are referenced by live code. They must be moved before deletion:

**1. HealthReport, HealthTree, CompanyHealthTree, HealthNode** (`container/health.py`)
- Used by: `daemon/agent_handle.py`, `supervisor/company_root.py`, `bot/cogs/health.py`, `bot/embeds.py`
- Move to: `src/vcompany/supervisor/health.py` or `src/vcompany/shared/health.py`

**2. MemoryStore** (`container/memory_store.py`)
- Used by: `supervisor/scheduler.py`, `autonomy/backlog.py`, `autonomy/project_state.py`, `supervisor/company_root.py`
- Move to: `src/vcompany/shared/memory_store.py`

**3. ChildSpec, ChildSpecRegistry, RestartPolicy** (`container/child_spec.py`)
- Used by: `supervisor/supervisor.py`, `supervisor/company_root.py`, `supervisor/project_supervisor.py`, `daemon/runtime_api.py`
- Move to: `src/vcompany/supervisor/child_spec.py`

**4. ContainerContext** (`container/context.py`)
- Used by: `daemon/runtime_api.py` (create_strategist), `supervisor/company_root.py`
- If Strategist is ported away from container path, this can be deleted entirely
- Otherwise move to `src/vcompany/supervisor/context.py`

### Critical Migration: Strategist Agent Path

The Strategist currently uses the OLD container path:
1. `RuntimeAPI.create_strategist()` creates a `ChildSpec` + `ContainerContext`
2. Calls `CompanyRoot.add_company_agent(spec)` which calls `create_container()` from factory.py
3. Returns an `AgentContainer` (specifically `CompanyAgent`)
4. `CompanyAgent.initialize_conversation()` creates a `StrategistConversation` with `LocalTransport`
5. `StrategistConversation` uses `AgentTransport.exec()` and `AgentTransport.exec_streaming()`

This entire chain is dead code. The Strategist must be migrated to either:
- **Option A (Recommended):** Port `StrategistConversation` to use `subprocess` directly (remove transport abstraction) since it only does `subprocess.run(["claude", ...])` anyway. The LocalTransport piped mode is just a thin wrapper over subprocess.
- **Option B:** Port Strategist to vco-worker like other agents. This is more work and out of scope for Phase 34 (the CONTEXT says "StrategistConversation-from-daemon" should be removed, implying Option A).

For Option A: `StrategistConversation` currently calls `transport.setup()`, `transport.exec()`, and `transport.exec_streaming()`. These map to:
- `setup()`: creates subprocess infrastructure (no-op for piped mode)
- `exec()`: runs `subprocess.run()` with stdin/stdout capture
- `exec_streaming()`: runs `subprocess` yielding stdout lines

Replace with direct `asyncio.create_subprocess_exec()` calls. The class becomes self-contained with no transport dependency.

### Critical Migration: MentionRouterCog isinstance Dispatch

`MentionRouterCog._deliver_to_agent()` (line 196-239) does:
```python
if isinstance(agent, AgentHandle):
    # Send InboundMessage
else:
    # Legacy AgentContainer path
```

After dead code removal, all agents will be AgentHandle. The legacy else-branch can be deleted and the isinstance check simplified.

### Critical Migration: RuntimeAPI Dual Paths

`RuntimeAPI` methods `dispatch()`, `kill()`, `relaunch()`, `give_task()`, `relay_message()` all have:
```python
if isinstance(handle, AgentHandle):
    # New path
else:
    # Legacy container path
```

All legacy else-branches can be deleted.

### Critical Migration: CompanyRoot.stop()

`CompanyRoot.stop()` (line 714-724) has isinstance dispatch for stopping company agents that are AgentHandle vs AgentContainer. After cleanup, all company agents are AgentHandle -- simplify.

### Critical Migration: daemon.py References

`daemon.py` imports:
- `from vcompany.container.factory import set_agent_types_config` -- factory.py is being deleted but `set_agent_types_config` / `get_agent_types_config` are still used. Move to `models/agent_types.py` or `shared/`.

`daemon.py._handle_send_file()` (line 449) does:
```python
container = await self._runtime_api._root._find_container(agent_id)
if container and hasattr(container, "_transport") and container._transport:
    transport = container._transport
    if hasattr(transport, "resolve_file_to_host"):
```
This entire block is dead code (old transport path). Remove it.

### NetworkTransport Stub Design

The existing `ChannelTransport` protocol defines the contract:
```python
class ChannelTransport(Protocol):
    async def spawn(self, agent_id, *, config, env, working_dir) -> (reader, writer)
    async def connect(self, agent_id) -> (reader, writer)
    async def terminate(self, agent_id) -> None
    @property
    def transport_type(self) -> str
```

A `NetworkTransport` stub must implement this protocol using TCP or WebSocket instead of Unix domain sockets. The stub should:
1. Define the TCP/WebSocket connection flow (how head connects to remote worker)
2. Return `asyncio.StreamReader/StreamWriter` pairs (same as Native/Docker)
3. Handle connection addressing (host:port instead of socket path)
4. Not be production-ready but must have a basic connect/send/receive working

**Pattern:** `asyncio.start_server()` / `asyncio.open_connection()` for TCP gives native StreamReader/StreamWriter pairs -- identical interface to Unix sockets. This is the simplest path. WebSocket would require additional framing.

**Recommendation:** TCP stub using `asyncio.open_connection()` for the client side and `asyncio.start_server()` for a test server. The NDJSON framing already works over any stream transport. Add `host` and `port` parameters to the constructor. The stub proves the contract works over TCP without needing WebSocket complexity.

### Recommended Project Structure After Cleanup

```
src/vcompany/
  transport/
    __init__.py          # exports ChannelTransport, NativeTransport, DockerChannelTransport, NetworkTransport
    channel_transport.py  # ChannelTransport protocol (unchanged)
    channel/             # channel protocol messages (unchanged)
    native.py            # NativeTransport (unchanged)
    docker_channel.py    # DockerChannelTransport (unchanged)
    network.py           # NEW: NetworkTransport stub
    # DELETED: protocol.py, local.py, docker.py
  supervisor/
    child_spec.py        # MIGRATED from container/
    health.py            # MIGRATED from container/
    # existing: company_root.py, supervisor.py, project_supervisor.py, scheduler.py, strategies.py
  shared/
    memory_store.py      # MIGRATED from container/
  # DELETED entirely: agent/, handler/, container/
```

### Test Cleanup

Many test files reference dead code. Tests to DELETE:
- `test_gsd_agent.py`, `test_fulltime_agent.py`, `test_company_agent.py`, `test_continuous_agent.py`
- `test_gsd_lifecycle.py`, `test_continuous_lifecycle.py`, `test_event_driven_lifecycle.py`
- `test_container_lifecycle.py`, `test_container_stopping.py`, `test_container_blocked.py`
- `test_container_integration.py`, `test_container_tmux_bridge.py`, `test_container_factory.py`
- `test_container_context.py`, `test_container_health.py` (if HealthReport tests are pure unit tests, keep and update imports)
- `test_communication_port.py`, `test_discord_comm_port.py` (container version)
- `test_comm_port_wiring.py`

Tests to UPDATE (fix imports only):
- `test_child_spec.py` -- update `from vcompany.container.child_spec` to new location
- `test_memory_store.py` -- update `from vcompany.container.memory_store` to new location
- `test_health_tree.py` -- update `from vcompany.container.health` to new location
- `test_health_cog.py` -- update health imports
- `test_backlog.py`, `test_project_state.py` -- update MemoryStore import
- `test_scheduler.py` -- update MemoryStore import
- `test_company_root.py` -- update ChildSpec/ContainerContext imports
- `test_supervision_tree.py` -- update imports
- `test_bulk_failure.py`, `test_restart_strategies.py` -- update imports
- `test_degraded_mode.py` -- update imports
- `test_delegation.py` -- update imports
- `test_bot_client.py` -- remove GsdAgent references

### Anti-Patterns to Avoid

- **Deleting types before migrating references:** Always move types first, update imports, verify compilation, then delete old locations. Never delete and create simultaneously.
- **Breaking the Strategist:** The Strategist is the most critical agent (PM/owner communication). Test that it still works after migration before proceeding with further deletions.
- **Forgetting test cleanup:** Leaving tests that import deleted modules will cause test suite failures. Clean tests in the same plan as the code they test.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TCP stream transport | Custom framing/protocol | `asyncio.open_connection()` / `asyncio.start_server()` | Returns native StreamReader/StreamWriter, identical to Unix socket interface |
| WebSocket transport | Raw WebSocket implementation | `websockets` library (if needed later) | But for the stub, TCP is sufficient and simpler |
| Import graph analysis | Manual grep for all references | Python `ast` module or just careful grep | Grep is sufficient here since we know the codebase |

## Common Pitfalls

### Pitfall 1: Circular Import After Migration
**What goes wrong:** Moving `ChildSpec` to `supervisor/child_spec.py` can create circular imports if `supervisor.py` already imports from `child_spec.py` and vice versa.
**Why it happens:** The supervisor package has bidirectional dependencies.
**How to avoid:** Use `TYPE_CHECKING` blocks for type annotations. Keep runtime imports minimal. Test imports after each move.
**Warning signs:** `ImportError` at module load time.

### Pitfall 2: Forgetting `__init__.py` Re-exports
**What goes wrong:** Code that does `from vcompany.container import HealthReport` breaks even after migration if the new `__init__.py` doesn't re-export.
**How to avoid:** After migrating, grep for ALL import patterns (`from vcompany.container.health`, `from vcompany.container import`) and update each one. Don't leave backward-compat re-exports -- clean break.
**Warning signs:** `ModuleNotFoundError` or `ImportError` at runtime.

### Pitfall 3: Strategist Regression
**What goes wrong:** After removing the container path, the Strategist stops responding in Discord.
**Why it happens:** The Strategist initialization chain is complex: RuntimeAPI -> CompanyRoot.add_company_agent -> factory.create_container -> CompanyAgent -> StrategistConversation.
**How to avoid:** Port StrategistConversation to direct subprocess first, test it works, then remove the container chain.
**Warning signs:** Strategist not responding after `vco up`.

### Pitfall 4: NetworkTransport Assuming WebSocket Necessity
**What goes wrong:** Over-engineering the stub with WebSocket framing when TCP suffices.
**Why it happens:** "Network" implies HTTP/WebSocket, but the channel protocol is NDJSON over streams.
**How to avoid:** Use plain TCP (`asyncio.open_connection`). The NDJSON framing works over any byte stream. WebSocket is only needed if traversing HTTP proxies/firewalls (v5 concern).

### Pitfall 5: agent_types_config Orphaned
**What goes wrong:** `set_agent_types_config` / `get_agent_types_config` currently live in `container/factory.py` which is being deleted. The daemon and CompanyRoot still call these.
**How to avoid:** Move to `models/agent_types.py` where the AgentTypesConfig model already lives. The functions are just module-level getter/setters for a global.

## Code Examples

### StrategistConversation Without Transport (Direct Subprocess)

```python
# Replace transport.exec() with direct subprocess
async def _exec_claude(self, cmd: list[str], content: str, *, allow_failure: bool = False) -> str | None:
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._working_dir,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=content.encode()),
            timeout=600,
        )
        result = stdout.decode().strip()
        return result if result else "I don't have a response for that."
    except asyncio.TimeoutError:
        if allow_failure:
            return None
        return "Timed out."
```

### NetworkTransport Stub (TCP)

```python
class NetworkTransport:
    """TCP-based transport for remote vco-worker connections.

    Stub implementation for CHAN-04. Defines the contract for
    connecting to workers over TCP instead of Unix domain sockets.
    Not production-ready -- no TLS, no auth, no reconnection logic.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._host = host
        self._port = port
        self._connections: dict[str, tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}

    async def spawn(
        self,
        agent_id: str,
        *,
        config: dict,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Connect to a remote worker that is already listening on host:port.

        Unlike NativeTransport, NetworkTransport does NOT spawn the worker.
        The worker must be started independently on the remote machine.
        """
        reader, writer = await asyncio.open_connection(self._host, self._port)
        self._connections[agent_id] = (reader, writer)
        return reader, writer

    async def connect(self, agent_id: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Reconnect to a remote worker."""
        reader, writer = await asyncio.open_connection(self._host, self._port)
        self._connections[agent_id] = (reader, writer)
        return reader, writer

    async def terminate(self, agent_id: str) -> None:
        """Close the TCP connection (does not stop the remote worker)."""
        conn = self._connections.pop(agent_id, None)
        if conn:
            _, writer = conn
            writer.close()
            await writer.wait_closed()

    @property
    def transport_type(self) -> str:
        return "network"
```

### Updating CompanyRoot._get_transport()

```python
def _get_transport(self, transport_name: str) -> ChannelTransport:
    if not hasattr(self, '_transports'):
        self._transports: dict[str, ChannelTransport] = {}
    if transport_name not in self._transports:
        if transport_name == "native":
            self._transports[transport_name] = NativeTransport()
        elif transport_name == "docker":
            self._transports[transport_name] = DockerChannelTransport()
        elif transport_name == "network":
            from vcompany.transport.network import NetworkTransport
            self._transports[transport_name] = NetworkTransport()
        else:
            raise ValueError(f"Unknown transport: {transport_name}")
    return self._transports[transport_name]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| AgentTransport (setup/exec/send_keys/read_file) | ChannelTransport (spawn/connect/terminate) | Phase 29 (v4.0) | Transport is now purely about connectivity, not execution |
| Container objects on daemon side | Worker processes via channel protocol | Phase 30-33 (v4.0) | All agent logic runs inside execution environment |
| LocalTransport (tmux + subprocess) | NativeTransport (subprocess + Unix socket) | Phase 32 | Workers survive daemon restart |
| DockerTransport (docker-py SDK) | DockerChannelTransport (subprocess docker) | Phase 32 | No SDK dependency, socket communication |

## Open Questions

1. **Strategist as worker vs direct subprocess**
   - What we know: CONTEXT says remove "StrategistConversation-from-daemon" and "v3.1 shims"
   - What's unclear: Whether Strategist should become a vco-worker agent or continue as direct subprocess
   - Recommendation: Keep as direct subprocess for Phase 34 (simpler). Port to worker in a future phase if needed. The StrategistConversation is fundamentally different from other agents (it's a Claude CLI wrapper, not a GSD workflow).

2. **ProjectSupervisor survival after container deletion**
   - What we know: ProjectSupervisor creates containers from ChildSpecs. If container/ is deleted, ProjectSupervisor's container creation breaks.
   - What's unclear: Are there any active ProjectSupervisor code paths still needed?
   - Recommendation: ProjectSupervisor was already mostly superseded by CompanyRoot.hire(). Check if `add_project()` is still called. If yes, it needs refactoring. If no, it may also be dead code.

## Project Constraints (from CLAUDE.md)

- Python 3.12+ runtime
- No GitPython (subprocess for git operations)
- No database -- filesystem state (YAML/Markdown/JSON)
- discord.py 2.7.x for bot
- click 8.2.x for CLI
- asyncio for all async code
- subprocess/asyncio.subprocess for process spawning
- Testing: pytest (minimal -- only slippery parts per user preference)
- Linting: ruff

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all files in `src/vcompany/agent/`, `src/vcompany/container/`, `src/vcompany/handler/`, `src/vcompany/transport/`
- Grep analysis of all import references across `src/` and `tests/`
- Phase 29-33 CONTEXT and decision history from STATE.md

### Secondary (MEDIUM confidence)
- Python asyncio documentation for `asyncio.open_connection()` / `asyncio.start_server()` TCP stream API

## Metadata

**Confidence breakdown:**
- Dead code inventory: HIGH - direct codebase analysis, every reference traced
- Migration targets: HIGH - clear dependency graph from grep analysis
- NetworkTransport design: HIGH - ChannelTransport protocol is well-defined, TCP streams are native asyncio
- Strategist migration: MEDIUM - the approach is clear but the execution has edge cases around session persistence

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable internal architecture)
