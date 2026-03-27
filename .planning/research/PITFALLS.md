# Pitfalls Research

**Domain:** Agent container architecture migration -- supervision trees, container lifecycles, health reporting, delegation protocols added to existing multi-agent orchestration system
**Researched:** 2026-03-27
**Confidence:** HIGH (grounded in existing codebase analysis, Erlang/OTP supervision literature, and agent lifecycle management patterns)

## Critical Pitfalls

### Pitfall 1: Dual State Tracking Creates Split-Brain During Migration

**What goes wrong:**
The existing system tracks agent state in three places: `agents.json` (AgentsRegistry with AgentEntry), `AgentMonitorState` (in-memory per-agent monitor state), and `AgentWorkflowState` (in-memory workflow orchestrator state). The new AgentContainer introduces its own state machine (CREATING, RUNNING, SLEEPING, ERRORED, STOPPED, DESTROYED). During migration, both old and new state tracking run simultaneously. They disagree. The monitor sees an agent as "running" via the old `agents.json` while the new container reports it as "ERRORED". The bot acts on whichever state it reads first, producing contradictory Discord messages and incorrect recovery actions.

**Why it happens:**
In-place refactoring means the old `MonitorLoop._agent_states`, `AgentManager._registry`, and `WorkflowOrchestrator._agent_states` coexist with the new `AgentContainer.state`. Developers keep both systems "just in case" during the transition. The old `AgentEntry.status` field (Literal["starting", "running", "stopped", "crashed", "circuit_open"]) does not map cleanly onto the new container states (CREATING, RUNNING, SLEEPING, ERRORED, STOPPED, DESTROYED). Nobody defines the authoritative source of truth during the transition period.

**How to avoid:**
Define a single source of truth from day one of v2. The AgentContainer owns agent state. Period. The old `agents.json` registry becomes a persistence layer for the container's state, not an independent state tracker. Concretely: (1) AgentContainer exposes a `.status` property that returns the canonical state. (2) The old `AgentEntry` model gains a field that maps to the new container state enum. (3) MonitorLoop and WorkflowOrchestrator read state exclusively from containers, never from their own internal dicts. (4) Write an adapter: `ContainerRegistry` wraps the old `AgentsRegistry` and translates between old/new state representations. Delete the old representation only after all consumers are migrated.

**Warning signs:**
- Discord alerts that contradict each other ("agent-1 is running" followed by "agent-1 is errored")
- `vco status` showing different information than the bot's `!status` command
- Recovery actions firing for agents that are actually healthy
- Two different log lines reporting different states for the same agent in the same cycle

**Phase to address:**
Phase 1 (AgentContainer base abstraction) -- the state ownership must be settled before any other container work begins.

---

### Pitfall 2: Supervision Tree Restart Policies Interact Badly with tmux Lifecycle

**What goes wrong:**
The supervision tree implements `one_for_one` restart policy: when a GsdAgent container reports ERRORED, its ProjectSupervisor restarts it. But "restart" in Erlang means spawning a fresh lightweight process. In vCompany, "restart" means: kill the tmux pane, kill the Claude Code process, create a new tmux pane, launch a new Claude Code session, wait for it to boot (3+ seconds for trust prompt, 10+ seconds for GSD to load), and send it a resume command. This is a 30-60 second operation. During this time, the supervisor's restart timeout may expire, causing it to escalate (kill the supervisor itself), which cascades to kill ALL agents under that ProjectSupervisor.

**Why it happens:**
Erlang's supervision model assumes process creation is nearly instant (microseconds). vCompany's agent "processes" take 30-60 seconds to become operational. The existing `AgentManager.relaunch()` is synchronous and blocking -- it calls `self.kill(agent_id)` then `self.dispatch(agent_id, resume=True)`, with `time.sleep(3)` for trust prompt and potentially 120-second waits for Claude ready markers. If the supervision tree's `max_restart_intensity` timer starts ticking at restart initiation, not completion, every slow restart counts against the restart budget.

