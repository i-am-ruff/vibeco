# Phase 18: Daemon Foundation - Research

**Researched:** 2026-03-29
**Domain:** Python asyncio daemon with Unix socket IPC, PID file management, signal handling
**Confidence:** HIGH

## Summary

Phase 18 creates the runtime daemon that underpins the entire v3.0 CLI-first architecture. The daemon manages CompanyRoot, the Discord bot, and a Unix socket API -- all in a single asyncio event loop. The key shift from v2 is that `bot.run()` (which owns the event loop) is replaced with `asyncio.run()` owning the loop and `bot.start()` as a coroutine within it. All 12 requirements (DAEMON-01..06, SOCK-01..06) use only Python stdlib (asyncio, signal, os, json) plus existing project dependencies (click, discord.py, pydantic).

The technical challenge is modest but the design must be clean -- this is foundational infrastructure that every subsequent phase (19-23) builds upon. Key risks are: (1) getting signal handling right so graceful shutdown works under SIGTERM/SIGINT, (2) stale socket/PID cleanup for crash recovery, and (3) designing the NDJSON protocol with enough structure for forward compatibility while keeping it simple enough to debug with socat.

**Primary recommendation:** Build a `Daemon` class in `src/vcompany/daemon/` that owns the event loop, PID file, Unix socket server, and bot lifecycle. Keep it separate from CompanyRoot -- the daemon runs CompanyRoot, it does not extend it.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked -- this is an infrastructure phase with all implementation choices at Claude's discretion.

Key decisions established in STATE.md (carry forward):
- Daemon runs bot in-process via `bot.start()` not `bot.run()` -- avoids two-event-loop conflict
- Zero new runtime deps -- stdlib asyncio for socket, existing discord.py/pydantic/click
- State persistence deferred to v3.1 -- daemon restart loses state for now
- NDJSON over Unix socket -- simpler than JSON-RPC, debuggable with socat

### Claude's Discretion
All implementation choices: module structure, class hierarchy, protocol message format, PID file location, socket path, error code numbering, event subscription mechanism.

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase with clear scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DAEMON-01 | `vco up` starts runtime daemon as foreground process with CompanyRoot and supervision tree | Daemon class with `asyncio.run()`, refactored `up_cmd.py` |
| DAEMON-02 | Runtime daemon creates PID file on start and removes on clean exit | PID file pattern in `shared/paths.py`, atexit + finally cleanup |
| DAEMON-03 | Runtime daemon handles SIGTERM/SIGINT for graceful shutdown | `loop.add_signal_handler()` pattern, asyncio-safe shutdown sequence |
| DAEMON-04 | Runtime daemon cleans up stale socket on start (PID probe before unlink) | `os.kill(pid, 0)` probe pattern |
| DAEMON-05 | `vco down` sends graceful shutdown signal to running daemon | New Click command, reads PID file, sends SIGTERM |
| DAEMON-06 | `vco up` starts Discord bot alongside daemon in same event loop | `bot.start()` coroutine in `asyncio.gather()` or sequential startup |
| SOCK-01 | Runtime daemon listens on Unix socket with asyncio.start_unix_server | stdlib asyncio.start_unix_server, verified available on Python 3.12 |
| SOCK-02 | NDJSON protocol for request-response communication | One JSON object per newline, StreamReader.readline() for framing |
| SOCK-03 | Request framing includes method, params, and request ID | Pydantic models for request/response schema |
| SOCK-04 | Error responses include error code, message, and request ID | Standard error code enum, always includes request_id |
| SOCK-05 | Event subscription -- connected clients can subscribe to daemon events | Per-connection subscription set, daemon broadcasts to subscribers |
| SOCK-06 | Protocol version field in handshake for forward compatibility | Client sends hello with version, server validates on connect |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio (stdlib) | Python 3.12 | Event loop, Unix socket server, signal handling | Already used throughout codebase. `start_unix_server` is the correct API for Unix domain sockets. |
| json (stdlib) | Python 3.12 | NDJSON serialization | Zero-dep JSON encoding/decoding. NDJSON is just `json.dumps() + "\n"` per message. |
| signal (stdlib) | Python 3.12 | SIGTERM/SIGINT handling | `loop.add_signal_handler()` for asyncio-safe signal handling. |
| os (stdlib) | Python 3.12 | PID file management, process probing | `os.getpid()`, `os.kill(pid, 0)` for stale PID detection. |
| click | 8.2.x | CLI commands (`vco up`, `vco down`) | Already in pyproject.toml, all CLI commands use Click. |
| pydantic | 2.11.x | Protocol message models | Already in pyproject.toml, used for all config/data validation. |
| discord.py | 2.7.x | Bot co-start via `bot.start()` | Already in pyproject.toml. `bot.start()` is a coroutine (unlike `bot.run()` which owns the loop). |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib (stdlib) | Python 3.12 | Socket and PID file paths | All path operations in codebase use pathlib. |
| logging (stdlib) | Python 3.12 | Daemon logging | Existing logging pattern throughout codebase. |
| enum (stdlib) | Python 3.12 | Error codes, method registry | Type-safe protocol constants. |

