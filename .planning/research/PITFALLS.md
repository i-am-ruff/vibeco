# Pitfalls Research

**Domain:** Autonomous multi-agent orchestration (Discord + tmux + Claude Code + filesystem IPC + git)
**Researched:** 2026-03-25
**Confidence:** HIGH (most pitfalls verified across multiple sources and official documentation)

## Critical Pitfalls

### Pitfall 1: Filesystem Plan Gate Reads Partial Writes

**What goes wrong:**
The monitor loop detects a new PLAN.md via filesystem watcher or polling, reads it immediately, and posts an incomplete or corrupt plan to #plan-review. The agent is still writing the file when the monitor reads it. This is a Time-of-Check-Time-of-Use (TOCTTOU) race condition fundamental to inotify-based and polling-based file monitoring.

**Why it happens:**
File creation and file content completion are not atomic operations. `inotify` fires `IN_CREATE` when the file descriptor is opened, not when writing finishes. Even with `IN_CLOSE_WRITE`, editors and tools that use write-then-rename patterns (like many text editors) create additional complexity. Polling on a 60-second loop may catch a file mid-write if the agent is writing a large plan.

**How to avoid:**
Use a sentinel/completion marker pattern. The agent writes PLAN.md first, then writes a PLAN.md.ready marker file (or appends a known footer like `<!-- PLAN COMPLETE -->`). The monitor only processes PLAN.md after detecting the marker. Alternatively, use atomic write: write to PLAN.md.tmp then rename to PLAN.md (rename is atomic on Linux within the same filesystem).

**Warning signs:**
- Truncated plans appearing in Discord
- Plans missing closing sections
- Intermittent "file not found" errors when monitor tries to read a detected file

**Phase to address:**
Phase 1 (core infrastructure) -- this is foundational to the plan gate mechanism.

---

### Pitfall 2: Crash Recovery Loop Becomes an Infinite Resource Drain

**What goes wrong:**
An agent crashes due to a persistent error (bad git state, corrupted clone, exhausted context window). The crash recovery system relaunches it with `/gsd:resume-work`. The agent hits the same error within seconds, crashes again. Even with the "3 crashes per hour, stop on 4th" rule, those 3 crashes consume API tokens, pollute git history with partial commits, and may corrupt shared state (INTERFACES.md, PROJECT-STATUS.md) before the circuit breaker trips.

**Why it happens:**
Crash recovery assumes the failure is transient (network blip, temporary resource contention). But many agent failures are persistent: a merge conflict the agent cannot resolve, a corrupted `.claude` directory, a plan that references deleted files. Blindly relaunching without diagnosing the failure mode guarantees repeated failure.

**How to avoid:**
Implement crash classification before relaunch. On crash detection: (1) check git status of the clone for conflicts or dirty state, (2) check if the last N commits were reverts or empty, (3) check if the crash log contains known persistent errors (e.g., "merge conflict", "file not found", "context window exceeded"). Only auto-relaunch for unclassified crashes. For classified persistent errors, alert immediately without retry. Also implement exponential backoff between retries (30s, 2min, 10min) rather than immediate relaunch.

**Warning signs:**
- Agent producing the same error message across multiple crashes
- Agent's last git log showing revert-commit-revert patterns
- API token burn rate spiking without corresponding code output
- Agent relaunching and crashing within <60 seconds repeatedly

**Phase to address:**
Phase 2 (agent lifecycle management) -- must be in place before agents run autonomously for extended periods.

---

### Pitfall 3: Git Merge Conflicts Discovered Only at Integration Time

**What goes wrong:**
Multiple agents work on separate branches for hours. At integration time, their branches have conflicting changes to shared files (package.json, shared types, configuration files, lock files). The conflicts are too complex for automated resolution. Hours of agent work may need to be partially redone, and the integration pipeline stalls while a human resolves conflicts manually.

**Why it happens:**
Directory ownership in agents.yaml prevents direct file overlap, but shared files (package.json, tsconfig.json, shared type definitions, lock files) are inherently cross-cutting. Even with ownership boundaries, agents may modify the same interface contracts or import paths. The longer branches diverge, the harder merges become.

