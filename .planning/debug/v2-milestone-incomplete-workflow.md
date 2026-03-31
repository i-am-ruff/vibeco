---
status: investigating
trigger: "v2-milestone-incomplete-workflow: agents sit idle after dispatch, health tree flat, no autonomous workflow"
created: 2026-03-28T00:00:00Z
updated: 2026-03-28T02:30:00Z
---

## Current Focus

hypothesis: CONFIRMED — Architecture doc promises vs code reality reveals 14 behavioral gaps across 9 architecture sections
test: Line-by-line reading of every architecture section against actual source code
expecting: N/A — gap analysis complete
next_action: Return structured gap analysis to caller

## Symptoms

expected: /new-project should create a fully operational system where agents autonomously start working (GSD phases, discuss-plan-execute). Health tree should show CompanyRoot->ProjectSupervisor->agents hierarchy including PM/Strategist.
actual: /new-project creates containers, launches Claude Code sessions in tmux, but agents sit at empty Claude prompts doing nothing. Health tree shows flat "Project: X / agent1: running / agent2: running" with no hierarchy. No PM or Strategist visible.
errors: No errors — everything reports success.
reproduction: Run /new-project with agents.yaml, check tmux sessions, run /health.
started: State after completing all 12 v2.0 phases + gap closure.

## Eliminated

## Evidence

- timestamp: 2026-03-28T00:10:00Z
  checked: v2.0-ROADMAP.md — v1 Phase 10 "Autonomous GSD Agent Dispatch"
  found: v1 Phase 10 D-04 explicitly says "Orchestrator sends standard GSD commands: /gsd:discuss-phase N, /gsd:plan-phase N, /gsd:execute-phase N. Each command runs its stage fully and stops. Orchestrator sends the next command after the gate passes."
  implication: The requirement to send GSD commands to agents existed in v1. v2 was supposed to absorb WorkflowOrchestrator into GsdAgent (TYPE-01).

- timestamp: 2026-03-28T00:15:00Z
  checked: WorkflowOrchestratorCog.start_workflow() (workflow_orchestrator_cog.py:489-515)
  found: Method only posts a Discord system event message ("Workflow started -- Phase {phase}, entering DISCUSS stage"). It does NOT send any command to the tmux pane. No call to send_keys, send_command, or any tmux interaction.
  implication: Agents receive Claude Code session but never receive a GSD command. They sit at empty prompts.

- timestamp: 2026-03-28T00:17:00Z
  checked: AgentContainer._build_launch_command() (container.py:87-102)
  found: Launches "claude --dangerously-skip-permissions --append-system-prompt-file {prompt_path}" — starts Claude Code but provides no initial work command or prompt.
  implication: The launch command starts the tool but gives it nothing to do.

- timestamp: 2026-03-28T00:20:00Z
  checked: CLI dispatch_cmd.py (lines 58-110)
  found: Has --command and --resume options but prints "Note: work command must be sent manually via tmux or 'vco up'." — never actually sends the command. The bot path has no equivalent.
  implication: Even the CLI acknowledged this gap but never resolved it.

- timestamp: 2026-03-28T00:25:00Z
  checked: v2.0-REQUIREMENTS.md — searched for any requirement about sending GSD commands
  found: No requirement explicitly states "send initial GSD command to agent after dispatch." TYPE-01 says "GsdAgent with internal phase FSM absorbing WorkflowOrchestrator" and MIGR-01 says "CompanyRoot replaces flat VcoBot.on_ready()." Neither says "and sends /gsd:discuss-phase to the tmux pane."
  implication: Requirements gap — the critical handoff step (container start -> GSD command delivery) was never specified.

- timestamp: 2026-03-28T00:30:00Z
  checked: v2.0-ROADMAP.md Phase 8.2 success criteria
  found: Phase 8.2 SC-1 says "/dispatch creates an AgentContainer, starts it via the supervision tree, and launches the tmux session — container state tracks real tmux liveness." No mention of sending a GSD command after launch.
  implication: Even the deep integration phase only specified container-tmux lifecycle bridging, not work initiation.

- timestamp: 2026-03-28T00:35:00Z
  checked: build_health_tree_embed() (embeds.py:300-374)
  found: Renders "Project: {supervisor_id}" as field header, then agents as list. CompanyRoot level is NOT rendered. The embed title is "Health Tree" with no CompanyRoot node shown.
  implication: Health tree rendering skips the CompanyRoot level — shows Project->Agents but not CompanyRoot->Project->Agents. This is a rendering gap, not data gap (CompanyHealthTree has the CompanyRoot state).

