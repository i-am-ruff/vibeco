# Feature Research

**Domain:** Autonomous multi-agent software development orchestration
**Researched:** 2026-03-25
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features that must work or the system is unusable. No credit for having them, but fatal if missing.

#### Agent Lifecycle Management

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Agent spawning with isolated workspaces | Agents editing the same files guarantees corruption. Isolation is the minimum viable coordination. | MEDIUM | Each agent gets its own repo clone with directory ownership defined in agents.yaml. Overstory and Agent-MCP both use this pattern. |
| Agent liveness monitoring | Without liveness checks, a dead agent looks like a working one. The operator has no visibility. | MEDIUM | 60s poll cycle checking process status (tmux pane alive, PID running). Overstory uses a tiered watchdog: Tier 0 mechanical daemon, Tier 1 AI-assisted triage. |
| Crash recovery with automatic relaunch | Claude Code sessions crash. Without auto-relaunch, a single crash stalls the entire pipeline until a human notices. | MEDIUM | Auto-restart with exponential backoff and a circuit breaker (max 3/hour, alert on 4th). Resume from last known state via /gsd:resume-work. Standard pattern across OmniDaemon, Kubernetes, systemd. |
| Agent termination (graceful and forced) | Operator must be able to stop runaway agents immediately. No kill switch = no safety. | LOW | Graceful: signal agent to finish current task. Forced: kill tmux pane. Both must work. |
| Process isolation | One agent crashing or looping must not affect others. Shared-process designs create cascading failures. | MEDIUM | Separate tmux panes, separate git clones, separate Claude Code sessions. OmniDaemon runs each agent in its own isolated process for exactly this reason. |

#### Communication and Coordination

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Shared status awareness (PROJECT-STATUS.md) | Agents working blind to each other's state produce contradictory or duplicate work -- the "passing ships problem." | MEDIUM | Monitor regenerates cross-agent status file and distributes to all clones every cycle. This is the shared scratchpad pattern identified as the structural fix for passing ships. |
| Interface contracts (INTERFACES.md) | Without explicit API contracts between agent domains, integration is guaranteed to fail. Each agent invents its own assumptions. | MEDIUM | Single source of truth for boundaries. Change requests flow through PM approval before distribution. Mirrors the "context synchronization" pattern in production multi-agent systems. |
| Agent-to-orchestrator status reporting | The orchestrator cannot make decisions (relaunch, reassign, integrate) without knowing agent state. | LOW | /vco:checkin command: fire-and-forget status post after each phase ships. Simple, unidirectional, low-overhead. |

#### Human-in-the-Loop

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Plan review gate | Agents executing unreviewed plans can waste hours building the wrong thing. Plan gates are the minimum viable oversight. | HIGH | Monitor detects PLAN.md, pauses agent, posts to #plan-review, waits for PM/owner approval. This is the "calibrated autonomy" pattern: full autonomy for execution, human gate for strategy. LangGraph's checkpointing enables equivalent pause-resume. |
| Question routing to humans | Agents that hang on unanswered questions block the entire pipeline. Questions must reach a human and return answers or timeouts. | MEDIUM | AskUserQuestion hook intercepts, routes through Discord, 10-min timeout with fallback. The PM/Strategist answers most questions autonomously; only low-confidence ones escalate to owner. |
| Owner escalation for high-stakes decisions | Not all decisions are equal. Some require human judgment. Without escalation, the system either blocks on everything or lets bad decisions through. | MEDIUM | Strategist confidence scoring (high/medium/low) with automatic @Owner mention on low-confidence decisions. Maps to the "approval queue with threshold calibration" pattern from production HITL systems. |

#### Monitoring and Observability

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Stuck agent detection | An agent spinning for 30+ minutes with no commits is wasting compute and blocking progress. Must be detected automatically. | MEDIUM | Monitor checks for commits in last 30 minutes. No commits = stuck. Alert + option to kill/relaunch. This catches infinite loops and context abandonment -- two top failure modes identified in agent observability research. |
| Aggregate status dashboard | Operator needs a single view of all agents: who is working, who is stuck, who finished, what phase each is in. | MEDIUM | !status command in Discord assembles cross-agent state. PROJECT-STATUS.md serves as the persistent version. |
| Alert system for failures | Silent failures are the worst failures. Crashes, stuck agents, repeated restarts must surface immediately. | LOW | Discord #alerts channel for crash notifications, stuck detection alerts, circuit breaker triggers. |

