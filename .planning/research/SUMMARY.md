# Project Research Summary

**Project:** vCompany — v3.0 CLI-First Architecture
**Domain:** Runtime daemon extraction, Unix socket IPC, CLI-as-API-client, state persistence
**Researched:** 2026-03-29
**Confidence:** HIGH

## Executive Summary

vCompany v3.0 is a structural rewrite that extracts all core orchestration logic from the Discord bot and moves it into a standalone runtime daemon. The system then follows the proven CLI-daemon pattern used by Docker, Tailscale, and Mullvad VPN: a long-lived daemon owns all state and operations; the CLI and bot are stateless thin clients communicating via a Unix domain socket with a newline-delimited JSON protocol. The motivating killer feature is Strategist Bash autonomy — once CLI commands exist, the Strategist's Claude session can call `vco hire`, `vco give-task`, and `vco dismiss` directly via its Bash tool, with no special callback parsing or action tags. This is the payoff for the entire rewrite.

The recommended implementation requires zero new runtime dependencies. Python 3.12 stdlib (`asyncio.start_unix_server`, `asyncio.open_unix_connection`, `json`) handles the socket protocol. All other needs are covered by existing deps: `aiosqlite` for crash-safe state persistence, `pydantic v2` for state serialization, `click` for CLI commands, and `discord.py` running via `await bot.start(token)` as an asyncio coroutine inside the daemon's event loop. The bot stays in-process with the daemon — this avoids the two-event-loop problem while enforcing a clean architectural boundary through the new `RuntimeAPI` abstraction.

The highest risk is extracting `VcoBot.on_ready()`, a ~300-line monolithic wiring harness that creates CompanyRoot and wires 15+ callback closures coupling every component to the bot process. Attempting this in a single phase will result in extended broken state. The correct approach is incremental: first refactor `on_ready()` into named methods without moving anything, then move CompanyRoot into the daemon behind a feature flag, then progressively replace callback closures with RuntimeAPI calls. State persistence adds a secondary risk: naive file writes corrupt on crash — extend the existing `MemoryStore` aiosqlite WAL pattern rather than inventing new file-based persistence.

## Key Findings

### Recommended Stack

Zero new runtime dependencies are needed for v3.0. The entire daemon-socket-CLI pattern is implemented with Python 3.12 stdlib plus existing deps. The one critical migration is switching from `bot.run(token)` to `await bot.start(token)` in the daemon's asyncio event loop — `bot.run()` creates its own blocking event loop, which conflicts with the daemon's. This is the single most important implementation detail in the entire rewrite.

**Core technologies:**
- `asyncio.start_unix_server` (stdlib): Socket server in daemon — integrates with existing asyncio loop, no framework overhead
- `asyncio.open_unix_connection` (stdlib): CLI-to-daemon client — `asyncio.run()` bridges sync click commands to async socket
- NDJSON via stdlib `json`: Wire protocol — `readline()` on StreamReader, simpler than JSON-RPC, debuggable with `socat`
- `aiosqlite` 0.22.1 (existing): Runtime state persistence — extend existing MemoryStore pattern, WAL mode crash-safe
- `pydantic` v2 (existing): State snapshot serialization — `model_dump_json()` / `model_validate_json()`, validates on restore
- `discord.py` 2.7.x (existing): Run as `await bot.start(token)` inside daemon event loop, not blocking `bot.run()`
- `click` 8.2.x (existing): CLI commands call `asyncio.run(_call_daemon(...))` — clean sync-to-async bridge per invocation

### Expected Features

All v3.0 features map to a strict dependency chain. PID file is the absolute foundation; CompanyRoot extraction is the hardest prerequisite; CLI commands only work once the socket server exists; bot refactoring and Strategist autonomy come last.

**Must have (table stakes — v3.0 core):**
- PID file + single-instance guard — prevents two daemons conflicting on socket and tmux sessions
- `vco up` / `vco down` daemon lifecycle — explicit start/stop with SIGTERM/SIGINT graceful shutdown
- CompanyRoot extraction from bot — supervision tree starts in daemon, not in `VcoBot.on_ready()`
- Unix socket server at `~/.vco/vco.sock` — NDJSON request/response, permissions `0o600`
- Shared `VcoClient` library — used by both CLI commands and bot, handles connection/serialization/errors
- Core CLI commands: `vco hire`, `vco give-task`, `vco dismiss`, `vco status`, `vco health`
- `vco new-project` composite command — init + clone + hire all agents via API
- State persistence — container state, pane IDs, task queues to SQLite on every state change
- State recovery on restart — reconnect tmux sessions, restore containers, mark crashed where panes gone
- Bot refactored to thin relay — slash commands call RuntimeAPI directly, no CompanyRoot ownership in bot

