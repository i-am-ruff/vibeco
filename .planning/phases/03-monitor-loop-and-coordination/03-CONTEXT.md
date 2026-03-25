# Phase 3: Monitor Loop and Coordination - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the monitor loop that continuously supervises agents (liveness, stuck detection, plan gate), generates and distributes PROJECT-STATUS.md across all clones, implements the INTERFACES.md contract system with change request flow, and creates the central INTERACTIONS.md reference for known interaction patterns.

</domain>

<decisions>
## Implementation Decisions

### Monitor Loop Core
- **D-01:** Monitor runs as an asyncio loop, checking each agent every 60 seconds with independent try/except per agent check (one agent's failure doesn't crash the monitor).
- **D-02:** Liveness check: uses TmuxManager.is_alive() from Phase 1 to verify pane exists, plus /proc PID validation from Phase 2's AgentManager pattern.
- **D-03:** Stuck detection: check git log in each clone for commits in last 30 minutes. No commits = stuck. Alert to Discord #alerts (placeholder callback until Phase 4).
- **D-04:** Monitor runs under a watchdog: writes a heartbeat file every cycle with timestamp. A simple secondary process (or systemd WatchdogSec) checks the heartbeat file age. If stale > 3 minutes, restarts monitor.

### Plan Gate (Option C — Monitor Intercepts Auto-Advance)
- **D-05:** When monitor detects new PLAN.md files in an agent's clone (by scanning .planning/phases/ for files newer than last check), it does NOT trigger execute-phase.
- **D-06:** Instead, monitor posts plans to Discord #plan-review channel (placeholder callback until Phase 4). Agent sits idle at the prompt — no spinning, no lock files.
- **D-07:** On PM approval (received via callback from Phase 4's Discord bot), monitor sends the `/gsd:execute-phase {N}` command to the agent's tmux pane via TmuxManager.send_command().
- **D-08:** On PM rejection, monitor sends the rejection feedback to the agent's tmux pane as a new prompt instructing it to re-plan with the given feedback.
- **D-09:** Plan detection uses file modification time comparison, not filesystem watchers (inotify). Polling at 60s is sufficient and more reliable.

### PROJECT-STATUS.md Generation
- **D-10:** Monitor reads each clone's `.planning/ROADMAP.md` (phase progress), `git log --oneline -5` (recent activity), and agents.json (agent state) every cycle.
- **D-11:** Assembles into PROJECT-STATUS.md using the exact format from VCO-ARCHITECTURE.md (per-agent phase list with emoji status, Key Dependencies section, Notes section).
- **D-12:** Writes to `{project}/context/PROJECT-STATUS.md` using write_atomic, then copies to each clone's root directory using write_atomic.
- **D-13:** `vco sync-context` command pushes updated INTERFACES.md, MILESTONE-SCOPE.md, and STRATEGIST-PROMPT.md to all clones (also using write_atomic).

### INTERFACES.md Contract System
- **D-14:** Agent proposes exact diff to INTERFACES.md via AskUserQuestion (routed through Discord in Phase 5).
- **D-15:** PM/Strategist reviews the proposal — approves or rejects with reasoning. PM's role is judgment only, not editing.
- **D-16:** On approval, orchestrator applies the agent's proposed diff to the canonical `{project}/context/INTERFACES.md` and distributes to all clones via sync-context.
- **D-17:** Change requests are logged in a `{project}/context/interface_changes.json` file (append-only) for audit trail.

### Monitor Watchdog
- **D-18:** Heartbeat file: `{project}/state/monitor_heartbeat` — updated with ISO timestamp every monitor cycle.
- **D-19:** Watchdog check: separate lightweight process or cron job checks heartbeat age. If > 180 seconds (3 missed cycles), restart monitor and alert.

### Claude's Discretion
- Internal monitor state management (how to track "last check time" per agent)
- Exact PROJECT-STATUS.md generation implementation (template vs string building)
- sync-context file copy strategy (parallel vs sequential per clone)
- Interface change diff application method (text patch vs full replacement)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `VCO-ARCHITECTURE.md` — Monitor loop section (lines 936-956), PROJECT-STATUS.md example (lines 260-298), INTERFACES.md contract system, sync-context command

### Phase 1+2 Code (reuse these)
- `src/vcompany/tmux/session.py` — TmuxManager.is_alive(), send_command() for plan gate
- `src/vcompany/orchestrator/agent_manager.py` — AgentManager reads agents.json for running agents list
- `src/vcompany/orchestrator/crash_tracker.py` — on_circuit_open callback pattern (reuse for monitor alerts)
- `src/vcompany/shared/file_ops.py` — write_atomic for all coordination file writes
- `src/vcompany/models/config.py` — ProjectConfig for project/agent metadata
- `src/vcompany/git/ops.py` — log() for git commit history checks (stuck detection)
- `src/vcompany/cli/main.py` — Click CLI group, add monitor/sync-context commands

### Research
- `.planning/research/PITFALLS.md` — Monitor as single point of failure (Pitfall), filesystem race conditions
- `.planning/research/ARCHITECTURE.md` — Supervisor/polling pattern, filesystem-as-IPC

### Requirements
- `.planning/REQUIREMENTS.md` — MON-01..08, COORD-01..03, SAFE-03

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `TmuxManager` — is_alive() for liveness, send_command() for plan gate approve/reject
- `write_atomic()` — for PROJECT-STATUS.md writes and distribution
- `git.ops.log()` — for stuck detection (check recent commits)
- `AgentManager` — reads agents.json to enumerate running agents
- `CrashTracker.on_circuit_open` — callback pattern to reuse for monitor alert hooks

### Established Patterns
- Callback injection for cross-phase integration (on_circuit_open from Phase 2)
- Pydantic models for state files (agents.json, crash_log.json — same for interface_changes.json)
- Click commands for CLI (add `vco monitor`, `vco sync-context`)

### Integration Points
- Monitor calls TmuxManager.is_alive() and send_command()
- Monitor reads agents.json (written by AgentManager)
- Monitor triggers CrashTracker recovery when dead agent detected
- Plan gate callback connects to Phase 4 Discord bot
- sync-context reuses write_atomic for clone distribution

</code_context>

<specifics>
## Specific Ideas

- Plan gate uses the "agent sits idle at prompt" approach — no lock files, no SIGSTOP, no hooks
- Monitor sends commands to tmux panes to control agent flow (approve → send execute command, reject → send re-plan prompt)
- Contract changes are agent-proposed, PM-judged, orchestrator-applied — PM never edits code

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-monitor-loop-and-coordination*
*Context gathered: 2026-03-25*
