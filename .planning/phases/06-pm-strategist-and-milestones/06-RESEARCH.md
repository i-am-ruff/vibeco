# Phase 6: PM/Strategist and Milestones - Research

**Researched:** 2026-03-25
**Domain:** AI-powered decision system (two-tier PM/Strategist), Anthropic SDK conversation management, Discord bot integration, milestone CLI
**Confidence:** HIGH

## Summary

Phase 6 transforms the empty `StrategistCog` placeholder into a two-tier AI decision system: a stateless PM tier that handles agent questions and plan reviews via heuristic confidence scoring, and a persistent Strategist tier that maintains a long-running Claude Opus conversation with the project owner. The existing codebase provides strong integration points -- `QuestionHandlerCog.on_message` is the intercept point for PM routing, `PlanReviewCog.handle_new_plan` is the intercept point for PM plan review, and `MonitorLoop._run_cycle` is where periodic status digests originate.

The Anthropic Python SDK (0.86.x on PyPI) provides `AsyncAnthropic` with `client.messages.stream()` for streaming Strategist responses to Discord, and `client.messages.count_tokens()` for detecting context limit approach at ~800K tokens. The persistent conversation is managed in-memory as a growing messages array (list of dicts with role/content), with periodic token counting to trigger the Knowledge Transfer handoff. The PM tier uses fresh `client.messages.create()` calls per question/plan with PM-CONTEXT.md as system prompt.

The CLI already has the `click.group()` pattern with `cli.add_command()` registration. Adding `vco new-milestone` follows the exact same pattern as existing commands (`init`, `dispatch`, `clone`). The `sync_context` module already distributes files to clones and needs only minor extension to include PM-CONTEXT.md generation.

**Primary recommendation:** Build the PM tier first (stateless, heuristic confidence, intercepts existing cogs), then the Strategist tier (persistent conversation, streaming to Discord), then milestone infrastructure. Each tier is independently testable.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: TWO distinct AI entities: Strategist (persistent Opus 1M conversation, personality-rich) and PM (stateless per-call, fresh context)
- D-02: Strategist is NOT a function-call bot. Continuous conversational entity with personality, like a CEO-friend
- D-03: Owner provides STRATEGIST-PERSONA.md as personality/system prompt input file. Phase 6 loads it and appends project context dynamically
- D-04: Strategist designed as central strategic intelligence, extensible to marketing/financial agents later
- D-05: Three-tier escalation: PM -> Strategist -> Owner (wait indefinitely for owner)
- D-06: LOW confidence <60%, MEDIUM 60-90%, HIGH >90%
- D-07: LOW confidence escalations wait indefinitely, no timeout
- D-08: PM confidence is heuristic-based (deterministic), not AI self-assessed. Two signals: context coverage and prior decision match
- D-09: Thresholds fixed for v1: >90% HIGH, 60-90% MEDIUM, <60% LOW
- D-10: Strategist runs as persistent Claude API conversation (messages array accumulating). Opus model with 1M context
- D-11: Owner interacts in #strategist channel. Messages forwarded to persistent conversation, responses posted back
- D-12: Context limit handoff at ~800K tokens. Self-generates Knowledge Transfer document. Fresh session starts with KT as foundation
- D-13: Periodic status digests every 30 minutes (configurable). Only changes since last digest
- D-14: PM reviews plans with three checks: scope alignment, dependency readiness, duplicate detection
- D-15: HIGH confidence all-checks-pass: PM auto-approves, owner gets notification in #plan-review, owner can retroactively reject
- D-16: LOW confidence or failures: PM escalates to Strategist for judgment
- D-17: Safety table validation already handled by Phase 5 -- PM does not re-check
- D-18: All decisions posted to #decisions (append-only): timestamp, question/plan, decision, confidence, who decided
- D-19: Phase 6 builds milestone infrastructure, not policy. `vco new-milestone` accepts MILESTONE-SCOPE.md, updates project, informs Strategist
- D-20: Rename STRATEGIST-PROMPT.md to PM-CONTEXT.md. Assembled from blueprint + interfaces + scope + status + decisions
- D-21: Strategist has separate user-provided STRATEGIST-PERSONA.md