**Should have (v3.x after core is proven):**
- Strategist Bash autonomy — Strategist calls `vco hire/give-task/dismiss` via Bash tool once CLI is battle-tested
- Daemon auto-start — any command auto-starts daemon if not running, reduces `vco up` friction
- Streaming responses — long-running commands stream progress to terminal

**Defer to v4+:**
- Socket event subscription (push) — bot subscribes to state changes; adds protocol complexity, defer until bot latency is noticeable
- TCP socket option — for multi-machine setups
- Authentication on socket — only if multi-user access needed

### Architecture Approach

The target architecture has four layers: (1) the runtime daemon (`VcoRuntime`) owns the asyncio event loop and starts CompanyRoot, socket server, bot, and state persistence as coordinated asyncio tasks; (2) `VcoSocketServer` accepts NDJSON connections and routes to `RuntimeAPI`; (3) `RuntimeAPI` is the single gateway replacing the 300 lines of `on_ready()` wiring — both socket server and in-process bot call this directly; (4) `StatePersistence` hooks into lifecycle events to snapshot state to SQLite on every change. The bot runs in-process as a coroutine sharing the daemon's event loop, with the architectural boundary enforced by RuntimeAPI, not process isolation.

**Major components:**
1. `VcoRuntime` (`runtime/daemon.py`) — daemon lifecycle: PID file, signal handling, ordered start/stop of all subsystems
2. `VcoSocketServer` (`runtime/server.py`) — NDJSON Unix socket, routes requests to RuntimeAPI, pushes events to subscribers
3. `RuntimeAPI` (`runtime/api.py`) — single gateway: replaces all `on_ready()` callback wiring; handles hire, give_task, dismiss, status, health_tree, new_project
4. `VcoClient` (`runtime/client.py`) — async+sync socket client shared by CLI commands; bot calls RuntimeAPI directly (in-process)
5. `StatePersistence` (`runtime/persistence.py`) — extends existing aiosqlite MemoryStore pattern to daemon-level state
6. `VcoBot` (existing, heavily modified) — Discord skin: slash commands call RuntimeAPI, no CompanyRoot ownership, no inline closures

### Critical Pitfalls

1. **The Big Bang Extraction** — Extracting CompanyRoot + all wiring in one phase leaves the system non-functional until every wire is reconnected. Prevention: refactor `on_ready()` into named methods first (no behavior change), then move CompanyRoot behind a feature flag. If the extraction PR touches more than 3 cog files simultaneously, it is too big.

2. **Two Event Loops** — `bot.run()` creates its own blocking event loop; two `asyncio.run()` calls in one process conflict. Prevention: use `await bot.start(token)` inside the daemon's event loop. This is the single most important implementation detail.

3. **Stale Unix Socket on Crash** — Python's `asyncio.start_unix_server()` does NOT clean up socket files on SIGKILL death (CPython issue #111246). `vco up` after a crash fails with "Address already in use." Prevention: on startup, attempt to connect to existing socket; if connection fails, unlink stale file and proceed. Back this with PID file + `os.kill(pid, 0)` liveness check.

4. **Callback Closure Hell** — Current `on_ready()` has 15+ closures capturing bot instance, channels, containers, and asyncio Futures. None cross a process boundary or refactor safely without first mapping each to a RuntimeAPI method. Prevention: audit every `_on_*` callback and classify "stays in bot" vs "moves to daemon" before touching anything.

5. **State Persistence Partial Writes** — Naive `Path.write_text(json.dumps(state))` is not atomic and will corrupt on SIGKILL. Prevention: use atomic writes (write to temp, `os.fsync()`, `os.rename()`) or extend existing aiosqlite MemoryStore with WAL mode. Never invent new JSON-file-based persistence when SQLite WAL is already proven in the codebase.

## Implications for Roadmap

Based on the dependency chain from FEATURES.md and the extraction risks from PITFALLS.md, five phases are suggested:

