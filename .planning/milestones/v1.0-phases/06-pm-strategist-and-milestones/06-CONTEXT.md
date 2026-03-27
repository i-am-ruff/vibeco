# Phase 6: PM/Strategist and Milestones - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a two-tier AI decision system: (1) the Strategist — a persistent, personality-rich Claude Opus conversation that serves as the owner's CEO-friend with strategic outlook, and (2) the PM — a stateless Claude API tier that handles tactical agent questions and plan reviews. The Strategist runs as a continuous conversation in #strategist, the PM makes fresh-context API calls per question/plan. Build the escalation chain (PM → Strategist → Owner), decision logging to #decisions, periodic status digests to the Strategist, context limit handoff with self-summarization, and milestone infrastructure (`vco new-milestone`, PM-CONTEXT.md generation).

</domain>

<decisions>
## Implementation Decisions

### Two-Tier Architecture
- **D-01:** The system has TWO distinct AI entities:
  - **Strategist** — persistent Claude Opus (1M context) conversation. Personality-rich, strategic outlook. Talks to the owner in #strategist. The "smartest in the room."
  - **PM** — stateless Claude API calls (per question/plan). Fresh context each time, less bias. Handles agent questions and plan reviews.
- **D-02:** The Strategist is NOT a function-call bot. It's a continuous conversational entity with personality, like a CEO-friend. Must feel human, minimal LLM feel.
- **D-03:** The owner provides the Strategist's personality/system prompt as an input file (e.g., `STRATEGIST-PERSONA.md`). Phase 6 builds infrastructure to load it and append project context dynamically.
- **D-04:** Future extensibility: the Strategist will later guide marketing and financial agents. It should be designed as the central strategic intelligence, not just a Q&A bot.

### Escalation Chain
- **D-05:** Three-tier escalation for agent questions:
  1. **PM** evaluates using heuristics → HIGH confidence: answers directly
  2. **PM not confident** → escalates to **Strategist** (adds message to persistent conversation)
  3. **Strategist confident** → answers, PM relays to agent
  4. **Strategist not confident (<60%)** → escalates to **Owner** in #strategist, waits indefinitely
