# Milestones

## v2.0 Agent Container Architecture (Shipped: 2026-03-28)

**Phases completed:** 9 phases, 24 plans, 42 tasks

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

---
