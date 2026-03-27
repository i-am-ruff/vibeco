---
phase: 9
slug: askuser-hook-sends-questions-to-agent-discord-channel-mentioning-pm-for-autonomous-q-a-forwarding
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-27
---

# Phase 9 — Validation Strategy

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
| 01-T1 | 09-01 | 1 | D-06, D-07, D-08 | unit (TDD) | `cd /home/developer/vcompany && uv run python -m pytest tests/test_routing.py -x -v` | tests/test_routing.py | ⬜ pending |
| 01-T2 | 09-01 | 1 | D-16, D-18 | grep verify | `cd /home/developer/vcompany && grep -n "VCO_AGENT_ID" src/vcompany/orchestrator/agent_manager.py && grep "86400" src/vcompany/templates/settings.json.j2` | src/vcompany/orchestrator/agent_manager.py | ⬜ pending |
| 02-T1 | 09-02 | 2 | D-01, D-02, D-12, D-13, D-15 | unit (TDD) | `cd /home/developer/vcompany && uv run python -m pytest tests/test_ask_discord.py -x -v && ! grep -r "vco-answers" tools/ask_discord.py && ! grep -r "DISCORD_AGENT_WEBHOOK_URL" tools/ask_discord.py` | tests/test_ask_discord.py | ⬜ pending |
| 03-T1 | 09-03 | 2 | D-04, D-09, D-10, D-11, D-19 | unit | `cd /home/developer/vcompany && uv run python -m pytest tests/test_question_handler.py -x -v && ! grep -r "vco-answers" src/vcompany/bot/cogs/question_handler.py && ! grep "AnswerView" src/vcompany/bot/cogs/question_handler.py` | tests/test_question_handler.py | ⬜ pending |
| 03-T2 | 09-03 | 2 | D-07 | unit | `cd /home/developer/vcompany && uv run python -m pytest tests/test_strategist_cog.py tests/test_question_handler.py tests/test_routing.py -x -v 2>&1 \| tail -30` | tests/test_strategist_cog.py | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements. No Wave 0 test scaffolding needed.
- All 5 tasks have `<automated>` verify commands.
- 100% sampling rate (every task has automated verification).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Discord message posting from hook | D-01, D-02 | Requires live Discord server and bot token | Post a test question via hook, verify message appears in correct #agent-{id} channel |
| Reply polling from hook | D-12 | Requires live Discord API interaction | Post question, have bot reply, verify hook detects and extracts answer |
| PM auto-answer flow | D-09, D-10, D-11 | End-to-end requires running bot + hook + PM tier | Trigger AskUserQuestion, verify PM evaluates and replies in Discord |
| Escalation flow | D-10, D-18 | Requires live bot with Strategist conversation | Trigger LOW confidence question, verify @mention escalation pattern |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved
