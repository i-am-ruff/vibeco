# Phase 10: Rework GSD Agent Dispatch for Fully Autonomous Operation - Research

**Researched:** 2026-03-27
**Domain:** GSD workflow patching, async state machines, Discord-based orchestration
**Confidence:** HIGH

## Summary

This phase builds a WorkflowOrchestrator that drives a per-agent state machine through the GSD pipeline (discuss, plan, execute+verify), with PM artifact review at each gate. The key technical challenges are: (1) auditing and patching GSD workflow files to eliminate non-AskUserQuestion interactive prompts, (2) detecting stage completion via `vco report` signals in Discord, (3) integrating the orchestrator alongside the existing MonitorLoop, and (4) updating the GSD config template to switch from assumptions-mode to full discussion with `skip_discuss: false`.

The codebase is well-structured for this. AgentManager already has `send_work_command()` for dispatching GSD commands to agent tmux panes. PlanReviewCog already handles PM plan review with confidence-based auto-approval. QuestionHandlerCog already routes AskUserQuestion calls through PM. The main new work is the WorkflowOrchestrator itself, the GSD patches, and wiring completion detection through Discord message monitoring.

**Primary recommendation:** Build WorkflowOrchestrator as a new Cog (or Cog-adjacent background task) that listens for `vco report` messages in agent channels and advances each agent through the state machine. Patch GSD workflows globally at `~/.claude/get-shit-done/workflows/` to add missing `vco report` calls and eliminate non-AskUserQuestion prompts. Keep MonitorLoop unchanged -- it handles liveness/stuck/plan detection, WorkflowOrchestrator handles stage transitions.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** New WorkflowOrchestrator class -- separate from MonitorLoop. Monitor handles liveness/alerts, orchestrator handles the state machine and gate transitions.
- **D-02:** Per-agent state machine. Each agent has its own independent loop: discuss -> [DISCUSSION_GATE] -> research+plan -> [PM_PLAN_REVIEW_GATE] -> execute+verify. Agents can be at different phases and different stages.
- **D-03:** Each agent has its own clone with its own .planning/ directory, ROADMAP.md, and STATE.md. Orchestrator reads each agent's GSD state independently.
- **D-04:** Orchestrator sends standard GSD commands without --auto: /gsd:discuss-phase N, /gsd:plan-phase N, /gsd:execute-phase N. Each command runs its stage fully and stops. Orchestrator sends the next command after the gate passes.
- **D-05:** auto_advance: false in GSD config. Prevents GSD from auto-chaining discuss->plan->execute. Orchestrator owns all transitions.
- **D-06:** Stage completion detected via vco report signals. Agent sends vco report "discuss-phase complete" (or similar). Orchestrator listens for these signals.
- **D-07:** PM reviews artifacts at each gate -- DISCUSSION_GATE reviews CONTEXT.md, PM_PLAN_REVIEW_GATE reviews PLAN.md, post-verify reviews VERIFICATION.md.
- **D-08:** Recovery after crash uses GSD's STATE.md position in the agent's clone.
- **D-09:** skip_discuss: false in GSD config. Discussion flows through Discord via Phase 9 AskUserQuestion hook.
- **D-10:** Multi-step discussion flow works through existing PM escalation chain (Phase 6 D-05).
- **D-11:** PM uses full project context + decision log memory for discussion answers.
- **D-12:** Patch GSD workflow source files directly in ~/.claude/get-shit-done/. Global patches on host machine.
- **D-13:** Full audit of all GSD workflow files to identify every interactive prompt. Create a coverage matrix. Patch ALL non-AskUserQuestion prompts.
- **D-14:** GSD config forces autonomous behavior -- no --auto flag needed. Config settings define behavior.
- **D-15:** Unknown/unexpected prompts block the agent and alert Discord.
- **D-16:** 10-minute escalation timeout for blocked agents.
- **D-17:** Major blockers via vco report mentioning PM or Strategist.
- **D-18:** Updated gsd_config.json.j2: skip_discuss: false, auto_advance: false, discuss_mode: "discuss", research: true, plan_check: true.

### Claude's Discretion
- WorkflowOrchestrator internal state persistence format (file-based, in-memory, or database)
- Exact vco report signal format/protocol for stage completion detection
- How WorkflowOrchestrator integrates with existing bot startup (new Cog, background task, or standalone)
- Which specific GSD prompts need patching (determined during audit)
- Whether WorkflowOrchestrator runs as an asyncio task alongside MonitorLoop or as a separate process

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

