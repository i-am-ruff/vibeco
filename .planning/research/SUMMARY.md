# Project Research Summary

**Project:** vCompany
**Domain:** Autonomous multi-agent software development orchestration (Python CLI + Discord bot + tmux + Claude Code)
**Researched:** 2026-03-25
**Confidence:** HIGH

## Executive Summary

vCompany is a single-machine orchestrator that manages multiple Claude Code agents working in parallel on the same codebase, coordinated through a CLI (`vco`), a Discord bot, and a filesystem-based monitor loop. Experts in this domain converge on a clear pattern: isolate agents in separate repo clones with branch-per-agent, coordinate through shared artifacts (not direct messaging), and supervise with a polling-based monitor that handles liveness, crash recovery, and plan gating. The recommended stack is Python 3.12 with click (CLI), discord.py (bot), libtmux (process management), and Pydantic (config validation), managed by uv. No database is needed -- all state lives on the filesystem, which is both the correct architectural choice and a massive simplification.

The recommended approach is a layered build: foundation (config models, git operations, tmux wrappers), then agent lifecycle (dispatch, kill, relaunch with crash recovery), then the monitor loop (liveness, stuck detection, status generation), then Discord bot and hooks (commands, alerts, AskUserQuestion routing), then the Strategist/PM bot and plan gate (the highest-value differentiator), then the integration pipeline (merge, test, PR), and finally quality-of-life features like structured standups. This ordering follows the strict dependency chain uncovered in architecture research: you cannot monitor agents you cannot dispatch, you cannot gate plans without a bot to post them to, and you cannot integrate without branches to merge.

The top risks are: (1) crash recovery loops burning resources when failures are persistent rather than transient -- mitigate with crash classification before relaunch, (2) merge conflicts discovered late because branches diverge too long -- mitigate with frequent integration checks and strict file ownership enforcement, (3) the monitor loop as a single point of failure -- mitigate with independent try/except per check and a watchdog supervisor, and (4) Discord gateway disconnects leaving agents unsupervised -- mitigate with async-only operations in the bot event loop and a connectivity health check in the monitor.

## Key Findings

### Recommended Stack

The stack is Python-centric with no database, no web server, and no task queue. This is correct for a single-machine orchestrator where state is inherently file-based. The key technology choices are well-established with high-confidence version pins. The only dependency risk is libtmux (pre-1.0, API instability) -- mitigate by wrapping it in a thin abstraction layer from day one.

**Core technologies:**
- **Python 3.12+ / uv** -- runtime and package management. uv replaces pip/venv/pip-tools entirely.
- **click 8.2.x** -- CLI framework for `vco` commands. Decorator-based command groups match the subcommand structure perfectly.
- **discord.py 2.7.x** -- Discord bot framework. Async-native, Cog-based modularity, built-in rate limit handling.
- **libtmux 0.55.x** -- Python API for tmux session/pane management. Pin tightly; wrap in abstraction layer.
- **Pydantic 2.11.x + pydantic-settings** -- Config validation (agents.yaml) and environment variable loading (.env).
- **httpx 0.28.x** -- Single HTTP client for both sync (CLI) and async (bot) contexts.
- **Rich 14.2.x** -- Terminal output formatting for `vco status` and monitoring.
- **anthropic 0.86.x** -- Anthropic SDK for the PM/Strategist bot.
- **watchfiles 0.24.x** -- Filesystem monitoring for plan gate detection.

**What to avoid:** GitPython (maintenance mode), requests (sync-only), nextcord/disnake (dead-end forks), any database, any web framework, any task queue.

### Expected Features

**Must have (table stakes):**
- Agent spawning with isolated repo clones and directory ownership
- Agent liveness monitoring (60s poll cycle) with stuck detection (30min no-commit threshold)
- Crash recovery with circuit breaker (3 restarts/hour, alert on 4th)
- Branch-per-agent with integration pipeline (merge + test + PR)
- Discord bot with operator commands (!dispatch, !status, !kill, !relaunch, !integrate)
- AskUserQuestion hook routing through Discord with 10-min timeout and fallback
- Plan review gate (monitor detects PLAN.md, pauses agent, posts to Discord for approval)
- PROJECT-STATUS.md generation and cross-clone distribution
- INTERFACES.md contract system for cross-agent coordination
- Declarative agents.yaml with per-agent GSD configuration injection

**Should have (differentiators):**
- PM/Strategist bot as autonomous decision layer (highest-value differentiator -- no competitor has this)
- Discord-native operation (async, multi-device, breaks the "must be at terminal" constraint)
- Contract-driven coordination via INTERFACES.md (higher-level than message passing)
- Filesystem-level plan gating (more robust than in-session hooks, survives context loss)
- Context-aware crash recovery using /gsd:resume-work + status injection
- Structured standup and checkin rituals for synchronization

