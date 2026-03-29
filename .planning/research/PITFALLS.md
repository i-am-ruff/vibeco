# Domain Pitfalls: CLI-First Architecture Rewrite (v3.0)

**Domain:** Extracting runtime daemon from Discord bot, Unix socket API, state persistence, CLI-as-API-client
**Researched:** 2026-03-29
**Specific to:** vCompany v3.0 -- adding daemon/socket/persistence to existing bot system

---

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or extended downtime.

### Pitfall 1: The Big Bang Extraction (Bot Dies During Transition)

**What goes wrong:** Attempting to extract CompanyRoot, supervisors, containers, and health monitoring from `VcoBot.on_ready()` into a daemon in a single phase. The 200+ line `on_ready()` method in `client.py` wires callbacks between 8+ components (CompanyRoot, MessageQueue, StrategistCog, PlanReviewCog, HealthCog, PM container, delegation, event sinks). Moving it all at once means the bot is non-functional until every wire is reconnected in the new architecture.

**Why it happens:** The current `client.py:on_ready()` is a monolithic wiring harness. Every component depends on being in the same process -- closures capture `self` (the bot), cogs, channels. Extracting piecemeal feels messy, so developers attempt a clean break.

**Consequences:** Extended period where neither old bot nor new daemon works. Testing requires the full wiring, so partial extraction is hard to validate. The system is unrecoverable until the full extraction is complete.

**Prevention:**
1. Phase 1 should ONLY extract CompanyRoot + supervision tree into a daemon, with the bot connecting to the daemon via socket for those operations.
2. Keep all Discord-specific wiring (cog callbacks, message queue, channel creation) in the bot process initially.
3. The daemon should expose a narrow API surface first (health, hire, dismiss, give-task, status) -- NOT try to replicate all the callback wiring.
4. Use a feature flag or environment variable to switch between "embedded CompanyRoot" (current) and "daemon CompanyRoot" (new) so you can roll back instantly.

**Detection:** If the daemon extraction PR touches more than 3 cog files simultaneously, it is too big.

**Phase target:** Phase 1 (Extract runtime)

---

### Pitfall 2: Callback Closure Hell (Wiring Breaks Across Process Boundary)

**What goes wrong:** The current architecture relies heavily on async callback closures that capture local references. Examples from `client.py`:
- `_on_strategist_response` captures `self` (the bot instance) and calls `self.get_channel()`
- `pm_event_sink` captures `pm_container` directly
- `_on_hire` captures `self.company_root` and `self.get_guild()`
- `_on_escalate_to_strategist` captures `strategist_container` and creates `asyncio.Future` objects

None of these can cross a process boundary. They are in-process Python closures with direct object references.

**Why it happens:** Erlang-style supervision trees work great in a single process with message passing. vCompany's v2 used Python closures as a quick substitute for real message passing. When the supervision tree moves to a daemon process, every closure breaks.

**Consequences:** Every callback needs to be replaced with a serializable event/command that crosses the Unix socket. If done carelessly, you end up with two event systems (the old closures for things that stay in-process, socket messages for cross-process) and unclear ownership of who handles what.

**Prevention:**
1. Audit every `_on_*` callback in `client.py` and classify as "stays in bot" or "moves to daemon."
2. Events that cross the process boundary must be JSON-serializable dicts, not closures with futures.
3. The PM event sink pattern (`pm_event_sink`) already sends dicts -- this is the RIGHT pattern. Extend it.
4. For things like `_on_escalate_to_strategist` that return values (via `asyncio.Future`), design a request-response protocol in the socket API from day one. Do NOT try to pickle futures across processes.

**Detection:** Any callback with `self.get_channel()`, `self.get_guild()`, or direct container references cannot move to the daemon.

**Phase target:** Phase 1 (Extract runtime) and Phase 3 (Bot as thin relay)

---

### Pitfall 3: Stale Unix Socket File on Crash

