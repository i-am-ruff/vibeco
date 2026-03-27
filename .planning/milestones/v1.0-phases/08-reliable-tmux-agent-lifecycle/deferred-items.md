# Deferred Items - Phase 08

## Pre-existing Test Failure

**File:** tests/test_dispatch.py::TestDispatch::test_dispatch_sets_env_vars_before_claude
**Issue:** Test expects `DISCORD_AGENT_WEBHOOK_URL` in the dispatch command string, but the current code exports `DISCORD_BOT_TOKEN`. Likely the test was written for an older version of the dispatch logic.
**Found during:** 08-01 full verification
**Not fixed:** Out of scope (pre-existing, not caused by 08-01 changes)