### Phase 1: Daemon Foundation
**Rationale:** PID file, socket server, and daemon lifecycle are absolute prerequisites with no external dependencies and well-documented patterns. Must resolve stale socket, two-event-loops, and signal handling pitfalls here or they infect everything downstream.
**Delivers:** `vco up` / `vco down`, PID file with `fcntl.flock()`, Unix socket server with NDJSON protocol, VcoClient library, `vco health` ping, socket permissions `0o600`
**Addresses:** PID file + single instance (P1), Unix socket server (P1), socket client library (P1), daemon status detection (P1)
**Avoids:** Pitfall 3 (stale socket — unlink on startup), Pitfall 5 (two event loops — `bot.start()` not `bot.run()`), Pitfall 7 (message framing — NDJSON with `readline()`), Pitfall 8 (signal handling — `loop.add_signal_handler()`), Pitfall 11 (PID race — `fcntl.flock()`), Pitfall 14 (protocol versioning — add `protocol_version` field from day one)

### Phase 2: CompanyRoot Extraction
**Rationale:** The hardest and highest-risk phase. CompanyRoot must move from `VcoBot.on_ready()` into the daemon before any CLI commands are possible. A refactor-first step (named methods, feature flag) de-risks the migration. Bot temporarily uses RuntimeAPI via direct reference while slash commands still function.
**Delivers:** CompanyRoot running inside daemon process, RuntimeAPI as single gateway replacing all `on_ready()` wiring, bot wired to RuntimeAPI instead of owning CompanyRoot directly
**Uses:** All stack elements from Phase 1 plus existing CompanyRoot, supervision tree, container FSM
**Avoids:** Pitfall 1 (big bang extraction — named methods refactor first), Pitfall 2 (callback closures — map each `_on_*` to RuntimeAPI method before migrating)

### Phase 3: CLI as API Clients
**Rationale:** Once the daemon owns CompanyRoot and exposes RuntimeAPI via socket, CLI commands are straightforward thin clients. Low-risk, immediate tangible value to human operators, and prerequisite to proving the interface is stable enough for Strategist autonomy.
**Delivers:** `vco hire`, `vco give-task`, `vco dismiss`, `vco status`, `vco new-project` as working CLI commands
**Uses:** `click` + `asyncio.run()` bridge pattern, VcoClient library
**Avoids:** Pitfall 6 (daemon not running — shared `connect_to_daemon()` with clear "run `vco up` first" errors)

### Phase 4: State Persistence and Recovery
**Rationale:** Crash-safe state is needed before the system is trusted in production. Implementing after daemon architecture is stable avoids premature optimization. Must use atomic writes and extend existing aiosqlite pattern.
**Delivers:** Container state, pane IDs, task queues persisted to `runtime.db`; daemon restart reconnects existing tmux sessions; crashed containers detected and marked for restart policy
**Uses:** `aiosqlite` existing pattern, `pydantic` `model_dump_json()` / `model_validate_json()`
**Avoids:** Pitfall 4 (partial writes — atomic via aiosqlite WAL), Pitfall 10 (schema migration — add `schema_version` on first write), Pitfall 12 (tmux pane recovery — store session/window names alongside pane IDs, verify on restart)

### Phase 5: Bot as Thin Relay and Strategist Autonomy
**Rationale:** Once CLI commands are proven stable with manual use, bot refactor is mechanical (replace CompanyRoot ownership with RuntimeAPI calls). Strategist autonomy is then free — Strategist runs `vco hire` via Bash tool with zero additional wiring. Both ship together because Strategist autonomy depends on CLI commands being battle-tested.
**Delivers:** Bot slash commands calling RuntimeAPI with no CompanyRoot imports, Strategist can `vco hire/give-task/dismiss` autonomously via Bash tool
**Avoids:** Pitfall 9 (bot error propagation — structured error codes + Discord deferred responses for all socket-backed commands), Pitfall 15 (sync CLI latency for Strategist — async hire with immediate acknowledgment, `--wait` flag optional), Pitfall 16 (Strategist conversation stays in daemon, text relayed via socket)

### Phase Ordering Rationale

