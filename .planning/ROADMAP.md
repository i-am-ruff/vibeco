# Roadmap: vCompany

## Milestones

- ✅ **v1.0 MVP** - Phases 1-10 (shipped 2026-03-27)
- ✅ **v2.0 Agent Container Architecture** - Phases 1-10 (shipped 2026-03-28)
- ✅ **v2.1 Behavioral Integration** - Phases 11-17 (shipped 2026-03-28)
- 🚧 **v3.0 CLI-First Architecture Rewrite** - Phases 18-23 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-10) - SHIPPED 2026-03-27</summary>

See `.planning/milestones/v1.0-ROADMAP.md` for full details.

</details>

<details>
<summary>v2.0 Agent Container Architecture (Phases 1-10, +8.1, +8.2, +9, +10) - SHIPPED 2026-03-28</summary>

- [x] Phase 1: Container Foundation (3/3 plans) -- completed 2026-03-27
- [x] Phase 2: Supervision Tree (2/2 plans) -- completed 2026-03-27
- [x] Phase 3: GsdAgent (2/2 plans) -- completed 2026-03-27
- [x] Phase 4: Remaining Agent Types and Scheduler (4/4 plans) -- completed 2026-03-27
- [x] Phase 5: Health Tree (2/2 plans) -- completed 2026-03-27
- [x] Phase 6: Resilience (3/3 plans) -- completed 2026-03-27
- [x] Phase 7: Autonomy Features (3/3 plans) -- completed 2026-03-28
- [x] Phase 8: CompanyRoot Wiring and Migration (3/3 plans) -- completed 2026-03-28
- [x] Phase 8.1: Integration Wiring (2/2 plans) -- completed 2026-03-28
- [x] Phase 8.2: Deep Integration (2/2 plans) -- completed 2026-03-28
- [x] Phase 9: Agent Type Routing + PM Event Dispatch (2/2 plans) -- completed 2026-03-28
- [x] Phase 10: MessageQueue Notification Routing (1/1 plan) -- completed 2026-03-28

See `.planning/milestones/v2.0-ROADMAP.md` for full details.

</details>

<details>
<summary>v2.1 Behavioral Integration (Phases 11-17) - SHIPPED 2026-03-28</summary>

- [x] Phase 11: Container Architecture Fixes (2/2 plans) -- completed 2026-03-28
- [x] Phase 12: Work Initiation (1/1 plan) -- completed 2026-03-28
- [x] Phase 13: PM Event Routing (1/1 plan) -- completed 2026-03-28
- [x] Phase 14: PM Review Gates (2/2 plans) -- completed 2026-03-28
- [x] Phase 15: PM Actions & Auto Distribution (2/2 plans) -- completed 2026-03-28
- [x] Phase 16: Agent Completeness & Strategist (2/2 plans) -- completed 2026-03-28
- [x] Phase 17: Health Tree Rendering (1/1 plan) -- completed 2026-03-28

See `.planning/milestones/v2.1-ROADMAP.md` for full details.

</details>

### v3.0 CLI-First Architecture Rewrite (In Progress)

**Milestone Goal:** Extract all core logic from the Discord bot into a runtime daemon with Unix socket API, making the CLI the primary interface and the bot a thin Discord skin.

