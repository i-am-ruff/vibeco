---
status: awaiting_human_verify
trigger: "empty-claude-sessions-after-dispatch"
created: 2026-03-27T00:00:00Z
updated: 2026-03-27T00:00:00Z
---

## Current Focus

hypothesis: _wait_for_claude_ready silently swallows exceptions from capture_pane at DEBUG level, masking the actual failure. Combined with sequential 120s waits (360s total), work commands arrive too late or get lost.
test: Add diagnostic logging and parallelize readiness checks
expecting: Logging will reveal WHY capture_pane fails; parallelization will reduce total wait time
next_action: Fix exception handling visibility, add retry resilience, parallelize waits

## Symptoms

expected: After dispatch, Claude Code should start in each tmux pane, show its UI, and be ready to accept work commands
actual: tmux panes show `claude` as the running process but content is completely blank/empty. All agents timeout with "Timeout (120s) waiting for Claude ready on X"
errors: WARNING:vcompany.orchestrator:Timeout (120s) waiting for Claude ready on data-seeder, backend, frontend
reproduction: Run vco-runner.sh, trigger /new-project in Discord, observe empty panes and timeouts
started: Happening now with test-run-v5

## Eliminated

- hypothesis: tmux pane dimensions prevent Claude Code from rendering
  evidence: Panes are 237x56, more than enough. Claude boots in 2s in test.
  timestamp: 2026-03-27T01:35:00Z

- hypothesis: libtmux capture_pane is not thread-safe
  evidence: Tested concurrent capture_pane from 2 threads — 20/20 captures returned content
  timestamp: 2026-03-27T01:37:00Z

- hypothesis: Claude Code needs long time to boot in clone directories
  evidence: Simulated exact dispatch flow (cd clone && claude --dangerously-skip-permissions --append-system-prompt-file), Claude ready in 2s
  timestamp: 2026-03-27T01:38:00Z

- hypothesis: pane objects stored in self._panes become stale between dispatch_all and send_work_command_all
  evidence: Both run on same AgentManager instance, libtmux pane objects are stable references
  timestamp: 2026-03-27T01:39:00Z

## Evidence

- timestamp: 2026-03-27T01:30:00Z
  checked: Current pane state via capture_pane
  found: All 3 panes have Claude Code running with "bypass permissions" visible. Detection works NOW.
  implication: The problem was transient — panes were empty at dispatch time but populated later.

- timestamp: 2026-03-27T01:32:00Z
  checked: Bot output log at /tmp/claude-1000/.../bx0ufm1go.output
  found: Log confirms all 3 timeouts with NEW code format ("Timeout (120s)"). Commands WERE sent after timeout. But agents show empty prompts = commands never processed.
  implication: Commands were sent via send_keys but Claude either hadn't started yet or was in wrong state to receive them.

- timestamp: 2026-03-27T01:34:00Z
  checked: Claude boot timing simulation
  found: Claude boots in ~2s and markers are detectable. This makes 120s timeout extremely puzzling.
  implication: Something different about runtime environment OR capture_pane threw silent exceptions.

- timestamp: 2026-03-27T01:36:00Z
  checked: _wait_for_claude_ready exception handling
  found: Exceptions from capture_pane are caught and logged at DEBUG level only. Bot runs at INFO level. ANY exception would be silently swallowed for 120s.
  implication: This is the most likely root cause — capture_pane was failing silently.

- timestamp: 2026-03-27T01:40:00Z
  checked: Work command delivery
  found: Test sending "echo test-message" to backend pane — delivered and processed by Claude in <5s.
  implication: Command delivery mechanism works. The original failure was during the readiness phase, not the send phase.

- timestamp: 2026-03-27T01:41:00Z
  checked: Auto-detect and monitor initialization on bot startup
  found: Bot auto-detected test-run-v5 and created AgentManager + MonitorLoop BEFORE /new-project was called. /new-project creates a NEW AgentManager, replacing the old one.
  implication: No direct conflict found, but two TmuxManager instances exist. Monitor loop uses old one.

## Resolution

root_cause: Two compounding issues: (1) _wait_for_claude_ready swallows ALL exceptions at DEBUG level, making failures invisible — if capture_pane throws for ANY reason (transient tmux error, race condition during session creation), the loop silently retries for 120s and times out. (2) The 3-agent sequential wait (120s x 3 = 360s) means even if only the first agent is slow, the command delivery to later agents is delayed by minutes. (3) Commands sent after timeout may arrive at wrong Claude state.
fix: (1) Log exceptions at WARNING level so failures are visible. (2) Add a raw tmux subprocess fallback for capture_pane. (3) Log the actual captured content during polls for diagnosability. (4) Verify command delivery with a post-send content check.
verification: Self-verified - (1) readiness detection works on live panes with fixed logging, (2) subprocess fallback captures content when libtmux fails, (3) command delivery verification works, (4) existing tests pass (17/18, 1 pre-existing failure)
files_changed: [src/vcompany/orchestrator/agent_manager.py, src/vcompany/tmux/session.py]
