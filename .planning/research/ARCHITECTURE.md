# Architecture Research

**Domain:** Autonomous multi-agent CLI orchestration system (AI development agents coordinated via process management, filesystem, and Discord)
**Researched:** 2026-03-25
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
+-----------------------------------------------------------------------+
|                         Human Layer                                    |
|   Owner (Discord) --> strategic direction, escalation responses        |
+----------------------------------+------------------------------------+
                                   |
+----------------------------------v------------------------------------+
|                       Discord Layer                                    |
|  +------------------+   +----------+  +----------+  +----------+      |
|  | PM/Strategist    |   | #plan-   |  | #standup |  | #alerts  |      |
|  | Bot (discord.py) |   | review   |  |          |  |          |      |
|  +--------+---------+   +----------+  +----------+  +----------+      |
|           |                                                            |
+-----------|------------------------------------------------------------+
            |
+-----------v------------------------------------------------------------+
|                     Orchestration Layer                                 |
|  +-------------+    +----------------+    +------------------+         |
|  | vco CLI     |    | Monitor Loop   |    | Plan Gate        |         |
|  | (click)     |    | (daemon thread)|    | (approval FSM)   |         |
|  +------+------+    +-------+--------+    +--------+---------+         |
|         |                   |                      |                   |
+---------+-------------------+----------------------+-------------------+
          |                   |                      |
+---------v-------------------v----------------------v-------------------+
|                       Agent Layer                                      |
|  +----------------+  +----------------+  +----------------+            |
|  | tmux pane 1    |  | tmux pane 2    |  | tmux pane N    |            |
|  | Agent clone 1  |  | Agent clone 2  |  | Agent clone N  |            |
|  | Claude Code    |  | Claude Code    |  | Claude Code    |            |
|  | + GSD pipeline |  | + GSD pipeline |  | + GSD pipeline |            |
|  +-------+--------+  +-------+--------+  +-------+--------+            |
|          |                    |                    |                    |
+----------.--------------------.--------------------.-------------------+
           |                    |                    |
+----------v--------------------v--------------------v-------------------+
|                    Integration Layer                                    |
|  +------------------+    +------------------+    +------------------+  |
|  | Branch merger     |    | Test runner      |    | PR creator       |  |
|  | (git operations) |    | (project tests)  |    | (gh CLI)         |  |
|  +------------------+    +------------------+    +------------------+  |
+------------------------------------------------------------------------+
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| **vco CLI** | Project init, agent dispatch, integration trigger, standup spawn, context sync | Python click app, single entry point |
| **Monitor Loop** | Liveness checks, stuck detection, plan gate trigger, PROJECT-STATUS.md regen, crash recovery | Python asyncio loop or threaded timer, 60s cycle |
| **PM/Strategist Bot** | Answer agent questions, review plans, escalate to owner, log decisions | discord.py Bot with Cogs, Anthropic SDK for LLM calls |
| **AskUserQuestion Hook** | Intercept agent questions, route to Discord, return answers, timeout fallback | Python script invoked by Claude Code hook system (stdin/stdout JSON) |
| **Plan Gate** | Detect new PLAN.md files, pause agent, post for review, wait for approval | Filesystem watcher in monitor loop + approval state machine |
| **Agent Sessions** | Run GSD pipeline autonomously in isolated clones | Claude Code processes in tmux panes, managed by libtmux |
| **Integration Pipeline** | Merge branches, run tests, create PR, dispatch fixes | Git operations + subprocess for test runner + gh CLI |
| **Context Distribution** | Keep PROJECT-STATUS.md, INTERFACES.md current across all clones | File copy from central context/ dir to each clone |

## Recommended Project Structure

