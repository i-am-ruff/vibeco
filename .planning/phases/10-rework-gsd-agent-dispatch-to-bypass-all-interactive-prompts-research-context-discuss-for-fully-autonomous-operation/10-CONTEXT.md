# Phase 10: Rework GSD Agent Dispatch for Fully Autonomous Operation - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a WorkflowOrchestrator that drives a deterministic per-agent state machine (`discuss → [DISCUSSION_GATE] → plan → [PM_PLAN_REVIEW_GATE] → execute+verify`), patch GSD workflow files to eliminate all non-AskUserQuestion interactive prompts, ensure discussion flows naturally through the Discord hook (not skipped), and add gate validation where PM reviews artifacts before advancing stages.

</domain>

<decisions>
## Implementation Decisions

### WorkflowOrchestrator (Deterministic State Machine)
- **D-01:** New `WorkflowOrchestrator` class — separate from MonitorLoop. Monitor handles liveness/alerts, orchestrator handles the state machine and gate transitions. Clean separation of concerns.
- **D-02:** Per-agent state machine. Each agent has its own independent loop: `discuss → [DISCUSSION_GATE] → research+plan → [PM_PLAN_REVIEW_GATE] → execute+verify`. Agents can be at different phases and different stages.
- **D-03:** Each agent has its own clone with its own `.planning/` directory, `ROADMAP.md`, and `STATE.md`. Orchestrator reads each agent's GSD state independently to determine position.
- **D-04:** Orchestrator sends standard GSD commands without `--auto`: `/gsd:discuss-phase N`, `/gsd:plan-phase N`, `/gsd:execute-phase N`. Each command runs its stage fully and stops. Orchestrator sends the next command after the gate passes.
- **D-05:** `auto_advance: false` in GSD config. This is inter-stage only — prevents GSD from auto-chaining discuss→plan→execute. Orchestrator owns all transitions.

### Gate Detection & Validation
- **D-06:** Stage completion detected via `vco report` signals. Agent sends `vco report "discuss-phase complete"` (or similar) when a stage finishes. Orchestrator listens for these signals.
- **D-07:** PM reviews artifacts at each gate — not just "does it exist" but "is it good enough":
  - **DISCUSSION_GATE:** PM reviews CONTEXT.md for quality, completeness, and alignment with project goals.
  - **PM_PLAN_REVIEW_GATE:** PM reviews PLAN.md files for scope alignment, dependency readiness, and quality (existing Phase 6 PM plan review).
  - After verify stage: PM reviews VERIFICATION.md status.
- **D-08:** Recovery after crash uses GSD's STATE.md position in the agent's clone. Orchestrator reads STATE.md to determine which stage to resume from.

### Discussion Flow (NOT Skipped)
- **D-09:** `skip_discuss: false` in GSD config. Discussion phase runs naturally. AskUserQuestion calls go through the Discord hook (ask_discord.py), PM/Strategist answers each question via Discord replies.
- **D-10:** Multi-step discussion flow works through the existing PM escalation chain (Phase 6 D-05):
  - Topic selection (multiSelect) → PM picks relevant topics using full project context + decision log memory
  - Per-topic option questions → PM selects options, medium/low confidence escalates to Strategist
  - Continue/next prompts → PM decides based on coverage
  - Finish prompt → PM wraps up discussion
- **D-11:** PM uses full project context (PROJECT.md, REQUIREMENTS.md, prior CONTEXT.md files, ROADMAP.md) + its own decision log memory for discussion answers. Medium or lower confidence → escalates to Strategist per Phase 6 D-05.

### GSD Source Patches
- **D-12:** Patch GSD workflow source files directly in `~/.claude/get-shit-done/`. Global patches on host machine — all agents inherit. Use `/gsd:reapply-patches` after GSD updates.
- **D-13:** Full audit of all GSD workflow files to identify every interactive prompt (AskUserQuestion or other). Create a coverage matrix. Patch ALL non-AskUserQuestion prompts to auto-select without user interaction.
- **D-14:** GSD config forces autonomous behavior — no `--auto` flag needed. Config settings (`skip_discuss: false`, `auto_advance: false`, `research: true`, `plan_check: true`) define the behavior. Agents are autonomous by config, not by flag.

### Fallback Behavior
- **D-15:** Unknown/unexpected prompts that slip through (not AskUserQuestion) → block the agent and alert Discord. Agent does NOT auto-select. PM/Owner must intervene.
- **D-16:** If agent blocks for 10 minutes on an unknown prompt with no intervention, orchestrator classifies as stuck and escalates. PM/Owner decides: restart, manually answer, or skip.

### Blocker Reporting
- **D-17:** Major blockers and issues go through `vco report` mentioning either PM or Strategist based on severity/relation. Not through AskUserQuestion — these are system-level alerts, not workflow questions.

### GSD Config Template Updates
- **D-18:** Updated gsd_config.json.j2 settings:
  - `skip_discuss: false` (was `true` — discussion now flows through Discord)
  - `auto_advance: false` (unchanged — orchestrator owns transitions)
  - `discuss_mode: "discuss"` (was `"assumptions"` — real discussion through Discord, not assumptions)
  - `research: true` (unchanged)
  - `plan_check: true` (unchanged)

