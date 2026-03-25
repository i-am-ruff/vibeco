# Phase 5: Hooks and Plan Gate - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the AskUserQuestion hook (`ask_discord.py`) that routes agent questions through Discord for answers, expand PlanReviewCog with the full plan gate workflow (detect, post, review, approve/reject), add per-agent plan gate state tracking, enforce interaction safety tables in plans (SAFE-01/SAFE-02), and add explicit auto-advance disable to the GSD config template.

</domain>

<decisions>
## Implementation Decisions

### Hook Answer Routing
- **D-01:** `ask_discord.py` posts questions to #strategist via Discord webhook (using `DISCORD_AGENT_WEBHOOK_URL` env var from Phase 2 D-04). Uses urllib from stdlib — no external dependencies.
- **D-02:** Answer delivery uses file-based polling. Bot writes answer to a known file path (e.g., `/tmp/vco-answers/{request-id}.json`). Hook polls the file every 5s with a 10-minute timeout. Clean IPC boundary — no shared runtime state.
- **D-03:** Hook is self-contained (HOOK-06) — no imports from main vcompany codebase. Only uses Python stdlib (urllib, json, os, time, uuid).
- **D-04:** Phase 5 routes all questions to humans in #strategist. Phase 6's Strategist will add AI auto-answering as an intercept layer — no integration points needed in Phase 5.

### Timeout Policy
- **D-05:** Timeout behavior is configurable per project with two modes:
  - **Block mode:** On timeout, hook returns a "block" response that pauses the agent until a human answers. Agent does not proceed with assumptions.
  - **Continue mode:** On timeout, hook falls back to recommended/first option, notes the assumption in the answer, and alerts #alerts. Agent keeps working.
- **D-06:** Timeout mode configured in project-level config (agents.yaml or a vco config file). Default is "continue" mode to match HOOK-04 spec.

### Plan Review UX
- **D-07:** Plans posted to #plan-review as a rich embed summary (agent ID, phase, plan number, task count, goal) with the full PLAN.md content attached as a file or posted in a thread.
- **D-08:** Approve/reject via Discord button components (Approve and Reject). On reject, bot prompts for feedback text in a modal. Matches Phase 4 D-03 confirmation pattern.
- **D-09:** Rejection feedback sent as a new prompt to the agent's tmux pane via TmuxManager.send_command() (per Phase 3 D-08).

### Agent Pause Mechanism
- **D-10:** Agents are monitor-commanded, not auto-advancing. GSD config template gets explicit `"auto_advance": false` in the workflow section to lock this off regardless of GSD default changes.
- **D-11:** After planning completes, agent naturally returns to prompt and sits idle. Monitor is the gate controller — it sends `/gsd:execute-phase {N}` only after all plans for the phase are approved.
- **D-12:** Per-phase execution trigger: monitor sends one `/gsd:execute-phase {N}` when ALL plans for a phase are approved, not per-plan. GSD handles executing plans in order.

### Plan Gate State Tracking
- **D-13:** Per-agent plan gate state tracked in state file with field `plan_gate_status`. Values: `idle`, `awaiting_review`, `approved`, `rejected`.
- **D-14:** Monitor uses this state to prevent double-sending execute commands and to report status in `!status` output.

### Interaction Safety Tables (SAFE-01/SAFE-02)
- **D-15:** Every PLAN.md must include an `## Interaction Safety` section with a markdown table using the 6 columns: Agent/Component, Circumstance, Action, Concurrent With, Safe?, Mitigation.
- **D-16:** Validation runs as part of plan gate review. When monitor detects a plan, it checks for the safety table before posting to #plan-review.
- **D-17:** Strictness is configurable per project:
  - **Warn mode:** Missing safety table adds a warning to the review embed. Reviewer can still approve.
  - **Block mode:** Plans without a safety table cannot be approved. Only reject is available, with message to re-plan with safety analysis.
- **D-18:** Default strictness is "warn" for v1.

