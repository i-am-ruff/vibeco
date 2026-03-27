---
phase: 5
slug: hooks-and-plan-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.24.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x --tb=short` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x --tb=short`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | HOOK-01 | unit | `uv run pytest tests/test_ask_discord.py::test_parse_stdin -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | HOOK-02 | unit | `uv run pytest tests/test_ask_discord.py::test_post_webhook -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | HOOK-03 | unit | `uv run pytest tests/test_ask_discord.py::test_poll_answer -x` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | HOOK-04 | unit | `uv run pytest tests/test_ask_discord.py::test_timeout_fallback -x` | ❌ W0 | ⬜ pending |
| 05-01-05 | 01 | 1 | HOOK-05 | unit | `uv run pytest tests/test_ask_discord.py::test_deny_response -x` | ❌ W0 | ⬜ pending |
| 05-01-06 | 01 | 1 | HOOK-06 | unit | `uv run pytest tests/test_ask_discord.py::test_no_external_imports -x` | ❌ W0 | ⬜ pending |
| 05-01-07 | 01 | 1 | HOOK-07 | unit | `uv run pytest tests/test_ask_discord.py::test_error_fallback -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | GATE-01 | unit | `uv run pytest tests/test_monitor_checks.py::test_check_plan_gate -x` | ✅ | ⬜ pending |
| 05-02-02 | 02 | 1 | GATE-02 | unit | `uv run pytest tests/test_plan_review_cog.py::test_post_plan -x` | ❌ W0 | ⬜ pending |
| 05-02-03 | 02 | 1 | GATE-03 | unit | `uv run pytest tests/test_plan_review_cog.py::test_gate_pauses -x` | ❌ W0 | ⬜ pending |
| 05-02-04 | 02 | 1 | GATE-04 | unit | `uv run pytest tests/test_plan_review_cog.py::test_reject_feedback -x` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 2 | SAFE-01 | unit | `uv run pytest tests/test_safety_validator.py::test_valid_table -x` | ❌ W0 | ⬜ pending |
| 05-03-02 | 03 | 2 | SAFE-02 | unit | `uv run pytest tests/test_safety_validator.py::test_missing_table -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ask_discord.py` — stubs for HOOK-01 through HOOK-07
- [ ] `tests/test_plan_review_cog.py` — stubs for GATE-02, GATE-03, GATE-04
- [ ] `tests/test_safety_validator.py` — stubs for SAFE-01, SAFE-02

*Existing `tests/test_monitor_checks.py` covers GATE-01 (plan detection).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end hook → Discord → answer flow | HOOK-01..05 | Requires live Discord webhook + bot | Deploy to test project, trigger AskUserQuestion, verify message appears in #strategist, reply, verify answer returns |
| Plan gate approval flow | GATE-02..04 | Requires live Discord bot + tmux agent | Create PLAN.md in test clone, verify review embed appears, click approve, verify execute command sent to pane |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
