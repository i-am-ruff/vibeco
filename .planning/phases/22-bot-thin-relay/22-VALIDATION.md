---
phase: 22
slug: bot-thin-relay
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 22 — Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Quick run command** | `uv run pytest tests/test_import_boundary.py tests/test_bot_relay.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x --timeout=30` |
| **Estimated runtime** | ~10 seconds |

## Sampling Rate

- **After every task commit:** Quick run
- **After every plan wave:** Full suite
- **Max feedback latency:** 10 seconds

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 22-01-01 | 01 | 1 | BOT-01 | unit | `pytest tests/test_bot_relay.py -x -k slash` | ❌ W0 | ⬜ pending |
| 22-01-02 | 01 | 1 | BOT-02 | unit | `pytest tests/test_import_boundary.py -x` | Exists | ⬜ pending |
| 22-02-01 | 02 | 2 | BOT-03 | unit | `pytest tests/test_bot_relay.py -x -k event` | ❌ W0 | ⬜ pending |
| 22-02-02 | 02 | 2 | BOT-04,BOT-05 | unit | `pytest tests/test_bot_relay.py -x -k relay` | ❌ W0 | ⬜ pending |

## Wave 0 Requirements

- [ ] `tests/test_bot_relay.py` — stubs for BOT-01, BOT-03, BOT-04, BOT-05

## Validation Sign-Off

**Approval:** pending