**How to avoid:**
(1) Separate "restart intent" from "restart completion" in the supervision tree. The supervisor marks the container as RESTARTING (a new state) and initiates the restart asynchronously. The restart completes when the container transitions to RUNNING, not when the restart function returns. (2) Restart intensity tracking must count completed restart cycles, not initiated ones. (3) Set generous restart windows: in Erlang you might use {3, 60} (3 restarts per 60 seconds). For vCompany, use {3, 600} (3 restarts per 10 minutes) because each restart takes 30-60 seconds. (4) The RESTARTING state must be visible in health reporting so operators can see agents that are in flight. (5) Make the restart truly async: `AgentManager.dispatch()` should return a Future/Task, and the supervisor awaits completion with its own timeout.

**Warning signs:**
- Supervisors cascading restart (all agents killed) after a single agent crash
- "max restart intensity reached" errors appearing after only 1-2 actual restarts
- Agent showing as RUNNING in the container but Claude Code not yet booted
- Long gaps between crash detection and agent resuming work

**Phase to address:**
Phase 2 (Supervision tree implementation) -- restart semantics must account for slow agent bootstrapping.

---

### Pitfall 3: Health Reporting Thundering Herd Saturates the Event Loop

**What goes wrong:**
Every AgentContainer self-reports its HealthReport every N seconds. The CompanyRoot aggregates these into a health tree. With 5+ agents, 1 ProjectSupervisor, and 2 CompanyAgents (PM/Strategist), that is 8+ health reports converging on the root every health interval. The aggregation triggers a Discord status push. If health reporting is synchronous or if all containers report at the same time (because they were all started at the same time), the event loop gets a burst of health processing that delays other async operations (Discord heartbeats, tmux checks, command delivery).

**Why it happens:**
All agents are dispatched in a loop by `AgentManager.dispatch_all()`, so they all start at roughly the same time. If health reporting runs on a fixed interval from start time, all containers report simultaneously. The existing `MonitorLoop._run_cycle()` already runs all agent checks via `asyncio.gather()`, but health report aggregation adds a new O(N) processing step after each report, plus Discord API calls for status pushes.

**How to avoid:**
(1) Stagger health report intervals with random jitter. Each container reports at `base_interval + random(0, base_interval * 0.3)` seconds from its last report, not from a global clock. (2) Health aggregation should be lazy/batched: the root collects reports into a buffer and only aggregates + pushes to Discord on a fixed interval (e.g., every 30 seconds), not on every individual report. (3) Use `asyncio.Queue` between containers and the aggregator to decouple report generation from processing. (4) Discord status pushes should be debounced: if the health tree did not change, do not send an update.

**Warning signs:**
- Discord heartbeat warnings during health aggregation cycles
- Spiky CPU usage every N seconds coinciding with health interval
- Status pushes to Discord arriving in bursts rather than evenly spaced
- Event loop blocked warnings in asyncio debug mode

**Phase to address:**
Phase 3 (Health tree implementation) -- but the staggering/debouncing pattern should be designed in Phase 1 when defining the HealthReport interface.

---

### Pitfall 4: Supervision Tree Inserts Between Bot and Existing Callbacks, Breaking Wiring

**What goes wrong:**
The current system has a carefully wired callback chain: `VcoBot.on_ready()` creates `AgentManager`, `MonitorLoop`, `CrashTracker`, then injects callbacks from `AlertsCog`, `PlanReviewCog`, and `CommandsCog` into the monitor. The WorkflowOrchestrator gets wired to the PlanReviewCog. This wiring happens in a specific order with specific references. Introducing a supervision tree (CompanyRoot -> ProjectSupervisor -> agents) means adding a new layer that intercepts lifecycle events (crashes, restarts, state transitions) that currently flow directly from MonitorLoop to AlertsCog/WorkflowOrchestrator. Inserting this layer breaks the existing callback contracts without anyone noticing until runtime.

