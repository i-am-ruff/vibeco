---
phase: 2
slug: supervision-tree
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 0.24.x |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/test_supervisor.py tests/test_restart_strategies.py tests/test_restart_tracker.py tests/test_supervision_tree.py -x -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_supervisor.py tests/test_restart_strategies.py tests/test_restart_tracker.py tests/test_supervision_tree.py -x -q`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 1 | SUPV-01 | integration | `uv run pytest tests/test_supervision_tree.py -x -q` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 1 | SUPV-02 | unit | `uv run pytest tests/test_restart_strategies.py::test_one_for_one -x -q` | ❌ W0 | ⬜ pending |
| 2-01-03 | 01 | 1 | SUPV-03 | unit | `uv run pytest tests/test_restart_strategies.py::test_all_for_one -x -q` | ❌ W0 | ⬜ pending |
| 2-01-04 | 01 | 1 | SUPV-04 | unit | `uv run pytest tests/test_restart_strategies.py::test_rest_for_one -x -q` | ❌ W0 | ⬜ pending |
| 2-02-01 | 02 | 1 | SUPV-05 | unit | `uv run pytest tests/test_restart_tracker.py -x -q` | ❌ W0 | ⬜ pending |
| 2-02-02 | 02 | 1 | SUPV-06 | integration | `uv run pytest tests/test_supervision_tree.py::test_escalation -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_supervisor.py` — Supervisor base class start/stop/add_child
- [ ] `tests/test_restart_strategies.py` — SUPV-02, SUPV-03, SUPV-04
- [ ] `tests/test_restart_tracker.py` — SUPV-05 sliding window
- [ ] `tests/test_supervision_tree.py` — SUPV-01, SUPV-06 integration

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