## Standard Stack

No new dependencies required. This phase uses the existing stack entirely:

| Library | Version | Purpose | Already Installed |
|---------|---------|---------|-------------------|
| discord.py | 2.7.x | Discord message listening for vco report signals | Yes |
| asyncio (stdlib) | N/A | State machine async loop, background tasks | Yes |
| pathlib (stdlib) | N/A | Reading agent clone STATE.md, CONTEXT.md, PLAN.md | Yes |
| dataclasses (stdlib) | N/A | WorkflowOrchestrator internal state (per D-01 pattern) | Yes |
| pydantic | 2.11.x | Extending AgentMonitorState or new model for workflow state | Yes |
| Jinja2 | N/A | gsd_config.json.j2 template update | Yes (already used) |

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
  orchestrator/
    agent_manager.py          # Existing -- send_work_command()
    workflow_orchestrator.py   # NEW -- state machine, gate logic
    crash_tracker.py           # Existing
  monitor/
    loop.py                    # Existing -- unchanged
    checks.py                  # Existing -- unchanged
  bot/
    cogs/
      plan_review.py           # Existing -- reused at PM_PLAN_REVIEW_GATE
      question_handler.py      # Existing -- handles discuss Q&A
      workflow_orchestrator_cog.py  # NEW -- Discord listener + Cog wrapper
    client.py                  # Modified -- wire WorkflowOrchestratorCog
  templates/
    gsd_config.json.j2         # Modified -- new config values
tools/
  patch_gsd_workflows.py       # NEW -- applies patches to GSD source files
```

### Pattern 1: WorkflowOrchestrator as Cog + Background Task
**What:** A discord.py Cog that listens for `vco report` messages in agent channels and runs a background asyncio task for the state machine loop. This follows the MonitorLoop pattern (bot creates background task in on_ready).
**When to use:** When the orchestrator needs both Discord event access (message listening) and periodic background processing.

**State Machine Per Agent:**
```
IDLE -> DISCUSS -> DISCUSSION_GATE -> PLAN -> PM_PLAN_REVIEW_GATE -> EXECUTE -> VERIFY -> PHASE_COMPLETE
                                                                                            |
                                                                                            v
                                                                                     (next phase or IDLE)