**Why it happens:**
The current `VcoBot.on_ready()` is already ~200 lines of sequential wiring with cross-references between Cogs and services. The supervision tree needs to intercept events that currently flow through `MonitorLoop.on_agent_dead` -> `AlertsCog` and `WorkflowOrchestrator.on_stage_complete`. But the existing callbacks are set up as direct function references. There is no event bus or message-passing system -- it is hardcoded dependency injection. Adding the supervisor as an intermediary means rewriting every callback chain, and missing even one causes silent failures (the callback just never fires).

**How to avoid:**
(1) Introduce an event bus before building the supervision tree. Even a simple `asyncio.Queue`-based pub/sub or Python's built-in `asyncio.Event` pattern. Containers publish lifecycle events (CRASHED, RESTARTED, STATE_CHANGED). Consumers subscribe. This decouples the supervision tree from existing Cogs. (2) Keep the existing callback wiring working during migration by having the supervision tree emit the same callbacks the MonitorLoop currently emits. ProjectSupervisor.on_child_crash() calls the same `on_agent_dead` callback that MonitorLoop currently calls. (3) Write integration tests that verify every callback chain fires end-to-end. The current codebase has interaction regression tests (Phase 7) -- extend them to cover supervision tree event flows. (4) Migrate callbacks to event bus one at a time, not all at once.

**Warning signs:**
- Alerts that used to fire no longer appearing in Discord
- Plan gates not triggering despite new PLAN.md files
- WorkflowOrchestrator not advancing agents past gates
- Silent failures with no errors in logs (because the callback was never registered)

**Phase to address:**
Phase 1 (AgentContainer base) for the event/communication mechanism. Phase 2 (supervision tree) for the actual callback migration.

---

### Pitfall 5: Container State Machine Transition Races with GSD State Machine

**What goes wrong:**
The new AgentContainer has its own state machine (CREATING -> RUNNING -> SLEEPING -> ERRORED -> STOPPED -> DESTROYED). The GsdAgent specialization adds an inner state machine (IDLE -> DISCUSS -> PLAN -> EXECUTE -> UAT -> SHIP). The existing WorkflowOrchestrator already has a state machine (IDLE -> DISCUSS -> DISCUSSION_GATE -> PLAN -> PM_PLAN_REVIEW_GATE -> EXECUTE -> VERIFY -> VERIFY_GATE -> PHASE_COMPLETE). That is three state machines tracking the same agent. When the GsdAgent transitions from EXECUTE to UAT, but the WorkflowOrchestrator thinks it is still in EXECUTE (because it detects completion via Discord message parsing with regex), and the container is in RUNNING (which does not encode phase progress at all), the system has three different answers to "what is agent-1 doing?"

**Why it happens:**
The existing WorkflowOrchestrator detects stage completion by parsing `vco report` Discord messages with regex patterns (`STAGE_COMPLETE_PATTERNS`). The new GsdAgent detects its own phase transitions internally. These are independent detection mechanisms operating on different signals at different times. The container's outer state machine (RUNNING/SLEEPING/ERRORED) is orthogonal to the inner GsdAgent phase machine, but consumers conflate them.

**How to avoid:**
(1) Collapse the WorkflowOrchestrator state machine INTO the GsdAgent container. The GsdAgent IS the workflow state machine -- there should not be a separate WorkflowOrchestrator tracking the same states. (2) The container's outer state (RUNNING/ERRORED/etc.) represents liveness. The inner state (DISCUSS/PLAN/EXECUTE/etc.) represents phase progress. These are orthogonal dimensions, not competing state machines. Make this explicit in the API: `container.lifecycle_state` vs `container.work_state`. (3) Eliminate the regex-based signal detection. GsdAgent should report phase transitions through the container's event system, not through Discord message parsing. (4) If the WorkflowOrchestrator must remain during migration, make it a consumer of GsdAgent events rather than an independent state tracker.

**Warning signs:**
- Agent reported as "executing" by one system and "plan review" by another
- Phase transitions firing twice (once from regex detection, once from container event)
- Commands sent to agents that are in the wrong state for those commands
- Gate reviews triggering for phases the agent has already moved past

