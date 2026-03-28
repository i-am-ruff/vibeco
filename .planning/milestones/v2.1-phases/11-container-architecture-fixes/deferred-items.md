# Deferred Items — Phase 11

## Pre-existing Test Failures (Out of Scope for 11-01)

These were failing before Phase 11 work began and are unrelated to FSM state changes.

### test_pm_tier.py::test_low_confidence_escalates_to_strategist
- **Issue:** Claude CLI subprocess communication fails with `ValueError: not enough values to unpack (expected 2, got 0)`
- **Root cause:** PM tier's `_answer_directly()` uses `asyncio.create_subprocess_exec` but the test environment doesn't have Claude CLI available
- **Scope:** PM tier / Strategist (Phase 16)

### test_report_cmd.py (4 tests)
- **Issue:** `AttributeError: <module 'vcompany.cli.report_cmd'> does not have the attribute 'httpx'`
- **Root cause:** Tests mock `vcompany.cli.report_cmd.httpx` but the module imports httpx differently
- **Scope:** CLI / report command
