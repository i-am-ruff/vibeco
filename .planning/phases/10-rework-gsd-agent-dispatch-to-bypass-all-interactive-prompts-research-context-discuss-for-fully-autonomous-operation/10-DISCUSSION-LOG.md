# Phase 10: Rework GSD Agent Dispatch - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 10-rework-gsd-agent-dispatch-to-bypass-all-interactive-prompts-research-context-discuss-for-fully-autonomous-operation
**Areas discussed:** GSD modification scope, Prompt audit & coverage, Dispatch command strategy, Fallback behavior, GSD phase invocation audit

---

## GSD Modification Scope

### How to handle GSD for autonomous operation?

| Option | Description | Selected |
|--------|-------------|----------|
| Config-only | Only use GSD's existing config surface. Zero source modifications. | |
| Config + hooks/wrappers | Use GSD config plus Claude Code hooks to intercept remaining prompts. | |
| Patch GSD source | Modify GSD workflow files directly. Use /gsd:reapply-patches after updates. | ✓ |

**User's choice:** Patch GSD source
**Notes:** None

### Where do patches live?

| Option | Description | Selected |
|--------|-------------|----------|
| In vCompany repo, deployed per clone | Patches stored in templates, deployed during vco clone. | |
| Global patches on host | Applied once to ~/.claude/get-shit-done/. All agents inherit. | ✓ |

**User's choice:** Global patches on host
**Notes:** None

---

## Prompt Audit & Coverage

### Audit thoroughness?

| Option | Description | Selected |
|--------|-------------|----------|
| Full audit + patch all prompts | Systematically read every GSD workflow file, identify every prompt, create coverage matrix. | ✓ |
| Known gaps only | Patch specific prompts already known. | |
| Runtime validation | Run dry-run agent and fix hangs as discovered. | |

**User's choice:** Full audit + patch all prompts
**Notes:** None

### How should auto behavior be configured?

| Option | Description | Selected |
|--------|-------------|----------|
| Config forces auto | GSD config settings make autonomous behavior default. No --auto flag needed. | |
| Require --auto flag | vco always passes --auto. Config is secondary. | |
| Both: config + flag | Belt-and-suspenders. | |

**User's choice:** Other (free text)
**Notes:** Critical design shift: --auto and config paths may bypass important AskUserQuestion calls. The correct model is:
1. No skip_discuss. Discussion flows through Discord via AskUserQuestion hook. PM/Strategist answers.
2. No other interactive prompts — all patched out.
3. Blockers go through vco report mentioning PM or Strategist.
4. Each stage runs autonomously within itself but does NOT auto-advance to the next stage.

### PM context for discussion questions

| Option | Description | Selected |
|--------|-------------|----------|
| PM uses full project context | Stateless but well-informed per question. | |
| Strategist handles discussions | Persistent conversation for coherent multi-step decisions. | |
| Pre-seed discussion answers | Generate discussion brief before starting. | |

**User's choice:** Other (free text)
**Notes:** PM uses full project context AND its own decision log memory. Medium or lower confidence → asks Strategist. Standard escalation chain applies to discussion questions.

---

## Dispatch Command Strategy

### What commands does orchestrator send?

| Option | Description | Selected |
|--------|-------------|----------|
| Standard GSD commands, no --auto | /gsd:discuss-phase N, /gsd:plan-phase N, /gsd:execute-phase N. Each runs and stops. | ✓ |
| Custom vco wrapper commands | /vco:discuss N, /vco:plan N, /vco:execute N wrapping GSD. | |
| GSD with --no-advance flag | Patch GSD to add --no-advance. | |

**User's choice:** Standard GSD commands, no --auto
**Notes:** None

### How does orchestrator detect stage completion?

| Option | Description | Selected |
|--------|-------------|----------|
| vco report signal | GSD workflows end with vco report. Orchestrator listens. | ✓ |
| File artifact detection | Watch for CONTEXT.md, PLAN.md, VERIFICATION.md. | |
| Both: report + artifact | Primary signal + fallback verification. | |

**User's choice:** vco report signal
**Notes:** None

### Crash recovery — how to determine resume stage?

| Option | Description | Selected |
|--------|-------------|----------|
| Check artifacts | Look for CONTEXT.md, PLAN.md, SUMMARY.md existence. | |
| STATE.md position | Read GSD's STATE.md in the clone. | ✓ |
| Orchestrator's own state | Persist own per-agent state file. | |

**User's choice:** STATE.md position
**Notes:** None

---

## Fallback Behavior

### Unknown prompt slips through?

| Option | Description | Selected |
|--------|-------------|----------|
| Catch-all hook + vco report | Auto-select + alert PM. Agent continues. | |
| Block and alert | Block agent, alert Discord. PM/Owner intervenes. | ✓ |
| Always auto-select first option | Silent auto-select. No alert. | |

**User's choice:** Block and alert
**Notes:** None

### How long to block?

| Option | Description | Selected |
|--------|-------------|----------|
| 10 minutes then escalate | Block, then orchestrator classifies as stuck. | ✓ |
| 5 minutes then auto-select | Short block, then auto-select and continue. | |
| Indefinite until intervention | Block forever. Most conservative. | |

**User's choice:** 10 minutes then escalate
**Notes:** None

---

## GSD Phase Invocation Audit

### How does orchestrator know which phase per agent?

| Option | Description | Selected |
|--------|-------------|----------|
| From agents.yaml + ROADMAP.md | Agent assignments + phase order. | |
| PM assigns phases | Dynamic phase assignment by PM. | |
| Sequential by roadmap | All agents on same phase. | |

**User's choice:** Other (free text)
**Notes:** WorkflowOrchestrator handles each agent separately. Each has its own roadmap and GSD state. First option closest.

### Validate artifacts at gates?

| Option | Description | Selected |
|--------|-------------|----------|
| Validate artifacts at each gate | Check existence and quality of CONTEXT.md, PLAN.md, VERIFICATION.md. | |
| Trust vco report signals | If agent reported complete, trust it. | |
| PM reviews artifacts | PM reads and evaluates artifacts at each gate. Quality review, not just existence. | ✓ |

**User's choice:** PM reviews artifacts
**Notes:** None

### auto_advance setting?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep false | Orchestrator sends explicit commands. Maximum control. | ✓ |
| Set to true | GSD auto-chains within stages. | |

**User's choice:** Keep false
**Notes:** Verified that auto_advance is inter-stage only (discuss→plan→execute transitions). Does NOT affect intra-stage progress. Keep false so orchestrator owns all transitions.

---

## Claude's Discretion

- WorkflowOrchestrator internal state format and persistence
- vco report signal format/protocol
- Bot integration approach (Cog, background task, standalone)
- Specific GSD prompts to patch (determined during full audit)
- Orchestrator runtime model (asyncio task vs separate process)

## Deferred Ideas

None — discussion stayed within phase scope
