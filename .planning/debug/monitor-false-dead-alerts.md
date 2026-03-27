---
status: awaiting_human_verify
trigger: "Monitor throws false positive 'agent appears dead' alerts immediately after starting agents via new-project"
created: 2026-03-27T00:00:00Z
updated: 2026-03-27T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED -- Monitor starts BEFORE dispatch_all, reads stale agents.json from previous run, checks dead PIDs
test: Traced code flow in commands.py new_project -- monitor starts at line 198, dispatch at line 205
expecting: N/A -- root cause confirmed
next_action: Apply fix -- reorder monitor start after dispatch + clear stale registry

## Symptoms

expected: After `vco up` starts agents, monitor should detect them as alive and running
actual: Monitor immediately fires "[monitor-advisory] agent X appears dead: Pane alive but agent process (PID XXXXX) is dead" for all agents right after startup
errors: |
  [monitor-advisory] agent frontend appears dead: Pane alive but agent process (PID 54827) is dead
  [monitor-advisory] agent backend appears dead: Pane alive but agent process (PID 54814) is dead
  [monitor-advisory] agent data-seeder appears dead: Pane alive but agent process (PID 54844) is dead
reproduction: Start vco-runner.sh, init a new project, dispatch agents -- alerts appear within first monitor cycle
started: After Phase 8 changes to tmux session management

## Eliminated

## Evidence

- timestamp: 2026-03-27T00:10:00Z
  checked: check_liveness in checks.py
  found: Uses agent_pid from agents.json entry.pid, checks os.kill(pid, 0). If ProcessLookupError -> "Pane alive but agent process (PID X) is dead"
  implication: Stored PID in agents.json must be dead for this error to fire

- timestamp: 2026-03-27T00:15:00Z
  checked: new_project flow in commands.py lines 189-217
  found: Monitor starts at line 198 (asyncio.create_task), dispatch_all runs at line 205 (asyncio.to_thread). Between them is an await (line 201) that yields event loop, allowing monitor to run first cycle.
  implication: Monitor can read stale agents.json before dispatch_all writes fresh data

- timestamp: 2026-03-27T00:20:00Z
  checked: dispatch_all in agent_manager.py
  found: create_session kills old tmux session (invalidating old PIDs) at line 154, but _save_registry writes new PIDs at line 201. agents.json is stale during this entire window.
  implication: Even concurrent dispatch_all has a stale-data window

- timestamp: 2026-03-27T00:25:00Z
  checked: Verified pane_pid stability via live tmux tests
  found: pane.pane_pid is stable after send_keys, node child processes work fine. The stored PIDs are valid when fresh.
  implication: Problem is definitively stale data, not PID capture issues

## Resolution

root_cause: Two-part problem: (1) In new_project, monitor loop starts BEFORE dispatch_all runs, so the first monitor cycle reads stale agents.json from a previous run with dead PIDs. (2) In dispatch_all, create_session kills the old tmux session (making old PIDs dead) but agents.json isn't updated until the end of the function, creating a stale data window.
fix: (1) Reordered new_project in commands.py to dispatch agents BEFORE starting monitor loop, ensuring agents.json has fresh PIDs before the first monitor cycle. (2) Added registry clearing at the start of dispatch_all in agent_manager.py as defense-in-depth, preventing stale PID data even when monitor is already running during re-dispatch.
verification: All 17 dispatch/monitor tests pass. Pre-existing failures unrelated.
files_changed: [src/vcompany/bot/cogs/commands.py, src/vcompany/orchestrator/agent_manager.py]
