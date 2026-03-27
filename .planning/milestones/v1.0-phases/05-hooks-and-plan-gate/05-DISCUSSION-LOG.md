# Phase 5: Hooks and Plan Gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 05-hooks-and-plan-gate
**Areas discussed:** Hook answer routing, Plan review UX, Agent pause mechanism, Safety table enforcement

---

## Hook Answer Routing

### Q1: How should ask_discord.py receive the answer back from Discord?

| Option | Description | Selected |
|--------|-------------|----------|
| File-based polling | Bot writes answer to /tmp/vco-answers/{request-id}.json. Hook polls every 5s. Simple, no network deps, self-contained. | ✓ |
| Discord API polling | Hook polls Discord API directly for replies. Requires bot token in clone context. | |
| Local HTTP callback | Hook starts tiny HTTP server, bot POSTs answer back. More complex but instant delivery. | |

**User's choice:** File-based polling — user asked which is architecturally sound; file-based IPC is the cleanest pattern for same-machine hook-to-daemon communication (failure isolation, stdlib-only, debuggable).
**Notes:** Rationale provided for architectural soundness: decoupling, failure isolation, HOOK-06 compliance, same-machine optimization, debuggability.

### Q2: Should the hook post questions directly to Discord or write a request file?

| Option | Description | Selected |
|--------|-------------|----------|
| Webhook POST | Hook POSTs to Discord webhook URL (DISCORD_AGENT_WEBHOOK_URL env var). No bot token needed. | ✓ |
| Request file for bot | Hook writes request file, bot picks it up and posts. Symmetric with answer path but adds latency. | |
| You decide | Claude picks. | |

**User's choice:** Webhook POST
**Notes:** Asymmetric by design: outbound instant (webhook), inbound polled (file).

### Q3: Should Phase 5 prepare Strategist integration or stay human-only?

| Option | Description | Selected |
|--------|-------------|----------|
| Human-only for Phase 5 | Route all questions to #strategist for human answer. Phase 6 adds AI. | ✓ |
| Prepare Strategist integration point | Design answer flow with explicit hook point for Phase 6 intercept. | |

**User's choice:** Human-only for Phase 5
**Notes:** Clean phase separation.

### Q4: Timeout fallback behavior?

| Option | Description | Selected |
|--------|-------------|----------|
| Alert only | Post to #alerts noting assumption made. Simple, matches HOOK-04 spec. | |
| Alert with override button | Alert includes button to override assumption. | |
| You decide | Claude picks. | |

**User's choice:** Other — configurable with two modes: (1) block agent execution on timeout, (2) alert only and continue with fallback. Per-project configuration.
**Notes:** User explicitly requested both options be available as a configurable setting.

---

## Plan Review UX

### Q1: How should plans be presented in #plan-review?

| Option | Description | Selected |
|--------|-------------|----------|
| Summary embed + full file | Rich embed with overview, full PLAN.md as file/thread attachment. | ✓ |
| Full plan inline | Entire PLAN.md in channel message. May hit Discord char limit. | |
| Summary only + link | Summary embed only, reviewer checks repo for details. | |

**User's choice:** Summary embed + full file

### Q2: How should the reviewer approve or reject?

| Option | Description | Selected |
|--------|-------------|----------|
| Buttons | Discord button components: Approve and Reject. Modal for rejection feedback. | ✓ |
| Reactions | Emoji reactions. Simpler but no feedback collection. | |
| Thread replies | Reply in thread. Natural but hard to parse. | |

**User's choice:** Buttons

### Q3: How should rejection feedback reach the agent?

| Option | Description | Selected |
|--------|-------------|----------|
| Send prompt to tmux pane | Monitor sends feedback as new prompt via TmuxManager. Per Phase 3 D-08. | ✓ (Claude's discretion) |
| Write feedback file | Bot writes file, agent's GSD resume picks it up. | |
| You decide | Claude picks. | ✓ |

**User's choice:** You decide — Claude selected tmux pane prompt (consistent with Phase 3 D-08 pattern).

---

## Agent Pause Mechanism

### Q1: How should the agent be paused during plan approval?

| Option | Description | Selected |
|--------|-------------|----------|
| Natural idle | GSD finishes planning, agent returns to prompt. Monitor doesn't send execute until approval. | ✓ |
| GSD auto-advance block | Inject config flag blocking auto-advance after planning. | ✓ |
| Sentinel file gate | Agent checks for .plan-approved file before proceeding. | |

**User's choice:** Combination — agents are monitor-commanded (natural idle) AND auto_advance is explicitly disabled in GSD config as a defensive measure. User asked for clarity on current architecture; confirmed agents don't auto-advance.
**Notes:** GSD config template currently lacks auto_advance setting. Adding explicit `"auto_advance": false` as defense-in-depth.

### Q2: Should monitor track plan gate state per-agent?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, track in state | plan_gate_status field: idle, awaiting_review, approved, rejected. | ✓ |
| Stateless — re-derive | Re-derive from plan mtimes each cycle. | |
| You decide | Claude picks. | |

**User's choice:** Yes, track in state

### Q3: Per-plan or per-phase execution trigger?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-phase | Send /gsd:execute-phase {N} once when ALL plans approved. | ✓ |
| Per-plan | Send execute for each plan individually as approved. | |
| You decide | Claude picks. | |

**User's choice:** Per-phase

---

## Safety Table Enforcement

### Q1: Where should safety table validation run?

| Option | Description | Selected |
|--------|-------------|----------|
| Part of plan gate review | Monitor checks for safety table before posting to #plan-review. Flags if missing. | ✓ |
| GSD plan-checker agent | Custom check in GSD's plan-check workflow. | |
| Separate CLI command | `vco validate-plan` command. | |

**User's choice:** Part of plan gate review

### Q2: How strict should the check be?

| Option | Description | Selected |
|--------|-------------|----------|
| Warn but allow | Missing table adds warning to embed. Reviewer can still approve. | |
| Hard block | Plans without table cannot be approved. | |
| Configurable per project | Project-level setting: warn or block. | ✓ |

**User's choice:** Configurable per project

### Q3: Safety table format?

| Option | Description | Selected |
|--------|-------------|----------|
| Markdown table in plan | 6-column table under ## Interaction Safety heading in PLAN.md. | ✓ |
| Separate safety file | Companion SAFETY.md per plan. | |
| You decide | Claude picks. | |

**User's choice:** Markdown table in plan

---

## Claude's Discretion

- Request ID generation strategy
- Answer file cleanup policy
- Exact embed formatting for plan review
- Plan gate state persistence format
- Safety table validation heuristics
- Rejection feedback sent to tmux pane (per Phase 3 D-08 pattern)

## Deferred Ideas

None — discussion stayed within phase scope
