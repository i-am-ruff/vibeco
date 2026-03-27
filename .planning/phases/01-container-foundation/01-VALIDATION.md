---
phase: 1
slug: container-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 0.24.x |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/test_container*.py tests/test_memory_store.py tests/test_child_spec.py tests/test_communication_port.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_container*.py tests/test_memory_store.py tests/test_child_spec.py tests/test_communication_port.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | CONT-01 | unit | `uv run pytest tests/test_container_lifecycle.py::test_valid_transitions -x` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | CONT-02 | unit | `uv run pytest tests/test_container_lifecycle.py::test_invalid_transitions -x` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | CONT-03 | unit | `uv run pytest tests/test_container_context.py -x` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | CONT-04 | unit (async) | `uv run pytest tests/test_memory_store.py -x` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 1 | CONT-05 | unit | `uv run pytest tests/test_child_spec.py -x` | ❌ W0 | ⬜ pending |
| 1-04-01 | 04 | 1 | CONT-06 | unit | `uv run pytest tests/test_communication_port.py -x` | ❌ W0 | ⬜ pending |
| 1-04-02 | 04 | 1 | HLTH-01 | unit | `uv run pytest tests/test_container_health.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_container_lifecycle.py` — stubs for CONT-01, CONT-02
- [ ] `tests/test_container_context.py` — stubs for CONT-03
- [ ] `tests/test_memory_store.py` — stubs for CONT-04
- [ ] `tests/test_child_spec.py` — stubs for CONT-05
- [ ] `tests/test_communication_port.py` — stubs for CONT-06
- [ ] `tests/test_container_health.py` — stubs for HLTH-01
- [ ] `tests/conftest.py` — shared fixtures (tmp SQLite paths, event loop)

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
