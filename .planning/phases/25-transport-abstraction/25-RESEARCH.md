# Phase 25: Transport Abstraction - Research

**Researched:** 2026-03-29
**Domain:** Protocol-based execution abstraction, daemon HTTP signaling, dependency injection
**Confidence:** HIGH

## Summary

Phase 25 replaces direct TmuxManager and subprocess usage in AgentContainer and StrategistConversation with an injected AgentTransport protocol. The codebase already has an established pattern for this exact kind of abstraction -- the CommunicationPort protocol from Phase 19 -- making this a well-understood refactor rather than novel design work.

The work breaks into three distinct tracks: (1) defining AgentTransport and implementing LocalTransport, (2) replacing sentinel temp file signaling with HTTP-based daemon signaling via `vco signal`, and (3) wiring transport injection through the factory and supervisor chain. All three tracks touch container.py heavily but in different sections, so they can be sequenced cleanly.

The daemon already has a Unix socket server (SocketServer with NDJSON protocol) but CONTEXT.md D-03 specifies HTTP for signal delivery. This means the daemon needs an HTTP endpoint in addition to its existing socket API, or the `vco signal` command needs to use the existing socket protocol (the CONTEXT says "HTTP endpoint on the daemon" but the daemon currently has no HTTP server). This is the one area requiring a design decision during planning.

**Primary recommendation:** Follow the CommunicationPort pattern exactly (runtime_checkable Protocol, Noop implementation for tests). Build LocalTransport wrapping TmuxManager + subprocess. Replace sentinel files completely with daemon-mediated signaling.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Thin transport -- AgentTransport handles raw execution primitives only: setup env, teardown env, exec command, check alive, read/write files. AgentContainer keeps task queueing, idle gating, and signal interpretation. Signal delivery mechanism lives in transport but signal semantics stay in container.
- **D-02:** Include read_file/write_file on the protocol now even though LocalTransport just delegates to pathlib.
- **D-03:** Agent readiness/idle signaling uses an HTTP endpoint on the daemon (not Unix socket, not temp files). `vco signal --ready/--idle` POSTs to the daemon's HTTP endpoint. Daemon receives signal and updates container state directly.
- **D-04:** Full implementation this phase -- build the daemon HTTP endpoint, implement the `vco signal` CLI command, update Claude Code hooks to call it. Sentinel temp files fully removed. No shims or local fallbacks.
- **D-05:** Nothing stays internal. StrategistConversation stops calling asyncio.create_subprocess_exec directly and goes through AgentTransport.
- **D-06:** LocalTransport handles both execution modes: tmux for interactive agents and subprocess for piped agents (Strategist). Both are transport concerns.
- **D-07:** Simple registry dict in the factory: `{"local": LocalTransport, "docker": DockerTransport}`. Looks up AgentConfig.transport field (default "local"), instantiates, injects into container. New transports = add one line. No plugin discovery.

### Claude's Discretion
- How LocalTransport internally decides between tmux session and subprocess based on agent type/config
- HTTP endpoint path and payload format for signal delivery
- Whether AgentTransport is a Protocol (structural typing) or ABC (nominal typing)
- How to migrate existing Claude Code hooks from temp file writes to HTTP calls

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TXPT-01 | AgentTransport protocol with setup/teardown/exec/is_alive/read_file/write_file methods | CommunicationPort pattern provides exact template; Protocol vs ABC analysis below |
| TXPT-02 | LocalTransport implements AgentTransport using TmuxManager + subprocess | TmuxManager already isolated; StrategistConversation._exec_claude provides subprocess pattern |
| TXPT-03 | AgentContainer uses injected AgentTransport instead of direct TmuxManager calls | Full inventory of TmuxManager touchpoints in container.py documented |
| TXPT-04 | StrategistConversation uses AgentTransport.exec() instead of direct subprocess | _exec_claude and send_streaming methods identified; both use asyncio.create_subprocess_exec |
| TXPT-05 | Agent readiness/idle signaling uses daemon endpoint via `vco signal` | Daemon socket infrastructure exists; HTTP endpoint design documented |
| TXPT-06 | AgentConfig.transport field (default "local") with factory injection | AgentConfig model and ContainerFactory patterns documented |
</phase_requirements>

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python typing.Protocol | stdlib | AgentTransport definition | Matches CommunicationPort pattern already in codebase |
| asyncio | stdlib | Async exec, subprocess management | Already used throughout for subprocess and task management |
| aiohttp | 3.x (new dep) | HTTP server in daemon for signal endpoint | Lightweight async HTTP; already a transitive dep via discord.py |
| click | 8.2.x | `vco signal` CLI command | Already the CLI framework |
| pydantic | 2.11.x | AgentConfig transport field, signal payloads | Already the config model framework |
| httpx | 0.28.x | `vco signal` HTTP client (sync) | Already in project for sync+async HTTP |

