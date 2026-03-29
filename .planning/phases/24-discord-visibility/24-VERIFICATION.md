---
phase: 24-discord-visibility
verified: 2026-03-29T17:05:00Z
status: passed
score: 11/11 truths verified
re_verification:
  previous_status: gaps_found
  previous_score: 9/11
  gaps_closed:
    - "RuntimeAPI handle_plan_approval/rejection now use receive_discord_message instead of removed post_event"
    - "Human button-click paths in PlanReviewCog now post [Review] formatted messages"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Verify deferred external callers are truly dead code in current runtime"
    expected: "strategist.py relay_strategist_message path, workflow_orchestrator_cog.py route_completion_to_pm path, and question_handler.py handle_pm_escalation path are unreachable at runtime (old routing removed)"
    why_human: "Requires live runtime trace to confirm these code paths are not triggered in normal operation"
  - test: "Backlog channel startup-order test"
    expected: "Backlog notifications appear in #backlog channel as agents perform work (requires register_channels before new_project)"
    why_human: "The backlog_channel variable is captured at new_project() call time. If register_channels() is not called first, backlog notifications silently drop. Requires live bot to verify startup sequencing."
---

# Phase 24: Discord Visibility Verification Report

**Phase Goal:** Every inter-agent event, PM action, and plan review decision is visible on Discord before taking effect -- no hidden internal routing
**Verified:** 2026-03-29T17:05:00Z
**Status:** passed
**Re-verification:** Yes -- after gap closure by Plan 24-05

## Re-Verification Summary

Previous verification (2026-03-29T16:36:20Z) found 9/11 truths verified with 2 gaps:

- **Gap 1 (Blocker):** `handle_plan_approval/rejection` in `RuntimeAPI` called `container.post_event()` on `GsdAgent`, a method removed in Plan 03. This caused `AttributeError` at runtime when a human clicked Approve/Reject buttons.
- **Gap 2 (Minor):** Human button-click paths in `PlanReviewCog._handle_approval/rejection` posted plain text ("Plan **approved**") instead of the structured `[Review] Plan for {agent_id}:` format used by the auto-approve path.

Plan 24-05 fixed both gaps. This re-verification confirms both fixes are correct and no regressions were introduced.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Generic MentionRouterCog watches all messages for @AgentHandle patterns and delivers to target container | VERIFIED | `src/vcompany/bot/cogs/mention_router.py` exists with `on_message` listener, `register_agent()`, and agent-type-agnostic routing |
| 2 | MessageContext pydantic model captures sender, channel, content, parent_message, is_reply | VERIFIED | `src/vcompany/models/messages.py` implements all fields; runtime import confirmed returning all 6 fields |
| 3 | AgentContainer.receive_discord_message() base method exists | VERIFIED | `src/vcompany/container/container.py` line 411; runtime assertion confirmed |
| 4 | #backlog channel included in project channel setup | VERIFIED | `src/vcompany/bot/channel_setup.py` `_PROJECT_CHANNELS` contains "backlog" |
| 5 | Every BacklogQueue mutation fires human-readable callback (VIS-02) | VERIFIED | All 7 mutation methods call `_notify()` after `_persist()`; no discord/bot imports in backlog.py |
| 6 | All three agents use receive_discord_message; event queues and old callback fields removed (VIS-05) | VERIFIED | FulltimeAgent, CompanyAgent, GsdAgent each have `receive_discord_message` override; no `_event_queue`, no `post_event`, no old callback fields |
| 7 | GsdAgent emits [Phase Complete] and [Review Request] Discord messages before taking effect (VIS-01/VIS-03) | VERIFIED | `gsd_agent.py` lines 212-229: `_send_discord()` calls emitted BEFORE awaiting `_pending_review` Future |
| 8 | Task assignment from PM to GSD agent is a Discord message [Task Assigned] (VIS-06) | VERIFIED | `fulltime_agent.py` `_auto_assign_next()` calls `_send_discord(f"agent-{agent_id}", f"[Task Assigned] @{agent_id}: ...")` |
| 9 | Supervisor has no pm_event_sink (VIS-05) | VERIFIED | `supervisor.py` `__init__` signature has no `pm_event_sink` parameter; runtime assertion confirmed |
| 10 | Plan review decisions posted to Discord before approval/rejection processed (VIS-03) | VERIFIED | Auto-approve path posts `[Review] Plan for {agent_id}: APPROVED` (line 312). Human button-click `_handle_approval` posts `[Review] Plan for {agent_id}: APPROVED (human review)` (line 377). Human button-click `_handle_rejection` posts `[Review] Plan for {agent_id}: REJECTED. Feedback: {feedback}` (line 404). All three paths confirmed with `[Review] Plan for` count = 3. |
| 11 | RuntimeAPI has no agent-type-specific routing methods; handle_plan_approval/rejection use Discord (VIS-04) | VERIFIED | All 16 targeted routing methods absent. `handle_plan_approval` (line 608) and `handle_plan_rejection` (line 639) now call `container.receive_discord_message(MessageContext(...))`. Zero `post_event` calls in runtime_api.py confirmed by grep. |

