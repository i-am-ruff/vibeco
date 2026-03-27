---
phase: 05-hooks-and-plan-gate
verified: 2026-03-25T20:45:00Z
status: passed
score: 13/13 must-haves verified
re_verification: false
---

# Phase 05: Hooks and Plan Gate Verification Report

**Phase Goal:** Agents can ask questions that route through Discord for answers, and new plans are gated for review before execution proceeds
**Verified:** 2026-03-25T20:45:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                             | Status     | Evidence                                                                                   |
|----|---------------------------------------------------------------------------------------------------|------------|--------------------------------------------------------------------------------------------|
| 1  | Hook reads AskUserQuestion JSON from stdin and returns deny+reason JSON on stdout                | VERIFIED | `parse_stdin()` reads `sys.stdin.read()`, `output_deny()` writes JSON; behavioral spot-check confirmed |
| 2  | Hook posts formatted question to Discord webhook with agent ID and options                        | VERIFIED | `post_question()` uses `urllib.request.urlopen` with embed payload including agent_id and fields |
| 3  | Hook polls `/tmp/vco-answers/{request_id}.json` every 5s for up to 10 minutes                   | VERIFIED | `poll_answer()` uses `time.sleep(5)`, `MAX_POLLS=120` (120 x 5s = 600s)                   |
| 4  | Hook falls back to first option on timeout in continue mode, blocks in block mode                | VERIFIED | `get_fallback_answer()` handles both `continue` and `block` modes; tests confirmed         |
| 5  | Hook NEVER hangs — top-level try/except guarantees JSON output on any error                       | VERIFIED | `if __name__ == "__main__":` wraps `main()` in try/except; behavioral spot-check on malformed stdin confirmed |
| 6  | Hook uses only Python stdlib (no imports from vcompany codebase)                                  | VERIFIED | AST check returned only `['__future__']` (which is stdlib); no httpx/requests/vcompany    |
| 7  | AgentMonitorState has plan_gate_status field with values idle/awaiting_review/approved/rejected   | VERIFIED | `plan_gate_status: Literal["idle", "awaiting_review", "approved", "rejected"] = "idle"` in monitor_state.py |
| 8  | Safety validator detects presence of Interaction Safety heading and 6-column table               | VERIFIED | `validate_safety_table()` with `REQUIRED_COLUMNS` list and `re.search(r'^##\s+Interaction Safety')` |
| 9  | PlanReviewCog posts plan summaries to #plan-review with rich embeds and file attachment           | VERIFIED | `handle_new_plan()` calls `build_plan_review_embed()`, creates `discord.File`, and posts via `_plan_review_channel.send()` |
| 10 | Approve button sets plan_gate_status to approved; reject button opens feedback modal             | VERIFIED | `PlanReviewView.approve()` sets `self.result = "approved"`; `reject()` sends `RejectFeedbackModal` |
| 11 | Rejection feedback is sent to agent tmux pane via TmuxManager                                    | VERIFIED | `_handle_rejection()` reads `AgentsRegistry`, finds `entry.pane_id`, calls `tmux.send_command()` |
| 12 | Bot listens for webhook messages in #strategist and creates interactive answer UIs               | VERIFIED | `QuestionHandlerCog.on_message()` filters by `message.webhook_id`, extracts `request_id`, posts `AnswerView` |
| 13 | Bot writes answer files atomically to /tmp/vco-answers/{request_id}.json for hook polling        | VERIFIED | `_write_answer_file_sync()` uses `tempfile.mkstemp()` + `os.rename()` atomic pattern      |

**Score:** 13/13 truths verified

### Required Artifacts

