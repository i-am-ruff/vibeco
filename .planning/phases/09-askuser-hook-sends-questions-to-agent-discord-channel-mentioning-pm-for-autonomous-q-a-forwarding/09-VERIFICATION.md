---
phase: 09-askuser-hook-sends-questions-to-agent-discord-channel-mentioning-pm-for-autonomous-q-a-forwarding
verified: 2026-03-27T02:00:00Z
status: passed
score: 20/20 must-haves verified
re_verification: false
---

# Phase 9: AskUser Hook Discord Routing Verification Report

**Phase Goal:** Reroute AskUserQuestion hook to post agent questions to #agent-{id} channels, implement Discord message routing framework with reply-based and @mention-based interaction rules, enable PM auto-answering via Discord replies, and replace file-based IPC with Discord-only answer delivery.
**Verified:** 2026-03-27T02:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                               | Status     | Evidence                                                                  |
|----|-------------------------------------------------------------------------------------|------------|---------------------------------------------------------------------------|
| 1  | route_message returns correct RouteTarget for reply-based messages                  | VERIFIED   | routing.py lines 159-189; 19 tests pass including reply routing cases     |
| 2  | route_message returns correct RouteTarget for @mention-based messages               | VERIFIED   | routing.py lines 191-206; test_routing.py covers @PM and @Strategist      |
| 3  | route_message returns channel-owner default in #agent-{id} channels                 | VERIFIED   | routing.py lines 208-214; TestChannelOwnerDefault passes                  |
| 4  | route_message returns STRATEGIST default in #strategist channel                     | VERIFIED   | routing.py lines 216-218; TestStrategistDefault passes                    |
| 5  | Strategist ignores messages not addressed to it per D-07                            | VERIFIED   | strategist.py line 131 `if route.target != RouteTarget.STRATEGIST: return`|
| 6  | Agent dispatch exports VCO_AGENT_ID env var alongside existing AGENT_ID             | VERIFIED   | agent_manager.py line 114 and 181 both export VCO_AGENT_ID               |
| 7  | Settings.json timeout supports long-running owner escalations                        | VERIFIED   | settings.json.j2 line 10: `"timeout": 86400`                             |
| 8  | Hook posts questions to #agent-{id} channel via Discord REST API (not webhook)      | VERIFIED   | ask_discord.py: resolve_channel + post_question use discord.com/api/v10   |
| 9  | Hook polls Discord API for replies to the question message                          | VERIFIED   | ask_discord.py poll_for_reply() checks message_reference.message_id       |
| 10 | First reply to the question message is treated as the answer                        | VERIFIED   | ask_discord.py line 231-232: first ref match returns immediately          |
| 11 | No file-based IPC remains (no /tmp/vco-answers/)                                    | VERIFIED   | grep returns no matches for vco-answers in hook or cogs                   |
| 12 | Hook uses VCO_AGENT_ID + DISCORD_BOT_TOKEN + DISCORD_GUILD_ID + PROJECT_NAME       | VERIFIED   | ask_discord.py line 326-330 reads all four env vars                       |
| 13 | Hook falls back to first option on 10-minute timeout for PM auto-answers            | VERIFIED   | MAX_POLLS_PM=120 (120*5s=10min); get_fallback_answer() selects first opt  |
| 14 | Hook continues polling beyond 10 minutes when escalation detected                   | VERIFIED   | poll_for_reply() sets effective_max=0 (infinite) on escalation marker     |
| 15 | Hook never hangs regardless of errors                                               | VERIFIED   | __main__ try/except guarantees output_deny on any exception               |
| 16 | QuestionHandlerCog detects question embeds in #agent-{id} channels (not #strategist)| VERIFIED  | question_handler.py line 62: is_question_embed(); no #strategist ref      |
| 17 | PM auto-answer is posted as a reply to the original question message                | VERIFIED   | question_handler.py lines 108, 114, 135, 152: await message.reply(...)    |
| 18 | PM escalation posts non-reply @Strategist mention (Pattern B per D-10)             | VERIFIED   | question_handler.py lines 123-124: message.channel.send() not reply       |
| 19 | Owner escalation posts in #agent-{id} channel (D-03)                               | VERIFIED   | question_handler.py line 149: channel=message.channel passed to escalation|
| 20 | StrategistCog uses routing framework + fetches replied-to content for D-07          | VERIFIED   | strategist.py lines 104-128: EntityRegistry, fetch_message, route_message |

