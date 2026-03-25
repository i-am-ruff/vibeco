# Roadmap: vCompany

## Overview

vCompany delivers an autonomous multi-agent orchestration system in seven phases, following a strict dependency chain: foundation utilities and config first, then agent lifecycle management, then the monitor loop that supervises agents, then the Discord bot that provides the human interface, then the hook and plan gate system that enables agent autonomy, then the PM/Strategist that automates decision-making, and finally the integration pipeline and communication rituals that close the loop. Each phase delivers a coherent, independently verifiable capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation and Configuration** - Config models, wrappers, project init, clone setup with agent artifacts
- [ ] **Phase 2: Agent Lifecycle and Pre-flight** - Dispatch, kill, relaunch, crash recovery, and headless behavior validation
- [ ] **Phase 3: Monitor Loop and Coordination** - Liveness checks, stuck detection, status generation, context distribution, contract system
- [ ] **Phase 4: Discord Bot Core** - Bot framework, channel structure, operator commands, role-based access
- [ ] **Phase 5: Hooks and Plan Gate** - AskUserQuestion hook, plan detection, plan review flow, interaction safety in planning
- [ ] **Phase 6: PM/Strategist and Milestones** - Autonomous question answering, plan review, confidence scoring, milestone management
- [ ] **Phase 7: Integration Pipeline and Communications** - Branch merging, test attribution, standup/checkin rituals, interaction regression tests

## Phase Details

### Phase 1: Foundation and Configuration
**Goal**: The system can parse agent configuration, create project structures, clone repos with per-agent isolation, and deploy all necessary artifacts to each clone
**Depends on**: Nothing (first phase)
**Requirements**: FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05, FOUND-06, FOUND-07, COORD-04, COORD-05, COORD-06, COORD-07
**Success Criteria** (what must be TRUE):
  1. Running `vco init` with a valid agents.yaml creates the full project directory structure (clones/, context/, agents/)
  2. Running `vco clone` produces one isolated repo clone per agent, each with its own branch, deployed hooks, GSD config, CLAUDE.md, and vco command files
  3. An invalid agents.yaml is rejected with clear validation errors before any filesystem changes occur
  4. Git and tmux operations work through wrapper abstractions that handle errors and log output
  5. All coordination file writes use atomic tmp-then-rename pattern (verified by test)
**Plans**: 4 plans
Plans:
- [x] 01-01-PLAN.md -- Project bootstrap + Pydantic config models
- [x] 01-02-PLAN.md -- Git wrapper, tmux wrapper, atomic file ops
- [x] 01-03-PLAN.md -- Jinja2 templates + vco init command
- [x] 01-04-PLAN.md -- vco clone command + artifact deployment

### Phase 2: Agent Lifecycle and Pre-flight
**Goal**: Agents can be launched, terminated, and automatically recovered from crashes, with validated understanding of Claude Code headless behavior
**Depends on**: Phase 1
**Requirements**: LIFE-01, LIFE-02, LIFE-03, LIFE-04, LIFE-05, LIFE-06, LIFE-07, PRE-01, PRE-02, PRE-03
**Success Criteria** (what must be TRUE):
  1. Running `vco dispatch agent-x` launches a Claude Code session in a tmux pane with correct flags and system prompt
  2. Running `vco dispatch all` creates a tmux session with one pane per agent plus a monitor pane
  3. Running `vco kill agent-x` terminates the agent session cleanly (graceful then forced)
  4. A crashed agent is automatically relaunched with `/gsd:resume-work`, with exponential backoff (30s, 2min, 10min), and the circuit breaker stops after 3 crashes/hour with a Discord alert
  5. Pre-flight tests validate Claude Code headless behaviors (stream-json heartbeat, permission hang, --max-turns exit, --resume recovery) and their results determine the monitor strategy
