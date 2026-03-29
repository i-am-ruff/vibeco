---
phase: 19
slug: communication-abstraction
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio 0.24+ |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_daemon_comm.py tests/test_discord_comm_adapter.py -x` |
| **Full suite command** | `uv run pytest tests/ -x --ignore=tests/test_container_tmux_bridge.py -m "not integration"` |
| **Estimated runtime** | ~8 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_daemon_comm.py tests/test_discord_comm_adapter.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x --ignore=tests/test_container_tmux_bridge.py -m "not integration"`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 19-01-01 | 01 | 1 | COMM-01 | unit | `pytest tests/test_daemon_comm.py::test_protocol_methods -x` | ❌ W0 | ⬜ pending |
| 19-01-02 | 01 | 1 | COMM-01 | unit | `pytest tests/test_daemon_comm.py::test_payload_models -x` | ❌ W0 | ⬜ pending |
| 19-01-03 | 01 | 1 | COMM-02 | unit | `pytest tests/test_daemon_comm.py::test_no_discord_imports -x` | ❌ W0 | ⬜ pending |
| 19-02-01 | 02 | 2 | COMM-03 | unit | `pytest tests/test_discord_comm_adapter.py::test_adapter_satisfies_protocol -x` | ❌ W0 | ⬜ pending |
| 19-02-02 | 02 | 2 | COMM-03 | unit | `pytest tests/test_discord_comm_adapter.py::test_adapter_registration -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_daemon_comm.py` — stubs for COMM-01, COMM-02
- [ ] `tests/test_discord_comm_adapter.py` — stubs for COMM-03

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Discord adapter sends real messages | COMM-03 | Requires live Discord connection | Start daemon with bot, trigger send_message via socket, verify message appears in Discord |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
