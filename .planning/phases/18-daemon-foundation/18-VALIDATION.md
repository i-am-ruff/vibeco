---
phase: 18
slug: daemon-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.24.x |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/test_daemon.py tests/test_daemon_socket.py tests/test_daemon_protocol.py tests/test_down_cmd.py -x` |
| **Full suite command** | `python -m pytest tests/ -x` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_daemon.py tests/test_daemon_socket.py tests/test_daemon_protocol.py tests/test_down_cmd.py -x`
- **After every plan wave:** Run `python -m pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 18-01-01 | 01 | 1 | DAEMON-01 | unit | `pytest tests/test_daemon.py::test_daemon_starts -x` | ❌ W0 | ⬜ pending |
| 18-01-02 | 01 | 1 | DAEMON-02 | unit | `pytest tests/test_daemon.py::test_pid_lifecycle -x` | ❌ W0 | ⬜ pending |
| 18-01-03 | 01 | 1 | DAEMON-03 | unit | `pytest tests/test_daemon.py::test_signal_shutdown -x` | ❌ W0 | ⬜ pending |
| 18-01-04 | 01 | 1 | DAEMON-04 | unit | `pytest tests/test_daemon.py::test_stale_cleanup -x` | ❌ W0 | ⬜ pending |
| 18-01-05 | 01 | 1 | DAEMON-06 | unit | `pytest tests/test_daemon.py::test_bot_costart -x` | ❌ W0 | ⬜ pending |
| 18-02-01 | 02 | 1 | SOCK-01 | unit | `pytest tests/test_daemon_socket.py::test_socket_accepts -x` | ❌ W0 | ⬜ pending |
| 18-02-02 | 02 | 1 | SOCK-02 | unit | `pytest tests/test_daemon_socket.py::test_ndjson_roundtrip -x` | ❌ W0 | ⬜ pending |
| 18-02-03 | 02 | 1 | SOCK-03 | unit | `pytest tests/test_daemon_protocol.py::test_request_model -x` | ❌ W0 | ⬜ pending |
| 18-02-04 | 02 | 1 | SOCK-04 | unit | `pytest tests/test_daemon_protocol.py::test_error_response -x` | ❌ W0 | ⬜ pending |
| 18-02-05 | 02 | 1 | SOCK-05 | unit | `pytest tests/test_daemon_socket.py::test_event_subscription -x` | ❌ W0 | ⬜ pending |
| 18-02-06 | 02 | 1 | SOCK-06 | unit | `pytest tests/test_daemon_socket.py::test_hello_handshake -x` | ❌ W0 | ⬜ pending |
| 18-03-01 | 03 | 2 | DAEMON-05 | unit | `pytest tests/test_down_cmd.py::test_down_sends_sigterm -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_daemon.py` — stubs for DAEMON-01, DAEMON-02, DAEMON-03, DAEMON-04, DAEMON-06
- [ ] `tests/test_daemon_socket.py` — stubs for SOCK-01, SOCK-02, SOCK-05, SOCK-06
- [ ] `tests/test_daemon_protocol.py` — stubs for SOCK-03, SOCK-04 (Pydantic model tests)
- [ ] `tests/test_down_cmd.py` — stubs for DAEMON-05

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Discord bot reachable on Discord | DAEMON-06 | Requires live Discord connection | Start daemon with `vco up`, verify bot appears online in Discord |
| socat roundtrip | SOCK-02 | Success criteria mentions socat specifically | `echo '{"jsonrpc":"2.0","method":"ping","id":1}' \| socat - UNIX-CONNECT:/tmp/vco-daemon.sock` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