#### Integration

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Branch-per-agent with merge pipeline | Agents must work on separate branches. Integration must be an explicit, orchestrated step -- not ad-hoc merges. | MEDIUM | Each agent commits to its own branch. Integration pipeline merges all branches, runs tests, identifies failures. This is the universal pattern -- Agent-MCP, Overstory, and every production system uses branch isolation. |
| Automated test execution post-merge | Merging without testing is merging blind. Tests catch integration issues that no amount of contract design prevents. | MEDIUM | Run full test suite after merge. Report failures with attribution to specific agent branches. |
| Merge conflict detection and reporting | When conflicts occur (and they will, despite file ownership), they must be surfaced clearly with enough context to resolve. | MEDIUM | Detect conflicts during merge, report to Discord with file list and conflict details. Human or PM decides resolution strategy. |

#### Configuration

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Declarative agent roster (agents.yaml) | Hardcoded agent definitions make the system non-reusable. Configuration must be external and project-specific. | LOW | Agent ID, owned directories, shared_readonly, GSD mode, system prompts. Standard YAML config. |
| Per-agent GSD configuration injection | Each agent needs appropriate autonomy settings. A research agent needs different GSD config than a frontend agent. | LOW | Inject yolo mode, assumption settings, system prompts into each clone's .gsd/ directory. |

### Differentiators (Competitive Advantage)

