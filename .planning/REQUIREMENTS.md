# Requirements: vCompany

**Defined:** 2026-03-29
**Core Value:** Agents run autonomously without hanging on terminal input, stay coordinated through contracts and status awareness, and produce integrated code that merges cleanly -- all operable from Discord.

## v3.0 Requirements

Requirements for CLI-First Architecture Rewrite. Each maps to roadmap phases.

### Daemon Lifecycle

- [x] **DAEMON-01**: `vco up` starts runtime daemon as foreground process with CompanyRoot and supervision tree
- [x] **DAEMON-02**: Runtime daemon creates PID file on start and removes on clean exit
- [x] **DAEMON-03**: Runtime daemon handles SIGTERM/SIGINT for graceful shutdown (stops containers, closes socket)
- [x] **DAEMON-04**: Runtime daemon cleans up stale socket file on start (PID probe before unlink)
- [x] **DAEMON-05**: `vco down` sends graceful shutdown signal to running daemon
- [x] **DAEMON-06**: `vco up` starts Discord bot alongside daemon in same event loop (`bot.start()`)

### Socket API

- [x] **SOCK-01**: Runtime daemon listens on Unix socket with asyncio.start_unix_server
- [x] **SOCK-02**: NDJSON protocol for request-response communication (one JSON object per line)
- [x] **SOCK-03**: Request framing includes method, params, and request ID
- [x] **SOCK-04**: Error responses include error code, message, and request ID
- [x] **SOCK-05**: Event subscription -- connected clients can subscribe to daemon events (health changes, agent transitions)
- [x] **SOCK-06**: Protocol version field in handshake for forward compatibility

### Communication Abstraction

- [x] **COMM-01**: CommunicationPort protocol formalized with methods for send_message, send_embed, create_thread, subscribe_to_channel
- [x] **COMM-02**: Daemon never imports discord.py -- all platform communication goes through CommunicationPort
- [x] **COMM-03**: DiscordCommunicationPort adapter implements CommunicationPort protocol in the bot layer
- [x] **COMM-04**: StrategistConversation runs in daemon, sends/receives through CommunicationPort (not StrategistCog)
- [x] **COMM-05**: PM review flow state machine runs in daemon, sends review requests and receives responses through CommunicationPort
- [x] **COMM-06**: Channel creation (project categories, agent channels) requested by daemon through CommunicationPort

### CLI Commands

- [x] **CLI-01**: `vco hire <type> <name>` creates agent container via socket API
- [x] **CLI-02**: `vco give-task <agent> <task>` queues task for agent via socket API
- [x] **CLI-03**: `vco dismiss <agent>` stops and cleans up agent via socket API
- [x] **CLI-04**: `vco status` shows supervision tree and agent states via socket API
- [x] **CLI-05**: `vco health` shows health tree with per-agent status via socket API
- [ ] **CLI-06**: `vco new-project` is composite command: init + clone + add_project via socket API (hires all agents from agents.yaml)

### CompanyRoot Extraction

- [x] **EXTRACT-01**: CompanyRoot and supervision tree run inside daemon process, not bot
- [x] **EXTRACT-02**: RuntimeAPI gateway class provides typed methods for all CompanyRoot operations
- [x] **EXTRACT-03**: All callback closures from on_ready() replaced with RuntimeAPI calls or event subscriptions
- [x] **EXTRACT-04**: Bot accesses CompanyRoot exclusively through RuntimeAPI (no direct imports)

### Bot Refactor

- [ ] **BOT-01**: All slash commands (/new-project, /dispatch, /kill, /relaunch, /health) call RuntimeAPI
- [ ] **BOT-02**: No container module imports in bot cogs
- [ ] **BOT-03**: Bot implements DiscordCommunicationPort and registers with daemon on startup
- [ ] **BOT-04**: Bot cogs are pure I/O adapters: Discord events -> daemon, daemon events -> Discord formatting (embeds, threads, reactions)
- [ ] **BOT-05**: Message relay handlers (on_message for agent/task channels) convert to generic messages and send to daemon

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
| State persistence / crash recovery | Deferred to v3.1 -- daemon restart loses state for now |
| Multi-machine distributed agents | v4 scope -- single machine only |
| Non-Discord CommunicationPort adapters (Slack, web) | v4 scope -- only DiscordCommunicationPort in v3.0, but abstraction is ready |
| HTTP/gRPC protocol | NDJSON over Unix socket is sufficient for single-machine |
| Database for state | Filesystem + aiosqlite is correct for v3.0 |
| Agent-to-agent direct messaging | v4 scope -- agents communicate through supervision tree and CommunicationPort |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DAEMON-01 | Phase 18 | Complete |
| DAEMON-02 | Phase 18 | Complete |
| DAEMON-03 | Phase 18 | Complete |
| DAEMON-04 | Phase 18 | Complete |
| DAEMON-05 | Phase 18 | Complete |
| DAEMON-06 | Phase 18 | Complete |
| SOCK-01 | Phase 18 | Complete |
| SOCK-02 | Phase 18 | Complete |
| SOCK-03 | Phase 18 | Complete |
| SOCK-04 | Phase 18 | Complete |
| SOCK-05 | Phase 18 | Complete |
| SOCK-06 | Phase 18 | Complete |
| COMM-01 | Phase 19 | Complete |
| COMM-02 | Phase 19 | Complete |
| COMM-03 | Phase 19 | Complete |
| COMM-04 | Phase 20 | Complete |
| COMM-05 | Phase 20 | Complete |
| COMM-06 | Phase 20 | Complete |
| EXTRACT-01 | Phase 20 | Complete |
| EXTRACT-02 | Phase 20 | Complete |
| EXTRACT-03 | Phase 20 | Complete |
| EXTRACT-04 | Phase 20 | Complete |
| CLI-01 | Phase 21 | Complete |
| CLI-02 | Phase 21 | Complete |
| CLI-03 | Phase 21 | Complete |
| CLI-04 | Phase 21 | Complete |
| CLI-05 | Phase 21 | Complete |
| CLI-06 | Phase 21 | Pending |
| BOT-01 | Phase 22 | Pending |
| BOT-02 | Phase 22 | Pending |
| BOT-03 | Phase 22 | Pending |
| BOT-04 | Phase 22 | Pending |
| BOT-05 | Phase 22 | Pending |
| STRAT-01 | Phase 23 | Pending |
| STRAT-02 | Phase 23 | Pending |
| STRAT-03 | Phase 23 | Pending |

**Coverage:**
- v3.0 requirements: 36 total
- Mapped to phases: 36
- Unmapped: 0

---
*Requirements defined: 2026-03-29*
*Last updated: 2026-03-29 after roadmap traceability mapping*
