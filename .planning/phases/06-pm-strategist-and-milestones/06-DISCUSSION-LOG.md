# Phase 6: PM/Strategist and Milestones - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 06-pm-strategist-and-milestones
**Areas discussed:** Confidence & escalation, Context & prompting, Plan review logic, Milestone management

---

## Major Architecture Shift

User clarified a fundamental misunderstanding: the Strategist is NOT a stateless API bot that answers agent questions. It is a **persistent, personality-rich conversational entity** — the owner's CEO-friend with strategic outlook. This led to a two-tier architecture:

1. **Strategist** — persistent Opus 1M conversation, strategic, talks to owner
2. **PM** — stateless API calls, tactical, handles agent questions and plan reviews

The entire discussion was reframed around this architecture.

---

## Confidence & Escalation

### Q1: How should confidence be determined?

| Option | Description | Selected |
|--------|-------------|----------|
| Self-assessed | Claude rates its own confidence | |
| Heuristic-based | Score based on measurable signals | ✓ |
| Hybrid | AI judgment + hard rules | |

**User's choice:** Heuristic-based — deterministic scoring, not AI self-assessment.

### Q2: What signals drive the heuristic?

| Option | Description | Selected |
|--------|-------------|----------|
| Context coverage | Topic appears in project docs | ✓ |
| Prior decision match | Similar question answered before | ✓ |
| Scope boundary | In-scope vs out-of-scope | |
| Question category | Hard rules per category | |

**User's choice:** Context coverage + prior decision match.

### Q3: Escalation timeout?

| Option | Description | Selected |
|--------|-------------|----------|
| Timeout with fallback | Wait then auto-answer | |
| Wait indefinitely | Block until owner responds | ✓ |
| You decide | | |

**User's choice:** Wait indefinitely for LOW confidence escalations.

### Q4: Confidence thresholds?

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed 90%/70% | Per original spec | |
| Fixed 90%/60% | Adjusted per user | ✓ |
| Configurable | Per-project setting | |

**User's choice:** Fixed but adjusted: >90% HIGH, 60-90% MEDIUM, <60% LOW. User explicitly said "Greater than 90% LOW is less than 60%."

---

## Context & Prompting (merged with Strategist architecture discussion)

### Q1: Strategist runtime?

| Option | Description | Selected |
|--------|-------------|----------|
| Persistent chat session | Continuously running conversation | ✓ |
| API with managed memory | Reconstructed context per call | |
| Let me explain | | |

**User's choice:** Persistent chat session preferred, API with memory as fallback.

### Q2: Three-tier escalation chain

User proposed (not from options): PM → Strategist → Owner chain. Each tier escalates what it can't handle.

### Q3: Strategist model?

| Option | Description | Selected |
|--------|-------------|----------|
| Opus (1M context) | Most capable, best personality | ✓ |
| Sonnet (200K) | Faster, cheaper | |
| Configurable | Per-project choice | |

**User's choice:** Opus (1M context)

### Q4: Context limit handoff?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-detect + self-summarize | Generate Knowledge Transfer doc at ~800K | ✓ |
| Periodic snapshots | Regular checkpoint writes | |
| You decide | | |

**User's choice:** Auto-detect + self-summarize

### Q5: Status awareness?

| Option | Description | Selected |
|--------|-------------|----------|
| Periodic digest | Every N minutes | ✓ |
| On-demand only | Read when asked | |
| Real-time every cycle | Every 60s | |

**User's choice:** Periodic, "a few times a day." Claude recommended every 30 minutes as default, configurable.

### Q6: Personality prompt?

| Option | Description | Selected |
|--------|-------------|----------|
| Template + user additions | Structured template with fillable sections | |
| User provides full prompt | Owner writes the personality doc | ✓ |
| Start minimal, evolve | Learn through conversation | |

**User's choice:** Owner provides full personality prompt as STRATEGIST-PERSONA.md.

---

## Plan Review Logic

### Q1: Who reviews plans?

| Option | Description | Selected |
|--------|-------------|----------|
| PM reviews, Strategist for edge cases | Matches escalation chain | ✓ |
| Strategist reviews all | Every plan through persistent conversation | |
| PM advises, owner decides | PM comments, owner clicks | |

**User's choice:** PM reviews, escalates edge cases to Strategist.

### Q2: Auto-approve?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-approve on HIGH | PM auto-approves, owner notified | ✓ |
| Always require human click | Owner is bottleneck | |
| Configurable | Per-project setting | |

**User's choice:** Auto-approve on HIGH confidence.

### Q3: PM review checks?

| Option | Description | Selected |
|--------|-------------|----------|
| Scope alignment | Plan within milestone scope | ✓ |
| Dependency readiness | Dependencies shipped or stubs included | ✓ |
| Safety table present | Already handled by Phase 5 | |
| Duplicate detection | Prevent two agents building same thing | ✓ |

**User's choice:** Scope alignment + dependency readiness + duplicate detection.

---

## Milestone Management

### Q1: What does `vco new-milestone` do?

| Option | Description | Selected |
|--------|-------------|----------|
| Full reset + re-dispatch | Clean start for all agents | |
| Scope update + selective restart | Only reset affected agents | |
| Let me explain | User unsure | ✓ |

**User's choice:** Unsure — depends on how GSD handles milestones in practice.

### Q2: Infrastructure-first approach?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, infrastructure first | Build commands, evolve policy through use | ✓ |
| Define minimal policy | Need default behavior even if flexible | |
| Defer milestones entirely | Push to post-v1 | |

**User's choice:** Infrastructure first.

### Q3: STRATEGIST-PROMPT.md naming?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, PM's system prompt | Keep current name | |
| Both use it | Shared context layer | |
| Rename it | Name is confusing with two entities | ✓ |

**User's choice:** Rename to PM-CONTEXT.md.

---

## Claude's Discretion

- PM-CONTEXT.md generation and assembly logic
- Knowledge Transfer document format
- Status digest format and content
- Decision log entry format
- QuestionHandlerCog modifications for PM intercept
- StrategistCog expansion to persistent conversation manager
- PM-to-Strategist communication mechanism

## Deferred Ideas

- Strategist guiding marketing/financial agents — future milestone
- Milestone workflow policy — evolves through use
- Configurable confidence thresholds — fixed for v1
- DM-based private Strategist conversations — #strategist channel only for v1