Features that set vCompany apart from both Claude Code's built-in Agent Teams and manual multi-agent setups.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| PM/Strategist bot as autonomous decision layer | Claude Code Agent Teams has a "team lead" but no persistent PM with project context that makes product decisions. The Strategist absorbs blueprint/milestone scope and answers agent questions without human involvement for high-confidence decisions. This is the "human-on-the-loop" pattern -- agents handle routine, humans handle edge cases. | HIGH | Requires Anthropic SDK integration, context management for large projects, confidence calibration. This is the hardest and highest-value feature. |
| Discord-native operation | Competing approaches (Agent Teams, Overstory, oh-my-claudecode) are terminal-native. Discord means the owner can dispatch, monitor, and intervene from a phone. Async-first, not session-bound. | MEDIUM | Discord.py bot with structured channel layout. Not technically novel but operationally transformative -- breaks the "must be at your terminal" constraint. |
| Contract-driven agent coordination | Most multi-agent systems use shared memory or message passing. INTERFACES.md is a higher-level abstraction: agents coordinate through explicit API contracts, not runtime messages. Changes require PM approval. This prevents the "cascading hallucination" problem where one agent's bad output propagates. | MEDIUM | The contract is a file, not a protocol. Simple to implement, powerful in effect. Agents read contracts at startup and when updated. |
| Filesystem-level plan gating | Claude Code Agent Teams has no plan review mechanism. Plans execute immediately. vCompany's monitor detects PLAN.md creation and pauses the agent externally, which is more reliable than in-session hooks because it survives context loss. | MEDIUM | Monitor watches filesystem, creates a lock file or sends SIGSTOP, posts plan to Discord. Resumes on approval. More robust than hook-based gating. |
| Project-agnostic orchestration | Most multi-agent coding tools are either framework-specific or require custom wiring per project. vCompany takes a blueprint + agents.yaml and orchestrates any project type. | LOW | This is a design constraint more than a feature -- but it becomes a differentiator when competing tools require per-project customization. |
| Structured standup and checkin rituals | No competing system has formalized team rituals (standups, checkins) for AI agents. These create natural synchronization points and give the owner a narrative of progress, not just status. | LOW | /vco:standup triggers interactive group standup with threaded feedback. /vco:checkin is fire-and-forget after each phase. Lightweight but creates rhythm. |
| Context-aware crash recovery | Basic crash recovery restarts the process. vCompany's recovery uses /gsd:resume-work to reload context and continue from the last phase -- not from scratch. Combined with PROJECT-STATUS.md distribution, a recovered agent knows what happened while it was down. | MEDIUM | Requires GSD's resume mechanism + fresh status injection. More sophisticated than simple process restart. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems. Deliberately NOT building these.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Real-time agent-to-agent messaging | Feels natural -- "agents should talk to each other like team members." | Creates tight coupling, message storms, and the echo chamber effect where agents reinforce each other's errors. Research shows centralized designs contain errors better than decentralized "bag of agents" designs. Inter-agent chat also burns context tokens rapidly. | Indirect coordination through shared artifacts (PROJECT-STATUS.md, INTERFACES.md). Agents communicate through the orchestrator and shared files, not direct channels. |
| Dynamic agent spawning based on workload | "The system should spin up more agents when there's more work." | Uncontrolled spawning exhausts machine resources (single-machine constraint), creates merge chaos with more branches, and makes the system unpredictable. Each new agent needs a clone, a tmux pane, and API quota. | Fixed agent roster in agents.yaml. The operator decides how many agents run. Scale is a human decision, not an automated one. |
| Automatic merge conflict resolution | "AI should resolve its own merge conflicts." | LLM-resolved conflicts may compile but introduce subtle semantic errors. In multi-agent systems, conflicts often signal a contract violation -- the resolution is to fix the contract, not to guess at the merge. Auto-resolution hides the real problem. | Detect and report conflicts to Discord. Human or PM decides strategy. Fix the contract (INTERFACES.md) that allowed the conflict. |
| Web UI / dashboard | "Discord is limiting -- build a proper web interface." | A web UI is a separate product. It doubles the surface area, requires hosting, authentication, state synchronization. Discord is already a real-time, multi-device, multi-user interface with threading, permissions, and notifications built in. | Discord is the interface. Invest in rich Discord messages (embeds, buttons, threads) rather than building a parallel UI. |
| Multi-machine distributed agents | "Run agents across multiple machines for more parallelism." | Network partitions, distributed state, clock sync, SSH management -- each is a project unto itself. Single-machine is a massive simplification that eliminates entire categories of failure modes. | Single machine, v1. The architecture (agents.yaml, branch-per-agent) is compatible with future distribution, but don't build for it now. |
| Full autonomy mode (no human gates) | "Remove the plan gate for speed -- trust the agents." | Without oversight, agents can waste hours on wrong approaches. The plan gate costs minutes but saves hours. Research consistently shows that "human-on-the-loop" outperforms full autonomy for complex tasks. The 17x error amplification in unsupervised multi-agent systems is well-documented. | Keep plan gate. Make PM/Strategist handle most approvals automatically. The human only sees low-confidence escalations. Speed comes from smarter automation, not removed oversight. |
| Fine-grained task assignment by orchestrator | "The orchestrator should break down the milestone into specific tasks and assign them to agents." | This requires the orchestrator to understand the codebase deeply enough to decompose work -- which is the hard part of software engineering. Over-specifying tasks also removes agent autonomy, making them less effective. | Give agents ownership of directories/domains and milestone scope. Let GSD handle task decomposition within each agent's domain. The orchestrator coordinates, not micromanages. |

## Feature Dependencies

```
[Agent Spawning with Isolated Workspaces]
    +--requires--> [Declarative Agent Roster (agents.yaml)]
    +--requires--> [Per-agent GSD Configuration Injection]

[Crash Recovery]
    +--requires--> [Agent Liveness Monitoring]
    +--requires--> [Agent Spawning] (to relaunch)

[Plan Review Gate]
    +--requires--> [Agent Liveness Monitoring] (to detect PLAN.md)
    +--requires--> [Discord Bot] (to post for review)
    +--requires--> [PM/Strategist Bot] (to review plans)

[PM/Strategist Bot]
    +--requires--> [Discord Bot] (as communication channel)
    +--requires--> [Question Routing] (to receive agent questions)

[Integration Pipeline]
    +--requires--> [Branch-per-Agent]
    +--requires--> [Automated Test Execution]
    +--requires--> [Merge Conflict Detection]

[Shared Status Awareness]
    +--requires--> [Agent Liveness Monitoring] (monitor generates status)
    +--requires--> [Agent-to-Orchestrator Reporting] (agents report state)

[Stuck Detection]
    +--requires--> [Agent Liveness Monitoring]
    +--enhances--> [Crash Recovery] (stuck = soft crash)

[Structured Standups]
    +--enhances--> [Shared Status Awareness]
    +--requires--> [Discord Bot]

[Owner Escalation]
    +--requires--> [PM/Strategist Bot] (confidence scoring)
    +--requires--> [Discord Bot] (@Owner mention)

[Contract-Driven Coordination]
    +--enhances--> [Integration Pipeline] (fewer conflicts)
    +--enhances--> [Shared Status Awareness] (clearer boundaries)
```