### Claude's Discretion
- WorkflowOrchestrator internal state persistence format (file-based, in-memory, or database)
- Exact `vco report` signal format/protocol for stage completion detection
- How WorkflowOrchestrator integrates with existing bot startup (new Cog, background task, or standalone)
- Which specific GSD prompts need patching (determined during audit)
- Whether WorkflowOrchestrator runs as an asyncio task alongside MonitorLoop or as a separate process

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### GSD Workflow Files (to audit and patch)
- `~/.claude/get-shit-done/workflows/discuss-phase.md` — Discussion workflow with AskUserQuestion prompts
- `~/.claude/get-shit-done/workflows/plan-phase.md` — Planning workflow with research gate, context gate, UI gate, checker loop
- `~/.claude/get-shit-done/workflows/execute-phase.md` — Execution workflow with checkpoint handling, verification
- `~/.claude/get-shit-done/workflows/execute-plan.md` — Per-plan execution (spawned by execute-phase)

### Existing Orchestration Code
- `src/vcompany/orchestrator/agent_manager.py` — Agent dispatch, send_work_command, readiness detection
- `src/vcompany/monitor/loop.py` — MonitorLoop (liveness checks, callbacks, 60s cycle)
- `src/vcompany/monitor/checks.py` — check_liveness, check_stuck, check_plan_gate
- `src/vcompany/bot/cogs/plan_review.py` — PlanReviewCog (plan gate, PM review, execute dispatch)

### PM / Strategist (gate reviewers)
- `src/vcompany/strategist/pm.py` — PM tier with confidence scoring and plan review
- `src/vcompany/bot/cogs/strategist.py` — StrategistCog (persistent conversation, escalation)
- `src/vcompany/bot/cogs/question_handler.py` — QuestionHandlerCog (Discord Q&A flow from Phase 9)

### Templates (to update)
- `src/vcompany/templates/gsd_config.json.j2` — GSD config deployed to agent clones
- `src/vcompany/templates/settings.json.j2` — Claude Code hooks config

### Prior Phase Context
- `.planning/phases/09-askuser-hook-sends-questions-to-agent-discord-channel-mentioning-pm-for-autonomous-q-a-forwarding/09-CONTEXT.md` — Discord-only IPC, routing framework, PM auto-answer
- `.planning/phases/05-hooks-and-plan-gate/05-CONTEXT.md` — Hook design, plan gate mechanics
- `.planning/phases/06-pm-strategist-and-milestones/06-CONTEXT.md` — PM/Strategist escalation chain (D-05), confidence scoring

### Reporting
- `src/vcompany/cli/report_cmd.py` — vco report command (direct Discord posting)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **MonitorLoop** (`src/vcompany/monitor/loop.py`): Per-agent checks every 60s. WorkflowOrchestrator runs alongside but doesn't replace it.
- **AgentManager** (`src/vcompany/orchestrator/agent_manager.py`): `send_work_command()` for sending GSD commands to agent panes.
- **PlanReviewCog** (`src/vcompany/bot/cogs/plan_review.py`): PM plan review already implemented — reuse for PM_PLAN_REVIEW_GATE.
- **PMTier** (`src/vcompany/strategist/pm.py`): Confidence scoring and plan review — reuse for DISCUSSION_GATE artifact review.
- **report_cmd** (`src/vcompany/cli/report_cmd.py`): `vco report` posts to Discord — already used by GSD workflows for stage signals.
- **check_plan_gate** (`src/vcompany/monitor/checks.py`): Mtime-based plan detection — pattern for artifact detection.
- **AgentMonitorState** (`src/vcompany/monitor/monitor_state.py`): Per-agent state tracking — extend or compose for workflow state.

### Established Patterns
- **Callback injection**: Bot injects callbacks into MonitorLoop at startup — same pattern for WorkflowOrchestrator.
- **asyncio.to_thread()**: All blocking operations wrapped for async safety.
- **vco report**: Direct Discord posting for status signals — already in GSD workflow templates.
- **Per-agent state files**: AgentMonitorState tracks per-agent liveness — extend for workflow stage tracking.

### Integration Points
- **WorkflowOrchestrator ↔ AgentManager**: Orchestrator calls `send_work_command()` to dispatch GSD commands.
- **WorkflowOrchestrator ↔ PMTier**: Orchestrator invokes PM review at each gate.
- **WorkflowOrchestrator ↔ vco report listener**: Orchestrator listens for Discord messages matching stage completion patterns.
- **WorkflowOrchestrator ↔ MonitorLoop**: Parallel but independent — monitor checks liveness, orchestrator drives workflow.
- **GSD config template ↔ clone deployment**: Updated gsd_config.json.j2 deployed during `vco clone`.

</code_context>

<specifics>
## Specific Ideas

- The workflow is a deterministic state machine per agent — not ad-hoc command dispatch. This enables verification of what has been done and what should be done next.
- Discussion is NOT skipped — it flows through Discord naturally via the Phase 9 AskUserQuestion hook. PM answers discussion questions using project context + decision memory, escalating to Strategist when uncertain.
- The orchestrator reads each agent's own STATE.md (in its clone) for crash recovery — GSD's own tracking is the source of truth for position.
- GSD patches are global on host (`~/.claude/get-shit-done/`), not per-clone. `/gsd:reapply-patches` handles GSD updates.
- Unknown prompts BLOCK (not auto-select) — safety over speed. 10-minute escalation window.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-rework-gsd-agent-dispatch-to-bypass-all-interactive-prompts-research-context-discuss-for-fully-autonomous-operation*
*Context gathered: 2026-03-27*
