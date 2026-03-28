---
phase: 9
slug: agent-type-routing-and-pm-event-dispatch
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run python -m pytest tests/test_commands_cog.py tests/test_bot_client.py tests/test_container_factory.py tests/test_pm_integration.py -x -q` |
| **Full suite command** | `uv run python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~17 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run python -m pytest tests/test_commands_cog.py tests/test_bot_client.py tests/test_container_factory.py tests/test_pm_integration.py -x -q`
- **After every plan wave:** Run `uv run python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 17 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 9-01-01 | 01 | 1 | TYPE-04, TYPE-05 | unit | `uv run python -m pytest tests/test_container_factory.py tests/test_bot_client.py -x -q` | ✅ needs update | ⬜ pending |
| 9-01-02 | 01 | 1 | AUTO-05 | unit | `uv run python -m pytest tests/test_pm_integration.py -x -q` | ✅ needs update | ⬜ pending |
| 9-02-01 | 02 | 2 | TYPE-04, TYPE-05 | unit | `uv run python -m pytest tests/test_commands_cog.py -x -q` | ✅ needs update | ⬜ pending |
| 9-02-02 | 02 | 2 | N/A (cleanup) | unit | `uv run python -m pytest tests/test_health_cog.py -x -q` | ✅ needs update | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Update `tests/test_container_factory.py` — test type routing from AgentConfig.type
- [ ] Update `tests/test_bot_client.py` — test FulltimeAgent detection in on_ready
- [ ] Fix `tests/test_pm_integration.py` — pre-existing failure (_write_answer_file_sync)
- [ ] Update `tests/test_commands_cog.py` — /new-project PM wiring

*Existing infrastructure covers pytest setup; Wave 0 updates existing test files.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PM receives GsdAgent completion event via Discord | AUTO-05 | Requires live Discord bot + running agents | 1. Dispatch a GSD agent 2. Complete a phase 3. Check PM received event |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 17s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
