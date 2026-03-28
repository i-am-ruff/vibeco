---
phase: 11
slug: container-architecture-fixes
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q --tb=short` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --tb=short`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | ARCH-02 | unit | `uv run pytest tests/test_company_root.py -k strategist` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | ARCH-03 | unit | `uv run pytest tests/test_state_machine.py -k blocked` | ❌ W0 | ⬜ pending |
| 11-01-03 | 01 | 1 | LIFE-01 | unit | `uv run pytest tests/test_state_machine.py -k stopping` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 1 | ARCH-04 | unit | `uv run pytest tests/test_communication.py -k comm_port` | ❌ W0 | ⬜ pending |
| 11-02-02 | 02 | 1 | ARCH-04 | integration | `uv run pytest tests/test_factory.py -k comm_port` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_state_machine.py` — stubs for BLOCKED/STOPPING FSM transitions (ARCH-03, LIFE-01)
- [ ] `tests/test_company_root.py` — stubs for Strategist as CompanyRoot child (ARCH-02)
- [ ] `tests/test_communication.py` — stubs for CommunicationPort wiring (ARCH-04)
- [ ] `tests/test_factory.py` — stubs for factory comm_port passing (ARCH-04)

*Existing test infrastructure exists — pytest + fixtures already configured.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Health tree renders BLOCKED state with reason | ARCH-03 | Discord embed rendering | Run `/health` in Discord after blocking an agent |
| Health tree renders STOPPING during shutdown | LIFE-01 | Timing-dependent transition | Run `/health` while shutting down an agent |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