**Installation:** No new dependencies required. All from stdlib or existing pyproject.toml.

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
├── daemon/
│   ├── __init__.py
│   ├── daemon.py           # Daemon class: lifecycle, PID, signals
│   ├── server.py           # Unix socket server + client handler
│   ├── protocol.py         # NDJSON protocol models (Request, Response, Error)
│   └── client.py           # Sync client for CLI commands (vco down, future vco status)
├── cli/
│   ├── up_cmd.py           # Refactored: creates Daemon, calls daemon.run()
│   └── down_cmd.py         # NEW: reads PID, sends SIGTERM
└── shared/
    └── paths.py            # Add VCO_SOCKET_PATH, VCO_PID_PATH constants
```

### Pattern 1: Daemon Lifecycle (`daemon.py`)

**What:** A `Daemon` class that owns the full lifecycle: PID file, socket server, bot, CompanyRoot.

**When to use:** Called from `vco up` to start everything.

**Key design:**
```python
class Daemon:
    """Runtime daemon managing CompanyRoot, bot, and socket API."""

    def __init__(self, bot: VcoBot, socket_path: Path, pid_path: Path):
        self._bot = bot
        self._socket_path = socket_path
        self._pid_path = pid_path
        self._server: asyncio.Server | None = None
        self._shutdown_event = asyncio.Event()
        self._subscribers: dict[int, asyncio.StreamWriter] = {}

    def run(self) -> None:
        """Entry point. Calls asyncio.run(self._run())."""
        asyncio.run(self._run())

    async def _run(self) -> None:
        """Main async lifecycle."""
        self._check_already_running()
        self._write_pid_file()
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, self._signal_shutdown)
            loop.add_signal_handler(signal.SIGINT, self._signal_shutdown)

            # Start socket server
            self._server = await asyncio.start_unix_server(
                self._handle_client, path=str(self._socket_path)
            )

            # Start bot (DAEMON-06: bot.start() not bot.run())
            bot_task = asyncio.create_task(self._bot.start(self._bot_token))

            # Wait for shutdown signal
            await self._shutdown_event.wait()

            # Graceful shutdown sequence
            await self._shutdown()
        finally:
            self._cleanup_pid_file()
            self._cleanup_socket()
```

### Pattern 2: Signal-Safe Shutdown

**What:** Signal handlers set an asyncio.Event; the main loop awaits it.

**When to use:** Always for daemon processes. Never do cleanup in signal handlers directly.

**Critical detail:** `loop.add_signal_handler()` runs the callback in the event loop thread, but it must be synchronous. Setting an `asyncio.Event` is the correct bridge -- the event's `set()` method is thread-safe and the main coroutine awaits it.

```python
def _signal_shutdown(self) -> None:
    """Signal handler -- just sets the event. NO async work here."""
    self._shutdown_event.set()