**Plans**: 3 plans
Plans:
- [x] 02-01-PLAN.md -- State models + crash tracker (backoff, circuit breaker, classification)
- [x] 02-02-PLAN.md -- Agent manager + dispatch/kill/relaunch CLI commands
- [x] 02-03-PLAN.md -- Pre-flight test suite + CLI command

### Phase 3: Monitor Loop and Coordination
**Goal**: Agents are continuously supervised with liveness checks, stuck detection, and cross-agent status awareness distributed to all clones
**Depends on**: Phase 2
**Requirements**: MON-01, MON-02, MON-03, MON-04, MON-05, MON-06, MON-07, MON-08, COORD-01, COORD-02, COORD-03, SAFE-03
**Success Criteria** (what must be TRUE):
  1. The monitor loop runs every 60 seconds, checking each agent independently (one agent's check failure does not affect others)
  2. A dead agent (tmux pane gone or process PID missing) is detected within one monitor cycle
  3. An agent with no git commits for 30+ minutes triggers a stuck alert
  4. PROJECT-STATUS.md is generated from all clones' state every cycle and distributed to every clone
  5. Running `vco sync-context` pushes updated INTERFACES.md, MILESTONE-SCOPE.md, and STRATEGIST-PROMPT.md to all clones
**Plans**: 4 plans
Plans:
- [x] 03-01-PLAN.md -- Monitor state models + check functions (liveness, stuck, plan gate)
- [x] 03-02-PLAN.md -- PROJECT-STATUS.md generation/distribution + heartbeat watchdog
- [x] 03-03-PLAN.md -- MonitorLoop class + vco monitor CLI command
- [x] 03-04-PLAN.md -- Coordination system (INTERFACES.md, sync-context, INTERACTIONS.md)

### Phase 4: Discord Bot Core
**Goal**: The owner can control and observe the entire agent fleet from Discord using bot commands
**Depends on**: Phase 3
**Requirements**: DISC-01, DISC-02, DISC-03, DISC-04, DISC-05, DISC-06, DISC-07, DISC-08, DISC-09, DISC-10, DISC-11, DISC-12
**Success Criteria** (what must be TRUE):
  1. Bot creates the full channel structure on project init (#strategist, #plan-review, #standup, #agent-{id}, #alerts, #decisions)
  2. Owner can dispatch, kill, relaunch, and check status of agents via Discord commands (!dispatch, !kill, !relaunch, !status)
  3. Commands are gated by Discord roles (only authorized roles can dispatch, kill, approve)
  4. All blocking CLI calls use asyncio.to_thread() so the bot never disconnects from the Discord gateway
  5. Bot monitors its own connectivity and reconnects automatically after network interruptions
**Plans**: 4 plans
Plans:
- [x] 04-01-PLAN.md -- Bot foundation (discord.py dep, config, client, channel setup, views, permissions, embeds)
- [x] 04-02-PLAN.md -- CommandsCog (all operator commands with role checks and async threading)
- [x] 04-03-PLAN.md -- AlertsCog (callback wiring, buffer, reconnect flush) + placeholder Cogs
- [x] 04-04-PLAN.md -- Bot startup wiring (on_ready init, monitor background task, vco bot CLI)

### Phase 5: Hooks and Plan Gate
**Goal**: Agents can ask questions that route through Discord for answers, and new plans are gated for review before execution proceeds
**Depends on**: Phase 4
**Requirements**: HOOK-01, HOOK-02, HOOK-03, HOOK-04, HOOK-05, HOOK-06, HOOK-07, GATE-01, GATE-02, GATE-03, GATE-04, SAFE-01, SAFE-02
**Success Criteria** (what must be TRUE):
  1. When an agent triggers AskUserQuestion, the question appears in #strategist with agent ID and options, and the answer is returned to the agent session
  2. If no one answers within 10 minutes, the hook falls back to the recommended option, notes the assumption, and alerts #alerts
  3. The hook never hangs regardless of failures (wrapped in try/except with guaranteed fallback)
  4. When the monitor detects a completed PLAN.md, the agent is paused and the plan is posted to #plan-review for approval or rejection
  5. A plan checker validates that plans include interaction safety tables analyzing concurrent scenarios
**Plans**: 4 plans
Plans:
- [x] 05-01-PLAN.md -- Self-contained ask_discord.py hook (AskUserQuestion interception, webhook posting, file-based answer polling)
- [x] 05-02-PLAN.md -- Plan gate state model, safety table validator, GSD config auto_advance disable
- [x] 05-03-PLAN.md -- PlanReviewCog expansion (views, embeds, approve/reject workflow, execution trigger)
- [ ] 05-04-PLAN.md -- QuestionHandlerCog (answer delivery) + bot startup wiring for plan gate callback

### Phase 6: PM/Strategist and Milestones
**Goal**: A two-tier AI decision system where the PM handles tactical questions/plan reviews with heuristic confidence, and the Strategist maintains a persistent conversation for strategic decisions and owner interaction
**Depends on**: Phase 5
**Requirements**: STRAT-01, STRAT-02, STRAT-03, STRAT-04, STRAT-05, STRAT-06, STRAT-07, STRAT-08, STRAT-09, MILE-01, MILE-02, MILE-03
**Success Criteria** (what must be TRUE):
  1. The Strategist answers agent questions using project context, with HIGH confidence answers delivered directly and LOW confidence answers escalated to @Owner
  2. The Strategist reviews plans against milestone scope and rejects off-scope, duplicate, or over-scoped plans
  3. The Strategist checks plans against PROJECT-STATUS.md and requires stubs/mocks when dependencies have not shipped
  4. All PM decisions are logged to the #decisions channel as an append-only record
  5. Running `vco new-milestone` updates milestone scope, resets agent states, and re-dispatches agents for the new milestone
**Plans**: 5 plans
Plans:
- [x] 06-01-PLAN.md -- PM data models, heuristic confidence scorer, PM-CONTEXT.md builder
- [x] 06-02-PLAN.md -- Strategist persistent conversation manager + Knowledge Transfer handoff
- [x] 06-03-PLAN.md -- PM tier (question evaluation + plan reviewer with three-check system)
- [x] 06-04-PLAN.md -- StrategistCog expansion + decision logging to #decisions
- [ ] 06-05-PLAN.md -- Wiring (PM intercepts, bot startup, status digests, milestone CLI, sync-context update)

### Phase 7: Integration Pipeline and Communications
**Goal**: Agent branches merge cleanly with automated testing and failure attribution, and agents communicate progress through structured standup and checkin rituals
**Depends on**: Phase 6
**Requirements**: INTG-01, INTG-02, INTG-03, INTG-04, INTG-05, INTG-06, INTG-07, INTG-08, COMM-01, COMM-02, COMM-03, COMM-04, COMM-05, COMM-06, SAFE-04
**Success Criteria** (what must be TRUE):
  1. Running `vco integrate` merges all agent branches into an integration branch, runs the test suite, and attributes failures to specific agent branches
  2. On test success, a PR to main is automatically created; on failure, a fix is dispatched to the responsible agent
  3. Merge conflicts are detected and reported to Discord with file details, and small conflicts are attempted automatically before escalating
  4. Running /vco:checkin posts phase completion status to the agent's #agent-{id} channel with commit count, summary, gaps, and next phase
  5. Running /vco:standup triggers a group standup in #standup with per-agent threads where the owner can reprioritize or ask questions
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation and Configuration | 0/4 | Planning complete | - |
| 2. Agent Lifecycle and Pre-flight | 0/3 | Planning complete | - |
| 3. Monitor Loop and Coordination | 0/4 | Planning complete | - |
| 4. Discord Bot Core | 0/4 | Planning complete | - |
| 5. Hooks and Plan Gate | 3/4 | In Progress|  |
| 6. PM/Strategist and Milestones | 2/5 | In Progress|  |
| 7. Integration Pipeline and Communications | 0/TBD | Not started | - |