```
vcompany/
├── src/
│   ├── cli/                    # vco CLI commands
│   │   ├── __init__.py
│   │   ├── main.py             # click group entry point
│   │   ├── init_cmd.py         # vco init
│   │   ├── clone_cmd.py        # vco clone
│   │   ├── dispatch_cmd.py     # vco dispatch
│   │   ├── monitor_cmd.py      # vco monitor
│   │   ├── integrate_cmd.py    # vco integrate
│   │   ├── standup_cmd.py      # vco standup
│   │   ├── status_cmd.py       # vco status
│   │   ├── kill_cmd.py         # vco kill
│   │   ├── relaunch_cmd.py     # vco relaunch
│   │   └── sync_context_cmd.py # vco sync-context
│   ├── bot/                    # Discord bot
│   │   ├── __init__.py
│   │   ├── bot.py              # Bot setup, startup, cog loading
│   │   ├── cogs/
│   │   │   ├── __init__.py
│   │   │   ├── commands.py     # !dispatch, !status, !kill, etc.
│   │   │   ├── strategist.py   # Question answering, confidence scoring
│   │   │   ├── plan_review.py  # Plan approval/rejection flow
│   │   │   └── alerts.py       # Alert routing and formatting
│   │   └── views/              # Discord UI components (buttons, modals)
│   │       └── approval.py     # Plan approval buttons
│   ├── orchestrator/           # Core orchestration logic (no CLI/Discord deps)
│   │   ├── __init__.py
│   │   ├── agent_manager.py    # Agent lifecycle: spawn, kill, relaunch
│   │   ├── monitor.py          # Monitor loop logic
│   │   ├── plan_gate.py        # Plan detection and approval FSM
│   │   ├── integrator.py       # Branch merge + test pipeline
│   │   ├── status_generator.py # PROJECT-STATUS.md generation
│   │   ├── context_sync.py     # Distribute context files to clones
│   │   └── crash_tracker.py    # Crash counting + recovery policy
│   ├── hooks/                  # Claude Code hook scripts
│   │   ├── ask_discord.py      # AskUserQuestion interceptor
│   │   └── templates/          # Hook config templates
│   │       └── settings.json   # .claude/settings.json template
│   ├── tmux/                   # tmux session management
│   │   ├── __init__.py
│   │   ├── session.py          # Create/destroy sessions and panes
│   │   └── liveness.py         # Pane alive checks, output capture
│   ├── models/                 # Data models and config parsing
│   │   ├── __init__.py
│   │   ├── agents_config.py    # agents.yaml parsing + validation
│   │   ├── project.py          # Project state model
│   │   └── agent_state.py      # Per-agent state tracking
│   └── shared/                 # Cross-cutting utilities
│       ├── __init__.py
│       ├── discord_client.py   # Webhook posting, message polling
│       ├── git_ops.py          # Git clone, branch, merge operations
│       ├── file_ops.py         # File copy, symlink, path resolution
│       └── logging.py          # Structured logging
├── commands/                   # Claude Code command templates deployed to clones
│   └── vco/
│       ├── checkin.md
│       └── standup.md
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── pyproject.toml
└── README.md
```

### Structure Rationale

- **src/cli/:** One file per CLI command keeps each command isolated and testable. The click group in main.py composes them. This avoids a monolithic vco.py file.
- **src/bot/cogs/:** discord.py's Cog pattern is the standard modular approach. Each Cog owns one domain of bot behavior (commands, strategist logic, plan review). Cogs can be loaded/unloaded independently.
- **src/orchestrator/:** Pure Python logic with no framework dependencies. The CLI and bot both call into this layer. This separation means orchestration logic is testable without spinning up Discord or click.
- **src/hooks/:** Standalone scripts that Claude Code invokes via its hook system. These read stdin JSON and write stdout JSON. They must be self-contained (no imports from src/) because they run in the agent clone's context, not the vcompany project.
- **src/tmux/:** Thin wrapper around libtmux. Isolating tmux operations makes it possible to mock them in tests and swap implementations if needed.
- **src/models/:** Pydantic or dataclass models for agents.yaml parsing, project state, and agent state. Centralizing models prevents scattered dict-access patterns.

## Architectural Patterns

### Pattern 1: Supervisor Process Pattern (Monitor Loop)

**What:** A long-running supervisor process periodically checks the health and state of all managed child processes (agents), takes corrective action on failures, and reports status upward.

**When to use:** Whenever you manage multiple autonomous processes that can crash, hang, or need coordination.