**Phase to address:**
Phase 2 (GsdAgent type specialization) -- this is where the state machines get consolidated. Design the relationship in Phase 1.

---

### Pitfall 6: Delegation Protocol Creates Unbounded Agent Spawning

**What goes wrong:**
ContinuousAgent (e.g., the Monitor agent running scheduled cycles) can request task spawns through the supervisor: "I found 3 failing tests, please spawn 3 GsdAgents to fix them." The supervisor creates 3 new agents. Those agents, upon analyzing their tasks, discover additional work and request more spawns. Without bounds, agent count grows exponentially, exhausting tmux panes, system memory, and API rate limits. On a single machine with a $50/day API budget, 10 concurrent Claude Code sessions can burn through the budget in under 2 hours.

**Why it happens:**
The delegation protocol is designed for flexibility -- continuous agents observe and react. But observation-reaction loops without bounds are positive feedback loops. The existing `dispatch_fix` in AgentManager already spawns fix tasks, but it is triggered by the integration pipeline (a bounded, serialized process). The new delegation protocol allows any ContinuousAgent to request spawns at any time, and if the PM auto-approves (HIGH confidence), there is no human check.

**How to avoid:**
(1) Hard cap on concurrent agents per ProjectSupervisor. Configuration in agents.yaml: `max_concurrent_agents: 5`. Supervisor refuses spawn requests beyond the cap with a queued backlog. (2) Spawn rate limiting: maximum N new agents per hour, regardless of demand. (3) The PM must approve all delegation-initiated spawns, even at HIGH confidence. No auto-approve for spawns. (4) Delegation requests must include a "depth" counter. Direct requests from ContinuousAgent are depth=0. If a spawned agent wants to delegate further, it is depth=1. Reject depth >= 2 by default. (5) Budget tracking: track API costs per supervisor and halt spawning when budget threshold is reached.

**Warning signs:**
- Agent count growing beyond the configured roster
- API costs spiking unexpectedly
- tmux sessions consuming significant system memory
- Multiple agents working on overlapping problems
- Spawn requests arriving faster than agents are completing work

**Phase to address:**
Phase 4 (Delegation protocol) -- caps and rate limits must be in the protocol from the start, not added after an incident.

---

### Pitfall 7: Decoupled Lifecycles Cause Orphaned Agents After Project Teardown

**What goes wrong:**
The design calls for "decoupled project/agent lifecycles" where project state is owned by the PM and agents read assignments. But when a project completes or is cancelled, agents that are mid-execution do not know to stop. The PM marks the project as complete, but 3 GsdAgents are still running, still consuming API tokens, still committing code to branches that will never be merged. The ProjectSupervisor is destroyed, but the agents' tmux panes are still alive because tmux does not care about Python object lifecycle.

**Why it happens:**
"Decoupled" is interpreted as "independent" rather than "loosely coupled with lifecycle contracts." The existing system ties agent lifecycle to the tmux session (`AgentManager.kill()` sends SIGTERM, `close()` cancels the monitor task), but the new container model introduces a layer of indirection. The container object is garbage collected in Python, but the underlying tmux pane and Claude Code process are external resources that survive Python object destruction.

**How to avoid:**
(1) Every container must implement `__del__` or (better) an explicit `destroy()` method that kills the underlying tmux pane and process. Use `contextlib.AsyncExitStack` or `async with` patterns for container lifecycle. (2) ProjectSupervisor.destroy() MUST cascade to all children. This is not optional. The Erlang model gets this right: supervisor termination kills all children. Implement the same guarantee. (3) Decouple means "crash isolation," not "lifecycle independence." A project ending is a graceful shutdown, not a crash -- every agent gets SIGTERM equivalent (a STOPPING state transition), a grace period to commit work, then forced termination. (4) The CompanyRoot must track all ProjectSupervisors and their children. A health tree audit after project teardown should show zero containers for that project.

**Warning signs:**
- tmux panes surviving after `!kill-project` or project completion
- Claude Code processes running with no corresponding container object
- API costs continuing after a project is marked complete
- Orphan branches in git from agents that were never properly stopped