### Dependency Notes

- **Plan Review Gate requires PM/Strategist Bot:** The PM reviews plans before they reach the owner. Without the PM, every plan needs human review, which defeats autonomous operation.
- **Crash Recovery requires Liveness Monitoring:** You cannot recover what you cannot detect. The monitor loop is the foundation for all reactive features.
- **Integration Pipeline requires Branch-per-Agent:** Integration is meaningless without branch isolation. The merge step assumes independent branches.
- **PM/Strategist Bot requires Discord Bot:** The Strategist communicates entirely through Discord. No bot = no Strategist.
- **Stuck Detection enhances Crash Recovery:** A stuck agent is a soft failure. Detection feeds into the same recovery pipeline as hard crashes.

## MVP Definition

### Launch With (v1)

Minimum viable product -- what's needed to validate that multi-agent orchestration produces working integrated code.

- [x] Agent spawning with isolated clones and directory ownership -- the foundation
- [x] agents.yaml configuration with per-agent GSD injection -- makes it project-agnostic
- [x] tmux session management (one pane per agent + monitor) -- process isolation
- [x] Monitor loop: liveness check, stuck detection, status regeneration -- the heartbeat
- [x] Crash recovery with circuit breaker (3 restarts/hour) -- resilience
- [x] Branch-per-agent with integration pipeline (merge + test) -- the payoff
- [x] Discord bot with !dispatch, !status, !kill, !relaunch, !integrate -- operator control
- [x] AskUserQuestion hook routing through Discord -- prevents terminal hang
- [x] Plan review gate with Discord posting -- minimum viable oversight
- [x] PROJECT-STATUS.md generation and distribution -- agent coordination
- [x] INTERFACES.md contract system -- prevents integration chaos
- [x] #alerts channel for crashes and stuck agents -- failure visibility

### Add After Validation (v1.x)

Features to add once core orchestration is proven to work.

