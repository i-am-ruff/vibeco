# Stack Research: v3.0 CLI-First Architecture — New Capabilities

**Domain:** Runtime daemon, Unix socket API, state persistence, CLI-as-API-client
**Researched:** 2026-03-29
**Confidence:** HIGH

## Scope

This research covers ONLY what is new for v3.0. The existing stack (Python 3.12, discord.py, anthropic, libtmux, pydantic v2, click, aiosqlite, python-statemachine, etc.) is validated and not re-evaluated.

## Recommended Stack Additions

### Zero New Dependencies for Core Features

The headline finding: **v3.0 needs zero new runtime dependencies.** Python 3.12 stdlib + existing deps cover everything.

| Feature | Implementation | Why No New Dep |
|---------|---------------|----------------|
| Unix socket server | `asyncio.start_unix_server()` | stdlib, production-grade, already in the asyncio event loop |
| Unix socket client | `asyncio.open_unix_connection()` | stdlib, pairs with server |
| JSON protocol | `json` module (stdlib) | Newline-delimited JSON over streams is trivial to implement |
| State serialization | `aiosqlite` (already a dep) | Extend existing MemoryStore pattern to runtime-level state |
| Process daemonization | `vco up` stays foreground, systemd manages it | Modern daemons don't double-fork; systemd Type=simple is correct |
| CLI-to-daemon communication | click (already a dep) + asyncio socket client | CLI commands become thin socket clients |
| State models | pydantic v2 (already a dep) | Serialize/deserialize container state snapshots |

### Core Technologies (No New Packages)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `asyncio.start_unix_server` | stdlib (3.12) | Runtime daemon socket API | Built into Python. Returns `(StreamReader, StreamWriter)` pairs. Integrates with existing asyncio event loop used by CompanyRoot, supervisors, health monitoring. No framework overhead. |
| `asyncio.open_unix_connection` | stdlib (3.12) | CLI client to daemon | Returns `(reader, writer)` pair. CLI commands open connection, send JSON request, read JSON response, close. Stateless per-command. |
| Newline-delimited JSON (NDJSON) | N/A | Wire protocol | Each message is one JSON object terminated by `\n`. `reader.readline()` reads one message. `writer.write(json.dumps(msg).encode() + b"\n")` sends one. No framing library needed. Simpler than JSON-RPC, sufficient for local IPC. |
| `aiosqlite` | 0.22.1 (existing dep) | Runtime state persistence | Already used for per-agent MemoryStore. Add a runtime-level state database for container snapshots, pane IDs, task queues. WAL mode, crash-safe. |
| `pydantic` v2 | 2.11.x (existing dep) | State snapshot models | `model_dump_json()` / `model_validate_json()` for serializing container state to SQLite and to the socket API. Type-safe, validates on deserialize. |
| `click` | 8.2.x (existing dep) | CLI commands as API clients | Each `vco` command opens a Unix socket, sends a request, prints the response. click handles arg parsing, the socket call is ~10 lines per command. |

### Optional: systemd Integration

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `sdnotify` | 0.3.2 | systemd readiness notification | Pure Python, zero dependencies, ~40 lines of code. Sends `READY=1` after daemon socket is listening. Enables `Type=notify` systemd unit. **Optional** -- only needed if deploying via systemd. Can inline the 10-line notify call instead of adding a dep. |

**Recommendation:** Do NOT add sdnotify as a dependency. If systemd integration is needed later, inline the notify call (it is literally `socket.sendto(b"READY=1", addr)`). Keep the dependency list clean.

## Protocol Design: Why NOT JSON-RPC

JSON-RPC 2.0 was considered and rejected:

| Factor | JSON-RPC | Custom NDJSON | Winner |
|--------|----------|---------------|--------|
| Complexity | Formal spec with id, method, params, result, error objects | Simple `{"cmd": "hire", "args": {...}}` / `{"ok": true, "data": {...}}` | NDJSON |
| Libraries | `ajsonrpc` (last release 2021, low maintenance) | stdlib `json` | NDJSON |
| Fit | Designed for stateless RPC over HTTP | Perfect for request/response over Unix socket | NDJSON |
| Debugging | Verbose wire format | `echo '{"cmd":"status"}' \| socat - UNIX:/tmp/vco.sock` | NDJSON |
| Streaming | Not designed for it | Easy: multiple `\n`-terminated lines | NDJSON |
| Batch calls | Supported but adds complexity | Not needed (one command = one connection) | NDJSON |

