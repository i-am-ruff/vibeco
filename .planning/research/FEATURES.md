# Feature Research: CLI-First Architecture with Runtime Daemon

**Domain:** CLI-first daemon architecture for multi-agent orchestration system
**Researched:** 2026-03-29
**Confidence:** HIGH

## Feature Landscape

This research targets the v3.0 milestone: extracting all core logic from the Discord bot into a runtime daemon with Unix socket API, making the CLI the primary interface and the bot a thin Discord skin. All features are evaluated against the existing v2.0/v2.1 codebase (CompanyRoot, supervision tree, containers, health tree) and the proven CLI-daemon patterns used by Docker, Tailscale, and Mullvad VPN.

### Table Stakes (Users Expect These)

Features that any CLI-first daemon architecture must have. Missing these means the system feels broken or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `vco up` / `vco down` daemon lifecycle | Every daemon-based tool has explicit start/stop. Docker has `dockerd`, Tailscale has `tailscaled`. Users need to control when the daemon runs. | MEDIUM | Needs PID file at `~/.vco/vco.pid`, stale PID detection, and `vco up` that refuses to double-start. SIGTERM/SIGINT handling for clean shutdown. Depends on: nothing (foundation). |
| PID file and single-instance guard | Standard daemon pattern -- prevents two instances from conflicting on the same socket and tmux sessions. Docker, Tailscale, systemd all enforce this. | LOW | Write PID to file on start, check on subsequent `vco up`. Remove on clean exit. Detect stale PIDs (process dead but file exists) via `os.kill(pid, 0)`. Depends on: nothing. |
| Unix socket API with JSON protocol | The communication channel between CLI and daemon. Tailscale uses HTTP-over-Unix-socket (LocalAPI). Docker uses HTTP-over-Unix-socket. Python has `asyncio.start_unix_server()` in stdlib. | MEDIUM | Socket at `~/.vco/vco.sock`. Newline-delimited JSON (simpler than HTTP, lighter than gRPC). Each request is `{"method": "hire", "params": {...}}`, each response is `{"ok": true, "result": {...}}` or `{"ok": false, "error": "..."}`. Depends on: daemon process. |
| CLI commands as thin API clients | Mullvad CLI is "solely responsible for command parsing, daemon communication, and output formatting." Docker CLI translates commands into API calls. Each `vco` subcommand opens socket, sends JSON, reads JSON, formats output. | MEDIUM | Each Click command: connect to socket, send request, read response, format with Rich. No state in CLI process. Error path: "daemon not running, run `vco up` first." Depends on: Unix socket API. |
| Graceful shutdown with state persistence | When daemon stops, running agent state must survive. Docker persists container state. Kubernetes drains connections. vCompany must snapshot container states, pane IDs, task queues to disk before exit. | HIGH | SIGTERM handler triggers ordered shutdown: (1) stop accepting new socket connections, (2) snapshot all container state to `~/.vco/state/`, (3) stop health monitoring, (4) close socket, (5) remove PID file. Timeout of 30s before force-exit. Depends on: state persistence. |
| State recovery on restart | Daemon restart must recover all agent containers from persisted state. Docker containers survive `dockerd` restart. This is the core value proposition -- bot crash no longer kills agents. | HIGH | On startup: read state from `~/.vco/state/`, reconnect to existing tmux sessions by pane ID (tmux sessions outlive the daemon), restore task queues, mark containers whose tmux panes are gone as CRASHED (trigger restart policy). Depends on: state persistence, daemon process. |
| Health check endpoint | Every daemon exposes health. Docker has `docker info`, Tailscale has `tailscale status`. `vco health` must work when daemon is up and return a clear error when down. | LOW | Socket request `{"method": "health"}` returns the existing `CompanyHealthTree`. `vco health` formats with Rich tables (reuse existing health embed logic). Depends on: Unix socket API. |
| Daemon status detection | CLI must know if daemon is up before sending commands. `vco status` when daemon is down should say "daemon not running" not hang or crash. | LOW | Check PID file existence + socket connectivity. Some commands work without daemon (e.g., `vco version`). Connection timeout of 2s on socket. Depends on: PID file. |
| Bot as thin relay | Discord bot becomes a presentation layer only. Slash commands translate to the same API calls the CLI uses. No container references in bot code. No CompanyRoot import in bot. | MEDIUM | Bot connects to Unix socket on startup. `/health` calls same endpoint as `vco health`, formats as Discord embed. `/new-project` calls same endpoint as `vco new-project`. Bot only adds Discord-specific formatting (embeds, buttons, threads). Depends on: Unix socket API, CLI commands. |
| `vco new-project` composite command | Currently `/new-project` in bot does init + clone + hire. The CLI version must do the same: create project, clone repos, hire each agent from agents.yaml. Single command, multiple API calls. | MEDIUM | Reads agents.yaml, calls `hire` for each agent sequentially. Reports progress to stdout (or Discord if called via bot). Replaces duplicated init logic in `bot/cogs/commands.py`. Depends on: `vco hire`, state persistence. |