- timestamp: 2026-03-28T00:37:00Z
  checked: HLTH-03 requirement text
  found: "Discord slash command /health renders the full status tree with state indicators." Phase 5 SC-2: "Running /health in Discord renders the full supervision tree with color-coded state indicators."
  implication: Requirement says "full supervision tree" which should include CompanyRoot, but the implementation renders only project and agent levels.

- timestamp: 2026-03-28T00:40:00Z
  checked: v2.0-MILESTONE-AUDIT.md
  found: Audit scores 34/34 requirements, 8/8 flows. E2E flow "/dispatch -> container start -> tmux session" marked Complete. No flow for "dispatch -> container start -> tmux session -> GSD command -> agent working." Audit did NOT flag the missing work initiation step.
  implication: Verification gap — audit checked structural completeness (container creates, starts, launches tmux) but not functional completeness (agent actually does work).

- timestamp: 2026-03-28T00:42:00Z
  checked: UAT results (05-UAT.md, committed 248c660)
  found: UAT test 6 flagged as blocker: "After /new-project, agents show as 'running (idle)' but nothing actually changed from v1 behavior. The supervision tree exists in memory but doesn't drive real agent lifecycle." The UAT caught it.
  implication: The gap was invisible to unit tests and audit but immediately visible in real E2E usage.

- timestamp: 2026-03-28T00:45:00Z
  checked: FulltimeAgent and CompanyAgent event handlers
  found: Audit tech debt notes both have "event handler body is `pass` (intentionally deferred per plan)." These containers exist in the tree but do nothing when events arrive.
  implication: PM and Strategist containers exist but are non-functional. They'll appear in /health tree but can't actually make decisions.

- timestamp: 2026-03-28T02:00:00Z
  checked: ARCHITECTURE SECTION 2 (Supervision Tree) vs code
  found: |
    CompanyRoot: EXISTS AND WORKS — company_root.py implements top-level supervisor with dynamic project management, escalation, scheduler. Strategist as direct child of CompanyRoot: NOT IMPLEMENTED — Strategist is not spawned by CompanyRoot; it is only created if included in agents.yaml child_specs under a ProjectSupervisor. Architecture says Strategist sits between CompanyRoot and ProjectSupervisors. Code puts all agent types (including fulltime/company) under ProjectSupervisor.
    ProjectSupervisor per project: EXISTS AND WORKS — project_supervisor.py is a thin Supervisor subclass, one per project.
    PM under ProjectSupervisor: EXISTS STRUCTURALLY — FulltimeAgent is created under ProjectSupervisor if agents.yaml includes a "fulltime" type. But PM does not drive workflow.
    "Every node supervises its children. No external watchdog.": PARTIALLY TRUE — supervision tree manages restart/escalation. But WorkflowOrchestratorCog is still an external orchestrator posting Discord messages; it is not a node in the supervision tree.
  implication: The supervision hierarchy is flat where the architecture specified a layered tree. Strategist should be a peer of ProjectSupervisors, not a child of one.

- timestamp: 2026-03-28T02:02:00Z
  checked: ARCHITECTURE SECTION 3 (AgentContainer) vs code
  found: |
    Communication port send(channel, message) / on_message(handler): IMPLEMENTED — CommunicationPort protocol in communication.py, DiscordCommunicationPort in discord_communication.py. BUT: DiscordCommunicationPort is never instantiated anywhere in the startup path. VcoBot.on_ready() and /new-project both create containers with comm_port=None (default). The protocol exists but is never wired.
    Container states CREATING->RUNNING->SLEEPING->ERRORED->STOPPING->STOPPED->DESTROYED: PARTIALLY IMPLEMENTED — ContainerLifecycle has creating, running, sleeping, errored, stopped, destroyed. Missing: STOPPING state. Architecture specifies 7 states; code has 6. The "stop" transition goes directly from running/sleeping/errored to stopped with no intermediate STOPPING state.
  implication: Communication port is dead code — structurally complete but never connected. Missing STOPPING state means no graceful shutdown signaling to the agent before termination.

