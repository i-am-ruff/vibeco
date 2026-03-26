---
phase: quick
plan: 01
subsystem: cli/report, monitor, bot/commands
tags: [discord, reporting, monitor, advisory]
dependency_graph:
  requires: []
  provides: [direct-discord-reporting, monitor-advisory-pipeline, toggle-advisories-command]
  affects: [agent_manager-dispatch-env-vars, monitor-loop-callbacks, commands-cog]
tech_stack:
  added: []
  patterns: [direct-discord-http-api-posting, channel-id-caching, advisory-callback-pattern]
key_files:
  created:
    - tests/test_report_cmd.py
  modified:
    - src/vcompany/cli/report_cmd.py
    - src/vcompany/orchestrator/agent_manager.py
    - src/vcompany/monitor/loop.py
    - src/vcompany/bot/cogs/commands.py
    - tests/test_monitor_loop.py
decisions:
  - "Direct Discord HTTP API via httpx with Bot token auth instead of webhook URL"
  - "Module-level dict cache for channel_id lookup to avoid repeated API calls"
  - "Advisory callback is async (Awaitable) matching existing callback patterns"
  - "Advisories default to enabled, toggled via /toggle-advisories"
metrics:
  duration: 3min
  completed: "2026-03-26"
---

# Quick Task 260326-vo1: Direct Discord Reporting + Monitor Advisory Summary

Direct Discord HTTP API posting from agents (no file intermediary) and advisory-only monitor output to #strategist with /toggle-advisories command.

## What Changed

### Task 1: Rewrite vco report to post directly to Discord via bot HTTP API
- **report_cmd.py**: Complete rewrite -- reads DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, AGENT_ID env vars, uses httpx to GET guild channels (find #agent-{id}), POST message directly. Module-level channel_id cache. 5s timeout, stderr fallback on failure.
- **agent_manager.py**: dispatch() and dispatch_all() now export DISCORD_BOT_TOKEN and DISCORD_GUILD_ID instead of DISCORD_AGENT_WEBHOOK_URL.
- **tests/test_report_cmd.py**: New test file covering happy path, channel caching, error fallback, and missing env vars.

### Task 2: Strip file-based reporting from monitor, add advisory pipeline
- **monitor/loop.py**: Removed on_agent_report parameter, _report_line_counts dict, and _check_agent_reports() method. Added on_advisory async callback. Advisory fires on dead/stuck detection (in addition to existing on_agent_dead/on_agent_stuck alert callbacks).
- **bot/cogs/commands.py**: Replaced _on_agent_report with _on_advisory (posts "[monitor-advisory]" messages to #strategist). Added _advisories_enabled flag and /toggle-advisories slash command. wire_monitor_callbacks now wires advisory instead of agent_report.
- **tests/test_monitor_loop.py**: Added 3 new tests for advisory callback on dead agent, stuck agent, and None advisory safety.

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED
