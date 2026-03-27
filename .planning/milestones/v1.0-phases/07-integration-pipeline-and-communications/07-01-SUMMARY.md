---
phase: "07"
plan: "01"
subsystem: integration-pipeline
tags: [integration, git-ops, merge, testing, attribution, pr-creation]
dependency_graph:
  requires: [git/ops.py]
  provides: [IntegrationPipeline, attribute_failures, IntegrationResult, TestRunResult]
  affects: [future integration CLI commands, Discord !integrate command]
tech_stack:
  added: []
  patterns: [N+1 attribution, async subprocess, pydantic result models]
key_files:
  created:
    - src/vcompany/integration/__init__.py
    - src/vcompany/integration/models.py
    - src/vcompany/integration/pipeline.py
    - src/vcompany/integration/attribution.py
    - tests/test_integration_pipeline.py
    - tests/test_attribution.py
  modified:
    - src/vcompany/git/ops.py
decisions:
  - "Agent branches use lowercase convention agent/{id.lower()} per D-03"
  - "N+1 attribution re-runs only failing tests, not full suite per D-06"
  - "Single agent + passes on isolation = _flaky; multiple agents + passes on all = _interaction"
  - "PR creation via gh pr create with --base main --head integrate/{timestamp}"
  - "Conflict files parsed from CONFLICT regex in git merge stderr"
metrics:
  duration: "4min"
  completed: "2026-03-25T22:14:00Z"
---

# Phase 07 Plan 01: Integration Pipeline Core Summary

Integration pipeline with git merge operations, N+1 test failure attribution using isolated agent branch re-runs, and PR creation via gh CLI.

## What Was Built

### Git Operations Extensions (src/vcompany/git/ops.py)
Added 6 new functions to the existing git ops module:
- `merge()` -- merge a branch with optional --no-ff, 120s timeout
- `fetch()` -- fetch from remote (default origin), 120s timeout
- `push()` -- push to remote with optional branch specification
- `diff()` -- passthrough diff with arbitrary args
- `merge_abort()` -- abort a merge in progress
- `checkout()` -- checkout an existing branch (distinct from checkout_new_branch)

### Integration Models (src/vcompany/integration/models.py)
- `TestRunResult` -- passed, total, failed, failed_tests, output
- `IntegrationResult` -- status (success/test_failure/merge_conflict/error), branch_name, merged_agents, test_results, attribution, pr_url, conflict_files, error

### Integration Pipeline (src/vcompany/integration/pipeline.py)
- `IntegrationPipeline` class with async `run()` method
- Creates `integrate/{timestamp}` branch from main
- Fetches, merges each agent branch (agent/{id.lower()})
- On merge conflict: parses conflict files, returns merge_conflict status
- On test pass: pushes branch, creates PR via `gh pr create`
- On test fail: calls `attribute_failures()`, returns test_failure with attribution

### Attribution Algorithm (src/vcompany/integration/attribution.py)
- `attribute_failures()` -- N+1 test failure attribution per D-06
- For each agent: creates `_attr_{agent_id}` temp branch from main, merges only that agent
- Re-runs only the specific failing tests (not full suite)
- Categorizes: agent-owned failures, `_interaction` (cross-agent), `_flaky` (passes on re-run)

## Test Coverage

- 22 tests for git ops extensions, models, and pipeline scenarios
- 5 tests for attribution algorithm (single-agent blame, interaction, flaky, temp branch creation, targeted re-runs)
- Total: 27 tests, all passing

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | d89601e | Git ops extensions + IntegrationPipeline + models |
| 2 | 553eb3a | N+1 test failure attribution algorithm |

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None -- all code is fully wired and functional.

## Self-Check: PASSED