```

### Pattern 2: vco report Signal Detection via on_message Listener
**What:** Cog's on_message listener watches #agent-{id} channels for messages matching stage completion patterns. This is the same pattern QuestionHandlerCog uses for detecting question embeds.
**When to use:** Detection of stage transitions.

### Pattern 3: Callback Injection for AgentManager Access
**What:** WorkflowOrchestrator receives AgentManager reference via injection in bot's on_ready, same as MonitorLoop gets callbacks. This avoids import cycles and enables testing.
**When to use:** Cross-component wiring.

### Anti-Patterns to Avoid
- **Do NOT poll files for stage completion** -- use Discord message detection via `vco report`. File polling adds latency and complexity.
- **Do NOT modify MonitorLoop** -- it handles liveness/stuck/plan detection. WorkflowOrchestrator is separate (D-01).
- **Do NOT use --auto flag** -- orchestrator sends bare GSD commands; autonomous behavior comes from config (D-04, D-14).
- **Do NOT auto-select on unknown prompts** -- block and alert (D-15).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Plan review at gates | Custom PM review logic | Existing PlanReviewCog + PMTier | Already implements confidence-based auto-approval (Phase 6) |
| Discussion Q&A routing | Custom question detection | Existing QuestionHandlerCog + ask_discord.py hook | Phase 9 already routes AskUserQuestion through Discord |
| Sending GSD commands | Custom tmux interaction | AgentManager.send_work_command() | Already handles pane resolution, ready detection, command verification |
| Decision logging | Custom logger | Existing DecisionLogger via StrategistCog | Already logs to decisions.jsonl |
| Crash recovery state | Custom state tracking | GSD's STATE.md in agent clone | Orchestrator reads STATE.md to determine resume position (D-08) |

## GSD Workflow Audit Results

### Critical Finding: discuss-phase Has NO vco report Call

The discuss-phase.md and discuss-phase-assumptions.md workflows do NOT emit `vco report` signals on completion. Only plan-phase.md and execute-phase.md do:

| Workflow | vco report at start | vco report at end | Pattern |
|----------|--------------------|--------------------|---------|
| research-phase.md | `vco report "starting research-phase $PHASE"` | `vco report "research-phase complete"` | Both present |
| plan-phase.md | `vco report "starting plan-phase $PHASE"` | `vco report "@PM plan-phase complete - ready for review"` | Both present |
| execute-phase.md | `vco report "starting execute-phase $PHASE_ARG"` | `vco report "@PM execute-phase complete - verify"` | Both present |
| discuss-phase.md | **NONE** | **NONE** | **MISSING -- must patch** |
| discuss-phase-assumptions.md | **NONE** | **NONE** | **MISSING -- must patch** |

**Action required:** Patch discuss-phase.md and discuss-phase-assumptions.md to add `vco report` calls at start and end.

### Interactive Prompt Audit (Agent-Facing Workflows Only)

Agents run these GSD commands: discuss-phase, plan-phase, execute-phase, execute-plan. Other workflows (new-project, settings, etc.) are user-only and don't need patching.

**Confidence: HIGH** -- verified by grep of actual GSD workflow source files.

#### discuss-phase.md (20 AskUserQuestion occurrences)
| Location | Prompt | Type | Patch Strategy |
|----------|--------|------|----------------|
| check_existing (context exists) | "Update it" / "Start fresh" / "Skip" | AskUserQuestion | Route through Discord hook -- PM decides |
| check_existing (plans exist) | "Continue and replan" / "Skip" | AskUserQuestion | Route through Discord hook -- PM decides |
| todo folding | "Which todos to fold in?" | AskUserQuestion multiSelect | Route through Discord hook -- PM decides |
| present_gray_areas | "Which areas to discuss?" | AskUserQuestion multiSelect | Route through Discord hook -- PM picks topics |
| discuss_areas (per area) | "Which approach?" | AskUserQuestion | Route through Discord hook -- PM selects |
| discuss_areas (follow-ups) | Targeted follow-up questions | AskUserQuestion | Route through Discord hook -- PM answers |
| finish ("Done" prompt) | "Explore more" / "I'm ready" | AskUserQuestion | Route through Discord hook -- PM decides |

**All discuss-phase AskUserQuestion prompts are legitimate** -- they represent actual design decisions that should flow through the Discord PM chain. NO patching needed for these; the existing Phase 9 hook handles them.

#### plan-phase.md (7 AskUserQuestion occurrences)
| Location | Prompt | Type | Patch Strategy |
|----------|--------|------|----------------|
| context_gate (no CONTEXT.md) | "Continue without" / "Run discuss first" | AskUserQuestion | **Patch: auto-select "Continue without context"** -- orchestrator already ran discuss |
| research_gate (no RESEARCH.md) | "Research first" / "Skip research" | AskUserQuestion | **Not triggered** -- config has `research: true`, research runs as subagent automatically |
| ui_gate (no UI-SPEC.md) | "Generate UI spec" / "Skip" | AskUserQuestion | **Patch: auto-select "Skip"** -- UI spec not in agent's scope |
| checker_loop | Handled by plan_check subagent | N/A | No patch needed |

#### execute-phase.md (7 AskUserQuestion occurrences)
| Location | Prompt | Type | Patch Strategy |
|----------|--------|------|----------------|
| cross_phase_regression | "Fix regressions" / "Continue" / "Abort" | AskUserQuestion | **Patch: auto-select "Fix regressions"** -- conservative default |
| (implicit in subagent control) | Various checkpoint prompts | checkpoint:* | **These are handled by execute-plan** |

#### execute-plan.md (2 AskUserQuestion occurrences)
| Location | Prompt | Type | Patch Strategy |
|----------|--------|------|----------------|
| previous_phase_check | "Proceed anyway" / "Address first" / "Review previous" | AskUserQuestion | **Patch: auto-select "Proceed anyway"** -- orchestrator already validated at gate |

### Auto-Advance Mechanism (Critical to Disable)

GSD has a `_auto_chain_active` ephemeral flag and `auto_advance` persistent config. When either is true, GSD auto-chains discuss->plan->execute. Per D-05, we MUST ensure:
- `auto_advance: false` in gsd_config.json.j2
- `_auto_chain_active: false` (or not set)
- Orchestrator sends commands WITHOUT `--auto` flag

This prevents GSD from self-advancing between stages. The orchestrator owns all transitions.

### GSD Config Template Changes

Current template (`src/vcompany/templates/gsd_config.json.j2`):
```json
{
  "mode": "yolo",
  "granularity": "standard",
  "model_profile": "balanced",
  "workflow": {
    "research": true,
    "plan_check": true,
    "verifier": false,
    "nyquist_validation": false,
    "discuss_mode": "assumptions",
    "skip_discuss": true,
    "auto_advance": false
  },
  "git": {
    "branching_strategy": "milestone",
    "milestone_branch_template": "gsd/{milestone}-{slug}"
  }
}
```

Required changes (per D-18):
```json
{
  "workflow": {
    "discuss_mode": "discuss",    // was "assumptions"
    "skip_discuss": false,        // was true
    "_auto_chain_active": false   // explicitly prevent auto-chaining
  }
}
```

## Common Pitfalls

### Pitfall 1: Discuss-Phase Has No Completion Signal
**What goes wrong:** Orchestrator cannot detect when discuss-phase finishes because there is no `vco report` call in discuss-phase.md.
**Why it happens:** GSD's discuss-phase was designed for interactive use; completion signals were only added to plan-phase and execute-phase.
**How to avoid:** Patch discuss-phase.md to add `vco report "discuss-phase complete"` at the end (before auto_advance step). Also add `vco report "starting discuss-phase $PHASE"` at the beginning.
**Warning signs:** Agent sits idle after discuss completes but orchestrator never advances.

### Pitfall 2: Auto-Advance Conflict
**What goes wrong:** If `_auto_chain_active` is true in the agent's GSD config, GSD will auto-chain from discuss to plan, bypassing the orchestrator's gate.
**Why it happens:** The `_auto_chain_active` flag persists in the config file and can be set by previous runs.
**How to avoid:** Template deploys with `_auto_chain_active: false`. Orchestrator never sends `--auto` flag. Patches ensure the auto_advance step respects the false config.
**Warning signs:** Agent starts plan-phase before orchestrator sends the command.

### Pitfall 3: Race Between MonitorLoop Plan Detection and WorkflowOrchestrator
**What goes wrong:** MonitorLoop detects new PLAN.md via mtime check and triggers PlanReviewCog, but WorkflowOrchestrator also needs to know about plan completion.
**Why it happens:** Two systems watching the same events.
**How to avoid:** WorkflowOrchestrator uses `vco report` signals for stage detection (Discord messages), NOT file watching. PlanReviewCog continues to handle plan review via MonitorLoop's file detection. The orchestrator listens for the PM's approval/rejection decision, not the plan file creation.
**Warning signs:** Double-posting of plan review, or orchestrator advancing before PM review completes.

### Pitfall 4: Context Gate Prompt in Plan-Phase
**What goes wrong:** When orchestrator sends `/gsd:plan-phase N`, GSD detects that CONTEXT.md exists (because discuss just created it) but still shows the "context exists, update/skip?" prompt.
**Why it happens:** The context_gate check in plan-phase.md triggers whenever CONTEXT.md exists.
**How to avoid:** Patch plan-phase.md context_gate to auto-select "Continue" when running without --auto. Or better: since config has `skip_discuss: false` and discuss already ran, the context exists legitimately. Patch to skip the prompt entirely when context exists.
**Warning signs:** Agent blocks waiting for AskUserQuestion response to a context existence check.

### Pitfall 5: Discussion Question Volume
**What goes wrong:** discuss-phase generates 15-25 AskUserQuestion calls per phase (topic selection, per-topic options, follow-ups, finish prompt). Each one goes through ask_discord.py -> Discord -> PM -> reply, with 5s polling intervals.
**Why it happens:** Discussion is designed for interactive user, not async PM responses.
**How to avoid:** Accept this latency. PM auto-answers at HIGH confidence (< 2s each including Claude CLI call), so typical 20 questions = ~40s + polling overhead = ~3-5 minutes per discussion. This is acceptable.
**Warning signs:** Discussion taking 10+ minutes per phase (indicates PM latency issues).

### Pitfall 6: GSD Patches Lost on GSD Update
**What goes wrong:** When GSD auto-updates (or user runs `gsd:update`), patches to `~/.claude/get-shit-done/workflows/` are overwritten.
**Why it happens:** GSD updates replace workflow files.
**How to avoid:** Create a `patch_gsd_workflows.py` tool that can be re-run after updates. Document in project. Could also add a pre-dispatch check that verifies patches are applied.
**Warning signs:** Agents start blocking on prompts that were previously patched.

## Code Examples

### WorkflowOrchestrator State Machine (Recommended Pattern)
```python
# Source: Derived from existing MonitorLoop pattern and D-01/D-02 decisions
from dataclasses import dataclass, field
from enum import Enum

