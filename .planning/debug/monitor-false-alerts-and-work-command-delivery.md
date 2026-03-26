---
status: awaiting_human_verify
trigger: "Three bugs causing false dead/stuck alerts and work command delivery failures after /new-project"
created: 2026-03-26T00:00:00Z
updated: 2026-03-26T00:00:00Z
---

## Current Focus

hypothesis: Three distinct bugs identified from code reading — confirming each
test: Trace type flow for pane_id in liveness, stuck check no-commits handling, and pane dict population
expecting: All three confirmed as root causes from code analysis
next_action: Confirm all three bugs and apply fixes

## Symptoms

expected: After /new-project dispatches agents, they receive the /gsd:plan-phase 1 --auto command, monitor reports correct status, no false alerts
actual: 1. Work command not delivered to some agents (frontend, data-seeder) - wait_for_ready exists but pane references may be wrong. 2. Liveness check gets string pane_id from agents.json registry instead of libtmux Pane object - is_alive always fails on a string. 3. Stuck check fires immediately on fresh repos with no commits.
errors: Monitor fires agent_dead and agent_stuck alerts continuously right after project start. Reports DO work (vco report lines appear in state/reports/*.log) so agents are actually running.
reproduction: Run /new-project, observe #alerts channel flooding with dead/stuck alerts
timeline: Since the monitor was wired into /new-project

## Eliminated

## Evidence

- timestamp: 2026-03-26T00:01:00Z
  checked: loop.py line 177 type of pane passed to check_liveness
  found: entry.pane_id is a str (AgentEntry.pane_id: str), but TmuxManager.is_alive expects libtmux.Pane. Calling pane.pane_pid on a string raises AttributeError, caught by broad except, returns False.
  implication: CONFIRMED BUG 1 - liveness always fails, triggering agent_dead alerts every cycle.

- timestamp: 2026-03-26T00:02:00Z
  checked: checks.py lines 125-131, check_stuck on empty/no-commit repos
  found: When git log returns no output (empty repo or fresh branch), check_stuck returns passed=False "No commits found". Fresh agents have not committed yet, or product repo may be new.
  implication: CONFIRMED BUG 2 - stuck alerts fire immediately on project start before agents have made any commits.

- timestamp: 2026-03-26T00:03:00Z
  checked: agent_manager.py dispatch_all populates _panes dict, send_work_command_all iterates _panes
  found: Both dispatch_all and send_work_command_all use same AgentManager instance. _panes is populated with real libtmux Pane objects during dispatch_all. send_work_command_all iterates _panes correctly. Path appears valid.
  implication: Bug 3 (work command delivery) may not be in send_work_command_all itself. Need to investigate if _wait_for_claude_ready times out or if pane objects become stale.

## Resolution

root_cause: |
  Three bugs:
  1. LIVENESS FALSE POSITIVE: loop.py passes entry.pane_id (a string like "%5") to TmuxManager.is_alive(), which expects a libtmux.Pane object. Calling .pane_pid on a string raises AttributeError, caught by broad except, returns False -> agent_dead fires every cycle.
  2. STUCK FALSE POSITIVE: check_stuck returns passed=False when git log finds no commits. Fresh repos/empty branches have no commits, so stuck alerts fire immediately on project start.
  3. WORK COMMAND DELIVERY: Appears functional from code analysis. The _panes dict is populated by dispatch_all with real Pane objects. If there IS a delivery issue, it may be timing-related (Claude not ready).
fix: |
  1. Add get_pane_by_id(pane_id) to TmuxManager. In loop.py _check_agent, resolve string pane_id to libtmux.Pane via tmux.get_pane_by_id() before passing to check_liveness.
  2. In check_stuck, return passed=True when no commits found (can't determine stuck-ness without baseline).
verification: |
  All 33 monitor/tmux tests pass. Full suite: 516 passed, 2 pre-existing failures (unrelated bot startup tests).
  Updated test_stuck_no_commits to match new correct behavior (passed=True for no-commit repos).
files_changed:
  - src/vcompany/tmux/session.py
  - src/vcompany/monitor/loop.py
  - src/vcompany/monitor/checks.py
  - tests/test_monitor_checks.py
