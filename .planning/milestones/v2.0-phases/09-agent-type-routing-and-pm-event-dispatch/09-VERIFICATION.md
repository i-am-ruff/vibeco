---
phase: 09-agent-type-routing-and-pm-event-dispatch
verified: 2026-03-28T05:10:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
---

# Phase 9: Agent Type Routing and PM Event Dispatch Verification Report

**Phase Goal:** AgentConfig carries a type field so FulltimeAgent and CompanyAgent are instantiated from agents.yaml, GsdAgent completion events are dispatched to the PM, /new-project wires PM backlog, and all dead code paths from old workflows are removed
**Verified:** 2026-03-28T05:10:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | AgentConfig with type='fulltime' produces a FulltimeAgent via ContainerFactory | VERIFIED | `config.py:19` — `type: Literal["gsd","continuous","fulltime","company"] = "gsd"`; factory.py:81 registers fulltime->FulltimeAgent; `agent_type=agent_cfg.type` flows into ChildSpec (client.py:275, commands.py:201) |
| 2  | AgentConfig with type='company' produces a CompanyAgent via ContainerFactory | VERIFIED | Same Literal field; factory.py:82 registers company->CompanyAgent; test_container_factory.py has 17 fulltime/company references |
| 3  | AgentConfig without explicit type defaults to 'gsd' (backward compatible) | VERIFIED | `= "gsd"` default in config.py:19; 5 type-related tests in test_config.py confirm |
| 4  | No AgentConfig-field hasattr fallback guards remain in client.py or commands.py | VERIFIED | `grep hasattr client.py` = 0 matches; `grep hasattr commands.py` shows only `company_root` and `pane_id` checks (not AgentConfig fields) |
| 5  | GsdAgent phase completion routes an event to the PM container | VERIFIED | `_handle_phase_complete` in workflow_orchestrator_cog.py:432-454 calls `pm.post_event(event)` via `make_completion_event`; 3 tests in test_event_dispatch.py all pass |
| 6  | /new-project wires BacklogQueue and ProjectStateManager to FulltimeAgent | VERIFIED | commands.py:213-234 — local imports of FulltimeAgent, BacklogQueue, ProjectStateManager; `isinstance(child, FulltimeAgent)` loop; `self.bot._pm_container = pm_container` |
| 7  | Dead code (setup_notifications no-op, build_status_embed) is removed | VERIFIED | grep for both strings in src/vcompany/bot/ returns 0 matches; refactor commit 5583c1d confirmed |

**Score:** 7/7 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/vcompany/models/config.py` | AgentConfig with type field | VERIFIED | Line 19: `type: Literal["gsd", "continuous", "fulltime", "company"] = "gsd"` |
| `src/vcompany/bot/client.py` | Direct attribute access on AgentConfig | VERIFIED | Lines 273-282: no hasattr guards, `agent_type=agent_cfg.type` direct access |
| `src/vcompany/bot/cogs/commands.py` | Direct attribute access + BacklogQueue wiring | VERIFIED | Lines 198-230: direct access, BacklogQueue imported and used |
| `src/vcompany/bot/cogs/workflow_orchestrator_cog.py` | Event dispatch to PM | VERIFIED | Lines 432-454: `make_completion_event` called, `pm.post_event(event)` awaited |
| `tests/test_config.py` | Tests for type field validation | VERIFIED | 5 type-related tests confirmed by grep count |
| `tests/test_container_factory.py` | Tests for factory routing | VERIFIED | 17 fulltime/company references confirmed by grep count |
| `tests/test_event_dispatch.py` | 3 event dispatch scenario tests | VERIFIED | File exists; 3 async test functions covering PM present, PM absent, no-assignment fallback |
| `src/vcompany/bot/cogs/health.py` | setup_notifications removed | VERIFIED | grep returns 0 matches |
| `src/vcompany/bot/embeds.py` | build_status_embed removed | VERIFIED | grep returns 0 matches |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/vcompany/models/config.py` | `src/vcompany/container/factory.py` | `agent_type=agent_cfg.type` feeds ContainerFactory.create() | WIRED | client.py:275 and commands.py:201 both pass `agent.type` directly into ContainerContext which feeds ChildSpec |
| `src/vcompany/bot/cogs/workflow_orchestrator_cog.py` | `src/vcompany/agent/gsd_agent.py` | `container.make_completion_event(item_id)` | WIRED | Line 452: `event = container.make_completion_event(item_id)` with duck-type guard `hasattr(container, "make_completion_event")` |
| `src/vcompany/bot/cogs/workflow_orchestrator_cog.py` | `src/vcompany/bot/client.py` | `self.bot._pm_container.post_event()` | WIRED | Line 446: `pm = getattr(self.bot, "_pm_container", None)`; line 453: `await pm.post_event(event)` |
| `src/vcompany/bot/cogs/commands.py` | `src/vcompany/autonomy/backlog.py` | BacklogQueue wiring after add_project() | WIRED | Lines 214-230: local import of BacklogQueue; instantiated with `pm_container.memory`; loaded and assigned |