### Claude's Discretion
- Request ID generation strategy (UUID vs sequential)
- Answer file cleanup policy (TTL, on-read deletion, periodic sweep)
- Exact embed formatting and color coding for plan review
- Plan gate state persistence format (extend existing agents.json or separate file)
- Safety table validation heuristics (regex for heading + table structure)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `.planning/research/ARCHITECTURE.md` — VCO-ARCHITECTURE.md authoritative design reference, hook and plan gate flow design

### Requirements
- `.planning/REQUIREMENTS.md` §Hooks and Plan Gate — HOOK-01 through HOOK-07, GATE-01 through GATE-04
- `.planning/REQUIREMENTS.md` §Interaction Safety — SAFE-01, SAFE-02

### Prior Phase Context
- `.planning/phases/03-monitor-loop-and-coordination/03-CONTEXT.md` — Plan gate detection mechanism (D-05 through D-09), monitor architecture
- `.planning/phases/04-discord-bot-core/04-CONTEXT.md` — PlanReviewCog placeholder (D-12), AlertsCog callback wiring (D-13), bot architecture

### Existing Code
- `src/vcompany/bot/cogs/plan_review.py` — Empty PlanReviewCog placeholder to be expanded
- `src/vcompany/bot/cogs/alerts.py` — AlertsCog with on_plan_detected callback (current plan alert implementation)
- `src/vcompany/monitor/checks.py` — check_plan_gate function (mtime-based plan detection)
- `src/vcompany/monitor/loop.py` — MonitorLoop with on_plan_detected callback wiring
- `src/vcompany/templates/settings.json.j2` — AskUserQuestion hook config (points to ask_discord.py)
- `src/vcompany/templates/gsd_config.json.j2` — GSD config template (needs auto_advance: false)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **PlanReviewCog** (`src/vcompany/bot/cogs/plan_review.py`): Empty Cog with bot reference, ready to be expanded with plan gate logic
- **AlertsCog** (`src/vcompany/bot/cogs/alerts.py`): Has `on_plan_detected` callback and alert buffering — plan detection alerts already work
- **check_plan_gate** (`src/vcompany/monitor/checks.py`): Mtime-based plan file detection, returns CheckResult with new_plans list
- **MonitorLoop** (`src/vcompany/monitor/loop.py`): Calls check_plan_gate per agent, invokes on_plan_detected callback for each new plan
- **views module** (`src/vcompany/bot/views/`): Discord button/view patterns from Phase 4 confirmation flows
- **embeds module** (`src/vcompany/bot/embeds.py`): Embed builder patterns from Phase 4
- **TmuxManager** (`src/vcompany/tmux/session.py`): send_command() for sending prompts to agent panes
- **write_atomic** (`src/vcompany/shared/atomic.py`): Atomic file write for answer files

### Established Patterns
- **Callback injection**: Bot injects callbacks into MonitorLoop at startup (Phase 4 D-13)
- **asyncio.to_thread()**: All blocking operations wrapped for async safety (Phase 4 D-14)
- **TYPE_CHECKING imports**: Cogs use TYPE_CHECKING for VcoBot to avoid circular imports
- **CheckResult dataclass**: Monitor checks return CheckResult with status, message, and metadata

### Integration Points
- **MonitorLoop.on_plan_detected callback** → needs to route to PlanReviewCog instead of (or in addition to) AlertsCog
- **PlanReviewCog** → needs access to TmuxManager for sending execute/reject commands to agent panes
- **GSD config template** → needs auto_advance: false added
- **settings.json.j2** → already configured, ask_discord.py needs to be created at the path it references

</code_context>

<specifics>
## Specific Ideas

- Timeout policy (block vs continue) mirrors a broader pattern — project-level config surface for orchestration behavior. Keep it simple for v1 (single config key per behavior).
- Safety table strictness follows same pattern — configurable per project.
- The hook → webhook → bot → file → hook flow is asymmetric by design: outbound is instant (webhook POST), inbound is polled (file). This is correct — don't try to make it symmetric.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-hooks-and-plan-gate*
*Context gathered: 2026-03-25*