- timestamp: 2026-03-28T02:05:00Z
  checked: ARCHITECTURE SECTION 4.1 (GsdAgent) vs code
  found: |
    Internal FSM IDLE->DISCUSS->PLAN->EXECUTE->UAT->SHIP: IMPLEMENTED — GsdLifecycle has all 6 states with proper compound state inside running.
    "Any state can transition to BLOCKED": NOT IMPLEMENTED — GsdAgent has mark_blocked()/clear_blocked()/is_blocked properties that set a timestamp and reason string. But BLOCKED is not an FSM state. The FSM has no blocked state and no transitions to it. blocked_since is just a Python attribute, invisible to the supervision tree and health reporting. inner_state never reports "blocked".
    "Checkpoint saved after each state transition": IMPLEMENTED — _checkpoint_phase() writes to MemoryStore after each advance_phase() call.
    "On crash: restart from last completed state": IMPLEMENTED — _restore_from_checkpoint() reads last checkpoint on start() and restores FSM configuration.
  implication: BLOCKED is not a real FSM state. PM cannot detect blocked agents through the health tree, only through the is_blocked property if someone calls it manually.

- timestamp: 2026-03-28T02:07:00Z
  checked: ARCHITECTURE SECTION 4.2 (ContinuousAgent) vs code
  found: |
    Internal cycle WAKE->GATHER->ANALYZE->ACT->REPORT->SLEEP: IMPLEMENTED — ContinuousLifecycle has all 6 phases (sleep_prep instead of SLEEP, since SLEEP is the outer state).
    "Can REQUEST task agents through its parent supervisor": IMPLEMENTED STRUCTURALLY — delegation.py has DelegationRequest/DelegationResult/DelegationTracker/DelegationPolicy. Supervisor.handle_delegation_request() spawns TEMPORARY agents. BUT: No code path exists where a ContinuousAgent actually calls handle_delegation_request(). The agent has no method to initiate delegation. The protocol exists but the agent side is unwired.
    Persistent memory with seen_items, pending_actions, briefing_log, config: NOT IMPLEMENTED — ContinuousAgent only persists cycle_count and checkpoint data. There are no seen_items, pending_actions, briefing_log, or config keys. The MemoryStore is used only for FSM recovery, not for the agent's operational memory.
  implication: ContinuousAgent delegation is structurally complete on the supervisor side but has no way to be triggered from the agent side. Operational memory schema is not implemented.

- timestamp: 2026-03-28T02:10:00Z
  checked: ARCHITECTURE SECTION 4.3 (FulltimeAgent / PM) vs code
  found: |
    "Responds to: GSD state transitions": PARTIALLY — FulltimeAgent._handle_event() routes task_completed, task_failed, add_backlog_item, request_assignment. But it does not receive GSD state transition events. The health_change callback in Supervisor fires on_health_change (HealthCog._notify_state_change) which posts to Discord #alerts. It does NOT post to the PM's event queue. PM never learns about agent state changes through its event queue.
    "Agent health changes": NOT WIRED — Same issue. on_health_change goes to HealthCog for Discord display, not to PM's event queue.
    "Briefings, Escalations": NOT WIRED — No code routes briefings or escalations to PM's event queue.
    "Milestone completion": PARTIALLY WIRED — WorkflowOrchestratorCog._handle_phase_complete() does post a task_completed event to PM. This is the one working event path.
    "Can trigger: Integration review": NOT IMPLEMENTED — PM has no method to trigger integration.
    "Milestone injection": NOT IMPLEMENTED — PM has no method to inject milestones into agent assignment queues.
    "Agent recruitment/removal": NOT IMPLEMENTED — PM cannot spawn or stop agents.
    "Escalation to Strategist": NOT IMPLEMENTED — No code routes PM events to CompanyAgent/Strategist.
    Persistent memory: milestone_backlog, active_milestone, decisions_log, integration_state, agent_roster: PARTIALLY — BacklogQueue persists backlog items. decisions_log, integration_state, agent_roster are not implemented.
  implication: PM can process events from its queue but almost nothing puts events on that queue. 1 of 5 event sources wired, 0 of 4 trigger capabilities implemented.

- timestamp: 2026-03-28T02:12:00Z
  checked: ARCHITECTURE SECTION 4.4 (CompanyAgent / Strategist) vs code
  found: |
    "Responds to: PM escalations": NOT WIRED — No code routes PM events to CompanyAgent.
    "Company-level continuous agent briefings": NOT WIRED — No briefing delivery mechanism.
    "Owner directives": PARTIALLY — StrategistCog handles Discord messages from owner in #strategist channel and responds via Anthropic API. This IS owner directive handling, but it runs as a separate Cog, not through CompanyAgent's event queue. CompanyAgent._handle_event() is `pass`.
    "Project lifecycle events": NOT WIRED.
    "Can trigger: New project creation": NOT IMPLEMENTED via CompanyAgent. StrategistCog + CommandsCog handle /new-project.
    "Cross-project resource reallocation": NOT IMPLEMENTED.
    "Strategic direction changes": NOT IMPLEMENTED.
    "Escalation to Owner": NOT IMPLEMENTED via CompanyAgent event system.
    Cross-project state: IMPLEMENTED — get/set_cross_project_state() with xp: prefix in MemoryStore.
  implication: CompanyAgent is an empty shell. All Strategist functionality is in StrategistCog (a Discord Cog), completely bypassing the container/event architecture. The architecture envisioned Strategist as an event-driven container; the implementation has it as a Discord bot extension.