**Phase Numbering:**
- Integer phases (18, 19, 20...): Planned milestone work
- Decimal phases (18.1, 18.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 18: Daemon Foundation** - Runtime daemon with PID file, signal handling, Unix socket server, and NDJSON protocol (completed 2026-03-29)
- [x] **Phase 19: Communication Abstraction** - CommunicationPort protocol and DiscordCommunicationPort adapter as the boundary between daemon and bot (completed 2026-03-29)
- [x] **Phase 20: CompanyRoot Extraction** - Move CompanyRoot, supervision tree, Strategist conversation, and PM review into daemon behind RuntimeAPI (completed 2026-03-29)
- [x] **Phase 21: CLI Commands** - All vco commands as thin socket API clients (completed 2026-03-29)
- [ ] **Phase 22: Bot Thin Relay** - Refactor bot to pure I/O adapter with zero container imports
- [ ] **Phase 23: Strategist Autonomy** - Strategist calls vco CLI commands via Bash tool, action tags removed

## Phase Details

### Phase 18: Daemon Foundation
**Goal**: User can start and stop a runtime daemon that listens on a Unix socket, with safe single-instance enforcement and graceful shutdown
**Depends on**: Nothing (first phase of v3.0)
**Requirements**: DAEMON-01, DAEMON-02, DAEMON-03, DAEMON-04, DAEMON-05, DAEMON-06, SOCK-01, SOCK-02, SOCK-03, SOCK-04, SOCK-05, SOCK-06
**Success Criteria** (what must be TRUE):
  1. Running `vco up` starts a daemon process that stays alive and creates a PID file; running `vco up` again refuses to start a second instance
  2. Running `vco down` gracefully shuts down the daemon (containers stopped, socket closed, PID file removed)
  3. The daemon survives a SIGTERM/SIGINT and shuts down cleanly; after a SIGKILL, the next `vco up` detects and cleans up the stale socket
  4. A client can connect to the Unix socket, send a JSON request, and receive a JSON response (verifiable with `socat`)
  5. The Discord bot starts alongside the daemon and is reachable on Discord
**Plans:** 3/3 plans complete
Plans:
- [x] 18-01-PLAN.md -- NDJSON protocol models and shared path constants
- [x] 18-02-PLAN.md -- Daemon class and Unix socket server
- [x] 18-03-PLAN.md -- CLI wiring (vco up refactor, vco down, sync client)

### Phase 19: Communication Abstraction
**Goal**: A formal CommunicationPort protocol exists that the daemon uses for all platform communication, with a Discord adapter implementing it in the bot layer
**Depends on**: Phase 18
**Requirements**: COMM-01, COMM-02, COMM-03
**Success Criteria** (what must be TRUE):
  1. A CommunicationPort protocol is defined with typed methods (send_message, send_embed, create_thread, subscribe_to_channel) that any platform adapter can implement
  2. The daemon module tree has zero imports from discord.py -- all outbound communication goes through CommunicationPort
  3. A DiscordCommunicationPort adapter exists in the bot layer that implements the protocol and is registered with the daemon on startup
**Plans:** 2/2 plans complete
Plans:
- [x] 19-01-PLAN.md -- CommunicationPort protocol, Pydantic payload models, Daemon integration
- [x] 19-02-PLAN.md -- DiscordCommunicationPort adapter, VcoBot registration

### Phase 20: CompanyRoot Extraction
**Goal**: CompanyRoot, supervision tree, Strategist conversation, and PM review flow all run inside the daemon process, accessed exclusively through a RuntimeAPI gateway
**Depends on**: Phase 19
**Requirements**: EXTRACT-01, EXTRACT-02, EXTRACT-03, EXTRACT-04, COMM-04, COMM-05, COMM-06
**Success Criteria** (what must be TRUE):
  1. CompanyRoot and the supervision tree initialize inside the daemon process, not inside VcoBot.on_ready()
  2. A RuntimeAPI class exists with typed methods for every CompanyRoot operation (hire, give_task, dismiss, status, health_tree, new_project)
  3. StrategistConversation runs in the daemon and sends/receives messages through CommunicationPort, not through StrategistCog directly
  4. PM review flow state machine runs in the daemon, sending review requests and receiving responses through CommunicationPort
  5. Channel creation (project categories, agent channels) is requested by the daemon through CommunicationPort, not by calling Discord APIs directly
**Plans:** 4/4 plans complete
Plans:
- [x] 20-01-PLAN.md -- RuntimeAPI gateway, CommunicationPort extensions (create_channel, edit_message)
- [x] 20-02-PLAN.md -- Callback replacement methods in RuntimeAPI, CompanyRoot.hire() guild removal
- [x] 20-03-PLAN.md -- Gut VcoBot.on_ready(), move CompanyRoot lifecycle to Daemon
- [x] 20-04-PLAN.md -- Rewire CommandsCog, import boundary tests, RuntimeAPI tests

### Phase 21: CLI Commands
**Goal**: Users can manage agents entirely from the terminal using vco CLI commands that talk to the daemon via socket API
**Depends on**: Phase 20
**Requirements**: CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06
**Success Criteria** (what must be TRUE):
  1. `vco hire gsd agent-name` creates a running agent container visible in `vco status` output
  2. `vco give-task agent-name "task description"` queues a task that the agent picks up
  3. `vco dismiss agent-name` stops the agent and cleans up its resources
  4. `vco status` and `vco health` display the supervision tree and health states from the running daemon
  5. `vco new-project` initializes a project and hires all agents defined in agents.yaml in one command
**Plans:** 2/2 plans complete
Plans:
- [x] 21-01-PLAN.md -- Connection helper, hire/give-task/dismiss/status/health CLI commands
- [x] 21-02-PLAN.md -- new_project daemon handler and composite vco new-project command

### Phase 22: Bot Thin Relay
**Goal**: All Discord slash commands delegate to RuntimeAPI with zero container module imports, and the bot acts as a pure I/O adapter between Discord and the daemon
**Depends on**: Phase 21
**Requirements**: BOT-01, BOT-02, BOT-03, BOT-04, BOT-05
**Success Criteria** (what must be TRUE):
  1. All slash commands (/new-project, /dispatch, /kill, /relaunch, /health) work by calling RuntimeAPI methods, not by touching containers directly
  2. Zero imports from `vcompany.container`, `vcompany.supervisor`, or `vcompany.agent` exist in any bot cog module
  3. The bot receives health changes, agent transitions, and escalation events from the daemon and formats them as Discord embeds, threads, and reactions
  4. Message relay (on_message in agent/task channels) converts Discord messages to generic messages and delivers them to the daemon through CommunicationPort
**Plans:** 3 plans
Plans:
- [ ] 22-01-PLAN.md -- RuntimeAPI gateway methods and expanded import boundary tests
- [ ] 22-02-PLAN.md -- Rewrite heavy cogs (commands.py, plan_review.py, workflow_orchestrator_cog.py)
- [ ] 22-03-PLAN.md -- Clean remaining cogs and finalize import boundary enforcement

### Phase 23: Strategist Autonomy
**Goal**: The Strategist agent manages workforce through vco CLI commands via its Bash tool, with no special action tag parsing in the bot
**Depends on**: Phase 22
**Requirements**: STRAT-01, STRAT-02, STRAT-03
**Success Criteria** (what must be TRUE):
  1. The Strategist can run `vco hire`, `vco give-task`, and `vco dismiss` from its Claude session's Bash tool and the commands succeed
  2. The `[CMD:...]` action tag parsing code is removed from StrategistCog
  3. The Strategist persona/system prompt references `vco` CLI commands for workforce management instead of action tags
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 18 -> 18.1 -> 18.2 -> 19 -> ... -> 23

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 18. Daemon Foundation | 3/3 | Complete    | 2026-03-29 |
| 19. Communication Abstraction | 2/2 | Complete    | 2026-03-29 |
| 20. CompanyRoot Extraction | 4/4 | Complete    | 2026-03-29 |
| 21. CLI Commands | 2/2 | Complete    | 2026-03-29 |
| 22. Bot Thin Relay | 0/3 | Not started | - |
| 23. Strategist Autonomy | 0/? | Not started | - |