**Score:** 20/20 truths verified

---

### Required Artifacts

| Artifact                                         | Expected                                   | Status     | Details                                                    |
|--------------------------------------------------|--------------------------------------------|------------|------------------------------------------------------------|
| `src/vcompany/bot/routing.py`                    | Message routing framework                  | VERIFIED   | 222 lines; exports RouteTarget, RouteResult, route_message, is_question_embed, extract_entity_from_prefix |
| `tests/test_routing.py`                          | Routing framework tests (min 80 lines)     | VERIFIED   | 312 lines, 19 test functions, all pass                     |
| `tools/ask_discord.py`                           | Discord REST API hook (post + reply poll)  | VERIFIED   | Contains discord.com/api/v10, resolve_channel, post_question, poll_for_reply, message_reference |
| `tests/test_ask_discord.py`                      | Hook unit tests (min 80 lines)             | VERIFIED   | 439 lines, 15 test functions, all pass                     |
| `src/vcompany/bot/cogs/question_handler.py`      | Agent-channel question detection           | VERIFIED   | Contains is_question_embed, message.reply, no ANSWER_DIR/AnswerView |
| `src/vcompany/bot/cogs/strategist.py`            | Routing framework adoption                 | VERIFIED   | Contains route_message, RouteTarget.STRATEGIST, fetch_message |
| `tests/test_question_handler.py`                 | Reworked tests (min 60 lines)              | VERIFIED   | 285 lines, 10 test functions, all pass                     |
| `tests/test_strategist_cog.py`                   | Routing integration tests (min 40 lines)   | VERIFIED   | 352 lines, 13 test functions, all pass                     |
| `src/vcompany/orchestrator/agent_manager.py`     | VCO_AGENT_ID in both dispatch paths        | VERIFIED   | Line 114 (dispatch) and 181 (dispatch_all) both export     |
| `src/vcompany/templates/settings.json.j2`        | 24h hook timeout                           | VERIFIED   | `"timeout": 86400` confirmed                              |

---

### Key Link Verification

| From                                      | To                              | Via                                 | Status   | Details                                                              |
|-------------------------------------------|---------------------------------|-------------------------------------|----------|----------------------------------------------------------------------|
| `src/vcompany/bot/routing.py`             | discord.Message                 | message.reference, mentions, channel| WIRED    | route_message() accepts message object and uses .reference, .mentions, .webhook_id |
| `src/vcompany/bot/cogs/question_handler.py` | `src/vcompany/bot/routing.py` | is_question_embed import            | WIRED    | Line 18: `from vcompany.bot.routing import is_question_embed`        |
| `src/vcompany/bot/cogs/question_handler.py` | `src/vcompany/strategist/pm.py`| PMTier.evaluate_question            | WIRED    | Line 104: `await self._pm.evaluate_question(question_text, agent_id)`|
| `src/vcompany/bot/cogs/strategist.py`     | `src/vcompany/bot/routing.py`   | route_message import                | WIRED    | Line 20: `from vcompany.bot.routing import EntityRegistry, RouteResult, RouteTarget, route_message` |
| `src/vcompany/bot/cogs/strategist.py`     | discord.TextChannel.fetch_message | Fetches replied-to content for routing | WIRED | Lines 113-119: fetch_message(message.reference.message_id)           |
| `tools/ask_discord.py`                    | Discord REST API                | urllib.request POST/GET             | WIRED    | Lines 128-130, 183-184, 208: all use _make_request with discord.com/api/v10/channels |
| `tools/ask_discord.py`                    | #agent-{id} channel             | resolve_channel + post_question     | WIRED    | Lines 337, 342: resolve_channel(agent_id) then post_question(channel_id) |