**Defer (v2+):**
- Strategist context summarization for large projects
- Sophisticated crash analysis (why, not just that)
- Agent performance metrics and analytics
- Multi-project concurrent orchestration
- Multi-machine distribution
- Dynamic agent spawning
- Automatic merge conflict resolution
- Web UI

### Architecture Approach

The system is organized into four layers: Human (owner on Discord), Discord (bot + channels), Orchestration (CLI + monitor + plan gate), and Agent (tmux panes with Claude Code + GSD). Communication between layers is deliberately simple: CLI and bot both call into a shared orchestrator library, agents coordinate through filesystem artifacts (never directly), and the hook system bridges agent questions to Discord via webhook POST and REST polling. All critical state lives on the filesystem and survives crashes. The only in-memory state is rebuilt from disk on restart.

**Major components:**
1. **vco CLI (click)** -- Project init, agent dispatch, integration trigger, standup, context sync
2. **Monitor Loop (asyncio)** -- Liveness checks, stuck detection, plan gate trigger, status regeneration, crash recovery
3. **Discord Bot (discord.py Cogs)** -- Owner commands, alert routing, plan review UI, strategist question handling
4. **PM/Strategist Bot (Anthropic SDK)** -- Autonomous plan review, agent question answering, confidence-based escalation
5. **AskUserQuestion Hook** -- Standalone script bridging Claude Code agents to Discord via webhook
6. **Integration Pipeline** -- Branch merge, test execution, PR creation, fix dispatch
7. **Context Distribution** -- Keeps PROJECT-STATUS.md and INTERFACES.md current across all clones

### Critical Pitfalls

1. **Crash recovery loops drain resources** -- Classify crashes before retrying. Persistent errors (bad git state, corrupted clone) should alert immediately, not retry 3 times. Use exponential backoff (30s, 2min, 10min) between retries.
2. **Merge conflicts discovered only at integration time** -- Integrate frequently (every 2-3 hours, not just at milestone end). Enforce strict directory ownership. Designate shared files (package.json, lock files) to a single agent or the orchestrator.
3. **Monitor loop as single point of failure** -- Wrap each check in independent try/except. Run under a watchdog (systemd or heartbeat-file checker). Set timeouts on all subprocess calls.
4. **Discord gateway disconnects** -- Never block the discord.py event loop. Use asyncio.to_thread() for all I/O. Monitor bot connectivity from the monitor loop. Buffer messages during disconnects.
5. **Filesystem plan gate reads partial writes** -- Use atomic write (write to .tmp, rename) or a completion marker. Never read PLAN.md on detection; wait for the ready signal.
6. **AskUserQuestion hook silently fails** -- Wrap the entire hook in try/except with guaranteed fallback response. Use OS-level timeout as backstop. Log every invocation.
7. **tmux zombie processes** -- Check actual process PID inside panes, not just tmux session existence. Reconcile expected PIDs every monitor cycle.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation and Configuration
**Rationale:** Everything depends on config parsing, file operations, git operations, and tmux session management. These are the leaf dependencies in the architecture's build order.
**Delivers:** Pydantic models for agents.yaml, git operations wrapper, tmux session/pane abstraction, `vco init` and `vco clone` commands, project directory structure.
**Addresses:** Declarative agent roster, per-agent GSD injection, process isolation setup.
**Avoids:** tmux zombie processes (Pitfall 7) by building proper PID-based liveness checking from the start. Partial plan reads (Pitfall 1) by establishing atomic file write patterns.

### Phase 2: Agent Lifecycle Management
**Rationale:** Before building monitoring or Discord, agents must be dispatchable, killable, and relaunchable. This is the first phase where the system does something useful (runs Claude Code agents).
**Delivers:** Agent spawn/kill/relaunch via CLI, crash tracking with circuit breaker, `vco dispatch`, `vco kill`, `vco relaunch` commands.
**Addresses:** Agent spawning with isolation, crash recovery, agent termination (graceful and forced).
**Avoids:** Crash recovery loops (Pitfall 2) by implementing crash classification and exponential backoff from the start.

### Phase 3: Monitor Loop and Status
**Rationale:** Depends on agent lifecycle (Phase 2). The monitor is the heartbeat -- without it, agents run unsupervised. Build this before Discord so it can be validated with terminal output alone.
**Delivers:** 60s poll loop with liveness checks, stuck detection, PROJECT-STATUS.md generation and distribution, context sync to clones, `vco monitor` and `vco status` commands.
**Addresses:** Liveness monitoring, stuck detection, shared status awareness, alert system (to log/terminal initially).
**Avoids:** Monitor as SPOF (Pitfall 8) by using independent try/except per check and a heartbeat-file watchdog.