### Claude's Discretion
- PM-CONTEXT.md generation template and assembly logic
- Knowledge Transfer document format and content structure
- Status digest format (compact summary vs full diff)
- Decision log entry format in #decisions
- QuestionHandlerCog modifications to route through PM before answering
- StrategistCog expansion from placeholder to persistent conversation manager
- How PM communicates with Strategist (API call to same conversation vs separate)

### Deferred Ideas (OUT OF SCOPE)
- Strategist guiding marketing/financial agents -- future milestone
- Milestone workflow policy (what happens when milestone ends) -- evolves through use
- Configurable confidence thresholds -- fixed for v1
- DM-based private conversations with Strategist -- #strategist channel only for v1
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STRAT-01 | Strategist loads project context into system prompt | PM-CONTEXT.md generation from blueprint+interfaces+scope+status+decisions; STRATEGIST-PERSONA.md loading for Strategist tier |
| STRAT-02 | Strategist answers agent questions with confidence scoring | PM tier heuristic confidence (context coverage + prior decision match); escalation chain PM->Strategist->Owner |
| STRAT-03 | HIGH confidence (>90%) answers directly | PM auto-responds via QuestionHandlerCog intercept; note CONTEXT.md overrides REQUIREMENTS.md threshold (>90% not >70%) |
| STRAT-04 | MEDIUM confidence (60-90%) answers with override note | PM answers with "PM confidence: medium -- @Owner can override" annotation |
| STRAT-05 | LOW confidence (<60%) tags @Owner and waits | PM escalates to Strategist; Strategist escalates to Owner if <60%; indefinite wait per D-07 |
| STRAT-06 | Reviews plans against milestone scope -- rejects off-scope/duplicate/over-scoped | PM plan review intercept before PlanReviewCog posting; three-check system per D-14 |
| STRAT-07 | Checks plans against PROJECT-STATUS.md for dependency readiness | PM reads status_generator output; checks dependency phases are "complete" |
| STRAT-08 | Context management summarizes older decisions at context limits | Token counting via count_tokens(); Knowledge Transfer doc generation at ~800K; fresh session with KT |
| STRAT-09 | Decision log -- all PM decisions posted to #decisions | DecisionLogCog or method on StrategistCog; append-only embed posts |
| MILE-01 | `vco new-milestone` updates scope, resets agent states, re-dispatches | New CLI command following existing click pattern; updates MILESTONE-SCOPE.md, calls sync_context |
| MILE-02 | Three input documents define a project: BLUEPRINT, INTERFACES, MILESTONE-SCOPE | Already exists conceptually; PM-CONTEXT.md assembles from these three |
| MILE-03 | STRATEGIST-PROMPT.md generated from blueprint+interfaces+scope+status+decisions | Renamed to PM-CONTEXT.md per D-20; generation function in coordination module |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | 0.86.x | Claude API for PM and Strategist | Official Anthropic SDK. AsyncAnthropic for async Discord bot context. Already specified in CLAUDE.md. 0.86.0 confirmed on PyPI. |
| discord.py | 2.7.x | Bot framework (already installed) | Already in use for 5 Cogs. Strategist expands existing StrategistCog. |
| httpx | 0.28.x | HTTP client (anthropic dependency) | anthropic SDK uses httpx internally. Already specified in CLAUDE.md stack. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.11.x | PM confidence models, decision log entries | Already installed. Use for PMDecision, ConfidenceResult, KnowledgeTransfer models. |
| pydantic-settings | 2.13.x | ANTHROPIC_API_KEY from .env | Already installed. Add anthropic_api_key field to settings model. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-memory messages array | SQLite conversation store | Unnecessary complexity for single-machine. Messages array is simpler, and KT handoff handles context limits. |
| Heuristic confidence | LLM self-assessed confidence | D-08 explicitly locks heuristic-based (deterministic). No AI self-assessment for PM tier. |
| count_tokens() API | Approximate tiktoken counting | count_tokens() is authoritative for Anthropic models. tiktoken is for OpenAI tokenizers. |

