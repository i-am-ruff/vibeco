# Milestones

## v3.0 CLI-First Architecture Rewrite (Shipped: 2026-03-29)

**Phases completed:** 6 phases, 15 plans, 29 tasks

**Key accomplishments:**

- NDJSON protocol Pydantic models with JSON-RPC 2.0 structure, ErrorCode enum, and daemon socket/PID path constants
- Runtime daemon with PID lifecycle management and NDJSON Unix socket server supporting hello handshake, ping, subscribe, and event broadcast
- Sync socket client, vco down with SIGTERM/PID polling, and vco up refactored to start Daemon lifecycle
- Runtime-checkable CommunicationPort protocol with 6 Pydantic payload models, NoopCommunicationPort adapter, and Daemon injection point -- zero discord imports in daemon tree
- DiscordCommunicationPort adapter translating CommunicationPort protocol to discord.py API calls with reconnect-safe daemon registration in VcoBot.on_ready
- RuntimeAPI gateway with typed async methods for CompanyRoot ops, CommunicationPort extended to 6 methods with create_channel and edit_message
- 22 on_ready closure replacements as typed RuntimeAPI methods using CommunicationPort, plus inbound relay methods for bidirectional COMM-04/COMM-05 paths
- VcoBot.on_ready() gutted to thin Discord adapter (510 lines removed), CompanyRoot lifecycle moved to Daemon._run() with socket API endpoints
- Bot cogs rewired to use RuntimeAPI exclusively for /new-project, COMM-04 inbound relay, COMM-05 approval/rejection, with import boundary and RuntimeAPI unit tests
- Five thin CLI commands (hire, give-task, dismiss, status, health) wrapping DaemonClient socket calls with Rich output formatting
- Composite vco new-project command and daemon socket handler -- bootstraps full project from CLI with init, clone, and supervision startup
- 9 new RuntimeAPI gateway methods (dispatch, kill, relaunch, remove_project, relay_channel_message, get_agent_states, checkin, standup, run_integration) and comprehensive import boundary test covering all 10 bot files with 20+ prohibited prefixes
- Three heaviest-violation cog files (commands.py, plan_review.py, workflow_orchestrator_cog.py) rewritten as pure RuntimeAPI delegates with zero prohibited imports and zero _find_container calls
- 5 remaining cog files (strategist, health, task_relay, workflow_master, question_handler) rewritten as pure I/O adapters with zero prohibited imports; alerts.py BOT-03 verified; all xfail markers removed from import boundary tests
- Removed [CMD:] action tag parsing from StrategistCog, replaced with vco CLI instructions in personas, bumped session to v11

---

## v2.0 Agent Container Architecture (Shipped: 2026-03-28)

**Phases completed:** 12 phases, 29 plans, 52 tasks

**Key accomplishments:**

- 6-state lifecycle FSM using python-statemachine with ContainerContext, HealthReport, and async CommunicationPort Protocol
- Async SQLite MemoryStore with WAL mode for per-agent KV/checkpoint persistence, plus ChildSpec/Registry for Erlang-style supervisor child declarations
- AgentContainer class wiring lifecycle FSM, context, memory store, health reporting, and communication port into the central agent abstraction
- Erlang-style Supervisor with one_for_one/all_for_one/rest_for_one restart strategies, sliding window intensity tracking, and parent escalation protocol
- Two-level supervision tree (CompanyRoot -> ProjectSupervisor -> AgentContainers) with dynamic project management and full escalation chain to Discord callback
- GsdLifecycle compound state machine with 6 phase sub-states nested inside running, HistoryState for sleep/wake and error/recover preservation, and serializable state for crash recovery
- GsdAgent container with compound FSM state decomposition, checkpoint persistence on phase transitions, and crash recovery from memory_store
- Factory registry maps agent_type strings to AgentContainer subclasses so supervisors create the correct container via polymorphic from_spec() dispatch
- ContinuousAgent with 6-phase cycle FSM (WAKE->GATHER->ANALYZE->ACT->REPORT->SLEEP_PREP), checkpoint-based crash recovery, and cycle count persistence
- EventDrivenLifecycle FSM with listening/processing compound states, FulltimeAgent (PM) and CompanyAgent (Strategist) with asyncio.Queue event processing and crash recovery
- Scheduler waking sleeping ContinuousAgents on persistent schedule with all four agent types registered in factory via register_defaults()
- Supervisor health tree aggregation with HealthNode/HealthTree/CompanyHealthTree models and async state-change notification callback
- Discord /health slash command with color-coded supervision tree embed, project/agent filtering, and state-change push notifications to #alerts
- Discord-agnostic priority message queue with health debounce and exponential backoff on rate limits using asyncio.PriorityQueue
- BulkFailureDetector with per-child sliding window correlation and Supervisor global backoff for upstream outage suppression
- DegradedModeManager with 3-failure threshold, 2-success auto-recovery, injectable health checks, and CompanyRoot dispatch gating
- BacklogQueue with Pydantic models, 8 async operations, MemoryStore persistence, and asyncio.Lock concurrency protection
- Delegation protocol with DelegationTracker enforcing per-requester concurrent caps and hourly rate limits, Supervisor spawning TEMPORARY agents on approval
- PM-owned ProjectStateManager with crash-safe assignment coordination, FulltimeAgent event routing, and GsdAgent assignment/completion methods
- DiscordCommunicationPort satisfying CommunicationPort Protocol via structural subtyping with asyncio.Queue inbox, plus VcoBot slash-only migration
- CompanyRoot supervision tree replaces v1 flat initialization in VcoBot.on_ready(), CommandsCog, and WorkflowOrchestratorCog
- Deleted 4 v1 source modules and 6 test files, updated 14+ import sites across CLI/cogs/tests to use TmuxManager and shared workflow types
- HealthCog loaded at startup, DegradedModeManager activated with Claude API health_check, MessageQueue wired for outbound notifications
- BacklogQueue and ProjectStateManager wired to FulltimeAgent after add_project(), with GsdAgent event contract verification
- AgentContainer bridges to TmuxManager for start/stop/liveness with 30s periodic monitoring in supervisors and injection chain from CompanyRoot to containers
- Discord slash commands wired to real tmux-backed container lifecycle -- /dispatch shows liveness and restarts stopped agents, /kill and /relaunch kill tmux panes, /status removed
- AgentConfig.type field with Literal["gsd","continuous","fulltime","company"] default "gsd" enabling config-driven factory routing and clean direct attribute access
- GsdAgent completion events routed to PM via WorkflowOrchestratorCog, /new-project PM backlog wired, dead code purged
- All 5 notification call sites rewired from direct channel.send() to MessageQueue.enqueue() with ESCALATION/SUPERVISOR/STATUS priority levels

---