- timestamp: 2026-03-28T02:15:00Z
  checked: ARCHITECTURE SECTION 5 (Supervision & Restart) vs code
  found: |
    Restart policies one_for_one, all_for_one, rest_for_one: IMPLEMENTED — All three strategies in supervisor.py with proper stop/restart ordering.
    max_restarts with time_window: IMPLEMENTED — RestartTracker with sliding window.
    on_max_exceeded escalate | stop_subtree: PARTIALLY — _escalate() stops all children and escalates to parent. "stop_subtree" is effectively what happens. But there's no configurable choice between "escalate" and "stop_subtree" — it always stops children then escalates.
    "PM supervision of GSD workflow: If agent stuck in same GSD state > threshold -> PM intervenes via Discord": NOT IMPLEMENTED — No code monitors how long an agent has been in a given GSD state. The monitor/checks.py and heartbeat.py exist but do not check GSD phase duration. PM's event queue is not fed with "agent stuck" events.
  implication: Restart semantics work. But the architecture-promised "PM intervenes when agent is stuck" supervision does not exist.

- timestamp: 2026-03-28T02:17:00Z
  checked: ARCHITECTURE SECTION 6 (Health Reporting) vs code
  found: |
    Full tree rendering showing CompanyRoot->Strategist->Projects->PM->Agents: NOT IMPLEMENTED — build_health_tree_embed() renders Project->Agents only. No CompanyRoot node. No Strategist node at CompanyRoot level. The architecture shows a hierarchical display; the code shows a flat per-project list.
    "Can be queried at any level": PARTIALLY — /health has project_filter and agent_filter params. But you cannot query CompanyRoot level or Strategist level.
    "State transitions trigger Discord notifications": IMPLEMENTED — HealthCog._notify_state_change() posts to #alerts on errored/running/stopped transitions via MessageQueue.
    "No polling from Discord side -- agents push their status changes": IMPLEMENTED — Container._on_state_change() fires callback on every FSM transition, which the supervisor caches and the HealthCog pushes to Discord.
  implication: Health data flows work. Health rendering is incomplete — missing top-level nodes and tree structure.

- timestamp: 2026-03-28T02:20:00Z
  checked: ARCHITECTURE SECTION 7 (Milestone Injection / Living Backlog) vs code
  found: |
    MilestoneBacklog with completed, active, queued: PARTIALLY — BacklogQueue has items with status PENDING/ASSIGNED/IN_PROGRESS/COMPLETED/CANCELLED. But there's no concept of "active milestone" vs "queued milestone". BacklogQueue is a flat task list, not a milestone hierarchy.
    Operations append, insert_after, insert_urgent, reorder, cancel: IMPLEMENTED — BacklogQueue has all five operations.
    "GSD begins on injected milestone automatically": NOT IMPLEMENTED — No code auto-assigns backlog items to idle GSD agents. ProjectStateManager.assign_next_task() exists but nobody calls it automatically. An agent would need to post a "request_assignment" event to PM, but GsdAgent has no code to do that. The pipeline is: backlog item exists -> ??? -> agent starts working. The ??? is not implemented.
  implication: Backlog storage and manipulation work. Automatic work distribution from backlog to agents does not exist.

- timestamp: 2026-03-28T02:22:00Z
  checked: ARCHITECTURE SECTION 8 (Delegation Protocol) vs code
  found: |
    ContinuousAgent -> REQUEST_TASK -> ProjectSupervisor -> Spawns TaskAgent -> TASK_COMPLETE -> ContinuousAgent: PARTIALLY — Supervisor.handle_delegation_request() creates TEMPORARY ChildSpec and starts child. DelegationTracker tracks active delegations. Completion is tracked via _make_state_change_callback() which calls tracker.record_completion(). BUT: ContinuousAgent has no method to initiate a delegation request. The "ContinuousAgent -> REQUEST_TASK" arrow does not exist in code. The supervisor and tracker are ready; the requester is not.
    "Allows policy enforcement (rate limits, approval gates)": IMPLEMENTED — DelegationPolicy with max_concurrent_delegations, max_delegations_per_hour, allowed_agent_types. DelegationTracker.can_delegate() enforces all three.
  implication: Delegation infrastructure is built but the initiator (ContinuousAgent) has no way to use it.

