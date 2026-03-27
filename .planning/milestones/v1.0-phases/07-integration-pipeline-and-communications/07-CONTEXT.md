# Phase 7: Integration Pipeline and Communications - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the integration pipeline (`vco integrate` with interlocked merge flow, per-branch test attribution, AI-assisted conflict resolution, auto-fix dispatch), the communication rituals (/vco:checkin auto-posting after phase completion, /vco:standup with blocking interlock and full owner control), and interaction regression tests (SAFE-04) derived from INTERACTIONS.md concurrent scenarios.

</domain>

<decisions>
## Implementation Decisions

### Integration Interlock
- **D-01:** Integration uses an interlock model, not instant execution:
  1. Owner triggers `!integrate` (or triggered programmatically)
  2. Monitor marks integration as "pending" — agents finish their current phase normally
  3. When ALL agents reach phase completion and are idle (blocked by plan gate), integration triggers automatically
  4. `vco integrate` merges all branches, runs tests, creates PR
  5. On success: agents are unblocked, monitor sends next phase commands
  6. On failure: responsible agents get auto-dispatched fix tasks, integration retries after fixes
- **D-02:** Integration waits for a natural synchronization point (all agents idle after phase completion). No agent is interrupted mid-work.

### Merge Strategy
- **D-03:** `vco integrate` creates an integration branch from main, merges all agent branches (agent/{id.lower()} per Phase 1 D-14).
- **D-04:** AI-assisted conflict resolution via the PM tier (stateless, fast). PM analyzes conflicting hunks with file context. Falls back to Discord escalation on low confidence.
- **D-05:** Non-overlapping changes auto-merge via git. Only overlapping-line conflicts invoke the PM resolver.

### Test Failure Attribution
- **D-06:** Per-branch test runs for accurate attribution:
  1. Merge all branches → run tests → if failures, record which tests failed
  2. For each agent branch: merge main + only that branch → re-run the failing tests
  3. If tests fail with just agent-A's branch → agent-A owns it
  4. If tests pass with every individual branch but fail merged → interaction failure between branches → escalate to Discord with both agents tagged
- **D-07:** Fix dispatch is automatic (INTG-05). Responsible agent receives failing test info and fix instructions via `/gsd:quick`. Owner notified in #alerts.

### PR Creation
- **D-08:** On test success, `vco integrate` creates a PR to main using `gh pr create` (INTG-06). PR includes: merged branches, test results, commit summary.

### Checkin Ritual
- **D-09:** /vco:checkin runs automatically after each phase completion. Monitor detects phase completion and sends /vco:checkin to the agent's tmux pane.
- **D-10:** Checkin posts to #agent-{id} channel with: commit count, summary, gaps/notes, next phase, dependency status (COMM-01, COMM-02).

### Standup Ritual
- **D-11:** /vco:standup uses a blocking interlock model:
  1. `!standup` triggers → each agent posts structured status in their per-agent thread in #standup
  2. Agents are BLOCKED — they do NOT resume until explicitly released
  3. Owner interacts in threads: ask questions, give feedback, reprioritize
  4. Owner clicks "Release" button (or types "go") per thread to unblock each agent
  5. No timeout — owner decides when each agent resumes
- **D-12:** Full owner control during standup (COMM-05): reprioritize agents, reassign work, change scope, ask questions. Agent receives owner questions as prompts in tmux pane, posts answers back to thread.
- **D-13:** Agent updates ROADMAP.md or STATE.md based on owner feedback during standup (COMM-06).

### Interaction Regression Tests (SAFE-04)
- **D-14:** Test suite derived from INTERACTIONS.md (Phase 3). For each interaction pattern marked as "critical," write a test that simulates the concurrent scenario.
- **D-15:** Tests marked with `@pytest.mark.integration` — run only during `vco integrate`, NOT on every pytest invocation. Keeps normal test suite fast.
- **D-16:** Tests use mocks/fakes for tmux and subprocess to simulate concurrent agent behavior without requiring actual running agents.

### Claude's Discretion
- Integration branch naming convention (e.g., `integrate/{timestamp}` or `integrate/{milestone}`)
- PR description template format
- Exact INTERACTIONS.md patterns to extract for regression tests
- Standup thread creation and formatting details
- Checkin embed format and content structure
- How to send questions from standup threads to agent tmux panes
- Retry logic for integration after fix dispatch

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `.planning/research/ARCHITECTURE.md` — VCO-ARCHITECTURE.md authoritative design reference