---

### Data-Flow Trace (Level 4)

N/A for this phase. All artifacts are orchestration/routing logic (no DB-backed data rendering). The hook posts to Discord REST API (external service), which is not verifiable programmatically. Test coverage verifies correctness via mocks.

---

### Behavioral Spot-Checks

| Behavior                                  | Command                                                                      | Result                        | Status  |
|-------------------------------------------|------------------------------------------------------------------------------|-------------------------------|---------|
| routing.py is valid Python and importable  | `uv run python -c "from vcompany.bot.routing import route_message, RouteTarget, RouteResult, EntityRegistry"` | No error | PASS    |
| ask_discord.py is valid Python            | `python3 -c "import ast; ast.parse(open('tools/ask_discord.py').read())"` | Exit 0                        | PASS    |
| All 57 phase tests pass                   | `uv run python -m pytest tests/test_routing.py tests/test_ask_discord.py tests/test_question_handler.py tests/test_strategist_cog.py` | 57 passed, 0 failed | PASS |
| No file-based IPC in any phase file       | grep for vco-answers/ANSWER_DIR/AnswerView in cogs and hook                  | No matches                    | PASS    |
| VCO_AGENT_ID in both dispatch paths       | grep -c VCO_AGENT_ID agent_manager.py                                        | 2 occurrences                 | PASS    |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                              | Status     | Evidence                                                           |
|-------------|-------------|--------------------------------------------------------------------------|------------|--------------------------------------------------------------------|
| D-01        | 09-02       | All questions post to #agent-{id} channel                                | SATISFIED  | ask_discord.py resolve_channel uses agent_id to find channel       |
| D-02        | 09-02       | Hook uses DISCORD_BOT_TOKEN + DISCORD_GUILD_ID via REST API              | SATISFIED  | ask_discord.py _make_request uses Bot token auth                   |
| D-03        | 09-02, 09-03| Escalation stays in #agent-{id} (no cross-posting to #strategist)        | SATISFIED  | question_handler.py line 149: channel=message.channel passed       |
| D-04        | 09-03       | All inter-component communication through Discord messages               | SATISFIED  | No file IPC in any cog; all answers via Discord reply              |
| D-05        | 09-02, 09-01| Entity prefix system ([PM], [agent-x]) in messages                       | SATISFIED  | ask_discord.py line 179: `[{agent_id}] has a question:`; question_handler lines 108, 114, 123-124 |
| D-06        | 09-01       | Message routing rules: reply-based, @mention-based, channel-owner default | SATISFIED | routing.py implements all 4 rules with priority order              |
| D-07        | 09-01, 09-03| Strategist ignores messages not directed to it                           | SATISFIED  | strategist.py line 131: returns if route.target != STRATEGIST      |
| D-08        | 09-01       | Routing framework is reusable by all Cogs                                | SATISFIED  | routing.py standalone module; imported by both question_handler and strategist |
| D-09        | 09-03       | PM monitors question embeds and evaluates                                | SATISFIED  | question_handler.py on_message detects is_question_embed then calls evaluate_question |
| D-10        | 09-03       | PM escalation uses non-reply mentions (Pattern B)                        | SATISFIED  | question_handler.py line 123: message.channel.send() not message.reply() |
| D-11        | 09-03       | PM replies as [PM] directly in Discord (no file writes)                  | SATISFIED  | question_handler.py lines 108, 114: await message.reply(f"[PM] {decision.answer}") |
| D-12        | 09-02       | Hook posts question, gets message ID, polls for replies                  | SATISFIED  | ask_discord.py: post_question returns msg_id, poll_for_reply uses it |
| D-13        | 09-02, 09-03| No /tmp/vco-answers file-based polling                                   | SATISFIED  | grep confirms no vco-answers/ANSWER_DIR/webhook_url anywhere        |
| D-14        | 09-02       | Hook is a blocking PreToolUse hook                                       | SATISFIED  | ask_discord.py: stdin parse -> post -> poll -> output_deny (blocking)|
| D-15        | 09-02       | In-place rewrite of tools/ask_discord.py                                 | SATISFIED  | File at tools/ask_discord.py (same path, settings.json.j2 unchanged)|
| D-16        | 09-01       | DISCORD_AGENT_WEBHOOK_URL replaced by DISCORD_BOT_TOKEN + DISCORD_GUILD_ID + VCO_AGENT_ID | SATISFIED | ask_discord.py reads all three; no DISCORD_AGENT_WEBHOOK_URL ref |
| D-17        | 09-02       | PM auto-answers: 10-minute timeout                                       | SATISFIED  | MAX_POLLS_PM=120 (120*5s=600s=10min)                               |
| D-18        | 09-02       | Owner escalations: wait indefinitely                                     | SATISFIED  | poll_for_reply switches to effective_max=0 on escalation marker; MAX_POLLS_ESCALATION=0 |
| D-19        | 09-03       | #decisions logs escalated decisions only (not routine HIGH answers)      | SATISFIED  | question_handler.py: line 109 explicitly skips logging for HIGH; _log_decision called only for MEDIUM/LOW/OWNER |
| D-20        | 09-02       | Agent channel is audit trail for routine Q&A                             | SATISFIED  | All messages (question, answer) posted in #agent-{id}; no cross-posting |

