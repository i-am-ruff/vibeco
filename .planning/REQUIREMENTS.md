# Requirements: vCompany

**Defined:** 2026-03-25
**Core Value:** Agents run autonomously without hanging, stay coordinated through contracts and status awareness, and produce integrated code — all operable from Discord.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Foundation

- [x] **FOUND-01**: System uses Pydantic models to parse and validate agents.yaml (agent roster, owned dirs, shared_readonly, gsd_mode, system prompts)
- [x] **FOUND-02**: `vco init` creates project directory structure (clones/, context/, agents/) from agents.yaml
- [x] **FOUND-03**: `vco clone` creates one repo clone per agent, copies context files, deploys hooks + GSD config + vco commands
- [x] **FOUND-04**: Git operations wrapper standardizes subprocess calls with error handling and logging
- [x] **FOUND-05**: tmux wrapper abstracts libtmux behind stable interface (create_pane, send_command, is_alive, get_output)
- [x] **FOUND-06**: All coordination file writes use atomic pattern (write to .tmp, then os.rename)
- [x] **FOUND-07**: Project uses uv for package management with pyproject.toml

### Agent Lifecycle

- [x] **LIFE-01**: `vco dispatch` launches Claude Code sessions in tmux panes with `--dangerously-skip-permissions` and `--append-system-prompt`
- [x] **LIFE-02**: `vco dispatch all` creates tmux session with one pane per agent plus monitor pane
- [x] **LIFE-03**: `vco kill` terminates a specific agent session (graceful signal then forced kill)
- [x] **LIFE-04**: `vco relaunch` restarts an agent with `/gsd:resume-work` to continue from last phase
- [x] **LIFE-05**: Crash recovery auto-relaunches failed agents with exponential backoff (30s, 2min, 10min)
- [x] **LIFE-06**: Circuit breaker stops relaunch after 3 crashes/hour and alerts via Discord
- [x] **LIFE-07**: Crash classification distinguishes transient failures (context exhaustion, API timeout) from persistent failures (corrupt git state, bad clone) before retrying

### Monitor Loop

- [x] **MON-01**: Monitor loop runs every 60s per agent with independent try/except per check
- [x] **MON-02**: Liveness check verifies tmux pane alive AND actual process PID inside pane (not just session existence)
- [x] **MON-03**: Stuck detection alerts when an agent has no git commits for 30+ minutes
- [x] **MON-04**: Monitor detects new PLAN.md files and triggers plan gate flow
- [x] **MON-05**: Monitor reads each clone's .planning/ROADMAP.md and git log to track phase progress
- [x] **MON-06**: Monitor generates PROJECT-STATUS.md from all clones' state every cycle
- [x] **MON-07**: Monitor distributes PROJECT-STATUS.md to all agent clones after generation
- [x] **MON-08**: Monitor runs under a watchdog (heartbeat file or systemd) to detect if monitor itself dies

### Discord Bot