### Note on HTTP Server Choice

The daemon needs an HTTP endpoint for signal delivery (D-03). Options:

1. **aiohttp** -- already a transitive dependency via discord.py. Can run a lightweight HTTP server alongside the existing asyncio event loop. Zero new deps.
2. **stdlib asyncio HTTP** -- Use `asyncio.start_server` and parse raw HTTP. No deps but fragile.
3. **Reinterpret D-03** -- Use the existing Unix socket NDJSON protocol (SocketServer) instead of HTTP. `vco signal` would POST via socket, not HTTP. This is simpler but contradicts the literal "HTTP endpoint" wording in D-03.

**Recommendation:** Use aiohttp since it is already installed (discord.py depends on it). Add a small aiohttp web.Application with a single POST endpoint inside the daemon's asyncio loop. The `vco signal` CLI command uses httpx (sync) to POST to it.

**Alternative:** If adding an HTTP server feels heavy, the existing SocketServer NDJSON protocol could handle signals via a new `signal` method. The Claude Code hooks would call `vco signal` which uses the DaemonClient (socket) rather than HTTP. This is architecturally simpler but means D-03's "HTTP" specification would need to be relaxed to "daemon endpoint."

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
├── transport/
│   ├── __init__.py
│   ├── protocol.py       # AgentTransport Protocol + NoopTransport
│   └── local.py           # LocalTransport (tmux + subprocess)
├── container/
│   ├── container.py       # Modified: uses AgentTransport instead of TmuxManager
│   └── factory.py         # Modified: transport registry + injection
├── daemon/
│   ├── daemon.py          # Modified: HTTP signal endpoint
│   └── signal_handler.py  # Signal endpoint handler
├── cli/
│   └── signal_cmd.py      # New: vco signal --ready/--idle
├── strategist/
│   └── conversation.py    # Modified: uses AgentTransport.exec()
└── models/
    └── config.py          # Modified: AgentConfig.transport field
```

### Pattern 1: AgentTransport Protocol (following CommunicationPort)

**What:** A `@runtime_checkable` Protocol defining the transport interface.
**When to use:** Always -- this is the core abstraction.
**Example:**
```python
# Source: Modeled on src/vcompany/daemon/comm.py CommunicationPort
from typing import Protocol, runtime_checkable
from pathlib import Path

@runtime_checkable
class AgentTransport(Protocol):
    """Execution environment abstraction for agents."""

    async def setup(self, agent_id: str, working_dir: Path, **kwargs) -> None:
        """Prepare the execution environment."""
        ...

    async def teardown(self, agent_id: str) -> None:
        """Clean up the execution environment."""
        ...

    async def exec(
        self,
        agent_id: str,
        command: str | list[str],
        *,
        stdin: str | None = None,
        timeout: float | None = None,
    ) -> str:
        """Execute a command and return stdout."""
        ...

    def is_alive(self, agent_id: str) -> bool:
        """Check if the agent's process is still running."""
        ...

    async def read_file(self, agent_id: str, path: Path) -> str:
        """Read a file from the agent's environment."""
        ...

    async def write_file(self, agent_id: str, path: Path, content: str) -> None:
        """Write a file to the agent's environment."""
        ...
