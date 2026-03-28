---
phase: 10
slug: messagequeue-notification-routing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run python -m pytest tests/test_bot_client.py tests/test_health_cog.py tests/test_message_queue.py -x -q` |
| **Full suite command** | `uv run python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~17 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run python -m pytest tests/test_bot_client.py tests/test_health_cog.py tests/test_message_queue.py -x -q`
- **After every plan wave:** Run `uv run python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 17 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | RESL-01 | unit | `uv run python -m pytest tests/test_health_cog.py tests/test_bot_client.py -x -q` | ✅ needs update | ⬜ pending |
| 10-01-02 | 01 | 1 | RESL-01 | unit | `uv run python -m pytest tests/test_bot_client.py tests/test_commands_cog.py -x -q` | ✅ needs update | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Update `tests/test_health_cog.py` — verify _notify_state_change uses enqueue
- [ ] Update `tests/test_bot_client.py` — verify callbacks use enqueue not direct send

*Existing infrastructure covers pytest setup; Wave 0 updates existing test files.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Rate-limit backoff under Discord 429 | RESL-01 | Requires real Discord API load | 1. Trigger rapid health state changes 2. Verify no 429 errors in logs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 17s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