- timestamp: 2026-03-28T02:24:00Z
  checked: ARCHITECTURE SECTION 9 (Decoupling) vs code
  found: |
    "receives phase assignments": PARTIALLY — GsdAgent.get_assignment() reads from MemoryStore. set_assignment() writes. But nobody calls set_assignment() in the startup/dispatch path. Agents start with no assignment.
    "reports completions": IMPLEMENTED — GsdAgent.make_completion_event() creates event dict. WorkflowOrchestratorCog._handle_phase_complete() routes it to PM.
    "Agent re-reads its current assignment from project state": NOT IMPLEMENTED — No code has the agent re-read its assignment on restart. _restore_from_checkpoint() restores FSM state but does not restore the work assignment context (what phase, what milestone, what task).
    "No interlocks": PARTIALLY TRUE — Agents don't directly depend on each other. But WorkflowOrchestratorCog is a centralized interlock between agents and gate reviews.
  implication: Assignment write path exists but nobody writes. Read path exists but nothing to read.

- timestamp: 2026-03-28T02:26:00Z
  checked: ARCHITECTURE SECTION 11 (Invariants) vs code
  found: |
    1. "Every running agent has exactly one parent supervisor": TRUE — Factory creates containers, supervisor manages them. No orphans possible.
    2. "No agent spawns children directly": TRUE — Only supervisors can spawn via handle_delegation_request or _start_child.
    3. "Agent crash never corrupts project state": TRUE — MemoryStore uses SQLite with WAL mode. Checkpoints are atomic. PM's state is in its own MemoryStore.
    4. "Container state transitions are atomic": MOSTLY TRUE — python-statemachine transitions are synchronous. But the "atomicity" of the outer async operations (like tmux launch during start()) is not transactional — if tmux launch fails after FSM transitions to running, the container says "running" with no tmux pane. The 30s liveness check in _monitor_child catches this eventually but there's a window.
    5. "Health is self-reported": TRUE — health_report() reads from container's own state.
    6. "Restart is idempotent": TRUE — _start_child cancels old task, clears old reports, creates fresh container.
    7. "GSD state machine consumes milestones from a queue": NOT IMPLEMENTED — GsdAgent has no code to consume from BacklogQueue. The queue exists, the agent has get_assignment(), but there is no automatic consumption loop.
    8. "Continuous agents are stateless between cycles except for memory_store": PARTIALLY — ContinuousAgent only persists cycle_count and checkpoint. Architecture-promised memory keys (seen_items, pending_actions, etc.) don't exist.
  implication: Structural invariants (1-6) are mostly upheld. Behavioral invariants (7-8) are not implemented.

## Resolution