**What goes wrong:** The daemon creates a Unix domain socket at a known path (e.g., `/tmp/vco-runtime.sock` or `~/.vco/runtime.sock`). If the daemon crashes or is killed with SIGKILL, the socket file remains on disk. Next startup, `asyncio.start_unix_server()` fails with `OSError: [Errno 98] Address already in use` because the stale socket file exists.

**Why it happens:** Unix domain sockets are filesystem entries. Unlike TCP sockets, the OS does not clean them up when the process dies. Python's `asyncio.start_unix_server()` does NOT automatically unlink existing socket files (this is a [known issue in CPython](https://github.com/python/cpython/issues/111246)).

**Consequences:** After any unclean shutdown, `vco up` fails. User must manually `rm /tmp/vco-runtime.sock` before restarting. This is especially bad because the whole point of the daemon is reliability.

**Prevention:**
1. On startup, check if the socket file exists. If it does, try to connect to it. If connection fails, the previous daemon is dead -- unlink the stale file and proceed.
2. Use a PID file alongside the socket. On startup, check if the PID is alive (`os.kill(pid, 0)`). If not, clean up both PID file and socket file.
3. Set socket permissions to 0o600 (owner only) for security.
4. Consider `$XDG_RUNTIME_DIR/vco/runtime.sock` instead of `/tmp/` -- XDG runtime dir is per-user and cleaned on logout.

**Detection:** `vco up` fails after a `kill -9` of the daemon process.

**Phase target:** Phase 1 (Extract runtime)

---

### Pitfall 4: State Persistence Partial Writes (Corruption on Crash)

**What goes wrong:** Container state, pane IDs, and task queues are persisted to disk. If the daemon crashes mid-write, the state file is corrupt (truncated JSON, incomplete YAML). On restart, the daemon cannot recover and either crashes again or starts with empty state, losing all running agent context.

**Why it happens:** Naive file writes (`Path.write_text(json.dumps(state))`) are NOT atomic. The OS can interrupt at any point during the write. Even `json.dump(state, open(path, 'w'))` leaves a truncated file on crash.

**Consequences:** State file corruption means the daemon cannot recover running containers after restart. Agents are still running in tmux but the daemon has lost their pane IDs, task queues, and lifecycle state. Manual recovery required.

**Prevention:**
1. Use atomic writes everywhere: write to temp file in same directory, `os.fsync()`, then `os.rename()` to target path. vCompany already has `write_atomic()` in `shared/file_ops.py` -- use it for ALL state persistence.
2. Keep a write-ahead log (WAL) or use SQLite with WAL mode for state. The existing `MemoryStore` (async SQLite) is already crash-safe -- extend it rather than inventing new file-based state.
3. On startup, validate state file integrity before loading (check JSON parses, required fields present).
4. Keep the previous state file as `state.json.bak` alongside `state.json` so there is always a fallback.

**Detection:** Kill the daemon with `kill -9` during a state write. Restart. Does it recover?

**Phase target:** Phase 4 (State persistence)

---

### Pitfall 5: Two Event Loops (Daemon + Bot Conflict)

**What goes wrong:** The daemon runs its own `asyncio.run()` with CompanyRoot, supervisors, health monitoring, and the socket server. The bot runs `discord.py`'s event loop (also asyncio). If both run in the same process (e.g., `vco up` starts both), they fight over the event loop. If they run in separate processes, they need IPC.

**Why it happens:** `discord.py` takes ownership of the event loop via `bot.run()` (which calls `asyncio.run()` internally). You cannot have two `asyncio.run()` calls in the same process. The current system works because everything is in the bot's event loop.

**Consequences:** If you try `asyncio.run(daemon_main())` and then `bot.run()`, the second one fails. If you try to share a loop, discord.py's internal assumptions about loop ownership may cause subtle bugs (tasks scheduled on wrong loop, callbacks not firing).