**Decision:** Use newline-delimited JSON with a minimal request/response envelope. The protocol is internal (CLI to local daemon), not a public API. Simplicity wins.

### Protocol Envelope

```python
# Request (CLI -> daemon)
{"cmd": "hire", "args": {"project": "myapp", "type": "researcher", "name": "scout"}}

# Success response (daemon -> CLI)
{"ok": true, "data": {"agent_id": "scout", "state": "creating"}}

# Error response (daemon -> CLI)
{"ok": false, "error": "Agent 'scout' already exists", "code": "AGENT_EXISTS"}
```

## Daemonization Strategy

### Foreground Process + systemd (Recommended)

Modern Linux daemons do NOT double-fork. The `vco up` command runs the runtime in the foreground. systemd (or tmux, or direct terminal) manages the process.

| Approach | Verdict | Why |
|----------|---------|-----|
| Double-fork daemon | REJECT | Legacy SysV pattern. Breaks logging, makes debugging harder, adds ~50 lines of fragile code. systemd documentation explicitly says "don't do this." |
| `python-daemon` (PEP 3143) | REJECT | Wraps double-fork. Same problems. PyPI package not maintained. |
| Foreground + systemd | USE THIS | `vco up` runs in foreground. systemd `Type=simple` (or `Type=notify` with inline sd_notify). Standard, debuggable, restartable. |
| Foreground + tmux | ALSO WORKS | Current pattern. `vco up` already runs in a tmux pane. Just keep doing this. |

**Architecture:**
```
# Development: run in terminal or tmux
vco up --project-dir /path/to/project

# Production: systemd unit
[Service]
Type=simple
ExecStart=/home/developer/.local/bin/vco up --project-dir /path/to/project
Restart=on-failure
```

The daemon is just the existing `vco up` command refactored to:
1. Start the asyncio event loop
2. Create CompanyRoot + supervision tree
3. Start the Unix socket server
4. Start the Discord bot (as an asyncio task, not `bot.run()` which blocks)
5. Serve forever

## State Persistence Design

### Extend Existing aiosqlite Pattern

The codebase already has `MemoryStore` (per-agent async SQLite with WAL mode). State persistence follows the same pattern at a higher level.

| State to Persist | Storage | Serialization |
|------------------|---------|---------------|
| Container snapshots (agent_id, type, state, config) | SQLite `containers` table | Pydantic `model_dump_json()` |
| Pane IDs (tmux pane references) | SQLite `pane_state` table | Simple key-value |
| Task queues (pending commands per agent) | SQLite `task_queue` table | JSON text column |
| Project config (agents.yaml snapshot) | SQLite `projects` table | YAML text blob |
| Supervision tree structure | SQLite `supervision` table | Parent-child relationships |

**Why SQLite (not flat files):** The project already uses aiosqlite. SQLite gives atomic writes, WAL mode concurrent reads, and crash safety for free. Flat YAML files for container state would be a regression.

**Why one runtime DB (not per-agent):** Per-agent DBs (MemoryStore) hold agent-private data. Runtime state is cross-cutting -- "which agents exist, what state are they in, what's queued." One `runtime.db` file at `$VCO_STATE_DIR/runtime.db`.

### Recovery Flow

```
vco up (restart)
  1. Open runtime.db
  2. Load container snapshots -> recreate AgentContainer objects with saved state
  3. Load pane IDs -> verify tmux panes still exist (stale = mark errored)
  4. Load task queues -> re-queue pending tasks
  5. Start socket server
  6. Start Discord bot
  7. Resume supervision tree
```

## CLI-as-API-Client Pattern

### Architecture