- Phases 1 and 2 must precede everything: all downstream features depend on the daemon existing and owning CompanyRoot.
- Phase 3 (CLI) precedes Phase 4 (persistence) because CLI commands are independently testable and deliver value without crash-safe state.
- Phase 4 (persistence) precedes Phase 5 (Strategist) because Strategist autonomy in production is not safe if a daemon crash loses all agent state.
- Phase 5 (Strategist) is intentionally last: it is the payoff feature and should only ship once phases 1-4 are stable.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** CompanyRoot extraction is the highest-risk phase. The wiring order in `on_ready()` has documented ordering constraints (PM event sink must be last per code comments). A detailed mapping of all 15+ callback closures to their RuntimeAPI equivalents is needed before Phase 2 begins. Recommend a pre-execution audit task.
- **Phase 4:** Tmux pane ID stability across daemon restarts needs validation. Research recommends storing session/window names alongside pane IDs, but the exact libtmux API for pane lookup by session+window+index needs confirmation against the pinned libtmux 0.55.x API.

Phases with standard patterns (skip research-phase):
- **Phase 1:** Unix socket + PID file patterns are thoroughly documented. All code samples are fully specified in ARCHITECTURE.md. Standard implementation.
- **Phase 3:** CLI-as-API-client is mechanical once the socket server exists. The `click` + `asyncio.run()` bridge pattern is straightforward with no unknowns.
- **Phase 5 (bot thin relay):** The migration map in FEATURES.md lists every existing feature and its v3.0 location. Execution is mechanical given the RuntimeAPI exists.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technologies are existing deps or Python stdlib. No new packages needed. Version compatibility confirmed. `bot.start()` vs `bot.run()` distinction verified against discord.py docs. |
| Features | HIGH | Feature dependency graph is well-defined. Reference architectures (Docker, Tailscale, Mullvad) provide strong analogies. MVP scope is explicit with prioritization matrix. |
| Architecture | HIGH | Based on direct codebase inspection. Component boundaries, data flow, all new module signatures, and protocol wire format are fully specified in ARCHITECTURE.md. |
| Pitfalls | HIGH | Pitfalls are grounded in specific codebase risks (named files, line numbers, code comments). CPython known issue #111246 on stale sockets is documented. Atomic write requirement is well-understood. |

**Overall confidence:** HIGH

### Gaps to Address

- **on_ready() wiring order:** The exact sequence of callback wiring in `on_ready()` has ordering constraints documented in code comments. A complete audit mapping each of the 15+ closures to its RuntimeAPI equivalent is needed before Phase 2 begins. This is a planning task, not a research task — assign it as the first task of Phase 2.
- **FSM state recovery with python-statemachine:** Container lifecycle FSM recovery (restoring state without replaying transitions) needs a passing test before Phase 4 ships. The `_fsm_state` field approach described in STACK.md needs validation against the pinned python-statemachine 3.x API.
- **Signal directory configurability:** `AgentContainer._signal_path` is currently hardcoded to `/tmp/`. If the daemon's `/tmp` ever diverges from agents' `/tmp` (e.g., future containerization), idle detection breaks. Make this configurable via environment variable before Phase 4 ships.
- **Discord channel creation on hire:** Currently embedded inside CompanyRoot — needs extraction to RuntimeAPI or a bot event handler before bot thin relay is complete. Needs explicit assignment in Phase 5 planning.

## Sources

### Primary (HIGH confidence)
- Python asyncio Streams docs — `start_unix_server`, `open_unix_connection` API reference
- CPython issue tracker #111246 — Unix socket not unlinked on close, confirmed behavior
- aiosqlite PyPI v0.22.1 — WAL mode, context manager usage
- pydantic v2 docs — `model_dump_json()` / `model_validate_json()` stable APIs
- systemd daemon documentation — "new-style" foreground daemon recommendation, double-fork explicitly discouraged
- discord.py docs — `bot.start()` vs `bot.run()` distinction
- Existing vCompany codebase — `VcoBot.on_ready()` in `bot/client.py`, CompanyRoot in `supervisor/company_root.py`

### Secondary (MEDIUM confidence)
- Docker Client-Server Architecture (OneUptime blog) — HTTP-over-Unix-socket pattern as reference
- Tailscale CLI Architecture (deepwiki) — LocalAPI over Unix socket, stateless CLI client pattern
- Mullvad VPN CLI (deepwiki) — stateless gRPC CLI client pattern
- Python asyncio Unix socket server (superfastpython.com) — `asyncio.start_unix_server()` usage examples
- Graceful Shutdown Patterns (geeksforgeeks system design) — ordered shutdown, connection draining

### Tertiary (LOW confidence)
- Community Python asyncio Unix socket discussion — edge case patterns for reconnection handling

---
*Research completed: 2026-03-29*
*Ready for roadmap: yes*