**Trade-offs:** Simple to implement and reason about. Polling introduces latency (up to one cycle delay). Acceptable here because 60s granularity is fine for agent supervision. Avoid event-driven alternatives (inotify, fswatch) for the core loop -- they add complexity without meaningful benefit at this timescale.

**Example:**
```python
import asyncio
from datetime import datetime, timedelta

class MonitorLoop:
    def __init__(self, project, interval=60):
        self.project = project
        self.interval = interval
        self.crash_counts: dict[str, list[datetime]] = {}

    async def run(self):
        while True:
            for agent in self.project.agents:
                await self._check_liveness(agent)
                await self._check_stuck(agent)
                await self._check_plan_gate(agent)
            await self._regenerate_status()
            await self._distribute_status()
            await asyncio.sleep(self.interval)

    async def _check_liveness(self, agent):
        if not agent.tmux_pane.is_alive():
            recent = self._recent_crashes(agent.id)
            if recent < 3:
                await self._relaunch(agent)
                self._record_crash(agent.id)
            else:
                await self._alert(f"{agent.id} crashed 4 times in 1 hour. Stopped.")

    def _recent_crashes(self, agent_id: str) -> int:
        cutoff = datetime.now() - timedelta(hours=1)
        self.crash_counts.setdefault(agent_id, [])
        self.crash_counts[agent_id] = [
            t for t in self.crash_counts[agent_id] if t > cutoff
        ]
        return len(self.crash_counts[agent_id])
```

### Pattern 2: Filesystem-as-IPC (Coordination via Files)

**What:** Processes coordinate by reading and writing well-known files rather than through sockets, queues, or shared memory. Detection happens via polling (check file mtime/existence) or filesystem watchers.

**When to use:** When coordinating processes that cannot share memory (separate Claude Code sessions), when state must survive process crashes, and when human-readable state is valuable for debugging.

**Trade-offs:** Simple, crash-resilient (files persist), debuggable (just read the file). Slower than sockets/queues. Race conditions possible without file locking. For this system, races are unlikely because: (a) only the monitor writes PROJECT-STATUS.md, (b) only agents write PLAN.md in their own clones, (c) directory ownership prevents cross-agent file conflicts.

**Key files as coordination primitives:**
- `PROJECT-STATUS.md` -- monitor writes, all agents read (one writer, many readers = no lock needed)
- `.planning/ROADMAP.md` -- agent writes, monitor reads (one writer, one reader per clone = no lock needed)
- `PLAN.md` files -- agent writes, monitor detects via mtime/existence check
- `INTERFACES.md` -- orchestrator writes (via sync-context), agents read-only

**When to use file locking:** Only if two processes legitimately write the same file. In this architecture, the ownership model prevents that. Use `filelock` (Python library) only for the crash tracker state file if the monitor and CLI both update it.

### Pattern 3: Hook-Based Message Passing (AskUserQuestion)

**What:** Claude Code's hook system allows intercepting tool calls via PreToolUse hooks. A script receives the tool call as stdin JSON, does external work (Discord API call, wait for response), and returns a JSON response that either allows, denies, or modifies the tool call.

**When to use:** When Claude Code agents need to communicate with external systems without hanging on terminal input.

**Trade-offs:** Elegant -- agents don't know they're talking to Discord, they just use AskUserQuestion normally. But the hook script must be self-contained (no shared imports from the main codebase) and must handle timeouts gracefully. The 10-minute timeout with fallback-to-first-option is the correct pattern; infinite waits risk orphaned sessions.

**Critical implementation detail:** The hook script runs in the agent clone's working directory, not the vcompany directory. It needs either absolute paths to shared config or environment variables for Discord webhook URLs and channel IDs.

### Pattern 4: Cog-Based Discord Bot Architecture

**What:** discord.py's Cog pattern organizes bot functionality into modular classes. Each Cog groups related commands, event listeners, and state. Cogs are loaded/unloaded at runtime.

**When to use:** Any discord.py bot with more than a handful of commands. Standard practice.

**Trade-offs:** Clean separation of concerns. Each Cog is independently testable. Hot-reloading Cogs during development is possible. Minor overhead of the Cog registration API.

