# Deferred Items - Phase 09

## Pre-existing Test Failures

1. **tests/test_pm_tier.py::test_low_confidence_escalates_to_strategist** — Mock for asyncio.create_subprocess_exec returns wrong shape from communicate(). The PM's _answer_directly falls through to a MEDIUM confidence path instead of LOW.

2. **tests/test_report_cmd.py::TestReportHappyPath::test_posts_to_correct_channel** — Patches vcompany.cli.report_cmd.httpx which no longer exists as a module-level import.