### Phase 4: Discord Bot Core
**Rationale:** Can be partially developed in parallel with Phase 2-3 since it reads from filesystem. But functionally depends on having agents and a monitor to command and observe. Establishes the communication channel needed for all subsequent features.
**Delivers:** discord.py bot with Cogs, owner commands (!dispatch, !status, !kill, !relaunch, !integrate), #alerts channel integration, webhook posting utility.
**Addresses:** Discord-native operation (differentiator), alert system (upgraded from terminal to Discord), operator control surface.
**Avoids:** Discord gateway disconnects (Pitfall 4) by using async-only operations from day one.

### Phase 5: Hooks and Plan Gate
**Rationale:** Depends on Discord bot (Phase 4) for question routing and plan posting. This is where the system becomes autonomous -- agents can ask questions and get answers, plans are gated before execution.
**Delivers:** AskUserQuestion hook (ask_discord.py), plan gate in monitor (detect PLAN.md, pause agent, post to Discord), plan approval/rejection UI in Discord.
**Addresses:** Plan review gate (table stakes), question routing to humans, AskUserQuestion hook.
**Avoids:** Hook silent failures (Pitfall 6) with defense-in-depth: try/except wrapper, OS-level timeout, guaranteed fallback. Partial plan reads (Pitfall 1) with completion markers.

### Phase 6: PM/Strategist Bot
**Rationale:** Depends on Discord bot infrastructure (Phase 4) and hook system (Phase 5). This is the highest-value differentiator but also the most complex feature. Build after the manual-approval path works to provide a fallback.
**Delivers:** Anthropic SDK integration, autonomous question answering with confidence scoring, automated plan review, owner escalation for low-confidence decisions.
**Addresses:** PM/Strategist bot (top differentiator), confidence-based escalation, autonomous operation.
**Avoids:** Strategist context saturation (Pitfall 5) by designing hierarchical context management with token budgets per section.

### Phase 7: Integration Pipeline
**Rationale:** Depends on agent lifecycle (Phase 2) and monitor (Phase 3) for knowing when agents complete. Used least frequently (only at milestone boundaries), so build after the continuous operation features.
**Delivers:** Branch merge pipeline (ordered by dependency), automated test execution, conflict detection and reporting, PR creation via gh CLI, fix dispatch to responsible agent.
**Addresses:** Branch-per-agent integration, automated test execution, merge conflict detection.
**Avoids:** Late merge conflicts (Pitfall 3) by supporting frequent integration checks, not just milestone-end merges.

### Phase 8: Standup System and Polish
**Rationale:** Quality-of-life features that enhance the system but are not required for core operation. Build last.
**Delivers:** Structured standup command with threaded Discord output, /vco:checkin fire-and-forget reporting, per-agent Discord channels, INTERFACES.md contract management workflow.
**Addresses:** Structured standups/checkins, per-agent channels, contract-driven coordination workflow.

### Phase Ordering Rationale

- **Phases 1-3 form the non-Discord core.** These can be fully tested from the terminal. An operator can dispatch agents, monitor them, and see status without Discord. This gives a working (if manual) system early.
- **Phase 4 adds the communication channel.** Discord is the UI, but the system must work without it first. If the bot goes down, the CLI still works.
- **Phases 5-6 add autonomy progressively.** Phase 5 enables plan gating with human review. Phase 6 upgrades to PM-automated review. This progression lets you validate the human-in-the-loop path before trusting the AI-in-the-loop path.
- **Phase 7 is deliberately late.** Integration is infrequent and high-stakes. Building it after the continuous operation features (monitoring, gating, recovery) are solid means you have a safety net when integration fails.
- **Phase 8 is polish.** Standups and checkins are valuable but not critical. The system is fully functional without them.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 5 (Hooks and Plan Gate):** Claude Code hook system specifics (stdin/stdout JSON format, hook types available, elicitation support) need validation against current Claude Code documentation. The hook runs in the agent clone's environment, which creates execution context challenges.
- **Phase 6 (PM/Strategist Bot):** Context management strategy needs detailed design. Token budgeting, rolling summarization, and confidence calibration are novel problems without established patterns. The Anthropic SDK's streaming API for Discord message editing needs prototyping.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** Pydantic models, click CLI, git subprocess, tmux via libtmux -- all well-documented with abundant examples.
- **Phase 2 (Agent Lifecycle):** Process spawning and management is standard. Circuit breaker pattern is well-established (Kubernetes CrashLoopBackOff).
- **Phase 4 (Discord Bot Core):** discord.py Cog architecture is extensively documented with official examples.
- **Phase 7 (Integration Pipeline):** Git merge operations via subprocess are straightforward. gh CLI for PR creation is well-documented.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All packages verified on PyPI with current versions. Versions confirmed. No speculative choices. |
| Features | HIGH | Feature landscape validated against 4 competing systems (Agent Teams, Overstory, Agent-MCP, OmniDaemon) and academic research on multi-agent error amplification. |
| Architecture | HIGH | Layered architecture with filesystem-as-IPC and supervisor-process patterns are battle-tested in production systems. Build order derived from clear dependency analysis. |
| Pitfalls | HIGH | Pitfalls cross-referenced against official documentation (Discord gateway, inotify manpage, Claude Code hooks) and production incident patterns (Kubernetes CrashLoopBackOff, tmux process lifecycle). |