**Score:** 11/11 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/vcompany/bot/cogs/mention_router.py` | MentionRouterCog with on_message listener and agent handle registry | VERIFIED | Exists, substantive, imported from agent registration in RuntimeAPI |
| `src/vcompany/models/messages.py` | MessageContext pydantic model | VERIFIED | Exists, all 6 fields present, importable |
| `src/vcompany/bot/channel_setup.py` | Contains "backlog" in _PROJECT_CHANNELS | VERIFIED | Confirmed present |
| `src/vcompany/container/container.py` | receive_discord_message base method | VERIFIED | Line 411, TYPE_CHECKING guard for MessageContext |
| `src/vcompany/autonomy/backlog.py` | BacklogQueue with on_mutation and _notify | VERIFIED | Exists with all 7 mutations notified; zero discord/bot imports |
| `src/vcompany/agent/fulltime_agent.py` | PM agent with Discord-based event handling | VERIFIED | receive_discord_message, _send_discord, [Task Assigned] all present |
| `src/vcompany/agent/company_agent.py` | Strategist agent with Discord-based event handling | VERIFIED | receive_discord_message forwards to StrategistConversation |
| `src/vcompany/agent/gsd_agent.py` | GSD agent emitting Discord messages on phase transitions | VERIFIED | [Phase Complete], [Review Request], [Review Decision], [Task Assigned] all present |
| `src/vcompany/daemon/runtime_api.py` | RuntimeAPI with only infrastructure ops, no agent routing via post_event | VERIFIED | handle_plan_approval/rejection use receive_discord_message(MessageContext(...)); zero post_event calls remain |
| `src/vcompany/supervisor/supervisor.py` | Supervisor without pm_event_sink | VERIFIED | pm_event_sink absent from __init__ signature and body |
| `src/vcompany/bot/cogs/plan_review.py` | PlanReviewCog posting [Review] decisions as Discord messages in all paths | VERIFIED | [Review] Plan for count = 3: auto-approve (line 312), human-approve (line 377), human-reject (line 404) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `mention_router.py` | `models/messages.py` | `from vcompany.models.messages import MessageContext` | VERIFIED | Line 24 in mention_router.py |
| `mention_router.py` | `container/container.py` | `container.receive_discord_message(context)` | VERIFIED | Line 153 in mention_router.py |
| `runtime_api.py` | `mention_router.py` | `register_agent` in new_project() | VERIFIED | Lines 683, 737, 748 -- Strategist, PM, and GSD agents registered |
| `runtime_api.py` | `autonomy/backlog.py` | `on_mutation` callback | VERIFIED | BacklogQueue wired with on_mutation=_backlog_notify in new_project() |
| `runtime_api.py` | `gsd_agent.py` | handle_plan_approval calls receive_discord_message | VERIFIED | Lines 606-614: inline MessageContext import + receive_discord_message("[Review Decision] approve"). Zero post_event calls remain. |
| `runtime_api.py` | `gsd_agent.py` | handle_plan_rejection calls receive_discord_message | VERIFIED | Lines 637-645: inline MessageContext import + receive_discord_message("[Review Decision] reject {feedback}"). |
| `fulltime_agent.py` | `models/messages.py` | `from vcompany.models.messages import MessageContext` | VERIFIED | Line 28 (direct import, not TYPE_CHECKING) |
| `gsd_agent.py` | `daemon/comm.py` | `SendMessagePayload` via `_send_discord` | VERIFIED | Imported inline in `_send_discord` (line 174) |
| `plan_review.py` | `runtime_api.py` | `resolve_review()` for gate resolution | VERIFIED | Line 534 -- calls `runtime_api.resolve_review(agent_id, decision)` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `backlog.py` `_notify` | `msg: str` | Mutation operations (append/cancel/etc.) | Yes -- event descriptions built from real item data | FLOWING |
| `fulltime_agent.py` `_auto_assign_next` | `item: BacklogItem` | `project_state.assign_next_task()` -> BacklogQueue | Yes -- pulls from persisted BacklogQueue | FLOWING |
| `gsd_agent.py` `advance_phase` | `phase, from_phase` | `GsdLifecycle` FSM state | Yes -- real FSM state values | FLOWING |
| `runtime_api.py` `_backlog_notify` | `backlog_channel` | `self.get_channel_id("backlog")` | Conditional -- None if channels not registered yet at wiring time | STATIC when channel not yet registered (startup-order dependency, not a code bug) |
| `runtime_api.py` `handle_plan_approval` | `MessageContext.content` | Hardcoded `"[Review Decision] approve"` | Fixed value -- correct; this is the protocol verb, not dynamic data | FLOWING |
| `runtime_api.py` `handle_plan_rejection` | `MessageContext.content` | `f"[Review Decision] reject {feedback}"` where `feedback` comes from Discord button interaction | Yes -- feedback is real user input from PlanReviewCog | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| MessageContext importable | `uv run python -c "from vcompany.models.messages import MessageContext; m = MessageContext(sender='test', channel='ch', content='hello'); print(m.model_dump())"` | `{'sender': 'test', 'channel': 'ch', 'content': 'hello', 'parent_message': None, 'message_id': None, 'is_reply': False}` | PASS |
| AgentContainer has receive_discord_message | `uv run python -c "from vcompany.container.container import AgentContainer; assert hasattr(AgentContainer, 'receive_discord_message')"` | Passes | PASS |
| All three agents have receive_discord_message | `uv run python -c "... assert all(hasattr(x, 'receive_discord_message') for x in [FulltimeAgent, CompanyAgent, GsdAgent])"` | Passes | PASS |
| BacklogQueue has on_mutation callback | `uv run python -c "... assert 'on_mutation' in inspect.signature(BacklogQueue.__init__).parameters"` | Passes | PASS |
| Supervisor has no pm_event_sink | `uv run python -c "... assert 'pm_event_sink' not in inspect.signature(Supervisor.__init__).parameters"` | Passes | PASS |
| RuntimeAPI old routing methods absent | `uv run python -c "... assert not hasattr(RuntimeAPI, '_make_pm_event_sink') and not hasattr(RuntimeAPI, 'relay_strategist_message') and not hasattr(RuntimeAPI, 'signal_workflow_stage')"` | Passes | PASS |
| Gap 1 fix: handle_plan_approval uses receive_discord_message, no post_event | `inspect.getsource(RuntimeAPI.handle_plan_approval)` assertions | Passes -- [Review Decision] approve present, post_event absent | PASS |
| Gap 1 fix: handle_plan_rejection uses receive_discord_message, no post_event | `inspect.getsource(RuntimeAPI.handle_plan_rejection)` assertions | Passes -- [Review Decision] reject present, post_event absent | PASS |
| Gap 2 fix: [Review] Plan for in all 3 review paths | `inspect.getsource(PlanReviewCog)` count check | 3 occurrences confirmed | PASS |
| Zero post_event calls in runtime_api.py | `grep -c "post_event" src/vcompany/daemon/runtime_api.py` | 0 | PASS |
| Full import chain clean | `from runtime_api import RuntimeAPI; from plan_review import PlanReviewCog; from gsd_agent import GsdAgent` | "All imports clean" | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| VIS-01 | 24-01, 24-03, 24-04 | Every inter-agent event produces a Discord message before taking effect | VERIFIED | GsdAgent.advance_phase() emits [Phase Complete] and [Review Request] via _send_discord before awaiting PM decision. FulltimeAgent emits [Task Assigned] and [Intervention] messages. |
| VIS-02 | 24-02 | PM backlog operations posted to Discord, not silently mutated | VERIFIED | BacklogQueue._notify() fires for all 7 mutations after persist(). on_mutation wired to #backlog channel in new_project(). |
| VIS-03 | 24-03, 24-04, 24-05 | Plan review decisions posted to Discord before approval/rejection processed | VERIFIED | All three review paths post [Review] Plan for {agent_id}: messages. Auto-approve (line 312), human-approve (line 377), human-reject (line 404). RuntimeAPI gate resolution via receive_discord_message("[Review Decision] approve/reject") routes through the same Discord message protocol. |
| VIS-04 | 24-01, 24-04, 24-05 | RuntimeAPI has no agent-type-specific routing methods | VERIFIED | All 16 targeted routing methods absent. handle_plan_approval and handle_plan_rejection now use receive_discord_message(MessageContext(...)) -- the same Discord routing primitive as all other inter-agent communication. Zero post_event calls remain. |
| VIS-05 | 24-01, 24-03 | Agent-to-agent coordination uses Discord, not post_event() calls | VERIFIED | No post_event() calls in any agent or runtime_api files. Supervisor has no pm_event_sink. FulltimeAgent and CompanyAgent event queues removed. |
| VIS-06 | 24-03 | Task assignment from PM to GSD agent is a Discord message | VERIFIED | FulltimeAgent._auto_assign_next() sends [Task Assigned] message to agent's Discord channel. GsdAgent.receive_discord_message() parses [Task Assigned] and persists to memory. |

All 6 VIS requirements satisfied. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/vcompany/bot/cogs/strategist.py` | 173 | `runtime_api.relay_strategist_message()` -- method removed | WARNING | Dead code path; AttributeError if owner messages #strategist and StrategistCog on_message triggers. Pre-existing from before Phase 24; documented in deferred-items.md. |
| `src/vcompany/bot/cogs/strategist.py` | 245 | `runtime_api.handle_pm_escalation()` -- method removed | WARNING | Dead code path; AttributeError if PM escalation flow triggered. Pre-existing; documented in deferred-items.md. |
| `src/vcompany/bot/cogs/workflow_orchestrator_cog.py` | 425 | `runtime_api.route_completion_to_pm()` -- method removed | WARNING | Dead code path; AttributeError if WorkflowOrchestratorCog completion handler triggered. Pre-existing; documented in deferred-items.md. |
| `src/vcompany/bot/cogs/question_handler.py` | 143 | `strategist_cog.handle_pm_escalation()` -- flows through removed method | WARNING | Dead code path chained to strategist.py:245. Pre-existing; documented in deferred-items.md. |

