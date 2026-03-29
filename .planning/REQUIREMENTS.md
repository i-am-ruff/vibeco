# Requirements: vCompany

**Defined:** 2026-03-29
**Core Value:** Agents run autonomously without hanging on terminal input, stay coordinated through contracts and status awareness, and produce integrated code that merges cleanly — all operable from Discord.

## v3.0 Requirements

Requirements for CLI-First Architecture Rewrite. Each maps to roadmap phases.

### Daemon Lifecycle

- [ ] **DAEMON-01**: `vco up` starts runtime daemon as foreground process with CompanyRoot and supervision tree
- [ ] **DAEMON-02**: Runtime daemon creates PID file on start and removes on clean exit
- [ ] **DAEMON-03**: Runtime daemon handles SIGTERM/SIGINT for graceful shutdown (stops containers, closes socket)
- [ ] **DAEMON-04**: Runtime daemon cleans up stale socket file on start (PID probe before unlink)
- [ ] **DAEMON-05**: `vco down` sends graceful shutdown signal to running daemon
- [ ] **DAEMON-06**: `vco up` starts Discord bot alongside daemon in same event loop (`bot.start()`)

### Socket API

- [ ] **SOCK-01**: Runtime daemon listens on Unix socket with asyncio.start_unix_server
- [ ] **SOCK-02**: NDJSON protocol for request-response communication (one JSON object per line)
- [ ] **SOCK-03**: Request framing includes method, params, and request ID
- [ ] **SOCK-04**: Error responses include error code, message, and request ID
- [ ] **SOCK-05**: Event subscription — connected clients can subscribe to daemon events (health changes, agent transitions)
- [ ] **SOCK-06**: Protocol version field in handshake for forward compatibility

### CLI Commands

- [ ] **CLI-01**: `vco hire <type> <name>` creates agent container via socket API
- [ ] **CLI-02**: `vco give-task <agent> <task>` queues task for agent via socket API
- [ ] **CLI-03**: `vco dismiss <agent>` stops and cleans up agent via socket API
- [ ] **CLI-04**: `vco status` shows supervision tree and agent states via socket API
- [ ] **CLI-05**: `vco health` shows health tree with per-agent status via socket API
- [ ] **CLI-06**: `vco new-project` is composite command: init + clone + hire per agent (uses CLI-01 internally)

### CompanyRoot Extraction

- [ ] **EXTRACT-01**: CompanyRoot and supervision tree run inside daemon process, not bot
- [ ] **EXTRACT-02**: RuntimeAPI gateway class provides typed methods for all CompanyRoot operations
- [ ] **EXTRACT-03**: All callback closures from on_ready() replaced with RuntimeAPI calls or event subscriptions
- [ ] **EXTRACT-04**: Bot accesses CompanyRoot exclusively through RuntimeAPI (no direct imports)

### Bot Refactor

- [ ] **BOT-01**: All slash commands (/new-project, /dispatch, /kill, /relaunch, /health) call RuntimeAPI
- [ ] **BOT-02**: No container module imports in bot cogs
- [ ] **BOT-03**: Bot receives daemon events via RuntimeAPI for Discord notifications (health, transitions, escalations)
- [ ] **BOT-04**: Message relay handlers (on_message for agent/task channels) call RuntimeAPI for task delivery

### Strategist Autonomy

- [ ] **STRAT-01**: Strategist calls `vco hire`, `vco give-task`, `vco dismiss` via Bash tool
- [ ] **STRAT-02**: `[CMD:...]` action tag parsing removed from StrategistCog
- [ ] **STRAT-03**: Strategist persona updated to reference `vco` CLI commands instead of action tags

## v3.1 Requirements

Deferred to future release. Tracked but not in current roadmap.

### State Persistence

- **PERSIST-01**: Container state persists to disk and survives daemon restart
- **PERSIST-02**: Task queue state persists and recovers on restart
- **PERSIST-03**: Daemon reconnects to running tmux sessions on restart
- **PERSIST-04**: FSM state recovery from persisted snapshots

## Out of Scope

| Feature | Reason |
|---------|--------|
| State persistence / crash recovery | Deferred to v3.1 — daemon restart loses state for now |
| Multi-machine distributed agents | v4 scope — single machine only |
| Alternative UIs (Slack, web) | v4 scope — Discord is the interface |
| HTTP/gRPC protocol | NDJSON over Unix socket is sufficient for single-machine |
| Database for state | Filesystem + aiosqlite is correct for v3.0 |
| Agent-to-agent direct messaging | v4 scope — agents communicate through supervision tree and Discord |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| — | — | — |

**Coverage:**
- v3.0 requirements: 25 total
- Mapped to phases: 0
- Unmapped: 25 ⚠️

---
*Requirements defined: 2026-03-29*
*Last updated: 2026-03-29 after initial definition*