**Installation:**
```bash
uv add "anthropic>=0.86,<1"
```

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
  bot/cogs/
    strategist.py          # Expand: StrategistCog (persistent conversation + owner channel bridge)
    question_handler.py    # Modify: add PM intercept before answer buttons
    plan_review.py         # Modify: add PM review before posting to #plan-review
  strategist/
    pm.py                  # NEW: PM tier (stateless Claude calls, heuristic confidence)
    conversation.py        # NEW: Persistent conversation manager (messages array, token tracking)
    context_builder.py     # NEW: PM-CONTEXT.md generation (assembles from project docs)
    confidence.py          # NEW: Heuristic confidence scorer (context coverage + decision match)
    decision_log.py        # NEW: Decision logging to #decisions channel
    knowledge_transfer.py  # NEW: KT document generation for context handoff
  cli/
    new_milestone_cmd.py   # NEW: vco new-milestone command
  coordination/
    sync_context.py        # MODIFY: update SYNC_FILES, add PM-CONTEXT.md generation
```

### Pattern 1: Two-Tier AI Architecture
**What:** PM tier handles questions/plans statelessly with heuristic confidence. Strategist tier maintains persistent conversation for strategic decisions and owner interaction.
**When to use:** Every agent question or plan goes through PM first. Only LOW confidence items reach Strategist.

```python
# PM Tier: stateless, fresh context per call
class PMTier:
    def __init__(self, client: AsyncAnthropic, context_path: Path):
        self._client = client
        self._context_path = context_path

    async def evaluate_question(self, question: str, agent_id: str) -> PMDecision:
        confidence = self._score_confidence(question)
        if confidence.level == "HIGH":
            answer = await self._answer_directly(question)
            return PMDecision(answer=answer, confidence=confidence, decided_by="PM")
        elif confidence.level == "MEDIUM":
            answer = await self._answer_directly(question)
            return PMDecision(answer=answer, confidence=confidence, decided_by="PM",
                            note="PM confidence: medium -- @Owner can override")
        else:
            return PMDecision(answer=None, confidence=confidence, escalate_to="strategist")
```

### Pattern 2: Persistent Conversation Manager
**What:** In-memory messages list that accumulates over time. Token counting at each addition. Auto-KT at ~800K tokens.
**When to use:** All Strategist interactions (owner messages, PM escalations, status digests).

```python
class StrategistConversation:
    def __init__(self, client: AsyncAnthropic, persona_path: Path):
        self._client = client
        self._system_prompt = persona_path.read_text()  # STRATEGIST-PERSONA.md
        self._messages: list[dict] = []
        self._total_tokens: int = 0
        self.TOKEN_LIMIT = 800_000  # trigger KT at this threshold

    async def send(self, content: str, role: str = "user") -> AsyncIterator[str]:
        self._messages.append({"role": role, "content": content})
        await self._check_token_limit()
        async with self._client.messages.stream(
            model="claude-opus-4-6",
            system=self._system_prompt,
            messages=self._messages,
            max_tokens=8192,
        ) as stream:
            full_text = ""
            async for text in stream.text_stream:
                full_text += text
                yield text
        self._messages.append({"role": "assistant", "content": full_text})

    async def _check_token_limit(self) -> None:
        result = await self._client.messages.count_tokens(
            model="claude-opus-4-6",
            system=self._system_prompt,
            messages=self._messages,
        )
        self._total_tokens = result.input_tokens
        if self._total_tokens >= self.TOKEN_LIMIT:
            await self._perform_knowledge_transfer()
```

### Pattern 3: Streaming to Discord Message Edit
**What:** Stream Strategist response chunks into a Discord message, editing in-place for perceived responsiveness.
**When to use:** All Strategist responses posted to #strategist channel.

```python
# In StrategistCog
async def _stream_to_channel(self, channel, conversation, content):
    msg = await channel.send("...")  # placeholder
    buffer = ""
    last_edit = 0
    async for chunk in conversation.send(content):
        buffer += chunk
        now = asyncio.get_event_loop().time()
        if now - last_edit > 1.0:  # rate-limit edits to 1/sec
            await msg.edit(content=buffer[:2000])  # Discord 2000 char limit
            last_edit = now
    await msg.edit(content=buffer[:2000])  # final edit