| Artifact                                               | Expected                                           | Status     | Details                                                      |
|--------------------------------------------------------|----------------------------------------------------|------------|--------------------------------------------------------------|
| `tools/ask_discord.py`                                 | Self-contained PreToolUse hook                     | VERIFIED   | Executable, 8881 bytes, all 8 functions present              |
| `tests/test_ask_discord.py`                            | Unit tests for hook behaviors                      | VERIFIED   | 12 tests, all pass                                           |
| `src/vcompany/models/monitor_state.py`                 | Extended AgentMonitorState with plan gate fields   | VERIFIED   | plan_gate_status, pending_plans, approved_plans added        |
| `src/vcompany/monitor/safety_validator.py`             | Safety table validation                            | VERIFIED   | validate_safety_table() with 6 required columns              |
| `src/vcompany/templates/gsd_config.json.j2`            | GSD config with auto_advance disabled              | VERIFIED   | `"auto_advance": false` present                              |
| `tests/test_safety_validator.py`                       | Unit tests for safety validation                   | VERIFIED   | 8 tests, all pass                                            |
| `src/vcompany/bot/views/plan_review.py`                | PlanReviewView with Approve/Reject buttons         | VERIFIED   | class PlanReviewView, result and feedback attributes         |
| `src/vcompany/bot/views/reject_modal.py`               | RejectFeedbackModal for rejection reason           | VERIFIED   | class RejectFeedbackModal, feedback_text attribute           |
| `src/vcompany/bot/cogs/plan_review.py`                 | Full PlanReviewCog with plan gate workflow         | VERIFIED   | handle_new_plan, _handle_approval, _handle_rejection, _trigger_execution, make_sync_callback all present |
| `src/vcompany/bot/embeds.py`                           | Plan review embed builder                          | VERIFIED   | build_plan_review_embed() with safety_valid parameter        |
| `tests/test_plan_review_cog.py`                        | Tests for plan review components                   | VERIFIED   | 29 tests, all pass                                           |
| `src/vcompany/bot/cogs/question_handler.py`            | QuestionHandlerCog with answer delivery            | VERIFIED   | QuestionHandlerCog, AnswerView, OtherAnswerModal, atomic write |
| `src/vcompany/bot/cogs/alerts.py`                      | Extended AlertsCog with timeout alert              | VERIFIED   | alert_hook_timeout() method present                          |
| `src/vcompany/bot/client.py`                           | Updated client wiring PlanReviewCog callback       | VERIFIED   | question_handler in _COG_EXTENSIONS, plan_review_cog.make_sync_callback() wired |
| `tests/test_question_handler.py`                       | Tests for QuestionHandlerCog                       | VERIFIED   | 11 tests, all pass                                           |

### Key Link Verification

| From                                        | To                                          | Via                                              | Status   | Details                                                           |
|---------------------------------------------|---------------------------------------------|--------------------------------------------------|----------|-------------------------------------------------------------------|
| `tools/ask_discord.py`                      | Discord webhook                             | `urllib.request.urlopen` POST                    | WIRED    | `urllib.request.urlopen(req, timeout=10)` at lines 115, 219       |
| `tools/ask_discord.py`                      | `/tmp/vco-answers/{request_id}.json`        | file polling loop with `time.sleep(5)`           | WIRED    | `poll_answer()` loops with `time.sleep(POLL_INTERVAL)`, checks `ANSWER_DIR / f"{request_id}.json"` |
| `src/vcompany/bot/cogs/plan_review.py`      | `src/vcompany/bot/views/plan_review.py`     | `PlanReviewView(` instantiation                  | WIRED    | Line 101: `view = PlanReviewView(agent_id=agent_id, plan_path=str(plan_path))` |
| `src/vcompany/bot/views/plan_review.py`     | `src/vcompany/bot/views/reject_modal.py`    | `RejectFeedbackModal(` on reject button          | WIRED    | `modal = RejectFeedbackModal()` in `reject()` button handler       |
| `src/vcompany/bot/cogs/plan_review.py`      | `src/vcompany/bot/embeds.py`                | `build_plan_review_embed(` call                  | WIRED    | Line 89: `embed = build_plan_review_embed(...)` in `handle_new_plan()` |
| `src/vcompany/bot/cogs/question_handler.py` | `/tmp/vco-answers/{request_id}.json`        | atomic file write via `os.rename`                | WIRED    | `_write_answer_file_sync()` uses `tempfile.mkstemp()` + `os.rename()` |
| `src/vcompany/bot/client.py`                | `src/vcompany/bot/cogs/plan_review.py`      | `plan_review_cog.make_sync_callback()` in MonitorLoop | WIRED | Lines 124-131: `plan_review_cog = self.get_cog("PlanReviewCog")`, callback injected as `on_plan_detected` |
| `src/vcompany/bot/cogs/question_handler.py` | #strategist channel                         | `on_message` listener watching for webhook embeds | WIRED   | `@commands.Cog.listener()` on `on_message()`, filters by `message.webhook_id` |

