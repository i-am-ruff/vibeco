# Phase 7: Integration Pipeline and Communications - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 07-integration-pipeline-and-communications
**Areas discussed:** Merge & conflict strategy, Test failure attribution, Standup & checkin rituals, Regression tests (SAFE-04)

---

## Merge & Conflict Strategy

### Q1: Integration trigger?

| Option | Description | Selected |
|--------|-------------|----------|
| Manual only | Owner triggers !integrate | |
| Auto after all agents complete phase | Monitor detects all done | |
| Scheduled interval | Every N hours | |
| Interlock model (user-proposed) | Trigger → agents finish current phase → all idle → integrate → unblock | ✓ |

**User's choice:** Interlock model — integration waits for all agents to reach natural synchronization point (idle after phase completion).

### Q2: Auto-conflict resolution scope?

| Option | Description | Selected |
|--------|-------------|----------|
| Non-overlapping only | Only git-resolvable conflicts | |
| AI-assisted resolution | Use Claude to analyze conflicting hunks | ✓ |
| No auto-resolution | All conflicts to Discord | |

**User's choice:** AI-assisted resolution.

### Q3: Which model for conflict resolution?

| Option | Description | Selected |
|--------|-------------|----------|
| PM tier (stateless, fast) | Cheap, deterministic, falls back on low confidence | ✓ |
| Strategist (persistent) | Richer context but burns Strategist window | |
| Dedicated resolver agent | Fresh context but adds agent type | |

**User's choice:** PM tier.

---

## Test Failure Attribution

### Q1: Attribution method?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-branch test runs | Merge main+each-branch individually, find which breaks | ✓ |
| File-based heuristic | Map test files to agent owned dirs | |
| Git blame on failing lines | Check which agent modified source | |

**User's choice:** Per-branch test runs (most accurate). User said "Decide the most accurate approach yourself."

### Q2: Fix dispatch approval?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-dispatch | Automatically send fix to responsible agent | ✓ |
| Approval required | Wait for owner approval | |
| You decide | | |

**User's choice:** Auto-dispatch.

---

## Standup & Checkin Rituals

### Q1: Checkin trigger?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto after phase completion | Monitor sends /vco:checkin automatically | ✓ |
| Triggered by !standup | Only during standups | |
| Both | Auto + standup | |

**User's choice:** Auto after phase completion.

### Q2: Standup owner power?

| Option | Description | Selected |
|--------|-------------|----------|
| Full control | Reprioritize, reassign, ask questions | ✓ |
| Read-only + questions | Informational only | |
| You decide | | |

**User's choice:** Full control.

### Q3: Standup flow?

| Option | Description | Selected |
|--------|-------------|----------|
| Poll + timeout | 5s poll, 5-min timeout | |
| Event-driven | on_message listener | |
| Blocking interlock (user-proposed) | Agents blocked until owner explicitly releases each one | ✓ |

**User's choice:** Blocking interlock — no timeout, agents stay blocked until owner clicks Release. User explicitly said "I don't want agents to resume work without me saying specifically that they are free to go."

---

## Regression Tests (SAFE-04)

### Q1: Test approach?

| Option | Description | Selected |
|--------|-------------|----------|
| Test suite from INTERACTIONS.md | Write tests for each critical concurrent pattern | ✓ |
| Integration-time smoke tests | Run only during vco integrate | |
| You decide | | |

**User's choice:** Test suite from INTERACTIONS.md.

### Q2: When to run?

| Option | Description | Selected |
|--------|-------------|----------|
| Every pytest run | In standard test suite | |
| Integration-only | @pytest.mark.integration, skip in normal runs | ✓ |
| You decide | | |

**User's choice:** Integration-only.

---

## Claude's Discretion

- Integration branch naming convention
- PR description template
- Exact INTERACTIONS.md patterns to extract
- Standup thread formatting
- Checkin embed format
- How standup questions route to tmux panes
- Integration retry logic after fix dispatch

## Deferred Ideas

None — discussion stayed within phase scope