root_cause: |
  ARCHITECTURE-TO-CODE GAP ANALYSIS — 14 behavioral gaps across 9 architecture sections.

  The v2 milestone successfully implemented the STRUCTURAL layer of the Agent Container Architecture:
  - Container lifecycle FSMs (all 4 agent types)
  - Supervision tree with restart strategies
  - Health reporting pipeline
  - MemoryStore persistence
  - Message queue with priority/debounce
  - Degraded mode detection
  - Bulk failure detection

  It did NOT implement the BEHAVIORAL layer — the parts that make agents actually do work:

  **CRITICAL GAPS (system non-functional without these):**

  GAP-01: WORK INITIATION — No GSD command sent to tmux after container launch
    Files: container.py:87-102, workflow_orchestrator_cog.py:489-515
    Architecture says: Agent receives work and begins
    Code does: Launches empty Claude Code session, posts Discord message
    Classification: Integration gap

  GAP-02: AUTOMATIC WORK DISTRIBUTION — Backlog items not auto-assigned to idle agents
    Files: backlog.py (complete), project_state.py (complete), gsd_agent.py (no consumption loop)
    Architecture says: "GSD begins on injected milestone automatically"
    Code does: Backlog exists but no auto-assignment mechanism
    Classification: Integration gap

  GAP-03: PM EVENT ROUTING — PM receives almost no events
    Files: fulltime_agent.py:109-135, supervisor.py:226-257
    Architecture says: PM responds to state transitions, health changes, briefings, escalations
    Code does: Only task_completed routed to PM. State transitions go to HealthCog for Discord display, not PM queue.
    Classification: Integration gap

  **MAJOR GAPS (system functional but degraded without these):**

  GAP-04: STRATEGIST AS CONTAINER — CompanyAgent._handle_event() is `pass`
    Files: company_agent.py:100-102
    Architecture says: Strategist responds to PM escalations, briefings, owner directives via event queue
    Code does: StrategistCog handles owner messages directly via Discord, bypassing CompanyAgent entirely
    Classification: Architecture gap — two parallel systems exist (Cog vs Container)

  GAP-05: COMMUNICATION PORT UNWIRED — DiscordCommunicationPort never instantiated
    Files: discord_communication.py (complete), client.py/commands.py (comm_port always None)
    Architecture says: send(channel, message), on_message(handler) for inter-container communication
    Code does: Protocol defined, Discord implementation complete, but never connected during container creation
    Classification: Integration gap

  GAP-06: BLOCKED STATE NOT IN FSM — is_blocked is a Python attribute, not an FSM state
    Files: gsd_agent.py:199-213, gsd_lifecycle.py (no blocked state)
    Architecture says: "Any state can transition to BLOCKED"
    Code does: Tracks blocked_since/blocked_reason as instance variables. FSM and health tree never see it.
    Classification: Execution gap

  GAP-07: PM TRIGGER CAPABILITIES — PM cannot trigger integration, milestone injection, recruitment, or escalation
    Files: fulltime_agent.py (no trigger methods)
    Architecture says: PM can trigger integration review, milestone injection, agent recruitment/removal, escalation to Strategist
    Code does: PM can process events from queue but has no outbound action methods
    Classification: Execution gap

  GAP-08: SUPERVISION HIERARCHY — Strategist under ProjectSupervisor instead of peer to it
    Files: commands.py:205-219, client.py:282-294
    Architecture says: Strategist is direct child of CompanyRoot, peer to ProjectSupervisors
    Code does: All agent types (including fulltime/company) placed under ProjectSupervisor
    Classification: Architecture gap

  **MINOR GAPS (system functional, rendering/completeness issues):**

  GAP-09: HEALTH TREE RENDERING — CompanyRoot level not shown
    Files: embeds.py:300-378
    Architecture says: Full tree rendering CompanyRoot->Projects->PM->Agents
    Code does: Shows Project->Agents only, no CompanyRoot node
    Classification: Execution gap

  GAP-10: MISSING STOPPING STATE — Container FSM has 6 states, architecture specifies 7
    Files: state_machine.py:16-31
    Architecture says: CREATING->RUNNING->SLEEPING->ERRORED->STOPPING->STOPPED->DESTROYED
    Code does: No STOPPING state. stop() transitions directly to stopped.
    Classification: Execution gap

  GAP-11: DELEGATION INITIATION — ContinuousAgent cannot request delegations
    Files: continuous_agent.py (no delegation method), delegation.py (infrastructure complete)
    Architecture says: ContinuousAgent -> REQUEST_TASK -> ProjectSupervisor
    Code does: Supervisor and tracker ready, but ContinuousAgent has no method to call them
    Classification: Integration gap

  GAP-12: CONTINUOUS AGENT MEMORY — Architecture memory schema not implemented
    Files: continuous_agent.py (only cycle_count and checkpoint)
    Architecture says: seen_items, pending_actions, briefing_log, config
    Code does: Only cycle_count persisted
    Classification: Execution gap

  GAP-13: ASSIGNMENT RECOVERY ON RESTART — Agent doesn't re-read assignment context
    Files: gsd_agent.py:182-185
    Architecture says: "Agent re-reads its current assignment from project state"
    Code does: Restores FSM state but not work context (what task, what phase, what milestone)
    Classification: Execution gap

  GAP-14: PM STUCK-AGENT MONITORING — No GSD phase duration checking
    Files: (no implementation anywhere)
    Architecture says: "If agent stuck in same GSD state > threshold -> PM intervenes"
    Code does: Nothing. No code checks how long an agent has been in a given state.
    Classification: Execution gap

  **ROOT PROCESS FAILURE:** The milestone implemented the container architecture as an infrastructure layer.
  It correctly built: containers, FSMs, supervision, health, persistence, resilience, delegation policy.
  It did not build: the behavioral wiring that connects these infrastructure pieces into an operational system.
  The gap is at the INTEGRATION level — each component works individually but they are not connected to each other.

fix:
verification:
files_changed: []