### Data-Flow Trace (Level 4)

| Artifact                                    | Data Variable     | Source                                   | Produces Real Data | Status   |
|---------------------------------------------|-------------------|------------------------------------------|--------------------|----------|
| `tools/ask_discord.py`                      | `answer`          | File poll at `/tmp/vco-answers/*.json`   | Yes (real file IPC) | FLOWING  |
| `src/vcompany/bot/cogs/question_handler.py` | `options`         | Discord embed fields from webhook message | Yes (webhook embed) | FLOWING  |
| `src/vcompany/bot/cogs/plan_review.py`      | `plan_content`    | `asyncio.to_thread(plan_path.read_text)` | Yes (real file read) | FLOWING  |
| `src/vcompany/bot/cogs/plan_review.py`      | `safety_valid`    | `validate_safety_table(plan_content)`    | Yes (real validation) | FLOWING  |
| `src/vcompany/bot/cogs/plan_review.py`      | state updates     | `self.bot.monitor_loop._agent_states`    | Yes (live state dict) | FLOWING  |

### Behavioral Spot-Checks

| Behavior                                             | Command                                                    | Result                                                                                 | Status |
|------------------------------------------------------|------------------------------------------------------------|----------------------------------------------------------------------------------------|--------|
| Non-AskUserQuestion tool gets allow response         | `echo '{"tool_name": "Read", ...}' \| python3 ask_discord.py` | `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}` | PASS   |
| Malformed stdin produces deny fallback, never hangs  | `echo 'bad json' \| python3 ask_discord.py`               | `{"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "Hook error (auto-fallback): ..."}}` | PASS   |
| All phase 05 unit tests pass                         | `uv run pytest tests/test_ask_discord.py tests/test_safety_validator.py tests/test_plan_review_cog.py tests/test_question_handler.py` | 60 passed | PASS   |
| Full test suite passes without regressions           | `uv run pytest tests/`                                     | 317 passed, 0 failed                                                                   | PASS   |

### Requirements Coverage

| Requirement | Source Plan | Description                                                                                      | Status    | Evidence                                                               |
|-------------|-------------|--------------------------------------------------------------------------------------------------|-----------|------------------------------------------------------------------------|
| HOOK-01     | 05-01       | ask_discord.py intercepts AskUserQuestion via PreToolUse hook                                    | SATISFIED | `if input_data.get("tool_name") != "AskUserQuestion": output_allow()`  |
| HOOK-02     | 05-01, 05-04 | Hook posts formatted question with agent ID and options to #strategist channel                  | SATISFIED | `post_question()` builds embed with agent_id; QuestionHandlerCog bridges to answer UI |
| HOOK-03     | 05-01, 05-04 | Hook polls for reply every 5s with 10-minute timeout                                            | SATISFIED | `POLL_INTERVAL=5`, `MAX_POLLS=120`; bot writes answer file atomically   |
| HOOK-04     | 05-01, 05-04 | On timeout, hook falls back to first option, notes assumption, alerts #alerts                   | SATISFIED | `get_fallback_answer()` + `alert_timeout()` posts warning embed; `alert_hook_timeout()` on AlertsCog |
| HOOK-05     | 05-01       | Hook returns deny + permissionDecisionReason carrying the answer back to Claude                  | SATISFIED | `output_deny(f"Human answered via Discord: {answer}")`                  |
| HOOK-06     | 05-01       | Hook is self-contained (no imports from main codebase) — runs in agent clone context             | SATISFIED | AST check: only stdlib imports (`sys`, `json`, `os`, `time`, `uuid`, `urllib`, `pathlib`) |
| HOOK-07     | 05-01       | Hook wrapped in try/except with guaranteed fallback response (never hangs)                       | SATISFIED | Top-level `except Exception as exc: output_deny(f"Hook error...")` confirmed by spot-check |
| GATE-01     | 05-02, 05-04 | Plan gate detects PLAN.md completion (via MonitorLoop)                                          | SATISFIED | MonitorLoop `on_plan_detected` callback routed to PlanReviewCog; state tracks `pending_plans` |
| GATE-02     | 05-03, 05-04 | Plan gate posts plans to #plan-review with agent ID, plan descriptions, task counts             | SATISFIED | `handle_new_plan()` builds embed with all fields, posts to `#plan-review` with file attachment |
| GATE-03     | 05-03, 05-04 | Plan gate pauses agent execution until PM/owner approves or rejects                             | SATISFIED | `await view.wait()` blocks coroutine; 3600s timeout; PlanReviewView Approve/Reject buttons |
| GATE-04     | 05-03       | On rejection, agent receives feedback and re-plans                                               | SATISFIED | `_handle_rejection()` sends feedback via `tmux.send_command(entry.pane_id, feedback_cmd)` |
| SAFE-01     | 05-02       | Plans include Interaction Safety Table with 6-column schema                                      | SATISFIED | `validate_safety_table()` checks for `## Interaction Safety` h2 + all 6 required columns |
| SAFE-02     | 05-02       | Plan checker agent validates interaction safety table completeness                               | SATISFIED | `validate_safety_table()` called in `handle_new_plan()` before posting; safety status shown in embed |

### Anti-Patterns Found

| File                                                  | Line | Pattern                         | Severity | Impact         |
|-------------------------------------------------------|------|---------------------------------|----------|----------------|
| `src/vcompany/bot/cogs/plan_review.py`                | 493  | `tmux.send_command` accesses `agent_manager._tmux` (private attr) | Info | Internal access, works in practice but fragile |

No blockers or warnings found. The single Info item accesses a private attribute of `AgentManager` (`_tmux`) which is an internal access pattern. It does not prevent the goal from being achieved.

### Human Verification Required

#### 1. Full Hook-to-Bot End-to-End Flow

**Test:** Configure a real Discord bot and agent with `DISCORD_AGENT_WEBHOOK_URL` and `VCO_AGENT_ID`. Trigger an agent that calls `AskUserQuestion`. Observe: webhook embed appears in #strategist, bot posts follow-up with option buttons, click a button, verify agent receives the answer.
**Expected:** Agent unblocks with "Human answered via Discord: {selected answer}"
**Why human:** Requires a live Discord server, bot token, and running agent — not testable programmatically.

#### 2. Plan Gate End-to-End Flow

**Test:** Dispatch an agent that writes a PLAN.md. Observe: embed appears in #plan-review with Approve/Reject buttons. Click Approve. Verify agent receives `/gsd:execute-phase` command in its tmux pane.
**Expected:** Agent advances to execution phase after approval.
**Why human:** Requires live Discord server, running MonitorLoop, live agent in tmux session.

#### 3. Plan Rejection Feedback Delivery

**Test:** From the #plan-review embed, click Reject, enter feedback text in the modal, submit. Verify the agent's tmux pane receives the rejection message.
**Expected:** Agent receives feedback and can replan (re-runs planning phase).
**Why human:** Requires live tmux session with agent running.

#### 4. Timeout Mode Behavior (block mode)

**Test:** Set `VCO_TIMEOUT_MODE=block`, trigger AskUserQuestion, do NOT answer in Discord for 10 minutes. Observe: agent is told to wait indefinitely, #alerts receives no auto-fallback notification.
**Expected:** Hook returns block message; agent pauses; no Discord notification in continue-mode alert channel.
**Why human:** 10-minute real-time wait, requires live environment.

### Gaps Summary

No gaps found. All 13 requirements satisfied, all 13 truths verified, all 8 key links wired, all 15 artifacts substantive and wired. The full test suite (317 tests) passes with zero failures. Two behavioral spot-checks confirmed the hook executes correctly: non-AskUserQuestion tools receive `allow` passthrough, and malformed stdin triggers the guaranteed error fallback.

---

_Verified: 2026-03-25T20:45:00Z_
_Verifier: Claude (gsd-verifier)_