### Differentiators (Competitive Advantage)

Features that make vCompany's CLI-first architecture stand out. Not required for initial launch, but high value.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Strategist Bash autonomy via same CLI | The Strategist agent (Claude in tmux) calls `vco hire`, `vco give-task`, `vco dismiss` via Bash tool. No special wiring, no action tag parsing, no Discord round-trip. Same interface for human, bot, and AI agents. This is the entire motivation for v3.0. | LOW | Once CLI commands work as API clients, this is free. The Strategist's `--allowedTools "Bash"` gives it `vco` access. Zero additional code beyond the CLI commands themselves. Depends on: CLI commands working. |
| Bot-independent operation | System fully functional without Discord bot running. Owner manages everything from terminal. Bot crash has zero impact on running agents. True graceful degradation. | LOW | Falls out naturally from the architecture. Daemon owns all state, CLI owns all logic, bot is optional. Only cost: ensure daemon never requires bot connection. Depends on: architecture itself. |
| Daemon auto-start on first command | Instead of requiring explicit `vco up`, any command auto-starts the daemon. Tailscale does this -- `tailscale up` starts `tailscaled` if needed. Reduces friction. | MEDIUM | CLI checks if daemon is running. If not, fork daemon to background, poll socket with backoff (max 5s), then send command. Must handle race (two commands auto-starting simultaneously -- use PID file as lock). Depends on: daemon lifecycle, PID file. |
| Streaming responses over socket | Long-running operations (like `vco new-project` cloning + hiring N agents) stream progress. Docker does this for `docker pull`. | MEDIUM | Socket protocol supports streaming: daemon sends multiple JSON lines per request, CLI prints each. Final line has `"done": true`. Enriches UX for composite commands. Depends on: Unix socket API. |
| Socket event subscription (push) | CLI or bot subscribes to events (state changes, health updates, task completions) via persistent socket connection. Bot uses this instead of polling. | HIGH | Pub/sub layer in daemon. Clients send `{"method": "subscribe", "events": ["health", "state"]}`. Daemon pushes events as they occur. Avoids polling but adds bidirectional protocol complexity. Defer unless bot performance demands it. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| HTTP/REST API instead of Unix socket | "More standard", "tools can curl it" | Adds network exposure, needs auth, CORS. vCompany is single-machine -- network sockets add attack surface with zero benefit. Docker's biggest security footgun is the TCP socket. | Unix domain socket with filesystem permissions (`chmod 600`). Same request/response semantics, zero network exposure. |
| gRPC for daemon communication | "Type-safe", "schema-driven" | Adds protobuf compilation step, heavy dependency (grpcio ~50MB), overkill for ~15 API methods on localhost. Mullvad uses gRPC but they ship cross-platform GUI clients. | Newline-delimited JSON over Unix socket. Define request/response schemas with Pydantic models. Type safety via Python, not protobuf. |
| Web dashboard for monitoring | "Visual overview", "graphs" | Adds web server, frontend build, WebSocket layer. Discord already is the visual interface. Terminal has Rich tables. | `vco status` with Rich formatting. Discord embeds for remote. Both consume same health API endpoint. |
| Database for state persistence | "SQLite is more robust", "queryable" | Adds migration complexity, another failure mode. Container state is a small tree (<100 nodes). JSON files are human-readable, diff-able, trivially debuggable. | JSON files in `~/.vco/state/`. One file per project. Atomic writes via `tempfile + os.rename()`. Already using filesystem state throughout codebase. |
| Plugin system for custom commands | "Extensibility" | Premature abstraction. vCompany has a fixed ~15 operations. Plugin systems add API surface to maintain with no current consumers. | Hard-code commands. Click's `group.add_command()` makes adding new ones trivial later. |
| Systemd integration (socket activation, service file) | "Proper daemon management" | Couples to systemd, doesn't work on macOS, adds packaging complexity. vCompany runs on one developer machine, not a fleet. | `vco up` with PID file. If systemd is wanted later, a unit file is 10 lines -- no architectural changes needed. |
| Multi-user access control on socket | "Security", "role-based access" | Single-machine, single-user system. Unix socket permissions handle access. Adding user auth to a local socket is complexity for a non-existent threat. | Socket file permissions: `chmod 600 ~/.vco/vco.sock`. Only owner can connect. |
| Bot calling CLI via subprocess | "Simpler than socket" | Subprocess overhead per command (fork, exec, Python startup ~200ms). Race conditions between concurrent subprocess calls. No connection reuse. | Bot connects to Unix socket directly (same as CLI does internally). Shared socket client code. One persistent connection, not N subprocesses. |