```

**Why Protocol over ABC:** CommunicationPort already uses Protocol with @runtime_checkable. The codebase convention is established. Protocol enables structural typing (duck typing) which is more Pythonic and doesn't require inheritance.

### Pattern 2: LocalTransport (dual-mode execution)

**What:** LocalTransport wraps TmuxManager for interactive agents and asyncio.create_subprocess_exec for piped agents.
**When to use:** Default transport for all local execution.
**Key insight:** The transport needs to know whether an agent is interactive (tmux) or piped (subprocess). This can be determined from the agent's ContainerContext.uses_tmux flag or a new transport-level config.

```python
class LocalTransport:
    """Local execution via tmux (interactive) or subprocess (piped)."""

    def __init__(self, tmux_manager: TmuxManager | None = None) -> None:
        self._tmux = tmux_manager or TmuxManager()
        self._sessions: dict[str, _AgentSession] = {}

    async def setup(self, agent_id: str, working_dir: Path, **kwargs) -> None:
        interactive = kwargs.get("interactive", True)
        session_name = kwargs.get("session_name")
        # Store session info for later exec/teardown
        self._sessions[agent_id] = _AgentSession(
            working_dir=working_dir,
            interactive=interactive,
            session_name=session_name,
        )
        if interactive:
            # Create tmux pane (but don't launch claude yet)
            ...

    async def exec(self, agent_id: str, command: str | list[str], **kwargs) -> str:
        session = self._sessions[agent_id]
        if session.interactive:
            # Send to tmux pane
            ...
        else:
            # Piped subprocess
            proc = await asyncio.create_subprocess_exec(...)
            stdout, _ = await proc.communicate(...)
            return stdout.decode()
```

### Pattern 3: Signal Delivery via Daemon

**What:** Replace sentinel temp files with `vco signal --ready/--idle` that POSTs to daemon.
**When to use:** All agent readiness/idle signaling.

Current flow:
```
Claude Code hook (Stop) -> echo idle > /tmp/vco-agent-{id}.state
Container -> polls /tmp/vco-agent-{id}.state every 1s
```

New flow:
```
Claude Code hook (Stop) -> vco signal --idle
vco signal CLI -> POST to daemon HTTP endpoint
Daemon -> directly updates container._is_idle
```

### Pattern 4: Factory Transport Injection

**What:** Factory looks up AgentConfig.transport field, instantiates transport, passes to container.
**Example:**
```python
# In factory.py
_TRANSPORT_REGISTRY: dict[str, type] = {
    "local": LocalTransport,
    # "docker": DockerTransport,  # Phase 26
}

def create_container(spec, ..., transport_type: str = "local", **kwargs):
    transport_cls = _TRANSPORT_REGISTRY.get(transport_type, LocalTransport)
    transport = transport_cls(...)
    return cls.from_spec(spec, ..., transport=transport, ...)