```

### Pattern 4: Heuristic Confidence Scoring
**What:** Deterministic scoring based on context coverage and prior decision match (D-08).
**When to use:** PM tier evaluates every question before answering.

```python
class ConfidenceScorer:
    def score(self, question: str, context_docs: dict[str, str],
              decision_log: list[dict]) -> ConfidenceResult:
        coverage = self._check_context_coverage(question, context_docs)
        prior_match = self._check_prior_decisions(question, decision_log)

        # Weighted combination: coverage 60%, prior match 40%
        raw_score = (coverage * 0.6) + (prior_match * 0.4)

        if raw_score > 0.9:
            level = "HIGH"
        elif raw_score >= 0.6:
            level = "MEDIUM"
        else:
            level = "LOW"

        return ConfidenceResult(score=raw_score, level=level,
                               coverage=coverage, prior_match=prior_match)
```

### Pattern 5: PM-CONTEXT.md Generation
**What:** Assemble PM context document from project sources. PM reads this fresh each call.
**When to use:** On sync-context, on new-milestone, on demand.

```python
# context_builder.py
CONTEXT_SOURCES = [
    ("PROJECT-BLUEPRINT.md", "## Project Blueprint"),
    ("INTERFACES.md", "## Interface Contracts"),
    ("MILESTONE-SCOPE.md", "## Current Milestone Scope"),
    ("PROJECT-STATUS.md", "## Project Status"),
]

def build_pm_context(project_dir: Path) -> str:
    """Assemble PM-CONTEXT.md from project documents."""
    sections = ["# PM Context -- auto-generated, do not edit\n"]
    context_dir = project_dir / "context"
    for filename, header in CONTEXT_SOURCES:
        path = context_dir / filename
        if path.exists():
            sections.append(f"\n{header}\n\n{path.read_text()}\n")
    # Append recent decisions from #decisions log
    decisions_path = project_dir / "state" / "decisions.json"
    if decisions_path.exists():
        sections.append("\n## Recent Decisions\n\n")
        # ... format recent decisions
    return "\n".join(sections)