**Cog boundaries for this system:**
- **CommandsCog:** Owner-facing commands (!dispatch, !status, !kill, !relaunch, !integrate, !standup)
- **StrategistCog:** Listens in #strategist for agent questions, calls Anthropic API, posts answers with confidence scoring
- **PlanReviewCog:** Listens in #plan-review for plan posts, manages approval buttons/reactions, posts approval/rejection
- **AlertsCog:** Receives alert webhooks from monitor, formats and routes to #alerts

### Pattern 5: tmux as Process Container

**What:** Use tmux sessions and panes as lightweight process containers for Claude Code agent sessions. libtmux provides a Python API for creating, monitoring, and killing panes.

**When to use:** When you need to run multiple long-lived interactive processes on a single machine with visibility into their output.

**Trade-offs:** tmux is ubiquitous on Linux, provides built-in output scrollback, and the owner can attach to any pane to see real-time agent output. libtmux is well-maintained. The alternative (raw subprocess.Popen) loses visibility and makes liveness checking harder. Docker containers would be overkill for single-machine operation.

**Session layout:**
```
vco-{project} (tmux session)
  +-- window: agents
  |     +-- pane 0: Agent BACKEND
  |     +-- pane 1: Agent FRONTEND
  |     +-- pane 2: Agent MOBILE
  |     +-- pane N: Agent N
  +-- window: monitor
        +-- pane 0: vco monitor loop
```

Using separate windows (not just panes) for monitor vs agents prevents accidental pane kills from affecting the monitor.

## Data Flow

### Agent Dispatch Flow

```
Owner (!dispatch or vco dispatch)
    |
    v
vco CLI (dispatch_cmd.py)
    |
    +--> Read agents.yaml for agent roster
    |
    +--> For each agent:
    |       |
    |       +--> Verify clone exists (or run clone first)
    |       +--> Inject: system prompt, CLAUDE.md, .claude/settings.json,
    |       |    .claude/commands/vco/*, .planning/config.json,
    |       |    PROJECT-STATUS.md, INTERFACES.md
    |       |
    |       +--> libtmux: create pane in vco-{project} session
    |       +--> Send keys: cd {clone_dir} && claude --dangerously-skip-permissions
    |              --append-system-prompt {agent_prompt} -p "/gsd:new-project"
    |
    v
Monitor loop starts (or already running)
```

### Agent Question Flow

```
Claude Code Agent (GSD discuss phase)
    |
    +--> AskUserQuestion tool call
    |
    v
PreToolUse hook fires --> ask_discord.py (stdin: JSON)
    |
    +--> Format question with agent ID + options
    +--> POST to Discord #strategist via webhook
    +--> Poll for reply (every 5s, max 10min)
    |
    v
PM/Strategist Bot (StrategistCog)
    |
    +--> Receives message in #strategist
    +--> Builds prompt: blueprint + interfaces + status + question
    +--> Calls Anthropic API
    +--> Assesses confidence (HIGH/MEDIUM/LOW)
    |
    +-- HIGH/MEDIUM --> Posts answer to #strategist
    +-- LOW --> Tags @Owner, waits for human answer
    |
    v
ask_discord.py detects reply
    |
    +--> Returns JSON: {permissionDecision: "deny",
    |    permissionDecisionReason: "PM answered: ..."}
    |
    v
Claude Code receives answer, continues GSD pipeline
```

### Monitor Cycle Flow

```
Every 60 seconds:
    |
    +--> For each agent pane:
    |       |
    |       +--> libtmux: check pane alive
    |       |       +-- dead --> crash_tracker: count recent crashes
    |       |                    +-- <3/hr --> relaunch with /gsd:resume-work
    |       |                    +-- >=3/hr --> alert #alerts, stop
    |       |
    |       +--> git -C {clone} log --oneline -1 --since="30 min ago"
    |       |       +-- no output --> alert "stuck" to #alerts
    |       |
    |       +--> Check .planning/ for new PLAN.md files (mtime > last check)
    |       |       +-- found --> trigger plan gate:
    |       |                     post to #plan-review, set agent state to "gated"
    |       |
    |       +--> Read .planning/ROADMAP.md for phase status
    |
    +--> Regenerate PROJECT-STATUS.md from all agents' ROADMAP.md + git log
    +--> Copy PROJECT-STATUS.md to all agent clones
    +--> Update dashboard / status output
```

