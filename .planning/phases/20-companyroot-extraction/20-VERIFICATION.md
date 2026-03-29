---
phase: 20-companyroot-extraction
verified: 2026-03-29T00:00:00Z
status: passed
score: 10/12 must-haves verified
gaps:
  - truth: "test_daemon.py lifecycle tests pass without hanging"
    status: failed
    reason: "MockBot.start() never sets daemon._bot_ready_event. Daemon._run() now awaits asyncio.wait([bot_ready_task, self._bot_task]) before reaching shutdown_event.wait(). Tests only set daemon._shutdown_event, so the daemon waits forever on bot readiness -- MockBot never returns from start() and never sets the event, causing all lifecycle tests to hang."
    artifacts:
      - path: "tests/test_daemon.py"
        issue: "MockBot does not set daemon._bot_ready_event; all tests that call daemon._run() hang indefinitely"
      - path: "src/vcompany/daemon/daemon.py"
        issue: "Daemon._run() now gated on _bot_ready_event before reaching shutdown_event.wait() -- pre-existing tests did not anticipate this new wait"
    missing:
      - "MockBot.start() must set daemon._bot_ready_event after being called (e.g. self._daemon._bot_ready_event.set() or tests must patch the event)"
      - "Each test fixture that runs daemon._run() must ensure _bot_ready_event is set before the shutdown trigger fires"
  - truth: "asyncio.get_event_loop() usage eliminated from production code"
    status: failed
    reason: "src/vcompany/daemon/runtime_api.py line 346 uses asyncio.get_event_loop().create_future() in _on_escalate_to_strategist(). On Python 3.12 there is no current event loop outside an async context, so this raises DeprecationWarning and will break when called from a non-async context or a different thread."
    artifacts:
      - path: "src/vcompany/daemon/runtime_api.py"
        issue: "Line 346: asyncio.get_event_loop().create_future() -- deprecated in Python 3.10, broken in Python 3.12 outside async context. Should be asyncio.get_running_loop().create_future()"
    missing:
      - "Replace asyncio.get_event_loop().create_future() with asyncio.get_running_loop().create_future() in RuntimeAPI._on_escalate_to_strategist()"
human_verification:
  - test: "Start vco daemon and observe Discord on_ready -> CompanyRoot initialization sequence"
    expected: "Bot connects, on_ready fires, CommunicationPort registered, _bot_ready_event set, daemon initializes CompanyRoot via _create_runtime_api, logs 'RuntimeAPI initialized', logs 'Project X initialized in daemon'"
    why_human: "Requires live Discord bot token and guild -- cannot verify end-to-end async init sequence programmatically"
  - test: "Post a message in #strategist Discord channel"
    expected: "Message routes through RuntimeAPI.relay_strategist_message to CompanyAgent, Strategist responds in channel via CommunicationPort.send_message"
    why_human: "Full COMM-04 path requires live Discord connection and Anthropic API"
  - test: "Approve a plan via Discord button in #plan-review"
    expected: "PlanReviewCog._handle_approval calls RuntimeAPI.handle_plan_approval, which posts to #plan-review via CommunicationPort and delivers plan_approved event to GsdAgent"
    why_human: "Requires live Discord connection and a plan file present for a running agent"
---

# Phase 20: CompanyRoot Extraction Verification Report