```
vco hire researcher scout
  |
  click parses args
  |
  open_unix_connection("/tmp/vco.sock")
  |
  send: {"cmd": "hire", "args": {"type": "researcher", "name": "scout"}}\n
  |
  read response line
  |
  {"ok": true, "data": {"agent_id": "scout", "state": "creating"}}
  |
  Rich formats output to terminal
  |
  exit 0
```

### Sync CLI Calling Async Socket

click commands are synchronous. The Unix socket client is async. Bridge with `asyncio.run()`:

```python
# In each CLI command
import asyncio

async def _call_daemon(cmd: str, args: dict) -> dict:
    reader, writer = await asyncio.open_unix_connection("/tmp/vco.sock")
    request = json.dumps({"cmd": cmd, "args": args}) + "\n"
    writer.write(request.encode())
    await writer.drain()
    response = await asyncio.wait_for(reader.readline(), timeout=30.0)
    writer.close()
    await writer.wait_closed()
    return json.loads(response)

@click.command()
def hire(type, name):
    result = asyncio.run(_call_daemon("hire", {"type": type, "name": name}))
    if result["ok"]:
        console.print(f"Hired {name}")
    else:
        console.print(f"Error: {result['error']}", style="red")
        raise SystemExit(1)
```

This is clean and works because each CLI invocation is a short-lived process. No event loop conflicts.

## Installation

```bash
# No new dependencies needed. Existing pyproject.toml covers everything.
# The only change is potentially adding sdnotify if systemd integration is desired:
# uv add sdnotify  # OPTIONAL, can inline instead
```

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| NDJSON over Unix socket | JSON-RPC 2.0 (`ajsonrpc`) | Over-engineered for local IPC. ajsonrpc last released 2021, low maintenance. Our protocol has ~10 commands, not a public API. |
| NDJSON over Unix socket | gRPC | Massive dependency, protobuf compilation step, designed for network services not local IPC. Absurd overkill. |
| NDJSON over Unix socket | HTTP over Unix socket (`httpx` + `uvicorn`) | Adds web framework dependency. HTTP overhead for local IPC is pointless. We already have httpx but don't need a web server. |
| NDJSON over Unix socket | msgpack | Binary protocol adds debugging friction. JSON is human-readable with `socat`. Performance doesn't matter for ~10 commands/minute. |
| `asyncio.start_unix_server` | `trio` | Different async runtime. Would require rewriting all existing asyncio code. No benefit for this use case. |
| Foreground daemon + systemd | `python-daemon` / double-fork | Legacy pattern. systemd docs explicitly discourage it. Breaks logging and debugging. |
| Foreground daemon + systemd | `supervisord` | Another process manager on top of systemd. Unnecessary layer. |
| aiosqlite for state | Redis | External service dependency for a single-machine orchestrator. SQLite is already in the stack and provides everything needed. |
| aiosqlite for state | Flat YAML files | No atomic writes, no concurrent read safety, no crash recovery. Regression from existing aiosqlite pattern. |
| Pydantic for serialization | `pickle` | Security risk (arbitrary code execution on load), not human-readable, version-sensitive. Pydantic JSON is safe and inspectable. |
| Pydantic for serialization | `dataclasses-json` | Pydantic is already in the stack with better validation. Adding another serialization library is pointless. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `ajsonrpc` / any JSON-RPC lib | Low maintenance, over-specified for local IPC, adds a dependency for something that is ~30 lines of custom code | Stdlib `json` + NDJSON protocol |
| `python-daemon` | PEP 3143 reference implementation. Legacy double-fork pattern. Not maintained. | Foreground process + systemd |
| `daemonize` PyPI package | Same double-fork anti-pattern | Foreground process + systemd |
| FastAPI / uvicorn | Adds web server for local IPC. HTTP overhead is pointless when client and server are on the same machine sharing a filesystem. | `asyncio.start_unix_server` |
| Redis / memcached | External service dependency. SQLite already in the stack. No need for a cache layer. | aiosqlite (existing) |
| `socket` module directly | Lower-level than asyncio streams. Would need manual event loop integration. | `asyncio.start_unix_server` / `open_unix_connection` |
| multiprocessing / threading for daemon | The runtime is already async (discord.py, supervisors, health monitoring). Adding threads/processes fragments the architecture. | Single asyncio event loop |