All 20 requirements satisfied.

---

### Anti-Patterns Found

No blockers or warnings detected.

| File                                              | Pattern | Severity | Impact |
|---------------------------------------------------|---------|----------|--------|
| No instances of TODO/FIXME/placeholder found      | —       | —        | —      |
| No return null / empty stub patterns found        | —       | —        | —      |
| No hardcoded empty data in rendering paths        | —       | —        | —      |

---

### Human Verification Required

#### 1. Live Discord Q&A Flow

**Test:** Run vco with a real agent session, trigger an AskUserQuestion tool call from Claude, observe the question appear in #agent-{id}, reply in Discord, verify Claude continues with the answer.
**Expected:** Question embed appears in correct channel within seconds of Claude calling AskUserQuestion; first reply resolves and agent continues.
**Why human:** Requires live Discord bot, live Claude agent session, and real Discord message observation. Cannot be mocked in unit tests.

#### 2. PM Auto-Answer Flow

**Test:** With PM injected, trigger a question the PM can answer with HIGH confidence. Verify the [PM] reply appears in the channel without owner intervention.
**Expected:** [PM] reply appears as a Discord reply to the question embed within 30 seconds; hook receives it and unblocks Claude.
**Why human:** Requires live Anthropic API key, Discord bot running, and observation of end-to-end message flow.

#### 3. Escalation Chain Visibility

**Test:** Trigger a question requiring escalation (LOW confidence PM). Observe: (1) [PM] Escalating message, (2) Strategist response, (3) if Strategist unsure: @Owner mention in #agent-{id} channel. Confirm #decisions channel gets an entry.
**Expected:** Non-reply escalation messages use Pattern B (standalone channel.send), #decisions receives entry only for MEDIUM/LOW/OWNER (not HIGH).
**Why human:** Full escalation chain requires live services and visual observation of Discord channel messages.

---

### Gaps Summary

No gaps. All automated checks passed at all three verification levels (exists, substantive, wired) plus data-flow spot-checks where applicable. All 57 tests pass (19 routing, 15 hook, 10 question_handler, 13 strategist_cog). All 20 requirements D-01 through D-20 are satisfied by concrete code evidence.

---

_Verified: 2026-03-27T02:00:00Z_
_Verifier: Claude (gsd-verifier)_