## Feature Dependencies

```
[PID File / Single Instance Guard]
    └──required by──> [Daemon Process (vco up/down)]
                          └──required by──> [Unix Socket API]
                                                └──required by──> [CLI Commands as API Clients]
                                                |                     └──required by──> [Bot as Thin Relay]
                                                |                     └──required by──> [Strategist Bash Autonomy]
                                                |                     └──required by──> [vco new-project composite]
                                                └──required by──> [Health Check Endpoint]

[State Persistence (write path)]
    └──required by──> [State Recovery (read path)]
    └──required by──> [Graceful Shutdown]

[Daemon Process]
    └──required by──> [State Persistence]

[CompanyRoot extraction from bot] ──required by──> [Daemon Process]

[Daemon Auto-Start] ──enhances──> [CLI Commands]
[Streaming Responses] ──enhances──> [Unix Socket API]
[Socket Event Subscription] ──enhances──> [Bot as Thin Relay]
```

### Dependency Notes

- **PID file is the absolute foundation.** Without single-instance guarantee, nothing else is safe. Build first, takes 30 minutes.
- **CompanyRoot extraction is the hardest prerequisite.** Currently created in `VcoBot.on_ready()` with extensive callback wiring to Discord. Must be extractable into a standalone daemon startup with no Discord dependency.
- **CLI Commands require Unix Socket API.** Every CLI command is a stateless client. Without the socket server, nothing works.
- **Bot as Thin Relay requires CLI Commands.** Bot slash commands either call the socket API directly or delegate to CLI. Either way, the API must exist first.
- **State Recovery requires State Persistence.** Cannot recover what wasn't saved. Tightly coupled -- implement the write path and read path together.
- **Strategist Bash Autonomy requires CLI Commands.** This is the killer feature motivating the entire rewrite, but it's the last link in the dependency chain. CLI commands must work first.
- **Daemon Auto-Start conflicts with explicit `vco up`.** Choose one as primary. Recommendation: require explicit `vco up` for v3.0 (simpler, debuggable), add auto-start as convenience later.
- **Bot should NOT call CLI via subprocess.** Both bot and CLI should share the same socket client library. Bot imports the client module directly rather than shelling out to `vco`.

## MVP Definition

### Launch With (v3.0 Core)

Minimum viable CLI-first architecture. Everything needed before the system is usable.

- [ ] **PID file + single-instance guard** -- `~/.vco/vco.pid`, stale detection, prevents double-start
- [ ] **Daemon process (`vco up` / `vco down`)** -- asyncio event loop, SIGTERM/SIGINT handlers, background process
- [ ] **CompanyRoot extraction from bot** -- supervision tree starts in daemon, not in `VcoBot.on_ready()`
- [ ] **Unix socket server** -- `asyncio.start_unix_server()` at `~/.vco/vco.sock`, JSON request/response
- [ ] **Socket client library** -- shared by CLI commands and bot, handles connection, serialization, errors
- [ ] **Core CLI commands** -- `vco hire`, `vco give-task`, `vco dismiss`, `vco status`, `vco health` as thin API clients
- [ ] **`vco new-project` composite** -- init + clone + hire all agents from agents.yaml via API
- [ ] **State persistence** -- container state, pane IDs, task queues to `~/.vco/state/` on every state change
- [ ] **State recovery** -- daemon startup reads persisted state, reconnects tmux sessions, restores containers
- [ ] **Graceful shutdown** -- SIGTERM snapshots state before exit
- [ ] **Bot refactored to thin relay** -- slash commands call socket API, no CompanyRoot/container imports in bot