- [x] **DISC-01**: Discord bot uses discord.py Cogs architecture (Commands, Strategist, PlanReview, Alerts)
- [x] **DISC-02**: Bot creates channel structure on project init (#strategist, #plan-review, #standup, #agent-{id}, #alerts, #decisions)
- [x] **DISC-03**: `!new-project` command accepts project config and triggers `vco init` + `vco clone`
- [x] **DISC-04**: `!dispatch` command triggers `vco dispatch` for specific agent or all
- [x] **DISC-05**: `!status` command shows aggregate view of all agents (phase, state, blockers)
- [x] **DISC-06**: `!standup` command triggers interactive group standup with threaded feedback
- [x] **DISC-07**: `!kill` command terminates a specific agent
- [x] **DISC-08**: `!relaunch` command restarts a specific agent
- [x] **DISC-09**: `!integrate` command triggers merge pipeline
- [x] **DISC-10**: Role-based access control — Discord roles determine who can dispatch, kill, approve, etc.
- [x] **DISC-11**: All blocking calls use asyncio.to_thread() to prevent gateway disconnects
- [x] **DISC-12**: Bot monitors its own connectivity and reconnects automatically

### Hooks and Plan Gate

- [x] **HOOK-01**: ask_discord.py intercepts AskUserQuestion tool calls via PreToolUse hook
- [x] **HOOK-02**: Hook posts formatted question with agent ID and options to #strategist channel
- [x] **HOOK-03**: Hook polls for reply every 5s with 10-minute timeout
- [x] **HOOK-04**: On timeout, hook falls back to recommended/first option, notes assumption, alerts #alerts
- [x] **HOOK-05**: Hook returns deny + permissionDecisionReason carrying the answer back to Claude
- [x] **HOOK-06**: Hook is self-contained (no imports from main codebase) — runs in agent clone context
- [x] **HOOK-07**: Hook wrapped in try/except with guaranteed fallback response (never hangs)
- [x] **GATE-01**: Plan gate detects PLAN.md completion (atomic write marker, not creation event)
- [x] **GATE-02**: Plan gate posts plans to #plan-review with agent ID, plan descriptions, task counts
- [x] **GATE-03**: Plan gate pauses agent execution until PM/owner approves or rejects
- [x] **GATE-04**: On rejection, agent receives feedback and re-plans

### PM/Strategist Bot

- [ ] **STRAT-01**: Strategist loads project context (blueprint, interfaces, milestone scope, status, prior decisions) into system prompt
- [ ] **STRAT-02**: Strategist answers agent questions using project context with confidence scoring
- [ ] **STRAT-03**: HIGH confidence (>90%) answers directly
- [ ] **STRAT-04**: MEDIUM confidence (70-90%) answers with "PM confidence: medium — @Owner can override"
- [ ] **STRAT-05**: LOW confidence (<70%) tags @Owner and waits for human input
- [ ] **STRAT-06**: Strategist reviews plans against milestone scope — rejects off-scope, duplicate, or over-scoped plans
- [ ] **STRAT-07**: Strategist checks plans against PROJECT-STATUS.md — requires stubs/mocks when dependencies aren't shipped
- [ ] **STRAT-08**: Context management summarizes older decisions and status when approaching context limits
- [ ] **STRAT-09**: Decision log — all PM decisions posted to #decisions channel (append-only)

### Coordination and Contracts

- [x] **COORD-01**: INTERFACES.md is the single source of truth for API contracts, shared types, and integration boundaries
- [x] **COORD-02**: Interface change request flow: agent asks via AskUserQuestion → PM approves → orchestrator distributes updated INTERFACES.md
- [x] **COORD-03**: `vco sync-context` pushes updated INTERFACES.md, MILESTONE-SCOPE.md, and STRATEGIST-PROMPT.md to all clones
- [x] **COORD-04**: Agent system prompt template generates --append-system-prompt with owned dirs, rules, milestone scope
- [x] **COORD-05**: CLAUDE.md generated per clone with cross-agent awareness rules and communication instructions
- [x] **COORD-06**: /vco:checkin.md and /vco:standup.md command files deployed to each clone's .claude/commands/vco/
- [x] **COORD-07**: .claude/settings.json with AskUserQuestion hook config deployed to each clone

### Integration Pipeline

- [ ] **INTG-01**: Each agent commits to its own branch (branch-per-agent)
- [ ] **INTG-02**: `vco integrate` creates integration branch from main, merges all agent branches
- [ ] **INTG-03**: Integration runs full test suite after merge
- [ ] **INTG-04**: Test failures attributed to specific agent branches
- [ ] **INTG-05**: On test failure, orchestrator dispatches /gsd:quick fix to responsible agent
- [ ] **INTG-06**: On success, creates PR to main
- [ ] **INTG-07**: Merge conflict detection reports conflicts to Discord with file list and details
- [ ] **INTG-08**: Conflict resolver agent attempts automatic resolution of small conflicts before escalating

### Standup and Checkin

- [ ] **COMM-01**: /vco:checkin posts phase completion status to agent's own #agent-{id} channel
- [ ] **COMM-02**: Checkin includes: commits count, summary, gaps/notes, next phase, dependency status
- [ ] **COMM-03**: /vco:standup posts structured status to #standup, creates thread per agent
- [ ] **COMM-04**: Standup sessions listen for owner replies in threads (poll every 5s, 5-min timeout)
- [ ] **COMM-05**: Owner can reprioritize agents, change scope, or ask questions via standup threads
- [ ] **COMM-06**: Agent updates ROADMAP.md or STATE.md based on owner feedback during standup

### Milestone Management

- [ ] **MILE-01**: `vco new-milestone` updates milestone scope, resets agent states, re-dispatches
- [ ] **MILE-02**: Three input documents define a project: PROJECT-BLUEPRINT.md, INTERFACES.md, MILESTONE-SCOPE.md
- [ ] **MILE-03**: STRATEGIST-PROMPT.md generated from blueprint + interfaces + scope + status + decisions

### Pre-flight

- [x] **PRE-01**: Pre-flight test suite validates Claude Code headless behavior before first project
- [x] **PRE-02**: Tests cover: stream-json heartbeat, permission hang behavior, --max-turns exit, --resume recovery
- [x] **PRE-03**: Results determine monitor strategy (stream-json liveness vs git-commit fallback)

### Interaction Safety

- [x] **SAFE-01**: Every phase plan includes an Interaction Safety Table analyzing concurrent scenarios (Agent/Component × Circumstance × Action × Concurrent With × Safe? × Mitigation)
- [x] **SAFE-02**: Plan checker agent validates interaction safety table completeness — rejects plans missing concurrency analysis
- [x] **SAFE-03**: Known interaction patterns documented in a central INTERACTIONS.md reference (e.g., monitor reads during agent writes, simultaneous git pushes, hook timeout during context compression)
- [ ] **SAFE-04**: Integration phase includes interaction regression tests for critical concurrent scenarios identified across all phases

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Scalability

- **SCALE-01**: Multi-machine distributed agents (SSH-based dispatch)
- **SCALE-02**: Multi-project concurrent orchestration
- **SCALE-03**: Dynamic agent spawning based on workload
- **SCALE-04**: Discord rate limit queuing and backoff

### Analytics

- **ANLYT-01**: Agent performance metrics (phase duration, commit velocity, crash rate)
- **ANLYT-02**: Cost tracking per agent (API tokens consumed)
- **ANLYT-03**: Milestone progress forecasting

### Recovery

- **RECV-01**: Sophisticated crash analysis (root cause, not just category)
- **RECV-02**: Automatic merge conflict resolution for complex conflicts
- **RECV-03**: Clone disk space optimization (shallow clones, shared objects)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web UI / dashboard | Discord is the interface — investing in rich embeds/threads, not a parallel UI |
| Mobile app | Discord mobile covers this use case |
| Product-specific logic | vCompany is project-agnostic — products are inputs, not features |
| Agent-to-agent direct messaging | Creates tight coupling and echo chambers — coordinate through shared artifacts instead |
| Full autonomy mode (no plan gate) | Plan gates prevent hours of wasted work — speed comes from smarter PM, not removed oversight |
| Fine-grained task assignment by orchestrator | GSD handles task decomposition within agent domains — orchestrator coordinates, not micromanages |
| CI/CD pipeline integration | Agents build and test locally for v1 |
| Database | All state is filesystem-based — correct for single-machine orchestrator |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | Phase 1 | Complete |
| FOUND-02 | Phase 1 | Complete |
| FOUND-03 | Phase 1 | Complete |
| FOUND-04 | Phase 1 | Complete |
| FOUND-05 | Phase 1 | Complete |
| FOUND-06 | Phase 1 | Complete |
| FOUND-07 | Phase 1 | Complete |
| COORD-04 | Phase 1 | Complete |
| COORD-05 | Phase 1 | Complete |
| COORD-06 | Phase 1 | Complete |
| COORD-07 | Phase 1 | Complete |
| LIFE-01 | Phase 2 | Complete |
| LIFE-02 | Phase 2 | Complete |
| LIFE-03 | Phase 2 | Complete |
| LIFE-04 | Phase 2 | Complete |
| LIFE-05 | Phase 2 | Complete |
| LIFE-06 | Phase 2 | Complete |
| LIFE-07 | Phase 2 | Complete |
| PRE-01 | Phase 2 | Complete |
| PRE-02 | Phase 2 | Complete |
| PRE-03 | Phase 2 | Complete |
| MON-01 | Phase 3 | Complete |
| MON-02 | Phase 3 | Complete |
| MON-03 | Phase 3 | Complete |
| MON-04 | Phase 3 | Complete |
| MON-05 | Phase 3 | Complete |
| MON-06 | Phase 3 | Complete |
| MON-07 | Phase 3 | Complete |
| MON-08 | Phase 3 | Complete |
| COORD-01 | Phase 3 | Complete |
| COORD-02 | Phase 3 | Complete |
| COORD-03 | Phase 3 | Complete |
| SAFE-03 | Phase 3 | Complete |
| DISC-01 | Phase 4 | Complete |
| DISC-02 | Phase 4 | Complete |
| DISC-03 | Phase 4 | Complete |
| DISC-04 | Phase 4 | Complete |
| DISC-05 | Phase 4 | Complete |
| DISC-06 | Phase 4 | Complete |
| DISC-07 | Phase 4 | Complete |
| DISC-08 | Phase 4 | Complete |
| DISC-09 | Phase 4 | Complete |
| DISC-10 | Phase 4 | Complete |
| DISC-11 | Phase 4 | Complete |
| DISC-12 | Phase 4 | Complete |
| HOOK-01 | Phase 5 | Complete |
| HOOK-02 | Phase 5 | Complete |
| HOOK-03 | Phase 5 | Complete |
| HOOK-04 | Phase 5 | Complete |
| HOOK-05 | Phase 5 | Complete |
| HOOK-06 | Phase 5 | Complete |
| HOOK-07 | Phase 5 | Complete |
| GATE-01 | Phase 5 | Complete |
| GATE-02 | Phase 5 | Complete |
| GATE-03 | Phase 5 | Complete |
| GATE-04 | Phase 5 | Complete |
| SAFE-01 | Phase 5 | Complete |
| SAFE-02 | Phase 5 | Complete |
| STRAT-01 | Phase 6 | Pending |
| STRAT-02 | Phase 6 | Pending |
| STRAT-03 | Phase 6 | Pending |
| STRAT-04 | Phase 6 | Pending |
| STRAT-05 | Phase 6 | Pending |
| STRAT-06 | Phase 6 | Pending |
| STRAT-07 | Phase 6 | Pending |
| STRAT-08 | Phase 6 | Pending |
| STRAT-09 | Phase 6 | Pending |
| MILE-01 | Phase 6 | Pending |
| MILE-02 | Phase 6 | Pending |
| MILE-03 | Phase 6 | Pending |
| INTG-01 | Phase 7 | Pending |
| INTG-02 | Phase 7 | Pending |
| INTG-03 | Phase 7 | Pending |
| INTG-04 | Phase 7 | Pending |
| INTG-05 | Phase 7 | Pending |
| INTG-06 | Phase 7 | Pending |
| INTG-07 | Phase 7 | Pending |
| INTG-08 | Phase 7 | Pending |
| COMM-01 | Phase 7 | Pending |
| COMM-02 | Phase 7 | Pending |
| COMM-03 | Phase 7 | Pending |
| COMM-04 | Phase 7 | Pending |
| COMM-05 | Phase 7 | Pending |
| COMM-06 | Phase 7 | Pending |
| SAFE-04 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 85 total
- Mapped to phases: 85
- Unmapped: 0

---
*Requirements defined: 2026-03-25*
*Last updated: 2026-03-25 after roadmap creation*