### Integration Flow

```
All agents complete (detected by monitor or manual trigger)
    |
    v
vco integrate
    |
    +--> Create integration branch from main
    +--> For each agent (ordered by dependency):
    |       +--> git merge {agent-branch} --no-edit
    |       +--> If conflict:
    |               +--> Log conflicting files
    |               +--> Attempt auto-resolution (theirs for non-overlapping dirs)
    |               +--> If unresolvable: alert, pause for manual resolution
    |
    +--> Run full test suite (project-specific test command from agents.yaml)
    |       +-- pass --> gh pr create to main
    |       +-- fail --> Parse test output, identify responsible agent
    |                    Dispatch /gsd:quick fix to that agent's clone
    |                    Re-run integration after fix
    |
    v
PR created, owner reviews and merges
```

### State Management

```
Persistent State (survives crashes):
    agents.yaml          --> Agent roster (human-edited, rarely changes)
    PROJECT-STATUS.md    --> Cross-agent awareness (monitor regenerates every cycle)
    INTERFACES.md        --> Contracts (PM/owner edits, orchestrator distributes)
    ROADMAP.md           --> Per-agent progress (agent writes in its clone)
    .planning/STATE.md   --> Per-agent decisions/blockers (agent writes)
    crash_state.json     --> Crash counts per agent (monitor writes, needs filelock)

Ephemeral State (in-memory, rebuilt on restart):
    Monitor loop state   --> Rebuilt by reading filesystem on startup
    tmux pane handles    --> Rediscovered by session/pane name convention
    Plan gate state      --> Rebuilt from PLAN.md mtimes + approval markers
```

**Key design principle:** All critical state lives on the filesystem. If the monitor crashes and restarts, it re-reads the filesystem and resumes. No database needed. No message queue needed.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-3 agents | Single tmux session, single window with panes. Monitor loop is simple. No performance concerns. |
| 4-8 agents | Multiple tmux windows (group by role). Monitor loop still fine at 60s. Discord rate limits may surface -- batch webhook calls. |
| 9+ agents | Split into multiple tmux sessions. Consider staggering monitor checks (not all agents in same cycle). Discord rate limits become real -- implement webhook queue with backoff. |

### Scaling Priorities

1. **First bottleneck: Discord rate limits.** Discord webhooks are limited to 30 requests per minute per channel. With 8+ agents posting questions, checkins, and standups, you will hit this. **Mitigation:** Queue webhook calls with rate limit awareness. Batch status updates. Use fewer channels (one shared agent channel instead of per-agent channels) if needed.

2. **Second bottleneck: Machine resources.** Each Claude Code session consumes memory and CPU. On a typical dev machine, 4-6 simultaneous Claude Code sessions is practical. Beyond that, response times degrade. **Mitigation:** Stagger agent dispatch (not all at once), use `--max-turns` to limit runaway sessions, monitor system resources.

3. **Third bottleneck: Context distribution.** Copying PROJECT-STATUS.md to N clones every 60 seconds is fine for small N. At 10+ clones, consider symlinks to a single file (but beware of agent tooling that may not follow symlinks correctly).

## Anti-Patterns

### Anti-Pattern 1: Shared Working Directory

**What people do:** Multiple agents work in the same repo clone to "save disk space."
**Why it's wrong:** Git operations conflict (simultaneous commits, branch switches). File writes collide. Claude Code sessions interfere with each other. Debugging becomes impossible.
**Do this instead:** One clone per agent. Disk space is cheap. Isolation is not.

### Anti-Pattern 2: Database for Coordination State

**What people do:** Set up SQLite/Postgres to track agent state, plan approvals, crash counts.
**Why it's wrong:** Adds infrastructure dependency, migration burden, and complexity for state that is naturally file-shaped. Agents already produce state as files (ROADMAP.md, PLAN.md). Adding a database creates two sources of truth.
**Do this instead:** Use the filesystem. Monitor reads agent files directly. The only state the orchestrator owns is crash_state.json (simple JSON, no schema migrations).