### Add After Validation (v3.x)

Features to add once core daemon + CLI architecture is proven stable.

- [ ] **Strategist Bash autonomy** -- Strategist calls `vco hire/give-task/dismiss` via Bash (once CLI commands are battle-tested with manual use)
- [ ] **Daemon auto-start** -- `vco hire` auto-starts daemon if not running (once explicit `vco up` feels tedious)
- [ ] **Streaming responses** -- long-running commands stream progress (once `vco new-project` feels too silent during multi-agent setup)
- [ ] **Socket event subscription** -- bot subscribes to push events instead of polling (once bot latency is noticeable)

### Future Consideration (v4+)

- [ ] **TCP socket option** -- for multi-machine setups where CLI runs on different host
- [ ] **Authentication on socket** -- if multi-user access is needed
- [ ] **Systemd unit file** -- for production deployment patterns
- [ ] **Alternative UI backends** -- Slack, web (all consume same socket API)

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| PID file / single instance | HIGH | LOW | P1 |
| Daemon process (vco up/down) | HIGH | MEDIUM | P1 |
| CompanyRoot extraction from bot | HIGH | HIGH | P1 |
| Unix socket server | HIGH | MEDIUM | P1 |
| Socket client library | HIGH | LOW | P1 |
| Core CLI commands (hire/task/dismiss/status/health) | HIGH | MEDIUM | P1 |
| State persistence | HIGH | HIGH | P1 |
| State recovery on restart | HIGH | HIGH | P1 |
| Graceful shutdown | HIGH | MEDIUM | P1 |
| vco new-project composite | HIGH | MEDIUM | P1 |
| Bot as thin relay | HIGH | MEDIUM | P1 |
| Daemon status detection | MEDIUM | LOW | P1 |
| Strategist Bash autonomy | HIGH | LOW | P2 |
| Daemon auto-start | MEDIUM | MEDIUM | P2 |
| Streaming responses | MEDIUM | MEDIUM | P3 |
| Socket event subscription | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have -- core v3.0 architecture, blocks all downstream features
- P2: Should have -- high value, low incremental cost, add once P1 is stable
- P3: Nice to have -- defer until specific pain point is felt

## Reference Architecture Analysis

These are not competitors but reference implementations of the identical CLI-daemon pattern vCompany v3.0 follows.

| Feature | Docker | Tailscale | Mullvad VPN | vCompany v3.0 Approach |
|---------|--------|-----------|-------------|----------------------|
| Daemon start | `dockerd` / systemd | `tailscaled` / systemd | `mullvad-daemon` / systemd | `vco up` -- explicit start, PID file, no systemd dependency |
| IPC mechanism | HTTP over Unix socket | HTTP over Unix socket (LocalAPI) | gRPC over Unix socket | Newline-delimited JSON over Unix socket (simpler than HTTP, lighter than gRPC) |
| CLI role | Stateless API client | Stateless LocalAPI client | Stateless gRPC client | Stateless socket client -- same proven pattern |
| State persistence | Container state in `/var/lib/docker` | Node state in `/var/lib/tailscale` | VPN config in `/etc/mullvad-vpn` | Container + queue state in `~/.vco/state/` |
| Restart recovery | Containers survive dockerd restart | Connections survive tailscaled restart | VPN reconnects after daemon restart | Agents survive daemon restart via tmux session reconnection |
| UI relay | Docker Desktop (Electron thin client) | Tailscale app (thin client) | Mullvad app (thin client) | Discord bot (thin relay to socket API) |
| Graceful shutdown | SIGTERM + container stop timeout | SIGTERM + connection drain | SIGTERM + tunnel teardown | SIGTERM + state snapshot + socket close |
| Auto-start | systemd handles it | `tailscale up` starts tailscaled | systemd handles it | Explicit `vco up` for now; auto-start in v3.x |

