---
phase: 22
slug: bot-thin-relay
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-29
---

# Phase 22 — Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Quick run command** | `uv run pytest tests/test_import_boundary.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x --timeout=30` |
| **Estimated runtime** | ~10 seconds |

## Sampling Rate

- **After every task commit:** Quick run
- **After every plan wave:** Full suite
- **Max feedback latency:** 10 seconds

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 22-01-01 | 01 | 1 | BOT-01 | unit | `pytest tests/test_import_boundary.py -x` + inline verify | Exists | pending |
| 22-01-02 | 01 | 1 | BOT-02 | unit | `pytest tests/test_import_boundary.py -x` | Exists | pending |
| 22-02-01 | 02 | 2 | BOT-01,BOT-02 | unit (import scan) | inline python verify script in plan | N/A | pending |
| 22-02-02 | 02 | 2 | BOT-04 | unit (import scan) | inline python verify script in plan | N/A | pending |
| 22-03-01 | 03 | 3 | BOT-02,BOT-03,BOT-04,BOT-05 | unit (import scan) | inline python verify script in plan | N/A | pending |
| 22-03-02 | 03 | 3 | BOT-02 | unit | `pytest tests/test_import_boundary.py -v` (xfail removed) | Exists | pending |

## Wave 0 Requirements

- [x] `tests/test_import_boundary.py` — exists, Plan 01 extends coverage to all 9 cogs

## Validation Sign-Off

**Approval:** pending
