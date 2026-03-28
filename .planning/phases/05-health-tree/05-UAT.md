---
status: partial
phase: 05-health-tree (milestone-wide UAT)
source: [all phase SUMMARY.md and VERIFICATION.md files]
started: 2026-03-28T06:00:00Z
updated: 2026-03-28T06:30:00Z
---

## Current Test

[testing stopped — v2 not operational end-to-end]

## Tests

### 1. Cold Start — Bot Boots with HealthCog
expected: Bot boots, HealthCog loads, /health appears in slash commands
result: pass

### 2. /health Command — Full Tree View
expected: /health shows supervision tree hierarchy with state emoji
result: issue
reported: "Health tree shows flat agent list, no CompanyRoot or ProjectSupervisor nodes. Agents show as 'running' even when nothing is actually running. Ghost state from previous runs persists. After clean start and /new-project, still shows flat list with no hierarchy."
severity: major

### 3. /health project=<id> — Filtered View
expected: /health project=<id> shows only that project subtree
result: pass

### 4. State-Change Push Notification
expected: Agent state transitions push to #alerts automatically
result: skipped
reason: No live agents running to trigger state change

### 5. Slash Commands Only — No ! Prefix
expected: ! prefix commands don't work, only slash commands
result: pass

### 6. CompanyRoot Supervision Startup
expected: After /new-project, supervision tree actively manages agent containers
result: issue
reported: "After /new-project, agents show as 'running (idle)' but nothing actually changed from v1 behavior. The dispatch path still uses old tmux-based flow. The supervision tree exists in memory but doesn't drive real agent lifecycle. No visible difference from v1."
severity: blocker

### 7. Degraded Mode — Claude API Down
expected: System enters degraded mode when Claude unreachable
result: blocked
blocked_by: other
reason: "Can't simulate Claude API outage in testing"

### 8. Message Queue — Rate Limit Handling
expected: Outbound messages flow through MessageQueue with priority
result: blocked
blocked_by: other
reason: "Can't observe internal queue behavior from Discord"

### 9. Living Backlog — PM Assignment
expected: PM has BacklogQueue assigned, processes events
result: issue
reported: "Nothing works after starting the project. V2 container system is not operational end-to-end. The bot still runs v1 logic paths."
severity: blocker

## Summary

total: 9
passed: 3
issues: 3
pending: 0
skipped: 1
blocked: 2

## Gaps

- truth: "Supervision tree actively manages agent containers through the new v2 lifecycle"
  status: failed
  reason: "User reported: v2 container system is built and unit-tested but not operational end-to-end. The bot's dispatch/lifecycle commands still execute v1 logic paths. The supervision tree, container FSMs, health reporting, resilience, and autonomy modules exist with 900+ passing unit tests but are not driving real agent behavior in the running Discord bot."
  severity: blocker
  test: 2, 6, 9
  artifacts: [src/vcompany/bot/client.py, src/vcompany/bot/cogs/commands.py, src/vcompany/bot/cogs/workflow_orchestrator_cog.py]
  missing: ["Deep integration — dispatch/kill/relaunch must use container lifecycle instead of raw tmux", "Health tree must reflect actual tmux session state, not phantom in-memory containers", "/status command should be removed or replaced by /health", "Agent 'running' state must correlate with actual tmux pane liveness"]