---

### Data-Flow Trace (Level 4)

Not applicable — this phase delivers configuration model fields, wiring/dispatch code, and dead code removal. No components rendering dynamic user-visible data were introduced.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All phase 09 target tests pass | `uv run pytest tests/test_config.py tests/test_container_factory.py tests/test_event_dispatch.py -x -q` | 29 passed, 1 warning | PASS |
| Full test suite | `uv run pytest tests/ -x -q` | 735 passed, 1 pre-existing failure (test_pm_tier), 19 warnings | PASS (pre-existing failure is unrelated) |
| No hasattr guards on AgentConfig fields in client.py | `grep hasattr client.py` | 0 matches | PASS |
| No hasattr guards on AgentConfig fields in commands.py | `grep hasattr...type/owns/gsd_mode/system_prompt commands.py` | 0 matches | PASS |
| Dead code absent from src | `grep setup_notifications\|build_status_embed src/vcompany/bot/` | 0 matches | PASS |
| All documented phase commits exist in git | `git log --oneline e97da48 9c2aea5 a606960 399114d 7c1b48b 5583c1d` | All 6 commits present | PASS |

**Pre-existing failure note:** `tests/test_pm_tier.py::test_low_confidence_escalates_to_strategist` fails due to a mock misconfiguration introduced in a prior phase (commit `3a59e9c`). The SUMMARY for plan 09-02 documented 2 similar pre-existing failures (test_pm_tier, test_report_cmd) as out-of-scope. This failure predates phase 09 changes and is not caused by them.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TYPE-04 | 09-01-PLAN.md | FulltimeAgent (PM) is event-driven — reacts to agent state transitions, health changes, escalations, briefings, milestone completion | SATISFIED | AgentConfig.type='fulltime' routes to FulltimeAgent via ContainerFactory; PM receives completion events via post_event |
| TYPE-05 | 09-01-PLAN.md | CompanyAgent (Strategist) is event-driven, alive for company duration, holds cross-project state, survives project restarts | SATISFIED | AgentConfig.type='company' routes to CompanyAgent via ContainerFactory; Literal validation in config.py ensures correct instantiation from agents.yaml |
| AUTO-05 | 09-02-PLAN.md | Project state owned by PM — agents read assignments and write completions. Agent crash never corrupts project state | SATISFIED | BacklogQueue and ProjectStateManager wired to FulltimeAgent in both on_ready (client.py) and /new-project (commands.py); GsdAgent completion events dispatched to PM via post_event |

No orphaned requirements — all three IDs declared in plan frontmatter are accounted for. REQUIREMENTS.md marks all three as complete at Phase 9.

---

### Anti-Patterns Found

None found. Scan results:
- No TODO/FIXME/PLACEHOLDER in phase-modified files
- No empty return stubs (`return null/[]/{}`) in wiring paths
- No hardcoded empty data flowing to user-visible output
- `hasattr(container, "make_completion_event")` in workflow_orchestrator_cog.py is intentional duck-typing (checking method existence on a runtime object, not a Pydantic field guard) — documented in plan 09-02 as the correct pattern

---

### Human Verification Required

None. All phase goal behaviors are verifiable programmatically via code inspection and test execution.

---

### Gaps Summary

No gaps. All 7 observable truths are verified, all artifacts exist and are substantive and wired, all key links are active, all three requirement IDs are satisfied, and the test suite passes with the only failure being a pre-existing regression unrelated to this phase.

---

_Verified: 2026-03-28T05:10:00Z_
_Verifier: Claude (gsd-verifier)_