**Phase to address:**
Phase 2 (supervision tree) for cascade termination. Phase 3 (decoupled lifecycles) for the graceful shutdown protocol.

---

### Pitfall 8: ContinuousAgent Scheduled Wake/Sleep Fights asyncio Event Loop

**What goes wrong:**
ContinuousAgent runs on scheduled cycles: WAKE -> GATHER -> ANALYZE -> ACT -> REPORT -> SLEEP. The "SLEEP" state means the agent's Claude Code session is idle (or terminated), and a scheduler in CompanyRoot triggers WAKE at the next scheduled time. But the scheduler is an asyncio timer running inside the Discord bot's event loop. If the scheduler uses `asyncio.sleep(seconds_until_next_wake)` with long durations (hours), and the event loop restarts (bot reconnect, exception recovery), all pending sleeps are cancelled. Agents that should wake up at 2 AM never do.

**Why it happens:**
`asyncio.sleep()` is not persistent. It is cancelled on task cancellation, and asyncio tasks are cancelled on event loop shutdown. The existing `VcoBot.close()` cancels `self._monitor_task`, which would also cancel any scheduler tasks. Discord bot reconnection (`on_ready` with `_initialized` guard) does not restart lost timers because the guard prevents re-initialization.

**How to avoid:**
(1) Persist scheduled wake times to disk (a simple JSON file: `{agent_id: next_wake_iso}`). On bot restart, the scheduler reads the file and re-creates timers for upcoming wakes. (2) Use `discord.ext.tasks.loop()` with a short interval (60 seconds) that checks the schedule file, rather than one long sleep per agent. This pattern matches the existing MonitorLoop (60-second cycle) and survives reconnections. (3) If using the `discord.ext.tasks` loop, mark it with `reconnect=True` so it auto-restarts on bot reconnection. (4) Never rely on in-memory-only scheduling for anything that should survive a process restart.

**Warning signs:**
- ContinuousAgents not waking up after bot restart
- Scheduled tasks drifting (waking 60s late because the check loop has a 60s interval)
- Multiple wake events firing simultaneously after a reconnect (catch-up problem)
- Agent SLEEP state persisting indefinitely