**How to avoid:**
Three-layer defense: (1) Integrate frequently -- do not let branches diverge for more than 2-3 hours. The monitor should trigger periodic integration checks, not just at milestone completion. (2) Use a tool like Clash (Rust CLI) to detect merge conflicts across worktrees in real-time during development, surfacing conflicts as they emerge rather than at merge time. (3) Designate truly shared files (package.json, lock files) as owned by a single "infrastructure" agent or managed exclusively by the orchestrator. No agent should independently modify shared config files -- they request changes via the INTERFACES.md contract system.

**Warning signs:**
- Branches diverging for >3 hours without integration check
- Multiple agents modifying files outside their owned directories
- Lock file (package-lock.json, yarn.lock) changes on multiple branches
- INTERFACES.md change requests stacking up without resolution

**Phase to address:**
Phase 2 (agent isolation and dispatch) for directory ownership enforcement. Phase 3 (integration pipeline) for conflict detection and frequent integration checks.

---

### Pitfall 4: Discord Bot Gateway Disconnects Kill Agent Coordination

**What goes wrong:**
The Discord bot loses its WebSocket connection to Discord's gateway (network hiccup, Discord outage, missed heartbeat ACK). During the disconnection window: agent questions via AskUserQuestion go unanswered (10-min timeout triggers fallback), plan approvals stall (agents idle), status updates are lost, and owner commands are undelivered. If reconnection is slow or the bot doesn't detect the disconnect, agents may be unsupervised for extended periods.

**Why it happens:**
Discord's gateway requires periodic heartbeats (typically every ~41 seconds). If the bot's event loop is blocked by a long-running synchronous operation (e.g., reading large files, computing diffs, calling the Anthropic API synchronously), it misses heartbeats and gets disconnected. discord.py handles reconnection automatically, but only if the event loop is not blocked.

**How to avoid:**
Never run blocking operations in discord.py's event loop. Use `asyncio.to_thread()` or `loop.run_in_executor()` for all file I/O, subprocess calls, and API calls. Set a conservative `heartbeat_timeout` (30 seconds instead of default 60). Implement a health-check mechanism: the monitor loop should verify Discord bot connectivity every cycle (60s). If the bot is disconnected, pause agent dispatches and alert via a fallback channel (e.g., system notification, log file, or even a simple HTTP webhook to an alternative service). Implement a local message queue that buffers outgoing Discord messages during disconnection and flushes on reconnect.

**Warning signs:**
- Bot appearing offline in Discord while agents are running
- AskUserQuestion hooks timing out and using fallback answers
- Gaps in #agent-{id} channel activity despite agents being active
- "Heartbeat blocked for more than N seconds" warnings in bot logs

**Phase to address:**
Phase 1 (Discord bot core) -- connection resilience must be in the foundation, not bolted on later.

---

### Pitfall 5: Strategist Bot Context Window Saturation

**What goes wrong:**
The PM/Strategist bot accumulates project context, agent questions, plan reviews, status updates, and decision history. As a project grows, the strategist's context fills up. It starts giving incoherent plan reviews, forgetting earlier architectural decisions, contradicting previous approvals, or hallucinating interfaces that do not exist. Agents receive bad guidance and build the wrong thing.

**Why it happens:**
LLMs suffer from "Lost in the Middle" -- information buried in long contexts is poorly recalled. Even with large context windows (200K tokens), quality degrades well before the limit. The strategist's role requires it to hold the most context of any component: full project blueprint, all INTERFACES.md contracts, recent agent statuses, decision history, and the current question/plan. Without active context management, this balloons quickly.

**How to avoid:**
Implement hierarchical context management for the strategist: (1) Persistent structured storage for decisions, interfaces, and architectural constraints (not in the context window -- retrieved on demand). (2) Rolling summaries of agent activity and decision history, with full details retrievable when needed. (3) Hard token budget: allocate explicit token budgets for each context section (system prompt: 2K, project blueprint: 4K, interfaces: 2K, recent activity: 2K, current task: remaining). (4) Place critical instructions (role definition, current milestone scope) at the start AND end of the prompt to counteract recency/primacy bias.