```

### Anti-Patterns to Avoid
- **Leaking transport details into AgentContainer:** Container should never import TmuxManager or call subprocess directly after this phase. All execution goes through self._transport.
- **Signal polling in container:** The new signal flow is push-based (daemon pushes to container), not poll-based. Do not keep the _watch_idle_signals polling loop.
- **Making AgentTransport aware of agent semantics:** Transport is raw execution. It does not know about "idle" or "ready" -- those are container concepts. The signal endpoint on the daemon routes to the container, not the transport.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP server in daemon | Raw asyncio HTTP parsing | aiohttp.web (already installed via discord.py) | HTTP parsing edge cases, content-type handling, error responses |
| Sync HTTP client for `vco signal` | urllib or raw sockets | httpx (already in project) | Clean API, timeout handling, error reporting |
| Protocol type checking | Manual isinstance checks | @runtime_checkable Protocol | Standard Python typing, matches codebase pattern |

## Common Pitfalls

### Pitfall 1: Circular Import Between Transport and Container
**What goes wrong:** transport/protocol.py imports container types, container.py imports transport types, causing ImportError at module load.
**Why it happens:** The transport protocol needs to reference types used by containers (like Path, ContainerContext) and containers need to reference the transport.
**How to avoid:** Use TYPE_CHECKING guards. The Protocol definition should have zero container imports. Container imports transport only at the type level or in method bodies.
**Warning signs:** ImportError on startup, "partially initialized module" errors.

### Pitfall 2: Async Mismatch in exec()
**What goes wrong:** LocalTransport.exec() for tmux mode needs to send a command and return, but tmux send_keys is fire-and-forget (no stdout capture). For subprocess mode, exec() returns stdout.
**Why it happens:** The two modes have fundamentally different execution models. Tmux is interactive (send input, read pane output later). Subprocess is batch (send stdin, get stdout).
**How to avoid:** exec() for tmux mode should be "send command to pane" semantics, not "run and return output." The protocol's exec() needs to accommodate both: for interactive agents it sends a command; for piped agents it runs and returns output. Consider splitting or using kwargs to distinguish.
**Warning signs:** Tests pass for subprocess mode but fail for tmux mode because return value semantics differ.

### Pitfall 3: Signal Race Condition During Startup
**What goes wrong:** Agent starts, Claude Code launches, SessionStart hook fires `vco signal --ready`, but the container is not yet registered in the daemon's lookup table (or the HTTP server is not yet listening).
**Why it happens:** There is a timing gap between container.start() creating the tmux session and the daemon being ready to receive signals for that agent.
**How to avoid:** Ensure the daemon registers the container's signal handler BEFORE launching the tmux session. The container registers itself with the daemon's signal router, then launches claude.
**Warning signs:** First agent signal silently dropped, agent appears stuck in "not ready" state.

### Pitfall 4: HTTP Port Conflict
**What goes wrong:** The daemon's HTTP server tries to bind to a port already in use.
**Why it happens:** Multiple daemon instances, or another service on the same port.
**How to avoid:** Use a configurable port (env var), default to something unlikely (e.g., 47200). Or use a Unix socket for HTTP too (aiohttp supports Unix sockets). Using a Unix socket avoids port conflicts entirely and matches the existing daemon socket pattern.
**Warning signs:** "Address already in use" on daemon startup.

### Pitfall 5: Breaking StrategistConversation Streaming
**What goes wrong:** StrategistConversation.send_streaming() uses line-by-line async iteration over proc.stdout. Routing through transport.exec() loses streaming capability.
**Why it happens:** exec() returns a string (completed output), but streaming needs incremental access.
**How to avoid:** Either (a) add a stream_exec() method to the transport protocol, or (b) have exec() accept a streaming callback, or (c) keep the Strategist's streaming as a transport-internal detail where LocalTransport handles it. Given D-05 says "nothing stays internal," option (a) is cleanest -- add an async generator method for streaming.
**Warning signs:** Strategist responses arrive all at once instead of progressively updating Discord.

### Pitfall 6: Forgetting to Update All Supervisor/CompanyRoot tmux_manager Plumbing
**What goes wrong:** Supervisor.__init__ and CompanyRoot pass tmux_manager down to create_container(). After the refactor, they should pass transport instead. Missing one site means some containers get a transport, others get a raw tmux_manager.
**Why it happens:** tmux_manager is passed through 4+ levels: Daemon -> CompanyRoot -> ProjectSupervisor -> Supervisor -> create_container.
**How to avoid:** Search for ALL tmux_manager references across the codebase and update each one. The full chain is: daemon.py -> company_root.py -> project_supervisor.py -> supervisor.py -> factory.py -> container.py.
**Warning signs:** Mixed behavior where some agents work and others crash with "tmux_manager is None."

## Code Examples

### Current TmuxManager Usage in Container (to be replaced)

```python
# container.py lines 239-291 -- _launch_tmux_session
# These direct TmuxManager calls ALL move into LocalTransport:
session = await asyncio.to_thread(self._tmux.get_or_create_session, self._project_session_name)
pane = await asyncio.to_thread(self._tmux.create_pane, session, window_name=self.context.agent_id)
self._pane_id = pane.pane_id
cmd = self._build_launch_command()
await asyncio.to_thread(self._tmux.send_command, pane, cmd)
```

### Current Sentinel File Logic (to be removed)

```python
# container.py lines 32-34, 126-166
_SIGNAL_DIR = Path("/tmp")
_SIGNAL_PREFIX = "vco-agent-"

def _read_signal(self) -> str | None:
    return self._signal_path.read_text().strip()

async def _wait_for_signal(self, expected, timeout=120.0, poll_interval=0.5):
    # Polling loop -- replaced by push-based daemon signals