**Phase to address:**
Phase 3 (ContinuousAgent type + Scheduler) -- persistent scheduling must be in the initial design.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keeping WorkflowOrchestrator AND GsdAgent state machines running in parallel | No need to rewrite WorkflowOrchestrator immediately | Two sources of truth for agent phase, inevitable divergence, doubled maintenance | Only during Phase 1-2 migration. Must be consolidated by end of GsdAgent phase. |
| Using dict-based event passing instead of a proper event bus | Simple, no new dependency, Pythonic | No type safety on events, easy to misspell event names, no tooling for debugging event flow | Acceptable for v2. Proper event bus (or Protocol-based typing) can be added later if the dict pattern causes bugs. |
| Container health reporting via polling instead of push | Simpler to implement, matches existing MonitorLoop pattern | Higher latency on health changes, CPU overhead from polling | Acceptable if poll interval <= 10 seconds. Push is better but adds complexity to every container. |
| Storing container state in JSON files instead of SQLite | No new dependency, human-readable, matches v1 pattern | No atomic multi-key updates, no query capability for historical health data | Acceptable for v2. The `memory_store` feature spec mentions "JSON/SQLite" -- start with JSON, migrate if querying becomes necessary. |
| Implementing only `one_for_one` restart policy, deferring `all_for_one` and `rest_for_one` | 70% of use cases covered with simpler code | Cannot handle scenarios where agents have shared state that must be reset together | Acceptable for v2 launch. `all_for_one` is only needed if agents share mutable state, which the isolation model prevents. |
| Hardcoding restart intensity limits instead of making them configurable per agent type | Faster implementation, fewer config options to document | GsdAgents (slow restart) and CompanyAgents (fast restart) have different optimal limits | Never acceptable. Different agent types have fundamentally different restart characteristics. Make it configurable from the start. |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Supervision tree + existing MonitorLoop | Running both MonitorLoop health checks AND supervisor health checks, causing duplicate alerts for the same event | MonitorLoop should delegate liveness checking to the supervision tree. The supervisor is the health authority. MonitorLoop becomes a status aggregator/reporter, not a health checker. |
| AgentContainer + AgentManager | Creating containers that wrap AgentManager calls but AgentManager also directly manages tmux state, causing two objects owning the same tmux pane | AgentContainer should own the tmux pane reference. AgentManager becomes a factory that creates containers, not a lifecycle manager. After creation, the container manages its own pane. |
| CompanyRoot + VcoBot | CompanyRoot lives in Python but VcoBot.on_ready() is where all initialization happens. Making CompanyRoot a field of VcoBot couples the supervision tree to Discord. | CompanyRoot should be independent of Discord. VcoBot holds a reference to CompanyRoot, not the other way around. CompanyRoot emits events that a BotAdapter translates to Discord messages. |
| GsdAgent + CrashTracker | GsdAgent has its own error handling (ERRORED state) but CrashTracker has independent crash classification (transient_context_exhaustion, persistent_repeated_error). Two systems classifying the same crash. | GsdAgent should use CrashTracker for classification. Container transitions to ERRORED, asks CrashTracker "should I retry?" and "how long should I wait?" CrashTracker is the crash policy engine, container is the lifecycle executor. |
| HealthReport + PROJECT-STATUS.md | Both represent "system status" but in different formats for different consumers. Generating both independently leads to drift. | PROJECT-STATUS.md should be derived from the health tree, not generated independently by `status_generator.py`. One source of truth (health tree) with multiple renderers (Discord embed, markdown file, CLI table). |
| Living milestone backlog + WorkflowOrchestrator phase tracking | Backlog says agent should work on milestone item X, but WorkflowOrchestrator has agent on phase Y from the old static roadmap. | The living backlog IS the source of work assignments. WorkflowOrchestrator reads from the backlog, not from a static phase number. The `start_agent(agent_id, phase)` API changes to `start_agent(agent_id, milestone_item)`. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Health tree aggregation walking the entire tree on every report | CPU spikes during health cycles, event loop delays | Incremental aggregation: only re-aggregate the subtree that changed. Cache the last aggregate and apply diffs. | >10 containers (5 agents + supervisors + company agents) |
| Container state persistence writing to disk on every state transition | Disk I/O spikes, especially with multiple agents transitioning simultaneously | Debounce writes: accumulate state changes for 1-2 seconds, then write once. Use `write_atomic` (already exists) for crash safety. | >5 agents transitioning states within the same second (e.g., after dispatch_all) |
| Supervision tree traversal for "docker ps" health display | Slow CLI response for `vco status`, Discord embed generation blocks | Cache the rendered tree. Invalidate on state change. Render lazily only when requested. | >15 containers in the tree |
| Per-container asyncio.Task for health reporting | Task scheduling overhead accumulates, asyncio task list grows | Use a single health collection loop that iterates containers, not one task per container. Matches the existing MonitorLoop pattern. | >20 containers |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Delegation protocol allowing ContinuousAgent to spawn agents with elevated permissions | A monitor agent could spawn a "fix" agent with `--dangerously-skip-permissions` that has broader filesystem access than intended | Spawned agents inherit the permission model of their parent's agent type config in agents.yaml. No permission escalation through delegation. |
| Container health reports including sensitive data (API keys, pane output with credentials) | Health tree visible in Discord status pushes could leak secrets | HealthReport schema must explicitly exclude sensitive fields. Pane output should be sanitized (strip env vars) before inclusion in any report. |
| Living milestone backlog writable by PM agent without validation | PM agent could inject malicious work items that cause agents to execute arbitrary code | Backlog mutations go through a Pydantic-validated schema. The PM tier's confidence scoring applies to backlog changes, with LOW confidence escalating to owner. |