### Requirements
- `.planning/REQUIREMENTS.md` §Integration Pipeline — INTG-01 through INTG-08
- `.planning/REQUIREMENTS.md` §Standup and Checkin — COMM-01 through COMM-06
- `.planning/REQUIREMENTS.md` §Interaction Safety — SAFE-04

### Prior Phase Context
- `.planning/phases/01-foundation-and-configuration/01-CONTEXT.md` — Agent branch convention (D-14: agent/{id.lower()})
- `.planning/phases/04-discord-bot-core/04-CONTEXT.md` — CommandsCog with !integrate and !standup scaffolds (D-05-D-07)
- `.planning/phases/05-hooks-and-plan-gate/05-CONTEXT.md` — Plan gate mechanism, agent pause model
- `.planning/phases/06-pm-strategist-and-milestones/06-CONTEXT.md` — PM tier for conflict resolution, Strategist conversation

### Existing Code
- `src/vcompany/bot/cogs/commands.py` — CommandsCog with placeholder !integrate and !standup
- `src/vcompany/coordination/interactions.py` — INTERACTIONS.md with concurrent patterns (source for SAFE-04 tests)
- `src/vcompany/git/ops.py` — Git wrapper (clone, checkout, branch, merge, log, push, status)
- `src/vcompany/orchestrator/agent_manager.py` — AgentManager for dispatch/kill/relaunch
- `src/vcompany/monitor/loop.py` — MonitorLoop with callback injection
- `src/vcompany/bot/views/confirm.py` — ConfirmView pattern for button interactions
- `src/vcompany/strategist/pm.py` — PMTier for conflict resolution heuristics
- `src/vcompany/templates/` — /vco:checkin.md and /vco:standup.md command templates

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **CommandsCog** (`src/vcompany/bot/cogs/commands.py`): Placeholder !integrate and !standup commands ready for expansion
- **git ops** (`src/vcompany/git/ops.py`): Git merge, branch, checkout, log wrappers — foundation for integration pipeline
- **AgentManager** (`src/vcompany/orchestrator/agent_manager.py`): dispatch/kill/relaunch — used for fix dispatch and agent control during standup
- **PMTier** (`src/vcompany/strategist/pm.py`): Stateless Claude API calls — reuse for conflict resolution
- **ConfirmView** (`src/vcompany/bot/views/confirm.py`): Button interaction pattern — reuse for standup Release button
- **MonitorLoop** (`src/vcompany/monitor/loop.py`): Callback injection, plan gate state tracking — extend for integration interlock
- **TmuxManager** (`src/vcompany/tmux/session.py`): send_command for routing standup questions to agent panes
- **build_alert_embed / build_status_embed** (`src/vcompany/bot/embeds.py`): Embed builders — extend for checkin/standup embeds

### Established Patterns
- **Callback injection**: Bot injects callbacks into MonitorLoop at startup
- **asyncio.to_thread()**: All blocking operations (git, file I/O) wrapped for async safety
- **ConfirmView button pattern**: Approve/Reject with callback — reuse for Release button
- **Plan gate interlock**: Monitor tracks state, blocks/unblocks agents — model for integration interlock
- **Atomic file writes**: write_atomic for coordination files

### Integration Points
- **CommandsCog.!integrate** → needs full implementation (currently placeholder)
- **CommandsCog.!standup** → needs full implementation (currently placeholder)
- **MonitorLoop** → needs integration pending state, checkin auto-trigger after phase completion
- **AgentManager** → needs fix dispatch method for INTG-05
- **PMTier** → needs conflict resolution method for INTG-08

</code_context>

<specifics>
## Specific Ideas

- The integration interlock mirrors the standup interlock: both block agents at natural synchronization points and release them explicitly. This is a shared "agent gate" pattern.
- Per-branch test attribution is the most accurate approach but costs N+1 test runs. Only re-run the failing tests (not the full suite) to keep it fast.
- Standup has NO timeout — the owner controls when each agent resumes. This matches the user's explicit request for full control over agent autonomy.
- Checkin is fire-and-forget (auto after phase completion), standup is interactive (blocking).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-integration-pipeline-and-communications*
*Context gathered: 2026-03-25*