class WorkflowStage(str, Enum):
    IDLE = "idle"
    DISCUSS = "discuss"
    DISCUSSION_GATE = "discussion_gate"
    PLAN = "plan"
    PM_PLAN_REVIEW_GATE = "pm_plan_review_gate"
    EXECUTE = "execute"
    VERIFY = "verify"
    PHASE_COMPLETE = "phase_complete"

@dataclass
class AgentWorkflowState:
    agent_id: str
    current_phase: int = 0
    stage: WorkflowStage = WorkflowStage.IDLE
    stage_started_at: float = 0.0
    blocked_since: float | None = None
    blocked_reason: str = ""
```

### vco report Signal Detection Pattern
```python
# Source: Follows QuestionHandlerCog.on_message pattern from Phase 9
import re

STAGE_COMPLETE_PATTERNS = {
    "discuss": re.compile(r"discuss-phase complete", re.IGNORECASE),
    "plan": re.compile(r"plan-phase complete", re.IGNORECASE),
    "execute": re.compile(r"execute-phase complete", re.IGNORECASE),
    "research": re.compile(r"research-phase complete", re.IGNORECASE),
}

def detect_stage_signal(message_content: str) -> str | None:
    """Extract stage name from vco report message, or None."""
    for stage, pattern in STAGE_COMPLETE_PATTERNS.items():
        if pattern.search(message_content):
            return stage
    return None