## UX Pitfalls (Discord Interface)

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Health tree dump as raw text in Discord | Unreadable wall of text, especially on mobile | Use Discord embeds with color-coded status (green/yellow/red). Collapsible sections per supervisor. Top-level summary first, details on request. |
| Supervision tree restart events flooding #alerts | Owner gets 5 alerts for a single agent crash (crash detected, supervisor notified, restart initiated, restart in progress, restart complete) | Single alert per lifecycle event with status updates as message edits, not new messages. "Agent-1 crashed. Restarting... [edit] Restarted successfully." |
| Delegation requests requiring owner approval for every spawn | Delegation becomes useless if every spawn needs a Discord button click | Three tiers: (1) Auto-approve up to max_concurrent_agents cap, (2) PM-approve for cap+1 to cap+3, (3) Owner-approve beyond that. Show pending delegations in a dashboard, not individual alerts. |
| Living backlog changes not visible to owner | PM reorders work silently, owner discovers agents working on unexpected tasks | Post backlog diffs to #decisions channel. "PM reordered backlog: moved 'auth system' from position 3 to position 1. Reason: dependency blocker." |

## "Looks Done But Isn't" Checklist

- [ ] **AgentContainer state machine:** States transition correctly -- but verify that EVERY state has a timeout/watchdog. An agent stuck in CREATING forever because Claude Code never booted is a container that "works" but is useless. Verify: forced transition to ERRORED after boot timeout.
- [ ] **Supervision tree restart:** Supervisor restarts a crashed agent -- but verify the restarted agent actually resumes work, not just boots. Check: does the restarted GsdAgent pick up from its last checkpoint or start from scratch?
- [ ] **Health reporting:** Health tree renders beautifully -- but verify it updates when state changes. A cached health tree that shows "all green" while an agent is ERRORED is worse than no health tree.
- [ ] **Delegation protocol:** ContinuousAgent can request spawns -- but verify spawned agents get proper context (clone, owned directories, agent prompt). A spawned agent with no context file is a waste of API tokens.
- [ ] **Living backlog:** PM can reorder items -- but verify agents actually read the updated backlog. If the agent reads the backlog at startup and never again, reordering is meaningless.
- [ ] **Cascade termination:** ProjectSupervisor.destroy() kills children -- but verify it kills the tmux panes and Claude Code processes, not just the Python container objects. Check: `tmux list-panes` should show no orphans after project teardown.
- [ ] **Event bus / callback migration:** Supervision events fire -- but verify existing Cog consumers (AlertsCog, PlanReviewCog, WorkflowOrchestratorCog) still receive them. Run the Phase 7 interaction regression tests after every callback migration.
- [ ] **Scheduler persistence:** ContinuousAgent schedule is set -- but verify it survives bot restart. Kill the bot, restart it, and check if the agent wakes on schedule.
- [ ] **Container + tmux pane ownership:** Container owns its pane -- but verify the pane reference is still valid after tmux server restart or session recreation. Stale pane references cause silent send_command failures.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Split-brain state (Pitfall 1) | MEDIUM | Audit all state sources. Pick the container's state as truth. Force-update agents.json to match. Restart monitor loop to clear in-memory state. |
| Cascade restart from slow bootstrap (Pitfall 2) | HIGH | If all agents were killed by supervisor cascade: manually restart the ProjectSupervisor with increased restart intensity limits. Agents need full redispatch. Work since last commit is lost for all agents. |
| Health thundering herd (Pitfall 3) | LOW | Add jitter to health intervals. No data loss, just performance degradation during the fix. |
| Broken callback wiring (Pitfall 4) | MEDIUM | Run interaction regression tests to identify which callbacks are broken. Re-wire manually. May require bot restart after fixing. Work in progress is preserved if agents are still running. |
| Triple state machine confusion (Pitfall 5) | HIGH | Stop relying on WorkflowOrchestrator for agents that have GsdAgent containers. Delete the duplicate state tracking. Requires careful migration with tests at each step. |
| Unbounded spawning (Pitfall 6) | MEDIUM-HIGH | Kill excess agents immediately. Implement caps retroactively. Audit API costs. Owner may need to manually review and approve the backlog of spawned tasks. |
| Orphaned agents (Pitfall 7) | LOW | `tmux kill-session -t vco-{project}` to kill all orphans. Check for orphan Claude Code processes with `ps aux | grep claude`. Clean up git branches. |
| Lost scheduled wakes (Pitfall 8) | LOW | Check schedule file, manually trigger WAKE for any agents past their scheduled time. Fix persistence mechanism. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Split-brain state (1) | Phase 1: AgentContainer base | Write a test that creates a container, changes its state, and verifies agents.json, MonitorLoop, and WorkflowOrchestrator all report the same state |
| Cascade restart from slow bootstrap (2) | Phase 2: Supervision tree | Simulate a 45-second agent restart (mock slow Claude boot) and verify supervisor does not cascade-kill siblings |
| Health thundering herd (3) | Phase 3: Health tree | Dispatch 5 agents simultaneously and measure event loop latency during health reporting. Assert < 100ms per aggregation cycle |
| Broken callback wiring (4) | Phase 1-2: Event mechanism + tree | Run ALL existing Phase 7 interaction regression tests after each migration step. Zero regressions allowed. |
| Triple state machine (5) | Phase 2: GsdAgent type | After GsdAgent implementation, delete WorkflowOrchestrator agent state tracking. Verify via test that only one state machine tracks phase progress per agent. |
| Unbounded spawning (6) | Phase 4: Delegation protocol | Write a stress test: ContinuousAgent requests 20 spawns. Verify cap enforced, excess queued, no more than max_concurrent_agents running. |
| Orphaned agents (7) | Phase 2: Supervision tree + Phase 3: Lifecycle decoupling | Call ProjectSupervisor.destroy(), then verify zero tmux panes and zero Claude Code processes for that project |
| Lost scheduled wakes (8) | Phase 3: ContinuousAgent + Scheduler | Set a wake schedule, kill the bot, restart it, verify the agent wakes on time. Specifically test the "bot was down during scheduled wake time" case. |