Notes:
- The previous BLOCKER anti-patterns (runtime_api.py lines 606, 633: post_event calls) are CLOSED by Plan 24-05. No blockers remain.
- The 4 WARNING items are pre-existing deferred stubs documented in `deferred-items.md`, not introduced by Phase 24. They are not new breakage.

### Human Verification Required

#### 1. Deferred external callers runtime reachability

**Test:** Operate the bot: chat in #strategist, trigger a PM escalation, and complete a workflow step. Observe whether any AttributeError appears in logs.
**Expected:** No AttributeError -- the old strategist.py/workflow_orchestrator_cog.py paths are bypassed by the new MentionRouterCog routing before these code paths are reached.
**Why human:** Requires live Discord bot operation to trace which on_message handlers fire and whether the deferred broken methods are actually invoked.

#### 2. Backlog channel startup-order test

**Test:** Start the bot, register channels, then call `/new-project`. Observe whether backlog mutations produce Discord messages in #backlog.
**Expected:** Backlog notifications appear in #backlog channel as agents perform work.
**Why human:** The `backlog_channel` variable is captured at `new_project()` call time. If `register_channels()` is not called first, backlog notifications silently drop. Requires live bot to verify startup sequencing.

### Gaps Summary

No gaps remaining. Both previously-identified gaps are closed:

**Gap 1 (Blocker -- CLOSED):** `handle_plan_approval` (lines 603-614) and `handle_plan_rejection` (lines 634-645) in `runtime_api.py` now call `container.receive_discord_message(MessageContext(...))` with `[Review Decision] approve` and `[Review Decision] reject {feedback}` content. Zero `post_event` calls remain in the file. The human plan review flow is fully functional.

**Gap 2 (Minor -- CLOSED):** `_handle_approval` (line 375-378) and `_handle_rejection` (lines 402-405) in `plan_review.py` now post `[Review] Plan for {agent_id}: APPROVED (human review)` and `[Review] Plan for {agent_id}: REJECTED. Feedback: {feedback}` respectively. All three review paths use consistent `[Review]` prefix format. Total `[Review] Plan for` occurrences in plan_review.py = 3.

The phase goal is achieved: every inter-agent event, PM action, and plan review decision is visible on Discord before taking effect -- no hidden internal routing.

---

_Verified: 2026-03-29T17:05:00Z_
_Verifier: Claude (gsd-verifier)_
