---
phase: 4
slug: discord-bot-core
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.24.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` section |
| **Quick run command** | `uv run pytest tests/test_bot*.py tests/test_channel_setup.py tests/test_commands_cog.py tests/test_alerts_cog.py -x` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | DISC-01 | unit | `uv run pytest tests/test_bot_client.py -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | DISC-02,10 | unit | `uv run pytest tests/test_channel_setup.py -x` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 2 | DISC-03..09,11 | unit | `uv run pytest tests/test_commands_cog.py -x` | ❌ W0 | ⬜ pending |
| 04-04-01 | 04 | 2 | DISC-12 | unit | `uv run pytest tests/test_alerts_cog.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `uv add "discord.py>=2.7,<3"` — discord.py dependency
- [ ] `tests/test_bot_client.py` — DISC-01 (cog loading, setup_hook)
- [ ] `tests/test_channel_setup.py` — DISC-02 (channel creation, permissions)
- [ ] `tests/test_commands_cog.py` — DISC-03..11 (all commands, role checks, async threading)
- [ ] `tests/test_alerts_cog.py` — DISC-12 (buffer, flush, callback wiring)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Bot connects to real Discord server | DISC-12 | Requires bot token + live server | Set DISCORD_BOT_TOKEN, run `vco bot`, verify bot appears online |
| Channel structure visible in Discord | DISC-02 | Visual verification in Discord UI | Run !new-project, verify category + channels created |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