**Prevention:**
1. `vco up` should start daemon and bot as SEPARATE processes (fork or subprocess). The daemon is the primary process; the bot is a child process that connects to the daemon via Unix socket.
2. Alternatively, run the daemon's socket server as a task WITHIN discord.py's event loop (like the current CompanyRoot). But this defeats the purpose of separation -- a bot crash still kills the daemon.
3. The clean design: daemon is its own process with `asyncio.run()`. Bot is its own process with `bot.run()`. They communicate via Unix socket. `vco up` spawns both, waits for both.
4. Use `asyncio.start_unix_server()` in the daemon process -- it integrates cleanly with asyncio's event loop.

**Detection:** Attempting to run both daemon and bot in the same `asyncio.run()` call or the same event loop.

**Phase target:** Phase 1 (Extract runtime)

---

## Moderate Pitfalls

### Pitfall 6: CLI-to-Daemon Communication Failures (Daemon Not Running)

**What goes wrong:** `vco status` (or any CLI command) tries to connect to the Unix socket and gets `ConnectionRefusedError` because the daemon is not running. Without good error handling, the user sees a Python traceback instead of a helpful message.

**Prevention:**
1. Every CLI command must catch `ConnectionRefusedError` and `FileNotFoundError` (socket file missing) and print "Runtime not running. Start with `vco up`."
2. Create a shared `connect_to_daemon()` utility that all CLI commands use, with consistent error handling.
3. Add a `--timeout` flag (default 5s) for socket connections. Long-running operations (like `vco new-project` which hires multiple agents) need longer timeouts.
4. Consider a two-tier approach: some commands (like `vco status`) could have a "degraded" mode that reads state files directly when the daemon is down.

**Phase target:** Phase 2 (CLI as API client)

---

### Pitfall 7: Message Framing on Unix Socket (Partial JSON Reads)

**What goes wrong:** JSON messages over a Unix socket stream are not self-delimiting. If you `recv(4096)` you might get half a message, or two messages concatenated. Naive `json.loads(data)` fails on partial reads or returns only the first message and silently drops the second.

**Prevention:**
1. Use length-prefix framing: send 4-byte big-endian length header followed by the JSON payload. Reader reads length first, then reads exactly that many bytes.
2. OR use newline-delimited JSON (NDJSON) where each message is a single line terminated by `\n`. Simpler but breaks if JSON contains literal newlines (use `json.dumps()` which escapes them by default).
3. `asyncio.StreamReader.readline()` works well with NDJSON and handles buffering correctly.
4. Do NOT use raw `socket.recv()` -- use `asyncio.open_unix_connection()` which returns `StreamReader`/`StreamWriter` with proper buffering.

**Phase target:** Phase 1 (Extract runtime) -- get this right from the start.

---

### Pitfall 8: Signal Handling in the Daemon (Orphaned Agents)

**What goes wrong:** The daemon receives SIGTERM (from `vco down` or system shutdown). It must gracefully shut down: stop accepting new connections, drain pending operations, stop all containers (which kills tmux panes), save state, then exit. If signal handling is wrong, the daemon exits immediately, leaving tmux panes running as orphans and state unsaved.

**Prevention:**
1. Register `SIGTERM` and `SIGINT` handlers using `loop.add_signal_handler()` (NOT `signal.signal()` which is not async-safe).
2. The handler should set a shutdown event (`asyncio.Event`) that the main loop checks.
3. Graceful shutdown sequence: (a) stop accepting socket connections, (b) wait for in-flight requests to complete (with timeout), (c) call `company_root.stop()` (which stops all containers), (d) persist final state, (e) unlink socket and PID files, (f) exit.
4. Set a maximum shutdown timeout (e.g., 30s). If containers do not stop within that time, force-kill tmux panes.
5. Handle SIGKILL separately -- you CANNOT handle it, so the startup recovery (Pitfall 4) must handle this case.

