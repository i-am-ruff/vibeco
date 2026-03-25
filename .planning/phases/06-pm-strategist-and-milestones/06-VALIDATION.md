---
phase: 6
slug: pm-strategist-and-milestones
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | STRAT-01, MILE-02, MILE-03 | unit | `uv run pytest tests/test_context_builder.py -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | STRAT-02, STRAT-03, STRAT-04, STRAT-05 | unit | `uv run pytest tests/test_pm_tier.py -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | STRAT-06, STRAT-07 | unit | `uv run pytest tests/test_pm_plan_review.py -x` | ❌ W0 | ⬜ pending |
| 06-03-01 | 03 | 2 | STRAT-08 | unit | `uv run pytest tests/test_conversation.py -x` | ❌ W0 | ⬜ pending |
| 06-03-02 | 03 | 2 | STRAT-09 | unit | `uv run pytest tests/test_decision_log.py -x` | ❌ W0 | ⬜ pending |
| 06-04-01 | 04 | 3 | MILE-01 | unit | `uv run pytest tests/test_new_milestone.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_context_builder.py` — stubs for STRAT-01, MILE-02, MILE-03
- [ ] `tests/test_pm_tier.py` — stubs for STRAT-02, STRAT-03, STRAT-04, STRAT-05
- [ ] `tests/test_pm_plan_review.py` — stubs for STRAT-06, STRAT-07
- [ ] `tests/test_conversation.py` — stubs for STRAT-08
- [ ] `tests/test_decision_log.py` — stubs for STRAT-09
- [ ] `tests/test_new_milestone.py` — stubs for MILE-01
- [ ] `tests/test_strategist_cog.py` — stubs for StrategistCog expansion
- [ ] Mock fixture for `AsyncAnthropic` client shared across tests
- [ ] Install anthropic SDK: `uv add "anthropic>=0.86,<1"`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Strategist streaming response to Discord | STRAT-02 | Requires live Discord + Anthropic API key | Send question via webhook, verify streamed response appears in #strategist |
| Owner escalation with @mention | STRAT-05 | Requires live Discord with vco-owner role | Trigger LOW confidence question, verify @Owner mention in #strategist |
| Knowledge Transfer handoff | STRAT-08 | Requires ~800K tokens of conversation | Simulate extended conversation, verify KT doc generation and fresh session continuity |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
