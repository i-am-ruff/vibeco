# Phase 2: Agent Lifecycle and Pre-flight - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver agent lifecycle management: `vco dispatch` launches Claude Code sessions in tmux panes with system prompts; `vco kill` terminates agents gracefully or forcefully; `vco relaunch` restarts with /gsd:resume-work; crash recovery auto-relaunches with exponential backoff and circuit breaker. Pre-flight tests validate Claude Code headless behavior before first real project.

</domain>

<decisions>
## Implementation Decisions

### Dispatch Mechanics
- **D-01:** `vco dispatch {agent-id}` launches `claude --dangerously-skip-permissions --append-system-prompt {agent_prompt_file}` in a tmux pane via the TmuxManager wrapper from Phase 1.
- **D-02:** `vco dispatch all` creates a tmux session named after the project, one pane per agent plus a monitor pane. Uses the tmux wrapper's create_session() and create_pane().
- **D-03:** Initial command sent to each pane: `claude --dangerously-skip-permissions --append-system-prompt {context/agents/{id}.md} -p '/gsd:new-project'` for fresh starts, or `-p '/gsd:resume-work'` for relaunches.
- **D-04:** Environment variables set per pane before launch: DISCORD_AGENT_WEBHOOK_URL, PROJECT_NAME, AGENT_ID, AGENT_ROLE.
- **D-05:** Dispatch records each agent's PID and tmux pane ID in a `{project}/state/agents.json` file for monitor/kill/relaunch to reference.

### Kill and Relaunch
- **D-06:** `vco kill {agent-id}` first sends SIGTERM to the Claude Code process, waits 10s, then SIGKILL if still alive. Falls back to killing the tmux pane.
- **D-07:** `vco relaunch {agent-id}` runs kill then dispatch with `-p '/gsd:resume-work'` flag.
- **D-08:** Both kill and relaunch update agents.json state file atomically.

### Crash Recovery
- **D-09:** Crash detection: monitor (Phase 3) checks tmux pane liveness. When dead, triggers recovery in this module.
- **D-10:** Crash classification before retry:
  - **Transient:** Clean exit (code 0) with checkpoint file existing → context exhaustion, safe to relaunch
  - **Transient:** Exit code non-zero but no corrupt state → API timeout or runtime error, safe to relaunch
  - **Persistent:** Same error message in last 2 crash logs → likely code/config issue, do NOT relaunch
  - **Persistent:** Corrupt .planning/ directory (missing STATE.md, broken ROADMAP.md) → requires manual intervention
- **D-11:** Exponential backoff between retries: 30s, 2min, 10min.
- **D-12:** Circuit breaker: max 3 crashes/hour per agent. On 4th crash, stop relaunch, alert Discord #alerts, require manual `!relaunch` to reset.
- **D-13:** Crash state tracked in `{project}/state/crash_log.json` with timestamps, exit codes, classification, and retry count.

### Pre-flight Tests
- **D-14:** Pre-flight test suite is a standalone Python script: `vco preflight` command.
- **D-15:** Tests run against a dummy project (temp dir with minimal agents.yaml).
- **D-16:** 4 tests from architecture doc:
  1. stream-json heartbeat reliability (can we read agent output in real time?)
  2. Permission hang behavior without --dangerouslySkipPermissions (does it hang or error?)
  3. --max-turns clean exit behavior (does it exit cleanly when turns exhausted?)
  4. --resume session recovery (can a killed session resume from checkpoint?)
- **D-17:** Results written to `{project}/state/preflight_results.json`. Monitor strategy determined by results (stream-json for liveness if reliable, git-commit fallback otherwise).

### Claude's Discretion
- Crash log format and rotation policy
- Pre-flight test timeout values
- Exact tmux session naming convention
- Whether to support `vco dispatch --dry-run` for validation without launching

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `VCO-ARCHITECTURE.md` — Agent dispatch section (lines 170-250), crash recovery table, pre-flight tests section
- `.planning/PROJECT.md` — Active requirements LIFE-01..07, PRE-01..03

### Phase 1 Code (reuse these)
- `src/vcompany/tmux/session.py` — TmuxManager wrapper, use for all tmux operations
- `src/vcompany/git/ops.py` — GitResult, git_clone, git_checkout_branch
- `src/vcompany/shared/file_ops.py` — write_atomic for crash state files
- `src/vcompany/cli/main.py` — Click CLI group, add dispatch/kill/relaunch/preflight here
- `src/vcompany/models/config.py` — AgentConfig, ProjectConfig, load_config

### Research
- `.planning/research/PITFALLS.md` — Crash recovery anti-patterns, tmux zombie detection
- `.planning/research/ARCHITECTURE.md` — Supervisor patterns, process management

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `TmuxManager` (src/vcompany/tmux/session.py): create_session, create_pane, send_command, is_alive, kill_pane — all needed for dispatch/kill
- `write_atomic` (src/vcompany/shared/file_ops.py): for crash_log.json and agents.json state writes
- `load_config` (src/vcompany/models/config.py): parse agents.yaml to get agent roster for dispatch all
- Click CLI group (src/vcompany/cli/main.py): add dispatch, kill, relaunch, preflight subcommands

### Established Patterns
- Subprocess-based operations with structured result types (GitResult pattern from Phase 1)
- Atomic file writes for all shared state
- Click decorators for CLI commands with project-dir option

### Integration Points
- TmuxManager.create_pane() for launching agent sessions
- TmuxManager.is_alive() will be called by monitor (Phase 3) for crash detection
- agents.json state file bridges dispatch (this phase) and monitor (Phase 3)

</code_context>

<specifics>
## Specific Ideas

- Use the same project directory structure from Phase 1: `~/vcompany/projects/{project}/state/` for runtime state
- Pre-flight results should be human-readable (not just JSON) — include pass/fail summary on stdout
- Crash classification should be extensible — new failure patterns can be added without changing the recovery logic

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-agent-lifecycle-and-pre-flight*
*Context gathered: 2026-03-25*