```

### Current StrategistConversation Subprocess (to be replaced)

```python
# conversation.py lines 274-285
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await asyncio.wait_for(
    proc.communicate(input=content.encode()),
    timeout=600,
)
```

### Current Claude Code Hooks (to be updated)

```json
// settings.json.j2 -- current sentinel file approach
"SessionStart": [{
    "command": "echo started > /tmp/vco-agent-${VCO_AGENT_ID}.state"
}],
"Stop": [{
    "command": "echo idle > /tmp/vco-agent-${VCO_AGENT_ID}.state"
}]
```

New hooks will call `vco signal` instead:
```json
// After phase 25
"SessionStart": [{
    "command": "vco signal --ready --agent-id ${VCO_AGENT_ID}"
}],
"Stop": [{
    "command": "vco signal --idle --agent-id ${VCO_AGENT_ID}"
}]
```

### CommunicationPort Pattern (to follow for AgentTransport)

```python
# Source: src/vcompany/daemon/comm.py
@runtime_checkable
class CommunicationPort(Protocol):
    async def send_message(self, payload: SendMessagePayload) -> bool: ...
    async def send_embed(self, payload: SendEmbedPayload) -> bool: ...
    # ... six async methods total

class NoopCommunicationPort:
    """No-op implementation for testing and fallback."""
    async def send_message(self, payload: SendMessagePayload) -> bool:
        return True