**Warning signs:**
- Strategist contradicting its own earlier decisions
- Plan reviews approving things that violate stated architectural constraints
- Strategist asking questions it was already told the answer to
- Response quality degrading as project progresses (compare early vs. late reviews)

**Phase to address:**
Phase 3 (strategist bot implementation) -- but the architecture for context management must be designed in Phase 1.

---

### Pitfall 6: AskUserQuestion Hook Silently Fails or Hangs

**What goes wrong:**
The `ask_discord.py` hook script is invoked by Claude Code when an agent needs to ask a question. The script must: send a Discord message, wait for a response, and return the answer to Claude Code's stdin. If the hook fails (Discord API error, timeout without proper fallback, script crash, Python environment issue), the agent either hangs indefinitely waiting for input, or receives a malformed response that causes unpredictable behavior.

**Why it happens:**
The hook runs as a subprocess of Claude Code, outside the normal Python runtime of the Discord bot. It needs its own Discord API access (likely via webhook or bot token), its own error handling, and its own timeout logic. The hook's execution environment may differ from development assumptions (different PATH, missing environment variables, wrong Python version). Additionally, the hook must handle the case where Discord is unreachable AND the case where no human responds within the timeout window.

**How to avoid:**
Build the hook with defense-in-depth: (1) Wrap the entire hook in a try/except with a guaranteed fallback response (deny + reason). Never let the hook exit without writing a response. (2) Use a timeout at the OS level (`timeout` command wrapping the Python script) as a backstop for hung network calls. (3) Test the hook in isolation before integrating -- simulate Discord failures, timeouts, and malformed responses. (4) Log every hook invocation and its outcome to a file for debugging. (5) Use the elicitation hook type (not a custom workaround) if Claude Code's hook system supports it natively for MCP-style elicitation.

**Warning signs:**
- Agents appearing stuck with no Discord activity
- Hook process zombies accumulating in the process table
- Agents receiving garbled or empty responses and producing nonsensical output
- `ps aux | grep ask_discord` showing multiple concurrent instances

**Phase to address:**
Phase 2 (hook system implementation) -- this is the critical IPC bridge and must be rock-solid before agents run autonomously.

---

### Pitfall 7: tmux Session State Drift and Zombie Processes

**What goes wrong:**
The orchestrator believes an agent is running in tmux pane 3, but the process in that pane has silently exited (segfault, OOM kill, SSH disconnect). The tmux pane still exists but is showing a dead shell or a bash prompt. The monitor's liveness check (if it only checks tmux session existence) reports the agent as alive. Meanwhile, the agent is producing no work, and the system thinks everything is fine.

**Why it happens:**
tmux sessions and panes persist independently of the processes running inside them. A pane survives its child process. Checking `tmux has-session` only verifies the tmux session exists, not that the expected process is alive within it. Additionally, if a session with the same name already exists when the orchestrator tries to create one, it may silently attach to the existing (possibly stale) session instead of creating a fresh one.

**How to avoid:**
Liveness checking must verify the actual process, not just the tmux container: (1) Use `tmux list-panes -t session -F '#{pane_pid}'` to get the PID of the shell in each pane, then check if that PID's child process (Claude Code) is still running. (2) Combine with output-based liveness: check if the pane's last output timestamp is recent (capture pane content periodically). (3) Before creating sessions, always kill any existing session with the same name (`tmux kill-session -t name 2>/dev/null; tmux new-session -d -s name`). (4) Track expected PIDs in the orchestrator state and reconcile every monitor cycle.

**Warning signs:**
- Agent status shows "running" but no commits for >30 minutes
- tmux pane showing a bash prompt instead of Claude Code output
- PID recorded by orchestrator no longer exists in process table
- Multiple tmux sessions with similar names

**Phase to address:**
Phase 1 (tmux session management) -- fundamental to the entire agent lifecycle.

---

### Pitfall 8: Monitor Loop Becomes a Single Point of Failure

**What goes wrong:**
The 60-second monitor loop handles liveness checks, stuck detection, plan gate triggers, status regeneration, and context distribution. If the monitor process itself crashes or hangs, ALL orchestration stops: stuck agents are not detected, plans are not gated, status is not regenerated, and crash recovery does not trigger. The system degrades silently.

