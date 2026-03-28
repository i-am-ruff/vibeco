---
phase: 3
slug: gsdagent
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 0.24.x |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/test_gsd_lifecycle.py tests/test_gsd_agent.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_gsd_lifecycle.py tests/test_gsd_agent.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 3-01-01 | 01 | 1 | TYPE-01 | unit | `uv run pytest tests/test_gsd_lifecycle.py -x` | ❌ W0 | ⬜ pending |
| 3-01-02 | 01 | 1 | TYPE-02 | unit | `uv run pytest tests/test_gsd_agent.py::TestCheckpointing -x` | ❌ W0 | ⬜ pending |
| 3-01-03 | 01 | 1 | TYPE-02 | unit | `uv run pytest tests/test_gsd_agent.py::TestCrashRecovery -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_gsd_lifecycle.py` — GsdAgent phase FSM transitions, nesting in RUNNING, HistoryState
- [ ] `tests/test_gsd_agent.py` — Checkpointing, crash recovery, state tracking, inner_state

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