**Phase target:** Phase 1 (Extract runtime)

---

### Pitfall 9: Bot-as-Thin-Relay Error Propagation

**What goes wrong:** A Discord slash command calls the daemon via Unix socket. The daemon returns an error (e.g., "agent not found"). The bot must translate this into a user-friendly Discord response. If error propagation is sloppy, the user sees "An error occurred" with no details, or worse, sees a raw JSON error object.

**Prevention:**
1. Define a clear error response format in the socket protocol: `{"ok": false, "error": "agent not found", "code": "AGENT_NOT_FOUND"}`.
2. The bot relay layer should map error codes to user-friendly messages. The daemon should NOT know about Discord formatting.
3. For long-running operations, use a streaming response pattern: daemon sends progress updates, bot edits the Discord message in-place. Do NOT block the Discord interaction response for more than 3 seconds (Discord interaction timeout).
4. Use Discord's deferred response pattern (`await interaction.response.defer()`) for any command that hits the daemon, since socket round-trip + daemon processing could exceed the 3-second limit.

**Phase target:** Phase 3 (Bot as thin relay)

---

### Pitfall 10: State Schema Migration (Version Drift)

**What goes wrong:** You persist container state as JSON in v3.0. In v3.1, you add a new field (`last_task_result`). Old state files lack this field. The daemon crashes on startup trying to deserialize old state into the new schema.

**Prevention:**
1. Include a `schema_version` field in every persisted state file.
2. Write migration functions: `migrate_v1_to_v2(data)`, etc. Run migrations on load.
3. Use Pydantic models with default values for ALL optional fields. `model_validate()` with `extra='ignore'` handles unknown fields gracefully.
4. Never remove a field from the schema without a migration. Mark deprecated fields as optional with defaults first, remove in a later version.
5. Test: save state with current version, bump schema, load old state. Does it work?

**Phase target:** Phase 4 (State persistence)

---

### Pitfall 11: Daemon PID File Race Condition

**What goes wrong:** Two `vco up` commands run simultaneously. Both check the PID file, find it absent, and proceed to start. Both try to bind the socket. One fails with "address in use." Or worse, both succeed briefly and corrupt state.

**Prevention:**
1. Use `fcntl.flock()` (advisory file lock) on the PID file. The first process locks it; the second gets `BlockingIOError` and exits with "Runtime already starting."
2. Write PID to the locked file AFTER acquiring the lock.
3. On `vco up`, check: (a) PID file exists? (b) PID alive? (c) Socket connectable? Only if all three fail, proceed with startup.
4. The lock file should be separate from the PID file to avoid TOCTOU races.

**Phase target:** Phase 1 (Extract runtime)

---

### Pitfall 12: Tmux Pane Recovery After Daemon Restart

**What goes wrong:** The daemon crashes. Agents are still running in tmux panes. The daemon restarts, loads persisted state, and knows agent X should have pane `%42`. But libtmux pane IDs are not stable across tmux server restarts. If tmux itself restarted, `%42` no longer exists. If only the daemon restarted (tmux still running), the pane ID IS still valid -- but the daemon must verify this.

**Prevention:**
1. On daemon startup, for each persisted container with a pane_id: verify the pane exists via `tmux.get_pane_by_id()`. If it does, reconnect. If not, mark the container as errored and let the restart policy handle it.
2. Store the tmux SESSION name and WINDOW name alongside the pane_id. These are more stable for recovery than raw pane IDs.
3. Consider storing the tmux session/window/pane indices rather than (or in addition to) the `%` pane IDs.
4. The `_signal_path` (sentinel file in `/tmp/`) can help: if the signal file says "idle" and the pane exists, the agent is likely still running.

**Phase target:** Phase 4 (State persistence)

---

## Minor Pitfalls

### Pitfall 13: Socket Permission Security