- **D-06:** LOW confidence threshold is <60% (not <70% as originally spec'd). MEDIUM is 60-90%. HIGH is >90%.
- **D-07:** LOW confidence escalations to the owner wait indefinitely — the agent blocks until the owner responds. No timeout fallback for strategic decisions.

### Confidence Heuristics (PM Tier)
- **D-08:** PM confidence is heuristic-based (deterministic), not AI self-assessed. Two signals:
  1. **Context coverage** — Does the question topic appear in blueprint, INTERFACES.md, or MILESTONE-SCOPE.md? More coverage = higher confidence.
  2. **Prior decision match** — Has a similar question been answered before (in #decisions log)? Exact match = HIGH, partial = MEDIUM, no match = LOW.
- **D-09:** Confidence thresholds are fixed for v1: >90% HIGH, 60-90% MEDIUM, <60% LOW.

### Strategist Runtime
- **D-10:** Strategist runs as a persistent Claude API conversation (messages array accumulating over time). Opus model with 1M context window.
- **D-11:** Owner interacts with the Strategist in the dedicated #strategist Discord channel. Messages there are forwarded to the persistent conversation. Responses posted back to the channel.
- **D-12:** Context limit handoff: auto-detect when approaching ~800K tokens. Strategist self-generates a Knowledge Transfer document (decisions, personality calibration, project state, owner preferences, open threads). Fresh session starts with this document as foundation.
- **D-13:** Periodic status digests: every 30 minutes, the monitor sends a compact PROJECT-STATUS.md summary to the Strategist conversation. Only changes since last digest. Interval is configurable.

### Plan Review (PM Tier)
- **D-14:** PM reviews plans automatically. Three checks:
  1. **Scope alignment** — Is the plan within MILESTONE-SCOPE.md? Files in agent's owned dirs? Requirements mapped to this phase?
  2. **Dependency readiness** — Does PROJECT-STATUS.md show dependencies shipped? If not, does plan include stubs/mocks?
  3. **Duplicate detection** — Has a similar plan been approved/executed by another agent?
- **D-15:** On HIGH confidence (all checks pass): PM auto-approves, agent proceeds immediately. Owner gets notification in #plan-review. Owner can retroactively reject.
- **D-16:** On LOW confidence or failures: PM escalates to Strategist (persistent conversation) for judgment. Strategist can approve, reject, or escalate to owner.
- **D-17:** Safety table validation already handled by Phase 5's safety_validator — PM does not re-check.

### Decision Logging
- **D-18:** All PM and Strategist decisions posted to #decisions channel as append-only record (STRAT-09). Each entry includes: timestamp, question/plan, decision, confidence level, who decided (PM/Strategist/Owner).

### Milestone Management
- **D-19:** Phase 6 builds milestone **infrastructure**, not policy. `vco new-milestone` accepts a new MILESTONE-SCOPE.md, updates the project, informs the Strategist. Exact workflow evolves through use.
- **D-20:** Rename STRATEGIST-PROMPT.md → PM-CONTEXT.md. This is the assembled project context document that the PM reads per call. Generated from blueprint + interfaces + scope + status + decisions.
- **D-21:** The Strategist has its own user-provided prompt file (STRATEGIST-PERSONA.md), separate from PM-CONTEXT.md.

### Claude's Discretion
- PM-CONTEXT.md generation template and assembly logic
- Knowledge Transfer document format and content structure
- Status digest format (compact summary vs full diff)
- Decision log entry format in #decisions
- QuestionHandlerCog modifications to route through PM before answering
- StrategistCog expansion from placeholder to persistent conversation manager
- How PM communicates with Strategist (API call to same conversation vs separate)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `.planning/research/ARCHITECTURE.md` — VCO-ARCHITECTURE.md authoritative design reference

### Requirements
- `.planning/REQUIREMENTS.md` §PM/Strategist Bot — STRAT-01 through STRAT-09
- `.planning/REQUIREMENTS.md` §Milestone Management — MILE-01, MILE-02, MILE-03

### Prior Phase Context
- `.planning/phases/05-hooks-and-plan-gate/05-CONTEXT.md` — Hook answer routing (D-01 through D-04), plan gate mechanics
- `.planning/phases/04-discord-bot-core/04-CONTEXT.md` — Bot architecture (D-11 through D-15), StrategistCog placeholder (D-12)

### Existing Code
- `src/vcompany/bot/cogs/strategist.py` — Empty StrategistCog placeholder to be expanded
- `src/vcompany/bot/cogs/question_handler.py` — QuestionHandlerCog (answer delivery, needs PM intercept layer)
- `src/vcompany/bot/cogs/plan_review.py` — PlanReviewCog (plan gate workflow, needs PM review integration)
- `src/vcompany/bot/client.py` — VcoBot with 5 Cogs loaded, callback injection pattern
- `src/vcompany/coordination/sync_context.py` — sync-context command (distributes docs to clones)
- `src/vcompany/monitor/loop.py` — MonitorLoop (status digest source)
- `src/vcompany/monitor/status_generator.py` — PROJECT-STATUS.md generation

### CLAUDE.md Stack Guidance
- `anthropic` SDK 0.86.x with `AsyncAnthropic` and `stream=True` for Strategist responses
- discord.py message editing for streaming Strategist responses to #strategist

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **StrategistCog** (`src/vcompany/bot/cogs/strategist.py`): Empty Cog with bot reference, ready for expansion
- **QuestionHandlerCog** (`src/vcompany/bot/cogs/question_handler.py`): Handles answer delivery — PM intercept layer inserts before this
- **PlanReviewCog** (`src/vcompany/bot/cogs/plan_review.py`): Full plan gate — PM review adds intelligence before approve/reject
- **AlertsCog** (`src/vcompany/bot/cogs/alerts.py`): Alert routing with `alert_hook_timeout` — reusable for escalation notifications
- **build_plan_review_embed** (`src/vcompany/bot/embeds.py`): Embed builder — extend for PM review annotations
- **status_generator** (`src/vcompany/monitor/status_generator.py`): Generates PROJECT-STATUS.md — source for periodic digests
- **sync_context** (`src/vcompany/coordination/sync_context.py`): Distributes files to clones — extend for PM-CONTEXT.md

### Established Patterns
- **Callback injection**: Bot injects callbacks into MonitorLoop at startup
- **asyncio.to_thread()**: All blocking operations wrapped for async safety
- **TYPE_CHECKING imports**: Cogs use TYPE_CHECKING for VcoBot
- **Atomic file writes**: write_atomic for coordination files
- **Cog architecture**: 5 Cogs loaded, each with setup() function

### Integration Points
- **QuestionHandlerCog.on_message** → needs PM intercept before presenting answer buttons
- **PlanReviewCog.handle_new_plan** → needs PM review before posting to #plan-review
- **MonitorLoop** → needs periodic digest callback for Strategist
- **VcoBot startup** → needs Strategist persistent conversation initialization
- **sync_context** → needs PM-CONTEXT.md generation added (rename from STRATEGIST-PROMPT.md)

</code_context>

<specifics>
## Specific Ideas

- The Strategist should feel like a CEO-friend, not an LLM. Owner provides personality prompt (STRATEGIST-PERSONA.md). Minimal "assistant" feel, maximum human conversational quality.
- The Strategist is the central strategic intelligence — designed to later guide marketing and financial agents, not just engineering.
- Context handoff at ~800K tokens is critical — the Knowledge Transfer doc must preserve personality calibration and owner relationship nuances, not just facts.
- Status digests every 30 minutes keep the Strategist passively aware without polluting the conversation. Compact format, changes-only.

</specifics>

<deferred>
## Deferred Ideas

- Strategist guiding marketing/financial agents — future milestone, Phase 6 builds the foundation
- Milestone workflow policy (what exactly happens when a milestone ends) — evolves through use
- Configurable confidence thresholds — fixed for v1, add configurability if needed later
- DM-based private conversations with Strategist — #strategist channel only for v1

</deferred>

---

*Phase: 06-pm-strategist-and-milestones*
*Context gathered: 2026-03-25*