### Anti-Pattern 3: Event-Driven Everything

**What people do:** Use inotify/watchdog for file change detection, WebSocket for Discord, message queues between components.
**Why it's wrong for this system:** Over-engineering. The system operates on a 60-second cycle. Detecting a new PLAN.md 0.5 seconds faster than polling provides zero value. Event-driven architectures add failure modes (missed events, event ordering, reconnection logic) without meaningful benefit at this timescale.
**Do this instead:** Poll on the monitor cycle. Use webhooks (fire-and-forget HTTP POST) for Discord writes. Use simple HTTP polling for Discord reads (in the hook script). Reserve event-driven patterns for the Discord bot itself (which must be event-driven by nature of the discord.py library).

### Anti-Pattern 4: Monolithic Hook Script

**What people do:** Put all Discord communication logic in ask_discord.py, including strategist prompt building, confidence scoring, and plan review.
**Why it's wrong:** The hook script must be fast, self-contained, and single-purpose. It runs in the agent clone context. It should post a question and wait for an answer -- nothing more. The strategist logic belongs in the Discord bot, which has full project context.
**Do this instead:** Hook script posts raw question to Discord. Bot (with full context) generates the answer. Hook script receives the answer and returns it. Clean separation.

### Anti-Pattern 5: Tight Coupling Between CLI and Bot

**What people do:** Have the CLI call Discord bot functions directly, or have the bot invoke CLI commands.
**Why it's wrong:** Creates circular dependencies and makes both harder to test.
**Do this instead:** CLI and bot communicate through Discord (webhooks, messages) and the filesystem (PROJECT-STATUS.md, approval markers). The orchestrator layer (src/orchestrator/) contains shared logic that both can call.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Discord API** | discord.py for bot; webhooks for fire-and-forget posts from hooks/monitor; REST API polling for hook reply detection | Webhook URLs stored as env vars. Bot token in env var. Never hardcode. |
| **Anthropic API** | anthropic Python SDK, called from StrategistCog | API key in env var. Use streaming for long responses. Manage token budget per call. |
| **Claude Code** | Subprocess via tmux (libtmux send_keys) | Not an API -- a CLI process. Communication via filesystem and hooks only. |
| **GitHub** | gh CLI for PR creation, branch operations | Called via subprocess from integrator. Requires gh auth login. |
| **Git** | subprocess calls to git CLI | All git ops go through src/shared/git_ops.py for consistency. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| CLI <--> Orchestrator | Direct Python function calls | CLI commands are thin wrappers around orchestrator functions |
| Bot <--> Orchestrator | Filesystem (reads PROJECT-STATUS.md, ROADMAP.md) | Bot never imports orchestrator code. Reads shared files. |
| Monitor <--> Agents | Filesystem (reads clone state) + tmux (liveness) | Monitor never sends data to agents except via file copy (context sync) |
| Hook <--> Bot | Discord messages (webhook POST + REST poll) | Fully decoupled. Hook posts question, polls for reply. Bot answers independently. |
| Bot <--> Owner | Discord messages and threads | Standard discord.py interaction |
| Agents <--> Agents | Never directly. Via INTERFACES.md + PROJECT-STATUS.md | Agents are unaware of each other. Coordination is emergent from shared contracts. |

## Build Order (Dependency Chain)

The architecture has clear dependency layers that dictate build order:

### Phase 1: Foundation (no external deps except tmux and git)
- `src/models/` -- agents.yaml parsing, project/agent state models
- `src/shared/` -- git_ops, file_ops, logging utilities
- `src/tmux/` -- libtmux wrapper for session/pane management
- `src/cli/main.py` + `init_cmd.py` + `clone_cmd.py` -- project setup

**Rationale:** Everything else depends on being able to parse config, manage files, and create tmux sessions. No Discord needed yet.

### Phase 2: Agent Lifecycle (depends on Phase 1)
- `src/orchestrator/agent_manager.py` -- spawn, kill, relaunch agents
- `src/cli/dispatch_cmd.py` + `kill_cmd.py` + `relaunch_cmd.py`
- `commands/vco/checkin.md` + `standup.md` (templates, not yet functional)