```

### Anti-Patterns to Avoid
- **Stateful PM:** The PM tier MUST be stateless per D-01. Fresh context per call. Do not accumulate conversation history in the PM.
- **AI self-assessed confidence:** D-08 explicitly locks heuristic-based confidence. Do not ask Claude "how confident are you?"
- **Polling for owner response in a loop:** Use discord.py's `wait_for` or event-based patterns for owner replies. Do not busy-poll.
- **Raw string building for system prompts:** Use the context builder pattern. Do not inline large prompts in code.
- **Editing Discord messages too frequently:** Discord rate-limits message edits. Batch stream chunks and edit at most once per second.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token counting | Manual tokenizer / estimation | `client.messages.count_tokens()` | Anthropic's official endpoint is authoritative for their models. Training-data tokenizers may diverge. |
| Streaming response accumulation | Manual chunk concatenation | `client.messages.stream()` with `.get_final_message()` | SDK handles all SSE events, error recovery, and accumulation. |
| Discord rate limiting for edits | Custom rate limiter | Time-gated edit (1/sec) + discord.py internal rate limiting | discord.py handles API rate limits internally. Just avoid excessive edit calls. |
| JSON serialization for decisions | Custom serializer | Pydantic `.model_dump_json()` | Already using Pydantic throughout the project. Consistent serialization. |

## Common Pitfalls

### Pitfall 1: Discord Message Length Limit
**What goes wrong:** Strategist responses exceed Discord's 2000-character message limit, causing API errors.
**Why it happens:** Claude Opus responses can be very long. Streaming without truncation crashes.
**How to avoid:** Truncate at 2000 chars for single messages. For longer responses, split into multiple messages or use Discord file attachments. Implement chunking in the stream-to-Discord bridge.
**Warning signs:** `discord.errors.HTTPException: 400 Bad Request` on message send/edit.

### Pitfall 2: Token Count API Call Frequency
**What goes wrong:** Calling `count_tokens()` on every message addition is expensive (API call per message).
**Why it happens:** Naive implementation counts after every single message.
**How to avoid:** Count tokens periodically (every N messages or every 5 minutes), not on every addition. Use a rough estimate (4 chars per token) between real counts. Only call the API when the estimate approaches 700K.
**Warning signs:** High API costs, slow Strategist response times.

### Pitfall 3: Async Context in Sync Callbacks
**What goes wrong:** MonitorLoop callbacks are sync (called from `asyncio.to_thread`). Scheduling async PM/Strategist calls from sync context requires `run_coroutine_threadsafe`.
**Why it happens:** Established pattern from AlertsCog/PlanReviewCog -- but now the PM call itself is async (Anthropic API).
**How to avoid:** Follow the exact same `run_coroutine_threadsafe` pattern used by `AlertsCog.make_sync_callbacks()`. The PM evaluation must be scheduled on the bot's event loop.
**Warning signs:** `RuntimeError: no running event loop` in PM calls.

### Pitfall 4: Persistent Conversation Memory Leak
**What goes wrong:** Messages array grows unboundedly, consuming RAM until OOM.
**Why it happens:** 1M context window means messages can accumulate to hundreds of MB of text.
**How to avoid:** Implement the Knowledge Transfer handoff (D-12) properly. Monitor `_total_tokens` and trigger KT at 800K. After KT, replace messages array with KT document + fresh start.
**Warning signs:** Python process memory growing steadily over hours.

### Pitfall 5: Race Between PM Answer and Owner Override
**What goes wrong:** PM auto-approves a plan (HIGH confidence), then owner retroactively rejects it after the agent has already started executing.
**Why it happens:** D-15 allows retroactive rejection. Agent may have already committed code.
**How to avoid:** Make retroactive rejection a "pause and notify" operation, not a "rollback" operation. Agent finishes current task, then receives rejection feedback. Do not attempt git rollback.
**Warning signs:** Agent in the middle of execution when rejection arrives.

### Pitfall 6: Decision Log Channel Flooding
**What goes wrong:** #decisions channel gets flooded with entries during active development, making it unreadable.
**Why it happens:** Every question and plan review generates a decision log entry (D-18).
**How to avoid:** Use compact embed format (not full-text). Group rapid decisions (within 30s) into a single summary embed. Include only essential fields.
**Warning signs:** #decisions channel has 50+ messages per hour.

### Pitfall 7: STRATEGIST-PERSONA.md Missing at Startup
**What goes wrong:** Bot crashes on startup because STRATEGIST-PERSONA.md does not exist yet.
**Why it happens:** File is user-provided, may not be created before first bot run.
**How to avoid:** Use a sensible default persona if file is missing. Log a warning. Do not crash. Make the Strategist tier gracefully degrade to PM-only mode.
**Warning signs:** `FileNotFoundError` on bot startup.

### Pitfall 8: Concurrent Strategist Messages
**What goes wrong:** Multiple PM escalations or owner messages arrive simultaneously, interleaving in the persistent conversation.
**Why it happens:** Multiple agents may escalate questions at the same time. Owner may also be chatting.
**How to avoid:** Use an asyncio.Lock on the conversation's `send()` method. Queue messages and process them sequentially. The Strategist conversation is a shared resource.
**Warning signs:** Garbled conversation context, Strategist responding to wrong questions.

## Code Examples

### Anthropic AsyncAnthropic Streaming (verified from SDK docs)
```python
# Source: https://github.com/anthropics/anthropic-sdk-python/blob/main/helpers.md
import anthropic

client = anthropic.AsyncAnthropic()

async with client.messages.stream(
    model="claude-opus-4-6",
    max_tokens=8192,
    system="You are a strategic advisor.",
    messages=[{"role": "user", "content": "What should we prioritize?"}],
) as stream:
    async for text in stream.text_stream:
        print(text, end="", flush=True)

# Get final accumulated message
final = await stream.get_final_message()
# final.usage.input_tokens, final.usage.output_tokens available
```

### Token Counting (verified from API docs)
```python
# Source: https://platform.claude.com/docs/en/api/messages-count-tokens
result = await client.messages.count_tokens(
    model="claude-opus-4-6",
    system="System prompt here",
    messages=[
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ],
)
print(result.input_tokens)  # e.g., 42
```

### Discord Message Streaming Pattern
```python
# Rate-limited message editing for streaming
import asyncio
import time

async def stream_to_discord(channel, stream_iter):
    msg = await channel.send("Thinking...")
    buffer = ""
    last_edit = time.monotonic()
    async for chunk in stream_iter:
        buffer += chunk
        now = time.monotonic()
        if now - last_edit >= 1.0:
            display = buffer[:2000]
            try:
                await msg.edit(content=display)
            except Exception:
                pass  # rate limit or error, skip this edit
            last_edit = now
    # Final edit with complete response
    if len(buffer) <= 2000:
        await msg.edit(content=buffer)
    else:
        await msg.edit(content=buffer[:1997] + "...")
        # Post overflow as follow-up or file
        for i in range(2000, len(buffer), 2000):
            await channel.send(buffer[i:i+2000])