```

### Pattern 3: PID File with Stale Detection (DAEMON-02, DAEMON-04)

**What:** Write PID on start, probe before unlink on next start, remove on clean exit.

```python
def _check_already_running(self) -> None:
    """Refuse to start if another daemon is running. Clean stale PID/socket."""
    if self._pid_path.exists():
        try:
            old_pid = int(self._pid_path.read_text().strip())
            os.kill(old_pid, 0)  # Signal 0 = existence check
            raise SystemExit(f"Daemon already running (PID {old_pid})")
        except ProcessNotFoundError:
            # Stale PID file -- previous crash
            self._pid_path.unlink(missing_ok=True)
            self._socket_path.unlink(missing_ok=True)
        except PermissionError:
            # Process exists but we can't signal it -- someone else's process
            raise SystemExit(f"PID {old_pid} exists but is not ours")

def _write_pid_file(self) -> None:
    self._pid_path.parent.mkdir(parents=True, exist_ok=True)
    self._pid_path.write_text(str(os.getpid()))

def _cleanup_pid_file(self) -> None:
    self._pid_path.unlink(missing_ok=True)
```

### Pattern 4: NDJSON Protocol (SOCK-02, SOCK-03, SOCK-04)

**What:** Newline-delimited JSON. One JSON object per line. StreamReader.readline() for framing.

**Protocol messages:**

```python
# Request (client -> daemon)
{"jsonrpc": "2.0", "id": "req-1", "method": "status", "params": {}}

# Response (daemon -> client)
{"jsonrpc": "2.0", "id": "req-1", "result": {"state": "running"}}

# Error (daemon -> client)
{"jsonrpc": "2.0", "id": "req-1", "error": {"code": -32601, "message": "Method not found"}}