```

### GSD Patch Application Pattern
```python
# Source: D-12 decision -- global patches to ~/.claude/get-shit-done/
from pathlib import Path
import re

GSD_WORKFLOWS_DIR = Path.home() / ".claude" / "get-shit-done" / "workflows"

def patch_discuss_phase_reports():
    """Add vco report calls to discuss-phase.md."""
    path = GSD_WORKFLOWS_DIR / "discuss-phase.md"
    content = path.read_text()

    # Add start report after <step name="parse_args">
    if 'vco report "starting discuss-phase' not in content:
        # Insert after the parse_args step opening
        content = content.replace(
            '<step name="check_existing">',
            '<step name="vco_report_start" priority="first">\n'
            '**MANDATORY** -- Run before anything else:\n'
            '```bash\n'
            'vco report "starting discuss-phase $PHASE" 2>/dev/null || true\n'
            '```\n'
            '</step>\n\n'
            '<step name="check_existing">',
        )

    # Add end report before auto_advance step
    if 'vco report "discuss-phase complete' not in content:
        content = content.replace(
            '<step name="auto_advance">',
            '<step name="vco_report_end">\n'
            '**MANDATORY** -- Run after context is written:\n'
            '```bash\n'
            'vco report "discuss-phase complete" 2>/dev/null || true\n'
            '```\n'
            '</step>\n\n'
            '<step name="auto_advance">',
        )

    path.write_text(content)
```

### Orchestrator Gate Review Pattern
```python
# Source: Follows PMTier.evaluate_question pattern from Phase 6
async def review_discussion_gate(
    self, agent_id: str, pm: PMTier, clone_dir: Path
) -> bool:
    """PM reviews CONTEXT.md at discussion gate. Returns True if approved."""
    context_path = clone_dir / ".planning" / "phases" / ... / "CONTEXT.md"
    # Find latest context file
    if not context_path.exists():
        return False

    content = context_path.read_text()
    review_question = (
        f"Review this CONTEXT.md from agent {agent_id}. "
        f"Is it complete and aligned with project goals? "
        f"Reply 'approved' or explain what's missing.\n\n{content[:3000]}"
    )
    decision = await pm.evaluate_question(review_question, agent_id)
    return decision.confidence.level in ("HIGH", "MEDIUM")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| GSD `--auto` flag for autonomous | Config-driven autonomy (D-14) | This phase | Orchestrator owns transitions, not GSD |
| Skip discuss (assumptions mode) | Full discussion through Discord | This phase | PM answers design questions via hook |
| File-based plan gate detection | Discord message-based stage detection | This phase | Faster, more reliable signal path |
| PlanReviewCog-only gate | Multi-gate orchestrator | This phase | Discussion and verify gates added |

## Open Questions

1. **Discuss-Phase Completion Detection Reliability**
   - What we know: discuss-phase has no vco report. We will patch it in.
   - What's unclear: If the patch location (before auto_advance) catches all exit paths (early exit, error, etc.).
   - Recommendation: Audit all exit paths in discuss-phase.md and ensure vco report fires on each. Add a fallback: if no signal received within timeout (30 min), orchestrator reads agent's STATE.md to check if context was written.