```

### Existing Callback Injection Pattern (from codebase)
```python
# Source: src/vcompany/bot/cogs/alerts.py make_sync_callbacks()
# Same pattern needed for PM/Strategist callbacks
def make_sync_callbacks(self) -> dict:
    loop = self.bot.loop
    def on_agent_question(agent_id: str, question: str, request_id: str) -> None:
        asyncio.run_coroutine_threadsafe(
            self.handle_agent_question(agent_id, question, request_id), loop
        )
    return {"on_agent_question": on_agent_question}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single system prompt | Separate persona + context files | D-03, D-20, D-21 | STRATEGIST-PERSONA.md (user personality) separate from PM-CONTEXT.md (project context) |
| AI self-assessed confidence | Heuristic deterministic confidence | D-08 | PM never asks Claude "how confident are you?" -- uses context coverage + decision match |
| token-counting beta header | Stable count_tokens() endpoint | SDK 0.86.x | No beta header needed -- `client.messages.count_tokens()` is stable API |
| STRATEGIST-PROMPT.md naming | PM-CONTEXT.md naming | D-20 | Rename in sync_context SYNC_FILES list; update all references |

## Open Questions

1. **PM-to-Strategist Communication Mechanism**
   - What we know: PM escalates LOW confidence items to Strategist. Strategist has a persistent conversation.
   - What's unclear: Should PM add the escalation as a user message to the Strategist conversation? Or should it be a separate API call?
   - Recommendation: Add escalation as a user message to the Strategist's persistent conversation. This gives the Strategist full context accumulation. Format: "[PM Escalation] Agent {id} asks: {question}. PM confidence: {score}. Context: {summary}."

2. **Decision Log Storage**
   - What we know: Decisions posted to #decisions channel (D-18). Also need for PM confidence scoring (prior decision match D-08).
   - What's unclear: Should decisions be stored only in Discord, or also in a local file for PM lookback?
   - Recommendation: Dual storage -- post to #decisions AND append to `state/decisions.json` (append-only JSON lines). PM reads the local file for prior decision matching. Discord is the human-readable log.

3. **Status Digest Diff Computation**
   - What we know: Digests should include "only changes since last digest" (D-13).
   - What's unclear: How to compute the diff between two PROJECT-STATUS.md snapshots.
   - Recommendation: Store the previous status text. Use simple line-by-line diff. Only include changed agent sections. If no changes, skip the digest entirely.

4. **Owner Reply Detection in #strategist**
   - What we know: Owner messages in #strategist should be forwarded to persistent conversation.
   - What's unclear: How to distinguish owner messages from bot messages and webhook messages.
   - Recommendation: Filter by: not a webhook message (`message.webhook_id is None`), not from the bot itself (`message.author.id != bot.user.id`), and author has `vco-owner` role. All qualifying messages are forwarded to the Strategist conversation.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | Yes | 3.12.3 | -- |
| uv | Package management | Yes | 0.11.1 | -- |
| anthropic SDK | PM and Strategist AI calls | No (not installed yet) | 0.86.0 (PyPI) | Install via `uv add "anthropic>=0.86,<1"` |
| pytest | Testing | Yes | 9.0.2 | -- |
| discord.py | Bot framework | Yes | Already in pyproject.toml | -- |
| ANTHROPIC_API_KEY | API authentication | Unknown | -- | Must be in .env; pydantic-settings validates on startup |

**Missing dependencies with no fallback:**
- `anthropic` SDK must be installed before any PM/Strategist code can run. First task.