## Existing Feature Migration Map

These v2.0/v2.1 features must be migrated or reconnected in the new architecture.

| Existing Feature | Current Location | v3.0 Location | Migration Notes |
|------------------|-----------------|---------------|-----------------|
| CompanyRoot + supervision tree | `VcoBot.on_ready()` in `bot/client.py` | Daemon main loop | Biggest extraction task. Must remove all Discord callback wiring from CompanyRoot constructor. |
| AgentContainer lifecycle FSM | `container/container.py` | Daemon (unchanged) | State machine stays identical. Must become serializable for persistence (add `to_dict()`/`from_dict()`). |
| Container tmux bridge | `container/container.py` | Daemon (unchanged) | Pane IDs must be persisted. On recovery, call `libtmux` to find existing pane by ID. |
| Health tree | `container/health.py` | Daemon, exposed via socket API | Already returns structured data. Add JSON serialization. |
| Task queue on containers | `container/container.py` | Daemon, persisted to disk | Queue must be serializable (list of task dicts). Write on every enqueue/dequeue. |
| Priority message queue | `resilience/message_queue.py` | Bot process (stays) | This is Discord-specific rate limiting. Stays in bot, not in daemon. |
| PM review gates | `bot/cogs/plan_review.py` | Split: UI in bot, state in daemon | Bot shows approve/reject buttons. Decision sent to daemon via socket API. Daemon updates container state. |
| Strategist conversation | `strategist/conversation.py` | Daemon (CompanyAgent) | Already in CompanyAgent container. Just needs to start in daemon, not bot. |
| Channel auto-setup | `bot/channel_setup.py` | Bot (stays) | Discord-specific. Bot creates channels, daemon doesn't know about Discord. |
| `/new-project` slash command | `bot/cogs/commands.py` | Bot calls `vco new-project` API | Bot becomes thin: parse slash command args, call socket API, format response as embed. |
| `/health` slash command | `bot/cogs/health.py` | Bot calls `vco health` API | Same pattern: socket call, format HealthTree as Discord embed. |

## Sources

- [Docker Client-Server Architecture](https://oneuptime.com/blog/post/2026-02-08-how-to-understand-the-docker-client-server-architecture/view) -- HTTP-over-Unix-socket pattern (MEDIUM confidence)
- [Tailscale CLI Architecture](https://deepwiki.com/tailscale/tailscale/6.1-tailscale-cli) -- LocalAPI over Unix socket, stateless CLI client pattern (MEDIUM confidence)
- [Mullvad VPN CLI](https://deepwiki.com/mullvad/mullvadvpn-app/5.1-command-line-interface) -- Stateless gRPC CLI client pattern (MEDIUM confidence)
- [Podman vs Docker Architecture](https://medium.com/@m.hassan.def/podman-and-docker-a-story-of-two-architectures-2bb0e1bfd79a) -- Daemon vs daemonless tradeoffs (MEDIUM confidence)
- [Python asyncio Unix socket server](https://superfastpython.com/asyncio-echo-unix-socket-server/) -- `asyncio.start_unix_server()` usage (HIGH confidence)
- [Python socket module docs](https://docs.python.org/3/library/socket.html) -- stdlib Unix domain socket support (HIGH confidence)
- [Python socketserver docs](https://docs.python.org/3/library/socketserver.html) -- ForkingUnixStreamServer added in 3.12 (HIGH confidence)
- [Graceful Shutdown Patterns](https://www.geeksforgeeks.org/system-design/graceful-shutdown-in-distributed-systems-and-microservices/) -- Ordered shutdown, connection draining (MEDIUM confidence)
- [start-stop-daemon man page](https://man7.org/linux/man-pages/man8/start-stop-daemon.8.html) -- PID file and daemon lifecycle management (HIGH confidence)
- [PM2 Graceful Shutdown](https://pm2.io/docs/runtime/best-practices/graceful-shutdown/) -- Signal handling, timeout patterns (MEDIUM confidence)

---
*Feature research for: CLI-first daemon architecture (vCompany v3.0)*
*Researched: 2026-03-29*
