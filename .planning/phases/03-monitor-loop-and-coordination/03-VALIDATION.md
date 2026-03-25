---
phase: 3
slug: monitor-loop-and-coordination
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.24.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` section |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~8 seconds |

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
| 03-01-01 | 01 | 1 | MON-01,02,03,04 | unit | `uv run pytest tests/test_monitor_loop.py tests/test_monitor_checks.py -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | MON-05,06,07 | unit | `uv run pytest tests/test_status_generator.py -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 1 | MON-08 | unit | `uv run pytest tests/test_heartbeat.py -x` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 2 | COORD-01,02,03 | unit | `uv run pytest tests/test_coordination.py tests/test_sync_context.py -x` | ❌ W0 | ⬜ pending |
| 03-04-01 | 04 | 3 | SAFE-03 | manual | Review INTERACTIONS.md content | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_monitor_loop.py` — MON-01 (cycle independence, error isolation)
- [ ] `tests/test_monitor_checks.py` — MON-02, MON-03, MON-04 (liveness, stuck, plan gate)
- [ ] `tests/test_status_generator.py` — MON-05, MON-06, MON-07 (roadmap parse, status gen, distribution)
- [ ] `tests/test_heartbeat.py` — MON-08 (heartbeat write, watchdog)
- [ ] `tests/test_coordination.py` — COORD-01, COORD-02 (interfaces, change log)
- [ ] `tests/test_sync_context.py` — COORD-03 (sync files to clones)
- [ ] pytest-asyncio added as dev dependency

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| INTERACTIONS.md covers known concurrent patterns | SAFE-03 | Content review, not automated | Read INTERACTIONS.md, verify all known interaction patterns documented |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
