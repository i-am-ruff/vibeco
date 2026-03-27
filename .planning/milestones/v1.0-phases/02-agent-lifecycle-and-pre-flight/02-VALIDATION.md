---
phase: 2
slug: agent-lifecycle-and-pre-flight
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (already installed from Phase 1) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` section |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | LIFE-05,06,07 | unit | `uv run pytest tests/test_crash_tracker.py -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | LIFE-01,02 | integration | `uv run pytest tests/test_dispatch.py -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | LIFE-03,04 | integration | `uv run pytest tests/test_kill.py -x` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | PRE-01,03 | unit+integration | `uv run pytest tests/test_preflight.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_crash_tracker.py` — LIFE-05, LIFE-06, LIFE-07 (backoff, circuit breaker, classification)
- [ ] `tests/test_dispatch.py` — LIFE-01, LIFE-02 (dispatch single + all)
- [ ] `tests/test_kill.py` — LIFE-03 (graceful + forced kill)
- [ ] `tests/test_relaunch.py` — LIFE-04 (kill then dispatch with resume)
- [ ] `tests/test_preflight.py` — PRE-01, PRE-03 (result interpretation)
- [ ] `tests/test_agent_state.py` — AgentsRegistry and AgentEntry models

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Pre-flight runs 4 live Claude Code tests | PRE-02 | Requires API key + real Claude invocation | Run `vco preflight test-project`, verify 4 tests execute with pass/fail/inconclusive |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