**What goes wrong:** The Unix socket is created with default permissions (often 0o755). Any user on the system can connect and send commands (hire agents, dismiss agents, etc.).

**Prevention:** Set socket permissions to `0o600` after creation. Use `os.chmod()`. Place the socket in a user-owned directory (`~/.vco/` or `$XDG_RUNTIME_DIR/vco/`), not `/tmp/` which is world-readable.

**Phase target:** Phase 1 (Extract runtime)

---

### Pitfall 14: Protocol Versioning from Day One

**What goes wrong:** The socket API is deployed without version negotiation. Later, you add a breaking change to the protocol. Old CLI versions send requests the new daemon does not understand. The daemon returns cryptic errors.

**Prevention:** Include `"protocol_version": 1` in every request/response from day one. The daemon should reject requests with unsupported versions with a clear error: "Protocol version 2 not supported. Update your CLI." This costs nothing to add upfront and saves pain later. Follow JSON-RPC 2.0 conventions or design a simple versioned envelope.

**Phase target:** Phase 1 (Extract runtime)

---

### Pitfall 15: Strategist Bash Autonomy Assumes Synchronous CLI

**What goes wrong:** The Strategist runs `vco hire researcher market-scout` via Bash tool. This CLI command connects to the daemon, sends the hire request, waits for the response. But hiring involves creating directories, deploying artifacts, creating Discord channels, and starting a tmux session. If the CLI blocks for 30+ seconds, the Strategist's Claude Code session may time out or the user may think it is stuck.

**Prevention:**
1. Make `vco hire` return quickly with an acknowledgment ("Hiring market-scout...") and optionally a `--wait` flag for synchronous completion.
2. Or accept the latency but ensure the CLI shows progress output (not silence for 30 seconds).
3. The daemon should handle the hire operation asynchronously internally -- the socket response can be "accepted, agent_id=market-scout" immediately, with the actual startup happening in the background.

**Phase target:** Phase 5 (Strategist autonomy)

---

### Pitfall 16: Losing the In-Process Strategist Conversation

**What goes wrong:** The Strategist's conversation history is managed by `CompanyAgent` with `StrategistConversation`. This object holds the full message history, token tracking, and the anthropic client. Moving CompanyRoot to the daemon means the Strategist conversation must also move. But `StrategistCog` in the bot receives Discord messages and needs to forward them to the conversation. Cross-process conversation management adds latency and complexity.

**Prevention:**
1. Keep the Strategist conversation in the daemon process (it does not need Discord directly).
2. The bot relays messages: user types in #strategist channel -> bot sends message text to daemon via socket -> daemon runs conversation -> daemon sends response text back via socket -> bot posts to Discord channel.
3. This naturally separates concerns but adds one round-trip of latency per message. Acceptable.
4. Streaming responses are harder: daemon must stream tokens back over the socket, bot must edit the Discord message with each chunk. Design the socket protocol to support streaming from the start (e.g., multiple response frames for one request).

**Phase target:** Phase 3 (Bot as thin relay)

---

## Phase-Specific Warnings