- [ ] PM/Strategist bot -- add when plan reviews and agent questions are overwhelming the human owner
- [ ] Confidence-based owner escalation -- add alongside Strategist
- [ ] Structured standups and checkins -- add when running multi-day milestones where progress narrative matters
- [ ] Per-agent Discord channels (#agent-{id}) -- add when agent logs in #alerts become noisy
- [ ] Role-based access control on Discord commands -- add when multiple humans interact with the system
- [ ] Merge conflict detection with attribution -- add when file ownership boundaries prove insufficient

### Future Consideration (v2+)

Features to defer until the core system is battle-tested.

- [ ] Strategist context summarization for large projects -- defer until context limits are actually hit
- [ ] Sophisticated crash analysis (why did it crash, not just that it crashed) -- defer until crash patterns are understood
- [ ] Agent performance metrics and analytics -- defer until there's enough history to analyze
- [ ] Multi-project concurrent orchestration -- defer until single-project is solid

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Agent spawning + isolation | HIGH | MEDIUM | P1 |
| agents.yaml + GSD injection | HIGH | LOW | P1 |
| Monitor loop (liveness, stuck, status) | HIGH | MEDIUM | P1 |
| Crash recovery + circuit breaker | HIGH | MEDIUM | P1 |
| Discord bot (core commands) | HIGH | MEDIUM | P1 |
| Branch-per-agent + integration pipeline | HIGH | MEDIUM | P1 |
| AskUserQuestion hook | HIGH | MEDIUM | P1 |
| Plan review gate | HIGH | HIGH | P1 |
| PROJECT-STATUS.md distribution | MEDIUM | MEDIUM | P1 |
| INTERFACES.md contracts | MEDIUM | LOW | P1 |
| PM/Strategist bot | HIGH | HIGH | P2 |
| Owner escalation (confidence scoring) | MEDIUM | MEDIUM | P2 |
| Structured standups/checkins | MEDIUM | LOW | P2 |
| Per-agent Discord channels | LOW | LOW | P2 |
| Role-based access control | LOW | MEDIUM | P2 |
| Strategist context summarization | MEDIUM | HIGH | P3 |
| Agent performance analytics | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch -- system does not function without these
- P2: Should have, add when core is validated and working
- P3: Nice to have, future consideration after battle-testing

## Competitor Feature Analysis

| Feature | Claude Code Agent Teams | Overstory | Agent-MCP | vCompany Approach |
|---------|------------------------|-----------|-----------|-------------------|
| Agent isolation | Separate context windows, shared filesystem | Separate processes, tiered watchdog | File-level locking | Separate repo clones with directory ownership |
| Communication | Direct teammate messaging | SQLite mail system (WAL mode) | Shared task board | Indirect via shared artifacts (STATUS, INTERFACES) |
| Human oversight | None built-in | Not specified | Not specified | Plan gate + PM/Strategist + owner escalation |
| Crash recovery | Session-level only | Auto-restart with crash protection | Not specified | Auto-relaunch with /gsd:resume-work + circuit breaker |
| Integration | Not applicable (shared workspace) | Git-based with branch management | File locking prevents conflicts | Branch-per-agent + merge pipeline + test execution |
| Operator interface | Terminal | Terminal/CLI | Terminal | Discord (async, multi-device) |
| Configuration | Settings.json flag | YAML config | JSON config | agents.yaml + per-agent GSD injection |
| Stuck detection | Not built-in | Tiered watchdog system | Not specified | Commit-based stuck detection (30min threshold) |
| Project agnostic | Yes (general purpose) | Yes (pluggable adapters) | Partially (needs custom setup) | Yes (blueprint + agents.yaml) |
| Autonomous PM | No | No | No | Yes (Strategist bot with confidence scoring) |

**Key competitive insight:** No existing system combines an autonomous PM layer with Discord-native operation. Claude Code Agent Teams is the closest competitor but is terminal-bound and lacks plan oversight. Overstory has the best observability (tiered watchdog) but no human-in-the-loop patterns. vCompany's differentiator is the full loop: autonomous operation with calibrated human oversight, operable from anywhere.

## Sources

- [Anthropic: Building a C compiler with parallel Claudes](https://www.anthropic.com/engineering/building-c-compiler) -- Anthropic's own multi-agent coding case study
- [Claude Code Agent Teams Docs](https://code.claude.com/docs/en/agent-teams) -- Official documentation for competing built-in feature
- [Chanl: Multi-Agent Patterns That Work in Production](https://www.chanl.ai/blog/multi-agent-orchestration-patterns-production-2026) -- Production pattern analysis, hierarchical orchestration recommendation
- [Towards Data Science: 17x Error Trap of Bag of Agents](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/) -- Error amplification in decentralized multi-agent systems
- [Overstory: Multi-agent orchestration for AI coding agents](https://github.com/jayminwest/overstory) -- Tiered watchdog, SQLite mail system patterns
- [Agent-MCP: Multi-agent via Model Context Protocol](https://github.com/rinadelph/Agent-MCP) -- File-level locking, task assignment patterns
- [GoCodeo: Collaborative Coding with AI](https://www.gocodeo.com/post/collaborative-coding-with-ai-managing-multiple-agents-generating-code) -- Merge strategy, file ownership, coordination patterns
- [MyEngineeringPath: Human-in-the-Loop Patterns 2026](https://myengineeringpath.dev/genai-engineer/human-in-the-loop/) -- Calibrated autonomy, threshold recalibration
- [OmniDaemon: Event-Driven Runtime for AI Agents](https://github.com/omnirexflora-labs/OmniDaemon) -- Process isolation, auto-restart, crash protection patterns
- [Deloitte: AI Agent Orchestration](https://www.deloitte.com/us/en/insights/industry/technology/technology-media-and-telecom-predictions/2026/ai-agent-orchestration.html) -- Human-in/on/out-of-the-loop autonomy spectrum
- [Microsoft Multi-Agent Reference Architecture: Observability](https://microsoft.github.io/multi-agent-reference-architecture/docs/observability/Observability.html) -- Agent observability patterns
- [Claude Code Hooks Multi-Agent Observability](https://github.com/disler/claude-code-hooks-multi-agent-observability) -- Hook-based monitoring for Claude Code agents

---
*Feature research for: Autonomous multi-agent software development orchestration*
*Researched: 2026-03-25*
