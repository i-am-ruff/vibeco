# Phase 3: Monitor Loop and Coordination - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 03-monitor-loop-and-coordination
**Areas discussed:** Plan gate pause, Contract flow
**Mode:** Interactive

---

## Plan Gate Pause

| Option | Description | Selected |
|--------|-------------|----------|
| Option C: Monitor intercepts | Agent finishes planning, sits idle at prompt. Monitor posts plans to Discord, sends execute command on approval. | ✓ |
| Option B: Hook-based | PreToolUse hook checks Discord for approval before execution starts. | |
| Option A: Sentinel file | Monitor writes lock file, agent spins waiting for it to disappear. | |

**User's choice:** Option C — Monitor intercepts auto-advance
**Notes:** Cleanest approach. Agent doesn't need special pause logic. Monitor controls when next command is sent to tmux pane.

---

## Contract Flow (INTERFACES.md Changes)

Initial options presented included "PM edits directly" — user rejected this, stating writing code is not the PM/Strategist's task.

Revised flow:

| Step | Actor | Action |
|------|-------|--------|
| 1 | Agent | Discovers need for interface change |
| 2 | Agent | Proposes exact diff via AskUserQuestion |
| 3 | PM/Strategist | Reviews proposal — approves or rejects with reasoning (judgment only) |
| 4 | Orchestrator | Applies approved diff and distributes to all clones |

**User's choice:** Agent proposes diff → PM judges → orchestrator applies
**Notes:** PM never edits code. PM's role is purely judgment — does the change make sense for the project, does it conflict with other agents' work.

---

## Areas Auto-Decided (Well-Specified in Architecture Doc)

- **Status generation:** Full format in VCO-ARCHITECTURE.md, 60s cycle, read ROADMAP.md + git log
- **Monitor watchdog:** Heartbeat file + systemd/cron check, standard pattern

## Claude's Discretion

- Internal monitor state management
- PROJECT-STATUS.md generation implementation
- sync-context file copy strategy
- Interface change diff application method

## Deferred Ideas

None
