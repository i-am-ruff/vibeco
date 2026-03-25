---
phase: 7
slug: integration-pipeline-and-communications
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

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
| 07-01-01 | 01 | 1 | INTG-02, INTG-03, INTG-06 | unit | `uv run pytest tests/test_integration_pipeline.py -x` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | INTG-04, INTG-05 | unit | `uv run pytest tests/test_attribution.py -x` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 1 | INTG-07, INTG-08 | unit | `uv run pytest tests/test_conflict_resolver.py -x` | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 2 | COMM-01, COMM-02 | unit | `uv run pytest tests/test_checkin.py -x` | ❌ W0 | ⬜ pending |
| 07-03-02 | 03 | 2 | COMM-03, COMM-04, COMM-05, COMM-06 | unit | `uv run pytest tests/test_standup.py -x` | ❌ W0 | ⬜ pending |
| 07-04-01 | 04 | 3 | INTG-01 thru INTG-08, COMM-01 thru COMM-06 | unit | `uv run pytest tests/test_integrate_wiring.py -x` | ❌ W0 | ⬜ pending |
| 07-05-01 | 05 | 3 | SAFE-04 | integration | `uv run pytest tests/test_interaction_regression.py -m integration -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_integration_pipeline.py` — stubs for INTG-02, INTG-03, INTG-05, INTG-06
- [ ] `tests/test_attribution.py` — stubs for INTG-04
- [ ] `tests/test_conflict_resolver.py` — stubs for INTG-07, INTG-08
- [ ] `tests/test_checkin.py` — stubs for COMM-01, COMM-02
- [ ] `tests/test_standup.py` — stubs for COMM-03 through COMM-06
- [ ] `tests/test_integrate_wiring.py` — stubs for integration wiring
- [ ] `tests/test_interaction_regression.py` — stubs for SAFE-04
- [ ] Add `pytest.mark.integration` marker to pyproject.toml

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full git merge + test + PR flow | INTG-02,03,06 | Requires real git repo with agent branches and GitHub remote | Set up test project with 2 agents, run !integrate, verify merge and PR |
| Standup blocking interlock | COMM-03,04,05 | Requires live Discord + running agents in tmux | Run !standup, verify agents block, interact in threads, release agents |
| AI conflict resolution via PM | INTG-08 | Requires actual merge conflict + Anthropic API | Create conflicting branches, integrate, verify PM resolution attempt |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 25s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