## Sources

- [Supervision Trees | Adopting Erlang](https://adoptingerlang.org/docs/development/supervision_trees/) -- restart intensity, max_restart_intensity patterns
- [Who Supervises The Supervisors? | Learn You Some Erlang](https://learnyousomeerlang.com/supervisors) -- supervisor design anti-patterns, state loss in restarts
- [Erlang Supervisor Behaviour](https://www.erlang.org/doc/system/sup_princ.html) -- one_for_one, all_for_one, restart strategies
- [The Supervision Tree Patterns That Make Systems Bulletproof](https://medium.com/@kanishks772/the-supervision-tree-patterns-that-make-systems-bulletproof-356199f178bb) -- hierarchical fault isolation, blast radius reduction
- [Kubernetes Agent Sandbox](https://kubernetes.io/blog/2026/03/20/running-agents-on-kubernetes-with-agent-sandbox/) -- agent lifecycle patterns, cold start, stateful singleton management
- [AI Agents and Their Life Cycle | The New Stack](https://thenewstack.io/ai-agents-and-their-life-cycle-what-you-should-know/) -- agent lifecycle management patterns
- [Stateful vs. Stateless Containerized Apps for Migration](https://dohost.us/index.php/2026/03/26/stateful-vs-stateless-designing-containerized-apps-for-easy-migration/) -- state persistence independent of container lifecycle
- [Trio supervision logic discussion](https://github.com/python-trio/trio/issues/569) -- Python async supervision patterns
- Existing vCompany codebase analysis: `bot/client.py`, `orchestrator/agent_manager.py`, `orchestrator/workflow_orchestrator.py`, `monitor/loop.py`, `monitor/checks.py`, `orchestrator/crash_tracker.py`, `models/agent_state.py`

---
*Pitfalls research for: Agent container architecture migration (vCompany v2.0)*
*Researched: 2026-03-27*