# Event (daemon -> subscribed clients, no id)
{"jsonrpc": "2.0", "method": "event.health_change", "params": {"agent": "BACKEND", "state": "healthy"}}
```

Note: Using JSON-RPC 2.0 framing convention (jsonrpc, id, method, params, result, error) gives us a well-known schema without importing a library. The transport is NDJSON (one object per line), not HTTP. This is simpler than inventing a custom schema and familiar to anyone who's seen LSP or similar protocols.

### Pattern 5: Client Connection Handling

**What:** Each client gets a handler coroutine managing its lifecycle.

```python
async def _handle_client(
    self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Handle a single client connection."""
    client_id = id(writer)
    try:
        while True:
            line = await reader.readline()
            if not line:
                break  # Client disconnected
            try:
                request = json.loads(line.decode())
            except json.JSONDecodeError:
                await self._send(writer, {
                    "jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "Parse error"}
                })
                continue
            response = await self._dispatch(request)
            if response is not None:
                await self._send(writer, response)
    finally:
        self._subscribers.pop(client_id, None)
        writer.close()
        await writer.wait_closed()

async def _send(self, writer: asyncio.StreamWriter, msg: dict) -> None:
    writer.write(json.dumps(msg).encode() + b"\n")
    await writer.drain()
```

### Pattern 6: Event Subscription (SOCK-05)

**What:** Clients send a `subscribe` method to receive daemon events.

```python
# Client subscribes
{"jsonrpc": "2.0", "id": "req-2", "method": "subscribe", "params": {"events": ["health_change", "agent_transition"]}}

# Daemon confirms
{"jsonrpc": "2.0", "id": "req-2", "result": {"subscribed": ["health_change", "agent_transition"]}}

# Daemon pushes events (no id = notification)
{"jsonrpc": "2.0", "method": "event.health_change", "params": {"agent": "BACKEND", "old": "healthy", "new": "degraded"}}
```

Implementation: maintain a `dict[int, tuple[asyncio.StreamWriter, set[str]]]` mapping client ID to writer and subscribed event types. On event, iterate and write to all matching subscribers. Handle broken pipe by removing subscriber.

### Pattern 7: Protocol Version Handshake (SOCK-06)

**What:** First message from client must be a `hello` with protocol version. Server validates.

```python
# Client sends first
{"jsonrpc": "2.0", "id": "hello", "method": "hello", "params": {"version": 1}}

# Server responds
{"jsonrpc": "2.0", "id": "hello", "result": {"version": 1, "daemon_version": "0.1.0"}}

# If version mismatch
{"jsonrpc": "2.0", "id": "hello", "error": {"code": -32600, "message": "Unsupported protocol version 99. Supported: [1]"}}
```

### Anti-Patterns to Avoid
- **Running bot.run() alongside asyncio.run():** Two event loops will deadlock. Always use `bot.start()` as a coroutine within the daemon's single `asyncio.run()`.
- **Doing async work in signal handlers:** Signal handlers run synchronously. Set an event flag only. Cleanup happens in the main coroutine.
- **Using TCP socket instead of Unix socket:** Unix sockets are local-only (security), faster (no TCP overhead), and support file permissions. Perfect for single-machine IPC.
- **Custom protocol framing:** NDJSON + JSON-RPC-style structure is well-understood. Don't invent length-prefix framing or binary protocols.
- **PID file without stale detection:** Always probe with `os.kill(pid, 0)` before assuming a PID file means a running daemon.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unix socket server | Raw socket module | `asyncio.start_unix_server` | Handles accept loop, backpressure, cleanup automatically |
| JSON framing | Length-prefix protocol | NDJSON (newline-delimited) | readline() handles framing, socat-debuggable, human-readable |
| Process management | daemonize, fork, setsid | Foreground process in tmux | DAEMON-01 says "foreground process". No double-fork needed. |
| Config validation | Manual dict parsing | Pydantic models | Already used everywhere. Protocol messages get free validation. |
| Signal handling | signal.signal() | `loop.add_signal_handler()` | asyncio-safe, runs in the event loop thread |

**Key insight:** This phase is pure stdlib Python. Every building block (asyncio server, signal, PID, json) is in the standard library. The only external dependency is discord.py for `bot.start()`. Resist the urge to add any new packages.

## Common Pitfalls

### Pitfall 1: bot.run() vs bot.start()
**What goes wrong:** `bot.run()` calls `asyncio.run()` internally, creating its own event loop. If the daemon also calls `asyncio.run()`, you get nested event loops or "event loop already running" errors.
**Why it happens:** discord.py's `bot.run()` is designed for standalone bots that own the process.
**How to avoid:** Use `bot.start(token)` which is a coroutine. Run it inside the daemon's event loop with `asyncio.create_task()`.
**Warning signs:** "RuntimeError: This event loop is already running" or bot blocking the socket server.

### Pitfall 2: Signal Handler Doing Async Work
**What goes wrong:** Calling `await something()` in a signal handler crashes with "can't await in synchronous context".
**Why it happens:** Signal handlers in asyncio are synchronous callbacks scheduled on the event loop.
**How to avoid:** Signal handler only sets `asyncio.Event`. Main coroutine awaits the event, then does async cleanup.
**Warning signs:** Daemon hangs on SIGTERM instead of shutting down cleanly.

### Pitfall 3: Socket File Left After Crash
**What goes wrong:** After SIGKILL, the socket file remains. Next `vco up` fails with "Address already in use" (errno 98).
**Why it happens:** SIGKILL cannot be caught -- no cleanup runs.
**How to avoid:** On startup, if socket exists, probe PID file. If PID is stale (process doesn't exist), unlink both files. This is DAEMON-04.
**Warning signs:** `OSError: [Errno 98] Address already in use` on second start after crash.

### Pitfall 4: Shutdown Order Matters
**What goes wrong:** Closing the socket server before stopping CompanyRoot means in-flight requests get connection reset. Stopping CompanyRoot before closing bot means the bot can't send final Discord messages.
**Why it happens:** Concurrent systems need ordered shutdown.
**How to avoid:** Shutdown order: (1) Stop accepting new socket connections, (2) Drain in-flight requests with timeout, (3) Stop CompanyRoot (stops containers, tmux), (4) Close bot (sends final Discord messages if possible), (5) Close socket server, (6) Remove PID/socket files.
**Warning signs:** "Connection reset by peer" errors in CLI during shutdown, or containers not cleaned up.

### Pitfall 5: StreamReader.readline() and Malformed Input
**What goes wrong:** If a client sends data without a newline, `readline()` blocks until one arrives or the connection closes. If the JSON object contains literal newlines, parsing fails.
**Why it happens:** NDJSON requires single-line JSON objects.
**How to avoid:** Set a max line length. Use `json.dumps(obj, ensure_ascii=True)` (no literal newlines). Add a read timeout so hung connections don't leak resources.
**Warning signs:** CLI hangs waiting for response, or daemon accumulates idle connections.

### Pitfall 6: vco down Race Condition
**What goes wrong:** `vco down` sends SIGTERM, then immediately exits. The daemon is still shutting down. User runs `vco up` and gets "already running".
**Why it happens:** SIGTERM is asynchronous -- the daemon hasn't cleaned up PID file yet.
**How to avoid:** After sending SIGTERM, `vco down` should poll the PID file (or socket) for up to N seconds until it disappears, then report success/timeout.
**Warning signs:** "Daemon already running" immediately after `vco down`.

### Pitfall 7: File Permissions on Socket
**What goes wrong:** Socket file created with world-readable permissions. Any user on the machine can send commands.
**Why it happens:** Default umask may be permissive.
**How to avoid:** Set socket file permissions to 0o600 (owner only) after creation. `os.chmod(socket_path, 0o600)`.
**Warning signs:** Security review flags -- but functionally it works, which makes it easy to miss.

## Code Examples

### Daemon Entry Point (from `up_cmd.py`)
```python
# Source: Pattern derived from asyncio docs + existing up_cmd.py
@click.command()
@click.option("--project-dir", type=click.Path(), default=None)
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]), default="INFO")
def up(project_dir: str | None, log_level: str) -> None:
    """Start the vCompany daemon."""
    # ... logging setup (keep existing) ...
    from vcompany.daemon.daemon import Daemon
    from vcompany.bot.client import VcoBot
    from vcompany.bot.config import BotConfig
    from vcompany.shared.paths import VCO_PID_PATH, VCO_SOCKET_PATH

    bot_config = BotConfig()
    bot = VcoBot(guild_id=bot_config.discord_guild_id, ...)

    daemon = Daemon(
        bot=bot,
        bot_token=bot_config.discord_bot_token,
        socket_path=VCO_SOCKET_PATH,
        pid_path=VCO_PID_PATH,
    )
    daemon.run()  # Blocks until shutdown
```

### vco down Command
```python
# Source: stdlib pattern
@click.command()
@click.option("--timeout", default=10, help="Seconds to wait for shutdown")
def down(timeout: int) -> None:
    """Stop the vCompany daemon."""
    from vcompany.shared.paths import VCO_PID_PATH
    import time

    if not VCO_PID_PATH.exists():
        click.echo("Daemon is not running (no PID file)")
        raise SystemExit(1)

    pid = int(VCO_PID_PATH.read_text().strip())
    try:
        os.kill(pid, 0)  # Check if alive
    except ProcessNotFoundError:
        VCO_PID_PATH.unlink(missing_ok=True)
        click.echo("Daemon was not running (stale PID file cleaned up)")
        return

    os.kill(pid, signal.SIGTERM)
    click.echo(f"Sent SIGTERM to daemon (PID {pid})")

    # Wait for clean shutdown
    for _ in range(timeout * 10):
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessNotFoundError:
            click.echo("Daemon stopped.")
            return

    click.echo(f"Daemon did not stop within {timeout}s. Use kill -9 {pid} to force.")
    raise SystemExit(1)
```

### NDJSON Client (for CLI commands)
```python
# Source: asyncio streams pattern
import json
import socket

def send_request(socket_path: str, method: str, params: dict | None = None) -> dict:
    """Synchronous NDJSON client for CLI commands."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)
    sock.settimeout(30.0)
    try:
        # Hello handshake
        hello = {"jsonrpc": "2.0", "id": "hello", "method": "hello", "params": {"version": 1}}
        sock.sendall(json.dumps(hello).encode() + b"\n")
        resp_line = b""
        while not resp_line.endswith(b"\n"):
            resp_line += sock.recv(4096)
        hello_resp = json.loads(resp_line)
        if "error" in hello_resp:
            raise RuntimeError(f"Handshake failed: {hello_resp['error']['message']}")

        # Send actual request
        req = {"jsonrpc": "2.0", "id": "req-1", "method": method, "params": params or {}}
        sock.sendall(json.dumps(req).encode() + b"\n")
        resp_line = b""
        while not resp_line.endswith(b"\n"):
            resp_line += sock.recv(4096)
        return json.loads(resp_line)
    finally:
        sock.close()
```

### Socat Testing (for success criteria 4)
```bash
# Connect and send a hello + ping request
echo '{"jsonrpc":"2.0","id":"hello","method":"hello","params":{"version":1}}' | \
  socat - UNIX-CONNECT:/tmp/vco-daemon.sock

# Or interactive session
socat READLINE UNIX-CONNECT:/tmp/vco-daemon.sock
```

## State of the Art

| Old Approach (v2) | Current Approach (v3.0) | Impact |
|---|---|---|
| `bot.run()` owns event loop | `asyncio.run()` with `bot.start()` | Daemon controls lifecycle, bot is a guest |
| All logic in `on_ready()` callbacks | CompanyRoot in daemon, bot connects via API | Clean separation of concerns |
| No IPC -- everything in-process | Unix socket NDJSON API | CLI and bot both talk to daemon |
| No PID management | PID file + stale detection | Single-instance enforcement, crash recovery |
| `vco up` starts bot directly | `vco up` starts daemon (which starts bot) | Daemon is the process, not the bot |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24.x |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/test_daemon.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DAEMON-01 | Daemon starts and creates CompanyRoot | unit | `pytest tests/test_daemon.py::test_daemon_starts -x` | Wave 0 |
| DAEMON-02 | PID file created on start, removed on stop | unit | `pytest tests/test_daemon.py::test_pid_lifecycle -x` | Wave 0 |
| DAEMON-03 | SIGTERM triggers graceful shutdown | unit | `pytest tests/test_daemon.py::test_signal_shutdown -x` | Wave 0 |
| DAEMON-04 | Stale socket cleaned on start | unit | `pytest tests/test_daemon.py::test_stale_cleanup -x` | Wave 0 |
| DAEMON-05 | vco down sends SIGTERM to daemon | unit | `pytest tests/test_down_cmd.py::test_down_sends_sigterm -x` | Wave 0 |
| DAEMON-06 | Bot starts alongside daemon | unit | `pytest tests/test_daemon.py::test_bot_costart -x` | Wave 0 |
| SOCK-01 | Unix socket server accepts connections | unit | `pytest tests/test_daemon_socket.py::test_socket_accepts -x` | Wave 0 |
| SOCK-02 | NDJSON request-response works | unit | `pytest tests/test_daemon_socket.py::test_ndjson_roundtrip -x` | Wave 0 |
| SOCK-03 | Request framing has method, params, id | unit | `pytest tests/test_daemon_protocol.py::test_request_model -x` | Wave 0 |
| SOCK-04 | Error responses have code, message, id | unit | `pytest tests/test_daemon_protocol.py::test_error_response -x` | Wave 0 |
| SOCK-05 | Event subscription works | unit | `pytest tests/test_daemon_socket.py::test_event_subscription -x` | Wave 0 |
| SOCK-06 | Protocol version handshake | unit | `pytest tests/test_daemon_socket.py::test_hello_handshake -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_daemon.py tests/test_daemon_socket.py tests/test_daemon_protocol.py tests/test_down_cmd.py -x`
- **Per wave merge:** `python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_daemon.py` -- covers DAEMON-01..04, DAEMON-06
- [ ] `tests/test_daemon_socket.py` -- covers SOCK-01, SOCK-02, SOCK-05, SOCK-06
- [ ] `tests/test_daemon_protocol.py` -- covers SOCK-03, SOCK-04 (Pydantic model tests)
- [ ] `tests/test_down_cmd.py` -- covers DAEMON-05

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | Runtime | Yes | 3.12.3 | -- |
| asyncio.start_unix_server | SOCK-01 | Yes | stdlib | -- |
| socat | Success criteria testing | No | -- | Can use Python client or `nc -U` for testing |
| tmux | Existing agent sessions | Yes (via libtmux dep) | -- | -- |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:**
- socat: Not installed. Tests should use the Python socket client. Success criteria 4 mentions socat but Python-based verification is equivalent. Can install with `apt install socat` if manual testing desired.

## Open Questions

1. **Socket path location**
   - What we know: `/tmp/vco-daemon.sock` is simple and conventional. `$XDG_RUNTIME_DIR/vco/daemon.sock` is more correct per FDO spec.
   - Recommendation: Use `/tmp/vco-daemon.sock` for simplicity. Can add `VCO_SOCKET_PATH` env var override later. XDG adds complexity without value for single-user single-machine.

2. **PID file location**
   - What we know: `/tmp/vco-daemon.pid` matches socket location convention.
   - Recommendation: Use `/tmp/vco-daemon.pid`. Same reasoning as socket path.

3. **Should `vco up` daemonize (fork to background)?**
   - What we know: DAEMON-01 says "foreground process". Current `vco up` runs bot in foreground.
   - Recommendation: Keep foreground. User runs in tmux session or with `&`. Daemonizing adds complexity (double-fork, stdout redirection, signal forwarding) with zero value when tmux is the deployment target.

4. **How many methods does the socket API need in this phase?**
   - What we know: Phase 18 is foundation. CLI commands come in Phase 21. Only `hello`, `ping`, `subscribe`, and `shutdown` are needed now.
   - Recommendation: Implement `hello`, `ping` (health check), `subscribe`, and `shutdown`. Future phases add domain methods. The dispatch table pattern makes adding methods trivial.

## Sources

### Primary (HIGH confidence)
- Python 3.12 asyncio docs -- `asyncio.start_unix_server()`, `StreamReader.readline()`, `loop.add_signal_handler()` -- all verified available on target Python 3.12.3
- Existing codebase: `bot/client.py` `VcoBot.close()` shows existing shutdown pattern, `bot.start()` vs `bot.run()` pattern documented in discord.py
- Existing codebase: `supervisor/company_root.py` shows CompanyRoot `start()/stop()` lifecycle

### Secondary (MEDIUM confidence)
- JSON-RPC 2.0 spec (jsonrpc.org) -- used as protocol framing convention, not full compliance (no batching, no HTTP transport)
- NDJSON spec (ndjson.org) -- one JSON value per line, `\n` delimiter

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib, verified on target Python
- Architecture: HIGH -- straightforward asyncio patterns, no novel design
- Pitfalls: HIGH -- common patterns well-documented, verified against Python 3.12 behavior
- Protocol: MEDIUM -- JSON-RPC-style framing is a design choice, could also use simpler custom format

**Research date:** 2026-03-29
**Valid until:** 2026-05-29 (stable domain, stdlib APIs don't change)