2. **WorkflowOrchestrator State Persistence**
   - What we know: In-memory state is simplest. File-based gives crash recovery.
   - What's unclear: How often the bot restarts. If rare, in-memory is fine with STATE.md fallback.
   - Recommendation: Use in-memory state (dataclass dict) with STATE.md as recovery source. On bot restart, orchestrator reads each agent's STATE.md to reconstruct position. This aligns with D-08.

3. **PM Review Quality for Discussion Gate**
   - What we know: PMTier does confidence-based evaluation. Plan review uses PlanReviewer with specialized logic.
   - What's unclear: Whether PMTier's generic evaluate_question is sufficient for CONTEXT.md review, or if a specialized DiscussionReviewer is needed.
   - Recommendation: Start with PMTier.evaluate_question for discussion gate. The question prompt can include specific criteria (completeness, alignment, scope). Specialize later if quality is insufficient.

## Environment Availability

Step 2.6: SKIPPED (no external dependencies identified) -- this phase is purely code/config changes using the existing stack.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml |
| Quick run command | `cd /home/developer/vcompany && uv run pytest tests/ -x --timeout=10` |
| Full suite command | `cd /home/developer/vcompany && uv run pytest tests/ --timeout=30` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-01 | WorkflowOrchestrator separate from MonitorLoop | unit | `uv run pytest tests/test_workflow_orchestrator.py::test_separate_from_monitor -x` | Wave 0 |
| D-02 | Per-agent independent state machine | unit | `uv run pytest tests/test_workflow_orchestrator.py::test_per_agent_state -x` | Wave 0 |
| D-04 | Commands sent without --auto | unit | `uv run pytest tests/test_workflow_orchestrator.py::test_commands_no_auto -x` | Wave 0 |
| D-06 | Stage completion via vco report signals | unit | `uv run pytest tests/test_workflow_orchestrator.py::test_signal_detection -x` | Wave 0 |
| D-07 | PM reviews artifacts at gates | unit | `uv run pytest tests/test_workflow_orchestrator.py::test_gate_reviews -x` | Wave 0 |
| D-12 | GSD patches applied correctly | unit | `uv run pytest tests/test_gsd_patches.py -x` | Wave 0 |
| D-15 | Unknown prompts block agent | unit | `uv run pytest tests/test_workflow_orchestrator.py::test_unknown_prompt_blocks -x` | Wave 0 |
| D-18 | GSD config template updated | unit | `uv run pytest tests/test_gsd_config_template.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x --timeout=10`
- **Per wave merge:** `uv run pytest tests/ --timeout=30`
- **Phase gate:** Full suite green before /gsd:verify-work

### Wave 0 Gaps
- [ ] `tests/test_workflow_orchestrator.py` -- covers D-01, D-02, D-04, D-06, D-07, D-15
- [ ] `tests/test_gsd_patches.py` -- covers D-12, D-13
- [ ] `tests/test_gsd_config_template.py` -- covers D-18

## Sources

### Primary (HIGH confidence)
- GSD workflow source files at `~/.claude/get-shit-done/workflows/` -- direct grep audit of all AskUserQuestion occurrences, vco report patterns, and auto_advance mechanisms
- `src/vcompany/orchestrator/agent_manager.py` -- verified send_work_command API and patterns
- `src/vcompany/monitor/loop.py` -- verified MonitorLoop architecture and callback injection
- `src/vcompany/bot/cogs/plan_review.py` -- verified PlanReviewCog PM review flow
- `src/vcompany/bot/cogs/question_handler.py` -- verified QuestionHandlerCog on_message pattern
- `src/vcompany/strategist/pm.py` -- verified PMTier evaluate_question API
- `src/vcompany/templates/gsd_config.json.j2` -- verified current template values

### Secondary (MEDIUM confidence)
- GSD auto-advance mechanism -- inferred from workflow source grep; confirmed _auto_chain_active and auto_advance config paths

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing
- Architecture: HIGH -- follows established patterns (Cog, callback injection, on_message)
- GSD audit: HIGH -- direct source file grep, all AskUserQuestion occurrences counted
- Pitfalls: HIGH -- derived from actual code audit (missing vco report in discuss-phase confirmed)

**Research date:** 2026-03-27
**Valid until:** 2026-04-15 (stable -- internal codebase, no external API changes)
