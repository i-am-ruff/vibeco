---
phase: 4
slug: remaining-agent-types-and-scheduler
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 0.24.x |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/test_continuous_agent.py tests/test_fulltime_agent.py tests/test_company_agent.py tests/test_scheduler.py tests/test_container_factory.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 1 | ALL | unit | `uv run pytest tests/test_container_factory.py -x` | ❌ W0 | ⬜ pending |
| 4-02-01 | 02 | 2 | TYPE-03 | unit | `uv run pytest tests/test_continuous_agent.py -x` | ❌ W0 | ⬜ pending |
| 4-02-02 | 02 | 2 | TYPE-04 | unit | `uv run pytest tests/test_fulltime_agent.py -x` | ❌ W0 | ⬜ pending |
| 4-02-03 | 02 | 2 | TYPE-05 | unit | `uv run pytest tests/test_company_agent.py -x` | ❌ W0 | ⬜ pending |
| 4-03-01 | 03 | 3 | AUTO-06 | unit | `uv run pytest tests/test_scheduler.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_container_factory.py` — factory creates correct subclass types
- [ ] `tests/test_continuous_agent.py` — TYPE-03 cycle FSM, checkpoint, restore
- [ ] `tests/test_fulltime_agent.py` — TYPE-04 event handling
- [ ] `tests/test_company_agent.py` — TYPE-05 cross-project state
- [ ] `tests/test_scheduler.py` — AUTO-06 wake scheduling, persistence

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