**Missing dependencies with fallback:**
- `ANTHROPIC_API_KEY` env var -- bot should start without it (warn, disable PM/Strategist features) for development/testing.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STRAT-01 | PM-CONTEXT.md generation from project docs | unit | `uv run pytest tests/test_context_builder.py -x` | No -- Wave 0 |
| STRAT-02 | PM answers questions with confidence scoring | unit | `uv run pytest tests/test_pm_tier.py -x` | No -- Wave 0 |
| STRAT-03 | HIGH confidence auto-answers directly | unit | `uv run pytest tests/test_pm_tier.py::test_high_confidence -x` | No -- Wave 0 |
| STRAT-04 | MEDIUM confidence answers with override note | unit | `uv run pytest tests/test_pm_tier.py::test_medium_confidence -x` | No -- Wave 0 |
| STRAT-05 | LOW confidence escalates to Strategist/Owner | unit | `uv run pytest tests/test_pm_tier.py::test_low_confidence_escalation -x` | No -- Wave 0 |
| STRAT-06 | Plan review: scope/duplicate/over-scope checks | unit | `uv run pytest tests/test_pm_plan_review.py -x` | No -- Wave 0 |
| STRAT-07 | Plan review: dependency readiness check | unit | `uv run pytest tests/test_pm_plan_review.py::test_dependency_check -x` | No -- Wave 0 |
| STRAT-08 | Context limit detection + KT handoff | unit | `uv run pytest tests/test_conversation.py::test_knowledge_transfer -x` | No -- Wave 0 |
| STRAT-09 | Decision log posting to #decisions | unit | `uv run pytest tests/test_decision_log.py -x` | No -- Wave 0 |
| MILE-01 | vco new-milestone updates scope + resets + re-dispatches | unit | `uv run pytest tests/test_new_milestone.py -x` | No -- Wave 0 |
| MILE-02 | Three input docs define a project | unit | `uv run pytest tests/test_context_builder.py::test_three_docs -x` | No -- Wave 0 |
| MILE-03 | PM-CONTEXT.md generated from project sources | unit | `uv run pytest tests/test_context_builder.py::test_pm_context_generation -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_context_builder.py` -- covers STRAT-01, MILE-02, MILE-03
- [ ] `tests/test_pm_tier.py` -- covers STRAT-02, STRAT-03, STRAT-04, STRAT-05
- [ ] `tests/test_pm_plan_review.py` -- covers STRAT-06, STRAT-07
- [ ] `tests/test_conversation.py` -- covers STRAT-08
- [ ] `tests/test_decision_log.py` -- covers STRAT-09
- [ ] `tests/test_new_milestone.py` -- covers MILE-01
- [ ] `tests/test_strategist_cog.py` -- covers StrategistCog expansion (owner channel bridge, streaming)
- [ ] Mock fixture for `AsyncAnthropic` client -- shared across all PM/Strategist tests
- [ ] Install anthropic SDK: `uv add "anthropic>=0.86,<1"`

## Project Constraints (from CLAUDE.md)

- Use `anthropic.AsyncAnthropic` with `stream=True` per CLAUDE.md stack patterns
- discord.py message editing for streaming Strategist responses
- Use `asyncio.to_thread()` for all blocking operations
- Use `TYPE_CHECKING` imports for VcoBot in cogs
- Use `write_atomic` for coordination file writes
- Use click for CLI commands (vco new-milestone)
- Use pydantic for data models
- Use pydantic-settings for env config (ANTHROPIC_API_KEY)
- Do not use GitPython, requests, or any library on the "What NOT to Use" list
- No database -- all state in files
- subprocess for git operations, not GitPython

## Sources

### Primary (HIGH confidence)
- Anthropic Python SDK GitHub (helpers.md) -- streaming API, event types, accumulation
- Anthropic API docs (messages-count-tokens) -- token counting endpoint, parameters
- PyPI anthropic 0.86.0 -- version confirmed available
- Existing codebase -- StrategistCog placeholder, QuestionHandlerCog, PlanReviewCog, AlertsCog, MonitorLoop, sync_context

### Secondary (MEDIUM confidence)
- Anthropic SDK README -- AsyncAnthropic usage patterns
- discord.py message editing -- rate limiting behavior (1 edit/sec safe)

### Tertiary (LOW confidence)
- Opus 1M context window token counting accuracy at scale -- verified endpoint exists but no production reports on accuracy at 800K+

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- anthropic SDK version confirmed on PyPI, all other libraries already installed
- Architecture: HIGH -- two-tier pattern well-defined by CONTEXT.md decisions, existing codebase patterns clear
- Pitfalls: HIGH -- based on direct codebase analysis and established async patterns
- Token counting: MEDIUM -- API exists and is documented but behavior at 800K+ tokens is untested in this project

**Research date:** 2026-03-25
**Valid until:** 2026-04-24 (30 days -- stable domain, SDK unlikely to break)
