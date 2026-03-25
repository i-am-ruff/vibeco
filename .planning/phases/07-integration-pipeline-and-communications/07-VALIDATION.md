---
phase: 7
slug: integration-pipeline-and-communications
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-25
---

# Phase 7 -- Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

**Nyquist note:** All tdd="true" tasks write failing tests FIRST within the same task action, then implement to pass them. This satisfies TDD intent without separate Wave 0 stub files. Tests that ARE the production artifact (test_interaction_regression.py) have tdd removed since the tests themselves are the deliverable.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio 0.24+ |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~25 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 25 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | INTG-02, INTG-03, INTG-06 | unit | `uv run pytest tests/test_integration_pipeline.py -x` | tdd-inline | pending |
| 07-01-02 | 01 | 1 | INTG-04, INTG-05 | unit | `uv run pytest tests/test_attribution.py -x` | tdd-inline | pending |
| 07-02-01 | 02 | 1 | INTG-07, INTG-08 | unit | `uv run pytest tests/test_conflict_resolver.py -x` | tdd-inline | pending |
| 07-03-01 | 03 | 1 | COMM-01, COMM-02 | unit | `uv run pytest tests/test_checkin.py -x` | tdd-inline | pending |
| 07-03-02 | 03 | 1 | COMM-01, COMM-02 | import | `uv run python -c "from vcompany.bot.embeds import build_checkin_embed"` | n/a | pending |
| 07-04-01 | 04 | 2 | INTG-05 | unit | `uv run pytest tests/test_integration_interlock.py -x` | tdd-inline | pending |
| 07-04-02 | 04 | 2 | INTG-05 | import | `uv run python -c "from vcompany.bot.cogs.commands import CommandsCog"` | n/a | pending |
| 07-05-01 | 05 | 3 | COMM-03, COMM-04, COMM-05, COMM-06 | unit | `uv run pytest tests/test_standup.py -x` | tdd-inline | pending |
| 07-05-02 | 05 | 3 | COMM-03, COMM-04, COMM-05, COMM-06 | import | `uv run python -c "from vcompany.bot.cogs.commands import CommandsCog"` | n/a | pending |
| 07-06-01 | 06 | 4 | SAFE-04 | config | `uv run pytest --markers \| grep integration` | n/a | pending |
| 07-06-02 | 06 | 4 | SAFE-04 | integration | `uv run pytest tests/test_interaction_regression.py -m integration -x` | n/a | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

Not applicable -- all tdd="true" tasks create tests inline before implementation within the same task. Test files that ARE the artifact (test_interaction_regression.py) do not use tdd="true".

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full git merge + test + PR flow | INTG-02,03,06 | Requires real git repo with agent branches and GitHub remote | Set up test project with 2 agents, run !integrate, verify merge and PR |
| Standup blocking interlock | COMM-03,04,05 | Requires live Discord + running agents in tmux | Run !standup, verify agents block, interact in threads, release agents |
| AI conflict resolution via PM | INTG-08 | Requires actual merge conflict + Anthropic API | Create conflicting branches, integrate, verify PM resolution attempt |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or inline TDD
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 not needed (inline TDD pattern used)
- [x] No watch-mode flags
- [x] Feedback latency < 25s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