**Why it happens:**
Concentrating all coordination logic in a single loop creates a fragile single point of failure. A single unhandled exception in any monitor function (e.g., parsing a malformed status file, git command timeout, disk full) kills the entire monitor. Python's GIL can also cause the monitor to hang if a blocking operation (subprocess call to git) takes longer than expected.

**How to avoid:**
(1) Wrap each monitor function in independent try/except blocks -- one failing check must not kill others. (2) Run the monitor under a process supervisor (systemd service with auto-restart, or a simple watchdog script). (3) Implement a heartbeat file that the monitor updates each cycle. A separate lightweight watchdog (even a cron job) checks the heartbeat file and restarts the monitor if stale. (4) Consider decomposing the monitor into independent async tasks rather than a sequential loop, so a hung git command does not block liveness checking. (5) Set timeouts on all subprocess calls within the monitor.

**Warning signs:**
- Monitor log file stops updating
- No status regeneration despite agent activity
- Plan gate not triggering for new PLAN.md files
- Crash recovery not firing for dead agents

**Phase to address:**
Phase 2 (monitor implementation) -- supervisor pattern should be designed in Phase 1.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Polling filesystem instead of inotify | Simpler implementation, no race conditions from event ordering | Wastes CPU cycles, 60s latency on detection, misses rapid changes | Acceptable for v1 -- polling at 60s is fine for plan gates and status files. Inotify is premature optimization here. |
| Storing agent state in flat files instead of a database | No dependency, easy to debug, agents can read directly | No transactions, concurrent write corruption, no query capability | Acceptable for v1 with single-machine deployment. Revisit if >5 concurrent agents. |
| Synchronous Anthropic API calls in strategist | Simpler code, easier debugging | Blocks Discord event loop, causes gateway disconnects | Never acceptable. Always use async from day one. |
| Hardcoded Discord channel names | Fast setup, no config needed | Breaks when channel structure changes, hard to test | Acceptable in Phase 1 prototype only. Must be configurable before multi-project use. |
| Single git remote for all agent branches | Simple setup | Branch namespace pollution, no isolation between projects | Acceptable for v1 single-project use. |
| Skipping integration tests between agent outputs | Faster development cycles | Merge conflicts compound, interface drift undetected | Never acceptable once >1 agent is running. |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Discord API | Sending messages in rapid succession from multiple agents, hitting rate limits (429 errors) | Implement a message queue with rate-limit-aware sending. discord.py handles per-route rate limits automatically, but bulk operations (posting status to 5 agent channels simultaneously) can still trigger global rate limits. Space messages 0.5-1s apart. |
| Claude Code hooks | Assuming the hook's working directory and environment match the development environment | Hooks run as subprocesses of Claude Code. Explicitly set PATH, PYTHONPATH, and use absolute paths to the Python interpreter. Test hooks via `claude --print-hook-output` before relying on them. |
| Claude Code + GSD | Assuming GSD state files (.gsd/) are always consistent after a crash | GSD writes multiple state files during transitions. A crash mid-transition can leave inconsistent state. On relaunch, validate GSD state before resuming; consider a `/gsd:reset` if state is corrupt. |
| tmux + Claude Code | Sending input to tmux panes with `tmux send-keys` and assuming immediate execution | tmux send-keys is asynchronous -- it queues keystrokes but does not guarantee they have been processed. Use `tmux wait-for` or poll for expected output after sending commands. |
| Git + parallel agents | Running `git push` from multiple agents simultaneously to the same remote | Git push is not atomic across branches, but concurrent pushes can fail with "remote rejected" if the remote ref is updated between fetch and push. Use retry logic on push failures, or serialize pushes through the orchestrator. |
| Anthropic API | Not handling rate limits or overloaded errors from the Anthropic API | Implement exponential backoff with jitter. The strategist bot and agents all share the same API key and rate limit bucket. During high activity (5 agents + strategist), you will hit rate limits. Consider staggering agent launches. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Reading entire PROJECT-STATUS.md into every agent's context on every update | Agents slow down, token usage spikes, context window fills faster | Use diffs or section-specific updates. Only send changed sections. | >3 agents generating frequent status updates |
| Git operations blocking the monitor loop | Monitor cycle takes >60s, liveness checks delayed, cascading detection failures | Set 10s timeout on all git subprocess calls. Use `--no-optional-locks` flag for read-only git operations. | >5 agents with large repos |
| Discord message content exceeding 2000 character limit | Messages silently truncated or API errors | Truncate with "... (full content in thread)" and post details as thread replies. Always check message length before sending. | Any plan or status longer than ~400 words |
| Strategist making API calls for every agent checkin | API costs scale linearly with agent count x checkin frequency | Batch agent updates. Strategist processes a digest of changes every N minutes, not every individual event. | >3 agents checking in every 10 minutes |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing Discord bot token and Anthropic API key in agents.yaml or git-tracked config | Tokens leaked to all agent clones, potentially committed to git history | Use environment variables or a .env file in gitignored location. Inject tokens at runtime, never store in config files that agents can read. |
| Agent clones having write access to the orchestrator's configuration | A rogue or confused agent could modify agents.yaml, hook scripts, or monitor config | Agent clones should have read-only access to orchestrator config. Use filesystem permissions (chmod) to enforce. Agents only write within their owned directories. |
| AskUserQuestion hook passing unsanitized agent output to Discord | Agent-generated content could contain @everyone mentions, Discord markdown exploits, or extremely long messages that break the channel | Sanitize all agent output before posting to Discord: strip @mentions, limit message length, escape markdown. |
| Running all agents under the same OS user | One agent's crash or malicious output could affect others' filesystems | For v1 single-machine, this is acceptable with directory ownership enforcement. For future hardening, consider per-agent OS users or containers. |