**Overall confidence:** HIGH

### Gaps to Address

- **Claude Code hook system behavior under crash:** What happens to a running hook (ask_discord.py) when the Claude Code session crashes? Does it become a zombie? Does Claude Code kill child processes on exit? Needs testing during Phase 5.
- **libtmux API stability at 0.55.x:** The library is pre-1.0 with documented breaking changes between minor versions. The thin abstraction layer mitigates this, but the exact API surface needed (create session, create pane, send keys, get PID, capture output) should be validated against 0.55.x specifically during Phase 1.
- **Discord rate limits under real agent load:** Theoretical analysis suggests 8+ agents will hit webhook rate limits, but the exact threshold depends on checkin frequency, question volume, and status update cadence. Needs empirical validation during Phase 4 with multiple agents.
- **Strategist confidence calibration:** No established methodology for calibrating an LLM's self-assessed confidence on code review decisions. This will require iterative tuning during Phase 6. Start with a simple high/medium/low threshold and adjust based on owner override frequency.
- **GSD resume-work reliability:** The /gsd:resume-work command is the linchpin of crash recovery. Its behavior when GSD state files are partially written or corrupt is unknown. Needs testing during Phase 2.

## Sources

### Primary (HIGH confidence)
- [discord.py 2.7.x](https://pypi.org/project/discord.py/) -- Bot framework, Cogs, gateway behavior
- [anthropic 0.86.x](https://pypi.org/project/anthropic/) -- Strategist SDK
- [libtmux 0.55.x](https://github.com/tmux-python/libtmux) -- tmux Python API
- [click 8.2.x](https://pypi.org/project/click/) -- CLI framework
- [Pydantic 2.11.x](https://pypi.org/project/pydantic/) -- Config validation
- [uv 0.9.x](https://docs.astral.sh/uv/) -- Package management
- [Discord Gateway docs](https://docs.discord.com/developers/events/gateway) -- Connection lifecycle, heartbeats
- [Discord Rate Limits docs](https://discord.com/developers/docs/topics/rate-limits) -- Webhook and API rate limits
- [inotify(7) manpage](https://man7.org/linux/man-pages/man7/inotify.7.html) -- Filesystem event pitfalls
- [Claude Code Hooks reference](https://code.claude.com/docs/en/hooks) -- Hook system behavior

### Secondary (MEDIUM confidence)
- [Anthropic: Building a C compiler with parallel Claudes](https://www.anthropic.com/engineering/building-c-compiler) -- Multi-agent coding patterns
- [Chanl: Multi-Agent Patterns in Production](https://www.chanl.ai/blog/multi-agent-orchestration-patterns-production-2026) -- Hierarchical orchestration recommendation
- [TDS: 17x Error Trap of Bag of Agents](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/) -- Error amplification research
- [Overstory](https://github.com/jayminwest/overstory) -- Tiered watchdog, SQLite mail patterns
- [Agent-MCP](https://github.com/rinadelph/Agent-MCP) -- File locking, task assignment patterns
- [Anthropic: Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) -- Context management strategies
- [Azure: Scheduler Agent Supervisor pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/scheduler-agent-supervisor) -- Supervisor pattern reference

### Tertiary (LOW confidence)
- [Clash: merge conflict detection](https://github.com/clash-sh/clash) -- Promising tool but unvalidated in this context
- [Tmux orchestrator blog post](https://ktwu01.github.io/posts/2025/08/tmux-orchestrator/) -- Single author, limited detail

---
*Research completed: 2026-03-25*
*Ready for roadmap: yes*