## Stack Patterns by Variant

**If bot needs to be optional (CLI-only mode):**
- Runtime daemon starts without Discord bot
- Socket API works identically
- `vco up --no-bot` flag skips bot startup
- Because the socket server and bot are separate asyncio tasks

**If multiple projects need simultaneous management:**
- Single runtime daemon, single socket
- Commands include `project` field in request
- CompanyRoot already supports multiple ProjectSupervisors
- Because the supervision tree is already multi-project capable

**If daemon socket path needs to be configurable:**
- Default: `/tmp/vco.sock` (or `$XDG_RUNTIME_DIR/vco.sock`)
- Override: `VCO_SOCKET` environment variable
- CLI reads same env var to find the socket
- Because different users on same machine need separate sockets

## Version Compatibility

| Existing Package | Compatible With New Usage | Notes |
|------------------|--------------------------|-------|
| aiosqlite 0.22.1 | Runtime state DB | v0.22.0+ changed Connection to not inherit from Thread. Current code uses context manager pattern, which is correct. No changes needed. |
| pydantic 2.11.x | State snapshot serialization | `model_dump_json()` / `model_validate_json()` are stable v2 APIs. No issues. |
| click 8.2.x | CLI-as-API-client commands | click commands call `asyncio.run()` for socket communication. No conflicts -- each CLI invocation is a separate process with its own event loop. |
| python-statemachine 3.x | State recovery from snapshots | FSM state can be set via `state_field` on model. Recovery sets `_fsm_state` before creating lifecycle, then validates transition is legal. |
| discord.py 2.7.x | Running as asyncio task (not `bot.run()`) | Use `await bot.start(token)` instead of `bot.run(token)`. `bot.run()` blocks with its own event loop; `bot.start()` is a coroutine that works in an existing loop. |

## Key Integration Points

### discord.py: `bot.start()` vs `bot.run()`

Current code uses `bot.run(token)` which creates its own event loop and blocks. The runtime daemon needs discord.py to be one task among many. Use `await bot.start(token)` instead:

```python
async def main():
    root = CompanyRoot(...)
    server = await asyncio.start_unix_server(handler, path="/tmp/vco.sock")
    bot = VcoBot(...)

    await asyncio.gather(
        server.serve_forever(),
        bot.start(bot_token),
        root.run(),  # supervision loop
    )
```

This is the single most important integration detail. Everything else is straightforward.

### State Recovery and python-statemachine

Container recovery must restore FSM state without replaying transitions. The `ContainerLifecycle` FSM uses `state_field="_fsm_state"` on the model. Set `container._fsm_state` before constructing the lifecycle, or use statemachine's `set_state()` if available. Verify this works with a test.

### Socket Permissions

Unix sockets inherit filesystem permissions. The socket file at `/tmp/vco.sock` should be created with mode `0o600` (owner-only). `asyncio.start_unix_server` does not set permissions, so call `os.chmod()` after server start.

## Sources

- [Python asyncio Streams documentation](https://docs.python.org/3/library/asyncio-stream.html) -- `start_unix_server`, `open_unix_connection` API reference (HIGH confidence)
- [ajsonrpc GitHub](https://github.com/pavlov99/ajsonrpc) -- evaluated and rejected, last release July 2021 (HIGH confidence)
- [sdnotify GitHub](https://github.com/bb4242/sdnotify) -- pure Python sd_notify, v0.3.2, ~40 lines (HIGH confidence)
- [systemd daemon documentation](https://www.freedesktop.org/software/systemd/man/latest/daemon.html) -- "new-style" foreground daemon recommendation (HIGH confidence)
- [aiosqlite PyPI](https://pypi.org/project/aiosqlite/) -- v0.22.1, December 2025 (HIGH confidence)
- [Python asyncio Unix socket discussion](https://discuss.python.org/t/how-open-a-unix-domain-socket-with-asyncio/55399) -- community patterns (MEDIUM confidence)

---
*Stack research for: v3.0 CLI-First Architecture -- Runtime Daemon, Unix Socket API, State Persistence*
*Researched: 2026-03-29*