## UX Pitfalls (Discord Interface)

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Posting raw logs or full file diffs to Discord channels | Owner drowns in noise, cannot find actionable information | Post summaries with expandable details in threads. Use Discord embeds for structured status. Link to full content (e.g., GitHub PR) instead of inlining. |
| No distinction between urgent alerts and routine updates | Owner ignores all notifications or misses critical ones | Use #alerts only for things requiring human action (crashes, low-confidence decisions). Routine updates go to #agent-{id} channels. Use Discord mentions (@Owner) only for escalations. |
| Requiring owner to type complex commands (!dispatch agent=backend scope="implement auth") | High friction, typos cause failures, hard to remember syntax | Use Discord slash commands with autocomplete. For complex operations, use interactive components (buttons, dropdowns) where possible. Provide sensible defaults. |
| Plan review in a flat channel with no threading | Multiple plans interleave, approvals get lost, context is unclear | Each plan review should be a Discord thread. Pin active plan reviews. Use reactions (checkmark/X) for quick approve/reject with thread for detailed feedback. |

## "Looks Done But Isn't" Checklist

- [ ] **Agent dispatch:** Agent is running in tmux -- but verify Claude Code actually started (not just a bash shell). Check for the Claude Code process specifically.
- [ ] **Plan gate:** Monitor detects PLAN.md -- but verify it waited for the file to be fully written before reading. Check for the completion marker.
- [ ] **Crash recovery:** Agent relaunched after crash -- but verify the underlying cause was addressed. Check that the new session is making progress (commits within 10 minutes).
- [ ] **Integration pipeline:** All branches merged -- but verify tests actually ran and passed. A merge without test execution is not integration.
- [ ] **Status distribution:** PROJECT-STATUS.md written to all clones -- but verify agents actually read it (check that agent context includes current status, not stale).
- [ ] **Discord connectivity:** Bot is "online" -- but verify it can actually send and receive messages. A bot can appear online while its event handlers are broken.
- [ ] **Hook system:** ask_discord.py exists in agent clone -- but verify it is executable, has correct shebang, correct Python path, and Discord token is accessible from the hook's environment.
- [ ] **Directory ownership:** agents.yaml defines ownership -- but verify enforcement. Can an agent actually write outside its owned directories? Test with a deliberate boundary violation.
- [ ] **Strategist decisions:** Strategist responded to a question -- but verify the response is coherent and consistent with previous decisions. Context saturation causes subtle quality degradation.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Partial plan read (Pitfall 1) | LOW | Re-read the plan file, re-post to Discord. No data loss. |
| Crash recovery loop (Pitfall 2) | MEDIUM | Kill the agent, clean up the clone's git state (`git reset --hard`, `git clean -fd`), re-dispatch with fresh context. May lose in-progress work since last commit. |
| Late merge conflicts (Pitfall 3) | HIGH | Manual conflict resolution required. May need to rebase one agent's entire branch. In worst case, one agent's work must be re-done on top of the other's. Prevention is 10x cheaper than recovery. |
| Discord disconnect (Pitfall 4) | LOW | discord.py auto-reconnects. Flush buffered messages on reconnect. Check for any unanswered AskUserQuestion hooks that timed out during the outage. |
| Strategist context saturation (Pitfall 5) | MEDIUM | Reset strategist context with fresh project summary. Re-derive current state from source of truth files (INTERFACES.md, agents.yaml, git log). Review recent decisions for inconsistencies. |
| Hook silent failure (Pitfall 6) | MEDIUM | Kill hung agent, check hook logs, fix hook, redispatch. Agent loses in-progress work since last commit. |
| tmux zombie (Pitfall 7) | LOW | Kill the stale session, redispatch the agent. Work since last commit is lost but the clone's git state is clean. |
| Monitor crash (Pitfall 8) | LOW-MEDIUM | Restart monitor. Agents continue running during monitor downtime but are unsupervised. Check for any missed plan gates or undetected crashes. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Partial plan read | Phase 1 (core infra) | Write a test that creates a PLAN.md slowly (simulated partial write) and verify monitor waits for completion marker |
| Crash recovery loop | Phase 2 (agent lifecycle) | Simulate a persistent crash (bad git state) and verify the system classifies it and stops retrying |
| Late merge conflicts | Phase 2 (dispatch) + Phase 3 (integration) | Run 2 agents that modify adjacent code, verify conflict is detected before integration time |
| Discord gateway disconnect | Phase 1 (Discord bot) | Simulate network interruption (iptables block) and verify bot reconnects and flushes queued messages |
| Strategist context saturation | Phase 3 (strategist) | Run strategist through 50+ decision cycles and verify response quality remains consistent |
| Hook silent failure | Phase 2 (hooks) | Kill Discord mid-hook-execution and verify agent receives fallback response, not a hang |
| tmux zombie detection | Phase 1 (tmux management) | Kill a Claude Code process inside tmux and verify monitor detects the dead agent within 2 cycles |
| Monitor single point of failure | Phase 2 (monitor) | Kill the monitor process and verify the watchdog restarts it within 30 seconds |

