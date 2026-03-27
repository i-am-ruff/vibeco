---
phase: 8
slug: reliable-tmux-agent-lifecycle
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.24.x |
| **Config file** | pyproject.toml [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/test_tmux.py tests/test_dispatch.py tests/test_monitor_checks.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_tmux.py tests/test_dispatch.py tests/test_monitor_checks.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | LIFE-01 | unit | `uv run pytest tests/test_tmux.py -x -q -k "send"` | Partially | ⬜ pending |
| 08-01-02 | 01 | 1 | LIFE-01 | unit | `uv run pytest tests/test_dispatch.py -x -q -k "wait_ready"` | Missing | ⬜ pending |
| 08-01-03 | 01 | 1 | LIFE-01 | unit | `uv run pytest tests/test_dispatch.py -x -q -k "send_work"` | Missing | ⬜ pending |
| 08-02-01 | 02 | 1 | MON-02 | unit | `uv run pytest tests/test_monitor_checks.py -x -q -k "liveness"` | Yes | ⬜ pending |
| 08-02-02 | 02 | 2 | LIFE-01 | integration | `uv run pytest tests/test_dispatch.py -x -q -k "parallel_send"` | Missing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_dispatch.py::TestSendWorkCommand` — stubs for send_work_command, _wait_for_claude_ready
- [ ] `tests/test_tmux.py::TestSendCommandStringPaneId` — tests for string pane_id acceptance
- [ ] `tests/test_dispatch.py::TestSendWorkCommandAll` — tests for parallel send to all agents

*Existing infrastructure partially covers phase requirements — Wave 0 fills gaps.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Agent dispatch + work command delivery completes in under 2 minutes for 3 agents | LIFE-01 | Requires live tmux sessions with Claude Code | 1. Run `vco dispatch` with 3 agents 2. Time from start to all commands delivered 3. Verify < 120s |
| Commands are visibly processed by agent Claude sessions | LIFE-01 | Requires visual confirmation of agent behavior | 1. Attach to agent tmux pane 2. Verify slash command appears and Claude processes it |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