**Rationale:** Before building monitoring or Discord integration, you need agents that can actually be dispatched and managed. Test with a single agent manually first.

### Phase 3: Monitor Loop (depends on Phase 2)
- `src/orchestrator/monitor.py` -- core loop with liveness and stuck detection
- `src/orchestrator/crash_tracker.py` -- crash counting + recovery policy
- `src/orchestrator/status_generator.py` -- PROJECT-STATUS.md generation
- `src/orchestrator/context_sync.py` -- distribute files to clones
- `src/cli/monitor_cmd.py` + `status_cmd.py`

**Rationale:** Monitor is the heartbeat of the system. Build it before Discord so you can validate agent supervision works with just terminal output / log files.

### Phase 4: Discord Bot Core (depends on Phase 1 models, independent of Phase 2-3)
- `src/bot/bot.py` -- bot setup, cog loading
- `src/bot/cogs/commands.py` -- owner commands (!status, !dispatch, etc.)
- `src/bot/cogs/alerts.py` -- alert formatting and routing
- `src/shared/discord_client.py` -- webhook posting utility

**Rationale:** The bot can be developed in parallel with Phase 2-3 since it reads from the filesystem and Discord, not from the orchestrator directly. Commands cog wraps CLI commands.

### Phase 5: Strategist + Hooks (depends on Phase 4 bot infrastructure)
- `src/bot/cogs/strategist.py` -- question answering with Anthropic API + confidence scoring
- `src/hooks/ask_discord.py` -- AskUserQuestion hook (posts to Discord, polls for reply)
- `src/bot/cogs/plan_review.py` -- plan approval/rejection UI
- `src/orchestrator/plan_gate.py` -- filesystem-level gate in monitor

**Rationale:** This is where the system becomes autonomous. Agents can ask questions and get answers without human intervention. Plan gate prevents agents from executing bad plans. This must work reliably before running multi-agent workloads.

### Phase 6: Integration Pipeline (depends on Phase 2 agent lifecycle, Phase 3 monitor)
- `src/orchestrator/integrator.py` -- branch merge + test + PR creation
- `src/cli/integrate_cmd.py`

**Rationale:** Integration only runs after all agents complete a milestone. It depends on agents having produced branches to merge. Build last because it's used least frequently.

### Phase 7: Standup System (depends on Phase 4 bot, Phase 2 agent lifecycle)
- `src/cli/standup_cmd.py` -- spawn standup sessions, manage lifecycle
- Functional `commands/vco/standup.md` -- standup command deployed to clones

**Rationale:** Standups are a quality-of-life feature. The system works without them (owner can read #agent-* channels). Build after core autonomy works.

## Sources

- [libtmux Python API for tmux](https://github.com/tmux-python/libtmux) -- programmatic tmux session and pane management
- [tmuxp session manager](https://github.com/tmux-python/tmuxp) -- validates libtmux API stability
- [discord.py Cogs documentation](https://discordpy.readthedocs.io/en/stable/ext/commands/cogs.html) -- standard modular bot architecture
- [discord.py hybrid commands](https://github.com/Rapptz/discord.py/discussions/8442) -- slash + text command unification
- [filelock library](https://py-filelock.readthedocs.io/) -- cross-platform file locking for Python
- [fasteners inter-process locks](https://fasteners.readthedocs.io/en/latest/guide/inter_process/) -- alternative file locking approach
- [Multi-agent orchestration patterns (Chanl)](https://www.chanl.ai/blog/multi-agent-orchestration-patterns-production-2026) -- production multi-agent patterns
- [Multi-agent system architectures (arXiv)](https://arxiv.org/html/2601.13671v1) -- academic survey of orchestration architectures
- [Tmux orchestrator for AI agents](https://ktwu01.github.io/posts/2025/08/tmux-orchestrator/) -- precedent for tmux-based agent management
- [VCO-ARCHITECTURE.md](/home/developer/vcompany/VCO-ARCHITECTURE.md) -- authoritative design reference for vCompany

---
*Architecture research for: autonomous multi-agent CLI orchestration system*
*Researched: 2026-03-25*