```

## Inventory of All Touchpoints to Modify

### container.py Modifications
| Line(s) | Current | New |
|---------|---------|-----|
| 29 | `from vcompany.tmux.session import TmuxManager` (TYPE_CHECKING) | `from vcompany.transport.protocol import AgentTransport` |
| 32-34 | `_SIGNAL_DIR`, `_SIGNAL_PREFIX` constants | Remove entirely |
| 58 | `tmux_manager: TmuxManager \| None = None` param | `transport: AgentTransport \| None = None` |
| 73-76 | `self._tmux`, `self._project_dir`, `self._project_session_name`, `self._pane_id` | `self._transport` |
| 97-99 | `_needs_tmux_session` property (checks `context.uses_tmux`) | Keep as-is (business logic, not transport) |
| 126-166 | Signal file methods (`_signal_path`, `_read_signal`, `_clear_signal`, `_wait_for_signal`) | Remove -- replaced by daemon push signals |
| 181-206 | `_drain_task_queue` and `_watch_idle_signals` (polling loop) | Replace polling with daemon callback registration |
| 210-237 | `_build_launch_command` | Move to LocalTransport |
| 239-290 | `_launch_tmux_session` | Delegate to `self._transport.setup()` + `self._transport.exec()` |
| 292-300 | `is_tmux_alive` | Delegate to `self._transport.is_alive()` |
| 310-334 | `health_report` signal refresh | Use `self._is_idle` set by daemon callback (no polling) |
| 346-351 | `start()` tmux check | Delegate to transport |
| 379-397 | `stop()` tmux cleanup | Delegate to `self._transport.teardown()` |

### factory.py Modifications
| Current | New |
|---------|-----|
| `tmux_manager: object \| None = None` param | `transport: AgentTransport \| None = None` param |
| Passes `tmux_manager` to `cls.from_spec()` | Passes `transport` to `cls.from_spec()` |
| Add transport registry dict | `_TRANSPORT_REGISTRY = {"local": LocalTransport}` |

### supervisor.py Modifications
| Current | New |
|---------|-----|
| `self._tmux_manager` stored, passed to `create_container` | `self._transport` stored, passed to `create_container` |
| `tmux_manager=self._tmux_manager` in `_start_child` | `transport=self._transport` |

### company_root.py Modifications
| Current | New |
|---------|-----|
| `TmuxManager()` created in `_create_runtime_api` | `LocalTransport(TmuxManager())` created instead |
| `tmux_manager=tmux_manager` passed to CompanyRoot | `transport=local_transport` passed |

### project_supervisor.py Modifications
| Current | New |
|---------|-----|
| `tmux_manager: object \| None = None` param | `transport: AgentTransport \| None = None` param |

### daemon.py Modifications
| Current | New |
|---------|-----|
| No HTTP server | Add aiohttp HTTP server for signal endpoint |
| No signal routing | Add `_handle_signal` method that finds container and sets `_is_idle` |

### config.py Modifications
| Current | New |
|---------|-----|
| No transport field on AgentConfig | Add `transport: str = "local"` field |

### settings.json.j2 Modifications
| Current | New |
|---------|-----|
| `echo started > /tmp/vco-agent-${VCO_AGENT_ID}.state` | `vco signal --ready --agent-id ${VCO_AGENT_ID}` |
| `echo idle > /tmp/vco-agent-${VCO_AGENT_ID}.state` | `vco signal --idle --agent-id ${VCO_AGENT_ID}` |

### New Files
| File | Purpose |
|------|---------|
| `src/vcompany/transport/__init__.py` | Package init |
| `src/vcompany/transport/protocol.py` | AgentTransport Protocol + NoopTransport |
| `src/vcompany/transport/local.py` | LocalTransport implementation |
| `src/vcompany/cli/signal_cmd.py` | `vco signal` CLI command |

## Open Questions

1. **HTTP vs Socket for Signal Delivery**
   - What we know: D-03 says "HTTP endpoint." The daemon currently has only a Unix socket server (NDJSON). Adding HTTP requires either aiohttp (already installed via discord.py) or raw asyncio HTTP.
   - What's unclear: Whether the user literally wants HTTP (new server, new port/socket) or whether using the existing socket protocol with a new "signal" method satisfies the intent.
   - Recommendation: Use aiohttp on a Unix socket (not TCP port) to avoid port conflicts. This satisfies "HTTP endpoint" literally while matching the Unix socket pattern. The `vco signal` CLI uses httpx to POST to the Unix socket HTTP endpoint. If this feels over-engineered, fall back to adding a "signal" method to the existing SocketServer -- simpler, one fewer protocol, but technically not HTTP.

2. **StrategistConversation Streaming Through Transport**
   - What we know: send_streaming() reads stdout line-by-line for real-time tool-use callbacks. A simple exec() that returns a string loses this.
   - What's unclear: Whether to add stream_exec() to the protocol or handle streaming as a LocalTransport internal detail.
   - Recommendation: Add `exec_streaming()` that returns an async iterator of lines. StrategistConversation calls `transport.exec_streaming()` instead of `transport.exec()`.

3. **Signal Delivery When Daemon is Down**
   - What we know: Currently sentinel files work even without the daemon running. With HTTP signals, if daemon is down, `vco signal` will fail.
   - What's unclear: Whether this matters in practice (agents should not be running without the daemon).
   - Recommendation: Have `vco signal` fail silently (exit 0) if daemon is unreachable. Claude Code hooks must not error out or they block the agent. Log a warning but don't crash.

## Sources

### Primary (HIGH confidence)
- `src/vcompany/daemon/comm.py` -- CommunicationPort Protocol pattern (established abstraction template)
- `src/vcompany/container/container.py` -- All TmuxManager touchpoints and signal logic (lines 29-397)
- `src/vcompany/tmux/session.py` -- TmuxManager API surface (17 methods)
- `src/vcompany/strategist/conversation.py` -- Subprocess calls at lines 274-285, 347-353
- `src/vcompany/container/factory.py` -- Current factory pattern with registry
- `src/vcompany/daemon/daemon.py` -- Current daemon lifecycle and socket server setup
- `src/vcompany/daemon/server.py` -- SocketServer with NDJSON protocol
- `src/vcompany/daemon/client.py` -- DaemonClient sync socket client
- `src/vcompany/models/config.py` -- AgentConfig Pydantic model
- `src/vcompany/supervisor/supervisor.py` -- tmux_manager plumbing through supervisor chain
- `src/vcompany/supervisor/company_root.py` -- TmuxManager creation in _create_runtime_api
- `src/vcompany/templates/settings.json.j2` -- Current Claude Code hooks (sentinel files)
- `src/vcompany/container/context.py` -- ContainerContext with uses_tmux flag

### Secondary (MEDIUM confidence)
- aiohttp is a transitive dependency via discord.py -- verified by CLAUDE.md noting discord.py "Uses aiohttp internally"

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, no new deps except aiohttp server usage
- Architecture: HIGH -- CommunicationPort provides exact template to follow
- Pitfalls: HIGH -- code has been fully read, all touchpoints inventoried
- Signal mechanism: MEDIUM -- HTTP vs socket decision needs user confirmation

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (stable internal refactor, no external dependency concerns)
