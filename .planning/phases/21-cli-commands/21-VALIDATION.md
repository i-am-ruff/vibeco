---
phase: 21
slug: cli-commands
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Quick run command** | `uv run pytest tests/test_cli_commands.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x --timeout=30` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_cli_commands.py -x -q`
- **After every plan wave:** Run full suite
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 21-01-01 | 01 | 1 | CLI-01..03 | unit | `pytest tests/test_cli_commands.py -x -k "hire or give_task or dismiss"` | ❌ W0 | ⬜ pending |
| 21-01-02 | 01 | 1 | CLI-04..05 | unit | `pytest tests/test_cli_commands.py -x -k "status or health"` | ❌ W0 | ⬜ pending |
| 21-02-01 | 02 | 2 | CLI-06 | unit | `pytest tests/test_cli_commands.py -x -k new_project` | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_cli_commands.py` — stubs for CLI-01..06

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full hire-give_task-dismiss cycle | CLI-01..03 | Requires running daemon + tmux | Start daemon, run `vco hire gsd test-agent`, `vco give-task test-agent "hello"`, `vco dismiss test-agent` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