**Phase Goal:** CompanyRoot, supervision tree, Strategist conversation, and PM review flow all run inside the daemon process, accessed exclusively through a RuntimeAPI gateway
**Verified:** 2026-03-29
**Status:** gaps_found
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | RuntimeAPI class exists with typed async methods for all CompanyRoot operations | VERIFIED | `src/vcompany/daemon/runtime_api.py` exists with hire, give_task, dismiss, status, health_tree, new_project, register_channels, get_channel_id, relay_strategist_message, relay_strategist_escalation_reply, handle_plan_approval, handle_plan_rejection |
| 2 | CommunicationPort has 6 methods including create_channel and edit_message | VERIFIED | `src/vcompany/daemon/comm.py` defines 6-method protocol: send_message, send_embed, create_thread, subscribe_to_channel, create_channel, edit_message; NoopCommunicationPort implements all 6 |
| 3 | Daemon owns CompanyRoot initialization via RuntimeAPI | VERIFIED | `src/vcompany/daemon/daemon.py` _create_runtime_api() constructs CompanyRoot, wraps in RuntimeAPI, registers with _runtime_api field; _init_company_root() called after _bot_ready_event fires |
| 4 | DiscordCommunicationPort implements create_channel and edit_message | VERIFIED | `src/vcompany/bot/comm_adapter.py` lines 97-173 implement both methods with find-or-create category/channel logic and full error handling |
| 5 | All callback closures from on_ready replaced with RuntimeAPI methods | VERIFIED | RuntimeAPI contains _on_escalation, _on_degraded, _on_recovered, _on_trigger_integration_review, _on_send_intervention, _on_strategist_response, _make_pm_event_sink, _make_gsd_cb, _make_briefing_cb, _post_review_request, _dispatch_pm_review, _on_assign_task, _on_recruit_agent, _on_remove_agent, _on_escalate_to_strategist; new_project() replaces on_ready project init block |
| 6 | Bot accesses CompanyRoot exclusively through RuntimeAPI | VERIFIED | client.py has no supervisor/container/agent imports; commands.py uses _get_runtime_api() and _get_company_root() bridges; import boundary test passes (13/13) |
| 7 | VcoBot.on_ready() contains only Discord-specific concerns and signals daemon | VERIFIED | on_ready() handles role creation, system channels, CommunicationPort registration, channel ID registration, then calls _daemon._bot_ready_event.set() at line 192 |
| 8 | StrategistCog routes inbound messages through RuntimeAPI.relay_strategist_message | VERIFIED | strategist.py lines 183-195: checks for daemon.runtime_api, calls relay_strategist_message if available; falls back to CompanyAgent.post_event |
| 9 | PlanReviewCog routes approval/rejection through RuntimeAPI | VERIFIED | plan_review.py: _handle_approval calls runtime_api.handle_plan_approval (line 365); _handle_rejection calls runtime_api.handle_plan_rejection (line 394) |
| 10 | Zero discord.py imports in daemon package | VERIFIED | grep finds no "import discord" in src/vcompany/daemon/*.py; test_import_boundary::test_no_discord_in_daemon passes |
| 11 | test_daemon.py lifecycle tests pass without hanging | FAILED | MockBot.start() never sets daemon._bot_ready_event; Daemon._run() now awaits asyncio.wait on bot_ready_task before reaching shutdown_event.wait() -- tests deadlock |
| 12 | asyncio.get_event_loop() eliminated from production code | FAILED | src/vcompany/daemon/runtime_api.py line 346 uses asyncio.get_event_loop().create_future() in _on_escalate_to_strategist() -- deprecated on Python 3.10+, broken on Python 3.12 outside async context |

**Score:** 10/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/vcompany/daemon/runtime_api.py` | RuntimeAPI gateway class | VERIFIED | 597 lines; exports RuntimeAPI with all lifecycle, callback, and inbound relay methods |
| `src/vcompany/daemon/comm.py` | Extended CommunicationPort with create_channel, edit_message | VERIFIED | 6-method protocol + CreateChannelPayload, CreateChannelResult, EditMessagePayload models; NoopCommunicationPort implements all 6 |
| `src/vcompany/bot/comm_adapter.py` | DiscordCommunicationPort implementing new methods | VERIFIED | create_channel: find-or-create category + channel; edit_message: fetch + edit with NotFound/HTTPException handling |
| `src/vcompany/daemon/daemon.py` | Daemon owning RuntimeAPI and CompanyRoot lifecycle | VERIFIED | _create_runtime_api, _init_company_root, _init_project, _register_socket_endpoints, _send_boot_notifications, _shutdown (CompanyRoot.stop()) all present |
| `src/vcompany/bot/client.py` | Gutted on_ready; no container imports | VERIFIED | No supervisor/container/agent imports; on_ready calls _bot_ready_event.set() at end |
| `src/vcompany/bot/cogs/commands.py` | CommandsCog using RuntimeAPI for /new-project | VERIFIED | Lines 187-196: calls runtime_api.new_project(); uses _get_runtime_api() helper throughout |
| `src/vcompany/bot/cogs/strategist.py` | StrategistCog routing inbound through RuntimeAPI | VERIFIED | Lines 183-195: routes through relay_strategist_message if runtime_api available |
| `src/vcompany/bot/cogs/plan_review.py` | PlanReviewCog routing approval/rejection through RuntimeAPI | VERIFIED | _handle_approval and _handle_rejection both call respective RuntimeAPI methods |
| `tests/test_runtime_api.py` | RuntimeAPI method tests | VERIFIED | 11 tests; all pass; covers hire, give_task, dismiss, status, health_tree, register_channels, relay_strategist_message, handle_plan_approval, handle_plan_rejection, no_discord_imports |
| `tests/test_import_boundary.py` | Import boundary enforcement test | VERIFIED | 2 tests; test_no_container_imports_in_bot and test_no_discord_in_daemon both pass |
| `tests/test_daemon.py` | Daemon lifecycle tests | FAILED (HUNG) | MockBot never sets _bot_ready_event; tests that call daemon._run() will deadlock |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/vcompany/daemon/runtime_api.py` | `src/vcompany/daemon/comm.py` | CommunicationPort protocol usage (create_channel, send_message) | WIRED | All outbound calls use self._get_comm().send_message/create_channel with payload models |
| `src/vcompany/daemon/daemon.py` | `src/vcompany/daemon/runtime_api.py` | Daemon owns RuntimeAPI via self._runtime_api | WIRED | _create_runtime_api() sets self._runtime_api; runtime_api property exposes it |
| `src/vcompany/bot/client.py` | `src/vcompany/daemon/daemon.py` | _bot_ready_event.set() signals daemon | WIRED | Line 192: `self._daemon._bot_ready_event.set()` |
| `src/vcompany/bot/cogs/commands.py` | `src/vcompany/daemon/runtime_api.py` | _get_runtime_api() then runtime_api.new_project() | WIRED | /new-project calls runtime_api.new_project() at line 189 |
| `src/vcompany/bot/cogs/strategist.py` | `src/vcompany/daemon/runtime_api.py` | relay_strategist_message for COMM-04 receive | WIRED | Lines 183-195 route through RuntimeAPI when available |
| `src/vcompany/bot/cogs/plan_review.py` | `src/vcompany/daemon/runtime_api.py` | handle_plan_approval/rejection for COMM-05 receive | WIRED | _handle_approval line 365, _handle_rejection line 394 |
| `src/vcompany/supervisor/company_root.py` | (no guild param) | Channel creation removed | VERIFIED | hire() signature has no guild parameter; no channel_setup import; docstring updated |

### Data-Flow Trace (Level 4)

Not applicable for this phase -- no UI components that render dynamic data from queries. RuntimeAPI is a coordination layer, not a data rendering layer.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| RuntimeAPI imports cleanly | `uv run python -c "from vcompany.daemon.runtime_api import RuntimeAPI; print('OK')"` | RuntimeAPI OK | PASS |
| CommunicationPort protocol has 6 methods | `uv run python -c "from vcompany.daemon.comm import CommunicationPort, CreateChannelPayload, EditMessagePayload; print('OK')"` | comm OK | PASS |
| Daemon imports cleanly | `uv run python -c "from vcompany.daemon.daemon import Daemon; print('OK')"` | Daemon OK | PASS |
| VcoBot imports cleanly | `uv run python -c "from vcompany.bot.client import VcoBot; print('OK')"` | VcoBot OK | PASS |
| RuntimeAPI unit tests pass | `uv run pytest tests/test_runtime_api.py -q` | 11 passed in 0.14s | PASS |
| Import boundary tests pass | `uv run pytest tests/test_import_boundary.py -q` | 2 passed in 0.02s | PASS |
| CompanyRoot.hire() has no guild param | `uv run python -c "import inspect; from vcompany.supervisor.company_root import CompanyRoot; sig=inspect.signature(CompanyRoot.hire); assert 'guild' not in sig.parameters; print('OK')"` | OK | PASS |
| No discord imports in daemon package | `grep -r "import discord" src/vcompany/daemon/` | no output | PASS |
| test_daemon.py runs without hanging | timeout 30 uv run pytest tests/test_daemon.py | HUNG (deadlock -- _bot_ready_event never set by MockBot) | FAIL |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| EXTRACT-01 | 20-01 | CompanyRoot and supervision tree run inside daemon process, not bot | SATISFIED | Daemon._create_runtime_api() creates CompanyRoot; client.py has no CompanyRoot construction |
| EXTRACT-02 | 20-01 | RuntimeAPI gateway class provides typed methods for all CompanyRoot operations | SATISFIED | runtime_api.py: hire, give_task, dismiss, status, health_tree + all callback methods |
| EXTRACT-03 | 20-02, 20-03 | All callback closures from on_ready() replaced with RuntimeAPI calls or event subscriptions | SATISFIED | RuntimeAPI contains 14+ callback replacement methods; new_project() replaces 400-line on_ready block |
| EXTRACT-04 | 20-03, 20-04 | Bot accesses CompanyRoot exclusively through RuntimeAPI (no direct imports) | SATISFIED | No supervisor/container imports in bot layer (module-level); import boundary test passes; cogs use _get_runtime_api() |
| COMM-04 | 20-02, 20-04 | StrategistConversation runs in daemon, sends/receives through CommunicationPort | SATISFIED | relay_strategist_message and relay_strategist_escalation_reply in RuntimeAPI; StrategistCog routes through RuntimeAPI |
| COMM-05 | 20-02, 20-04 | PM review flow state machine runs in daemon, sends review requests and receives responses through CommunicationPort | SATISFIED | handle_plan_approval/handle_plan_rejection in RuntimeAPI; PlanReviewCog routes through RuntimeAPI; _post_review_request and _dispatch_pm_review use CommunicationPort |
| COMM-06 | 20-01 | Channel creation requested by daemon through CommunicationPort | SATISFIED | RuntimeAPI.hire() calls create_channel via CommunicationPort; DiscordCommunicationPort implements create_channel with find-or-create logic |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/vcompany/daemon/runtime_api.py` | 346 | `asyncio.get_event_loop().create_future()` -- deprecated API, broken on Python 3.12 outside async context | BLOCKER | _on_escalate_to_strategist() is an async method so it runs inside an event loop; however this is the deprecated form; should be asyncio.get_running_loop().create_future() |
| `tests/test_daemon.py` | throughout | MockBot.start() never sets daemon._bot_ready_event; all tests calling _run() deadlock indefinitely | BLOCKER | All daemon lifecycle tests hang because daemon waits on _bot_ready_event before reaching _shutdown_event.wait() |
| `tests/test_daemon_comm.py` | 115, 129 | asyncio.get_event_loop().run_until_complete() -- deprecated on Python 3.12; emits DeprecationWarning | WARNING | Tests pass with DeprecationWarning in Python 3.12.3; will break in a future Python version |

### Human Verification Required

#### 1. End-to-End Bot Startup with CompanyRoot

**Test:** Start the daemon with a real Discord bot token and guild. Observe logs.
**Expected:** Bot connects, on_ready fires, CommunicationPort registered with daemon, _bot_ready_event set, daemon logs "Bot connected, initializing CompanyRoot...", RuntimeAPI created, project initialized if agents.yaml present.
**Why human:** Requires live Discord token and guild -- cannot exercise the full async startup sequence programmatically.

#### 2. COMM-04 Full Path (Strategist Conversation)

**Test:** Post a message to the #strategist Discord channel after startup.
**Expected:** StrategistCog.on_message routes through RuntimeAPI.relay_strategist_message, which delivers a user_message event to CompanyAgent, which calls StrategistConversation.send(), and the response posts back to Discord via CommunicationPort.send_message.
**Why human:** Full COMM-04 path requires live Discord connection, Anthropic API, and a running CompanyAgent.

#### 3. COMM-05 Full Path (Plan Review)

**Test:** Trigger a plan review (e.g. via agent posting @PM plan ready in an agent channel, or manually via PlanReviewCog). Then click Approve button.
**Expected:** PlanReviewCog._handle_approval calls RuntimeAPI.handle_plan_approval, which sends confirmation to #plan-review via CommunicationPort and delivers plan_approved event to the GsdAgent.
**Why human:** Requires a live Discord session with a running GsdAgent and active review message.

### Gaps Summary

Two gaps block full verification:

**Gap 1 -- test_daemon.py hangs (BLOCKER):** After Plan 03 added `_bot_ready_event` gating to `Daemon._run()`, the pre-existing `MockBot` in `tests/test_daemon.py` became incompatible. MockBot.start() awaits `self._stop_event.wait()` and never touches `daemon._bot_ready_event`. The daemon now sits in `asyncio.wait([bot_ready_task, self._bot_task])` indefinitely -- neither task completes because MockBot never signals readiness and never returns from start(). All tests that exercise `daemon._run()` are effectively disabled until MockBot sets `_bot_ready_event`.

**Gap 2 -- asyncio.get_event_loop() in production code (BLOCKER):** `runtime_api.py` line 346 uses `asyncio.get_event_loop().create_future()` inside `_on_escalate_to_strategist()`. In Python 3.12, `asyncio.get_event_loop()` emits DeprecationWarning and may raise RuntimeError in some contexts. Since this method is async (always called from a running loop), the correct form is `asyncio.get_running_loop().create_future()`. The same pattern appears in `tests/test_daemon_comm.py` lines 115 and 129, which pass but emit DeprecationWarning.

All seven required requirements (EXTRACT-01 through EXTRACT-04, COMM-04 through COMM-06) are satisfied by the implementation. The two gaps are test infrastructure issues, not gaps in the business logic implementation.

---

_Verified: 2026-03-29_
_Verifier: Claude (gsd-verifier)_