| Phase | Likely Pitfall | Mitigation |
|-------|---------------|------------|
| Phase 1: Extract runtime | Pitfall 1 (big bang extraction) | Extract CompanyRoot only, keep all bot wiring, use feature flag |
| Phase 1: Extract runtime | Pitfall 3 (stale socket) | PID file + socket existence check on startup |
| Phase 1: Extract runtime | Pitfall 5 (two event loops) | Daemon and bot must be SEPARATE processes |
| Phase 1: Extract runtime | Pitfall 7 (message framing) | Length-prefix or NDJSON framing from day one |
| Phase 1: Extract runtime | Pitfall 8 (signal handling) | `loop.add_signal_handler()` with graceful shutdown sequence |
| Phase 1: Extract runtime | Pitfall 11 (PID race) | `fcntl.flock()` on lock file |
| Phase 1: Extract runtime | Pitfall 14 (protocol version) | Include version field in all messages |
| Phase 2: CLI as API client | Pitfall 6 (daemon not running) | Shared `connect_to_daemon()` with clear error messages |
| Phase 3: Bot as thin relay | Pitfall 2 (callback closures) | Replace closures with serializable socket messages |
| Phase 3: Bot as thin relay | Pitfall 9 (error propagation) | Structured error codes + Discord deferred responses |
| Phase 3: Bot as thin relay | Pitfall 16 (Strategist conversation) | Keep conversation in daemon, relay text via socket |
| Phase 4: State persistence | Pitfall 4 (partial writes) | Atomic writes with fsync + rename, or extend MemoryStore |
| Phase 4: State persistence | Pitfall 10 (schema migration) | `schema_version` field + Pydantic defaults |
| Phase 4: State persistence | Pitfall 12 (tmux pane recovery) | Verify pane existence on startup, store session/window names |
| Phase 5: Strategist autonomy | Pitfall 15 (sync CLI) | Async hire with immediate acknowledgment |

---

## Codebase-Specific Risk Assessment

These risks are specific to vCompany's current codebase state:

### The `on_ready()` Wiring Monolith

The current `VcoBot.on_ready()` is approximately 200 lines of sequential wiring that creates closures, callbacks, and cross-references between 8+ components. This is the single biggest migration risk. The wiring order matters (e.g., PM event sink must be set LAST, per the comment on line 573-574 of `client.py`). Any extraction plan must preserve this ordering or explicitly redesign the initialization sequence.

**Recommendation:** Before extracting anything, refactor `on_ready()` into named methods (`_wire_strategist()`, `_wire_pm_events()`, `_wire_plan_review()`, etc.) while still in the bot process. This makes the extraction surface visible without changing behavior.

### Signal-Based Idle Detection State

Container idle detection uses sentinel files in `/tmp/`. The daemon needs access to these files. If daemon and agents run as the same user on the same machine (current design), this works. But the sentinel file path is hardcoded in `AgentContainer._signal_path`. If the daemon's `/tmp` is different (e.g., containerized), idle detection breaks.

**Recommendation:** Make signal directory configurable via environment variable or daemon config.

### MemoryStore (Async SQLite) Is Already Per-Agent

The existing `MemoryStore` uses async SQLite with WAL mode. This is already crash-safe for per-agent state. The new state persistence for the daemon should either extend MemoryStore or use a similar pattern -- do NOT invent a new JSON-file-based persistence when SQLite WAL is already proven in the codebase.

## Sources

- [CPython Issue: Unix socket not removed on close](https://github.com/python/cpython/issues/111246)
- [CPython Issue: Unlink stale unix socket before binding](https://github.com/python/asyncio/issues/425)
- [PEP 3143: Standard daemon process library](https://peps.python.org/pep-3143/)
- [Python signal module documentation](https://docs.python.org/3/library/signal.html)
- [Building Robust Graceful Shutdown in Python](https://medium.com/@har.avetisyan2002/building-robust-graceful-shutdown-in-python-beyond-with-open-25ac490b1b9b)
- [How to Implement Atomic File Operations in Python](https://iifx.dev/en/articles/460341744/how-to-implement-atomic-file-operations-in-python-for-crash-safe-data-storage)
- [PSA: Avoid Data Corruption by Syncing to the Disk](https://blog.elijahlopez.ca/posts/data-corruption-atomic-writing/)
- [JSON-RPC 2.0 Specification](https://www.jsonrpc.org/specification)
- [JSON-RPC 2.0 Transport: Sockets](https://www.simple-is-better.org/json-rpc/transport_sockets.html)
- [discord.py FAQ: Blocking and async](https://discordpy.readthedocs.io/en/stable/faq.html)
- [Asyncio Echo Unix Socket Server (Super Fast Python)](https://superfastpython.com/asyncio-echo-unix-socket-server/)
