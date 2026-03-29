---
phase: 20
slug: companyroot-extraction
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `pyproject.toml` (pytest section) |
| **Quick run command** | `uv run pytest tests/test_runtime_api.py tests/test_daemon.py tests/test_strategist_comm.py tests/test_pm_review_comm.py -x -q` |
| **Full suite command** | `uv run pytest tests/ --timeout=30` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_runtime_api.py tests/test_daemon.py tests/test_strategist_comm.py tests/test_pm_review_comm.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x --timeout=30`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 20-01-01 | 01 | 1 | EXTRACT-02 | unit | `pytest tests/test_runtime_api.py -x` | ❌ W0 | ⬜ pending |
| 20-01-02 | 01 | 1 | EXTRACT-01 | unit | `pytest tests/test_daemon.py -x -k runtime` | ❌ W0 | ⬜ pending |
| 20-02-01 | 02 | 2 | COMM-04 | unit | `pytest tests/test_strategist_comm.py -x` | ❌ W0 | ⬜ pending |
| 20-02-02 | 02 | 2 | COMM-05 | unit | `pytest tests/test_pm_review_comm.py -x` | ❌ W0 | ⬜ pending |
| 20-02-03 | 02 | 2 | COMM-06 | unit | `pytest tests/test_discord_comm_adapter.py -x -k channel` | Exists | ⬜ pending |
| 20-03-01 | 03 | 3 | EXTRACT-03 | integration | `pytest tests/test_bot_client.py -x -k ready` | Exists | ⬜ pending |
| 20-03-02 | 03 | 3 | EXTRACT-04 | unit | `pytest tests/test_import_boundary.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_runtime_api.py` — stubs for EXTRACT-02 (RuntimeAPI methods)
- [ ] `tests/test_import_boundary.py` — stubs for EXTRACT-04 (no container imports in bot)
- [ ] `tests/test_strategist_comm.py` — stubs for COMM-04 (Strategist via CommunicationPort)
- [ ] `tests/test_pm_review_comm.py` — stubs for COMM-05 (PM review via CommunicationPort)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CompanyRoot starts with live Discord bot | EXTRACT-01 | Requires live Discord connection + tmux | `vco up`, verify bot online, verify supervision tree via `vco status` |
| Strategist responds on Discord | COMM-04 | Requires live Anthropic API + Discord | Send message in strategist channel, verify response |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