## Sources

- [Discord Gateway documentation](https://docs.discord.com/developers/events/gateway)
- [Discord Rate Limits documentation](https://discord.com/developers/docs/topics/rate-limits)
- [discord.py FAQ and tasks documentation](https://discordpy.readthedocs.io/en/stable/faq.html)
- [discord.py rate limit issue #9418](https://github.com/Rapptz/discord.py/issues/9418)
- [inotify(7) Linux manual page](https://man7.org/linux/man-pages/man7/inotify.7.html)
- ["Correct or inotify: pick one" -- wingolog](https://wingolog.org/archives/2018/05/21/correct-or-inotify-pick-one)
- [Claude Code Hooks reference](https://code.claude.com/docs/en/hooks)
- [Claude Code hooks mastery examples](https://github.com/disler/claude-code-hooks-mastery)
- [Clash -- merge conflict detection for parallel AI agents](https://github.com/clash-sh/clash)
- [Git worktrees for parallel AI coding agents](https://devcenter.upsun.com/posts/git-worktrees-for-parallel-ai-coding-agents/)
- [Context window management in agentic systems](https://blog.jroddev.com/context-window-management-in-agentic-systems/)
- [Anthropic: Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [JetBrains Research: Efficient context management for LLM agents](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)
- [Kubernetes CrashLoopBackOff patterns](https://komodor.com/learn/how-to-fix-crashloopbackoff-kubernetes-error/)
- [Scheduler Agent Supervisor pattern -- Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/patterns/scheduler-agent-supervisor)

---
*Pitfalls research for: Autonomous multi-agent orchestration (vCompany)*
*Researched: 2026-03-25*
