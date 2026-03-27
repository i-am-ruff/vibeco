# Phase 9: AskUser Hook -> Agent Discord Channel + PM Mention - Research

**Researched:** 2026-03-27
**Domain:** Discord REST API, Claude Code hooks, Discord bot message routing
**Confidence:** HIGH

## Summary

Phase 9 rewrites the AskUserQuestion hook to post questions to `#agent-{id}` channels (instead of #strategist via webhook), replaces file-based IPC with Discord API reply-polling, and builds a general-purpose message routing framework for the Discord bot. The hook becomes a Discord REST API client (post question, poll for replies by message_reference), while the bot-side gains a routing dispatcher that determines which entity (PM, Strategist, Owner, agent) processes each message based on reply-target, @mention, or channel-owner defaults.

The three major work areas are: (1) hook rewrite -- `tools/ask_discord.py` switches from webhook+file-polling to bot-token REST API+reply-polling, (2) message routing framework -- a new module that all Cogs use for message dispatch, and (3) bot-side Cog rework -- QuestionHandlerCog is reworked to detect question embeds in agent channels and trigger PM evaluation, with answer delivery via Discord reply instead of file write.

**Primary recommendation:** Build the message routing framework as a standalone module (`src/vcompany/bot/routing.py`) consumed by all Cogs. Rewrite the hook to use stdlib `urllib.request` (preserving self-contained design per HOOK-06). Replace file-based IPC entirely with Discord API polling for message replies.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** All AskUserQuestion questions post to `#agent-{id}` channel (the agent's own channel). No questions go to #strategist directly.
- **D-02:** Hook uses `DISCORD_BOT_TOKEN` + `DISCORD_GUILD_ID` to resolve the `#agent-{id}` channel by name, then posts directly via Discord REST API. Aligns with VO1 direct-posting pattern.
- **D-03:** Escalation stays in `#agent-{id}`. Owner gets @mentioned there. No cross-posting to #strategist.
- **D-04:** All inter-component communication happens through Discord messages. Discord is the universal communication bus.
- **D-05:** Each entity has a visible identity prefix when speaking: `[PM]`, `[agent-frontend]`, `[agent-backend]`, etc. The Strategist is the exception -- speaks naturally with no prefix.
- **D-06:** Message routing rules (strict): Reply-based (only reply-target processes), @mention-based, channel-owner default, #strategist default.
- **D-07:** Strategist ignores messages that aren't: (a) replies to its own messages, (b) owner talking in #strategist without reply/mention, or (c) @mentions directed at it.
- **D-08:** This is a full routing framework, not Q&A-specific. All Cogs use it. Phase 9 builds it, Phase 10+ reuses it.
- **D-09:** Flow: Hook posts question as `[agent-x]` in `#agent-x` -> PM monitors for question embeds, evaluates -> Only the final answering entity replies to the original question message.
- **D-10:** PM escalation uses Pattern B (non-reply mentions). Only the resolver replies to the original question. First reply = the answer.
- **D-11:** PM replies as `[PM]` with the answer directly in Discord. No file writes.
- **D-12:** Hook posts question to Discord API, gets message ID back. Then polls Discord API for replies to that message. First reply to the question message IS the answer.
- **D-13:** No more `/tmp/vco-answers/{request-id}.json` file-based polling. Discord messages are the single source of truth.
- **D-14:** Hook remains a blocking PreToolUse hook -- intercept -> post question -> poll for reply -> return answer -> Claude continues.
- **D-15:** In-place rewrite of `tools/ask_discord.py`. Same file path keeps settings.json.j2 unchanged.
- **D-16:** Env vars change: `DISCORD_AGENT_WEBHOOK_URL` replaced by `DISCORD_BOT_TOKEN` + `DISCORD_GUILD_ID` + `VCO_AGENT_ID` (already set by dispatch).
- **D-17:** PM auto-answers: 10-minute timeout with continue/block mode from config.
- **D-18:** Owner escalations: wait indefinitely.
- **D-19:** #decisions channel logs escalated decisions only. Routine PM auto-answers stay in agent channels only.
- **D-20:** Agent channel IS the audit trail for routine Q&A.

### Claude's Discretion
- Bot-side Cog architecture for question detection and PM routing (rework QuestionHandlerCog vs absorb into PM tier)
- Hook dependency approach (stdlib-only vs httpx -- leaning stdlib to preserve self-contained design)
- Visual treatment of questions in agent channels (embeds vs plain text with prefix system)
- Poll interval and backoff strategy for Discord API reply polling
- How the routing framework is structured as a module (dispatcher class, middleware pattern, etc.)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

## Project Constraints (from CLAUDE.md)

- **Python 3.12+** runtime, **uv** for package management
- **discord.py 2.7.x** for bot framework, Cogs architecture
- **httpx** for async+sync HTTP; but hooks MUST be self-contained (HOOK-06: no imports from main codebase)
- **subprocess** over GitPython; **asyncio.to_thread()** for blocking ops in async contexts
- No database -- filesystem state only (though this phase removes the filesystem IPC!)
- **Atomic writes** pattern for any remaining file operations
- **pytest + pytest-asyncio** for testing
- GSD workflow for all changes

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.7.x | Bot Cog framework, on_message listeners, message routing | Already the project bot framework |
| urllib.request (stdlib) | N/A | Hook's Discord REST API calls | Self-contained per HOOK-06, no external deps |
| json (stdlib) | N/A | Hook stdin/stdout JSON, Discord API payloads | Already used |
| asyncio | N/A | Bot-side async message handling | Already used |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | 0.28.x | Reference pattern from report_cmd.py | NOT for hook (stdlib only); bot-side if needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| urllib.request in hook | httpx | httpx is cleaner but violates HOOK-06 self-contained requirement. Stick with urllib. |
| Embed-based questions | Plain text with prefix | Embeds are richer but harder to parse for reply detection. Use embeds for visual clarity -- the hook can parse reply content text regardless. |

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/bot/
  routing.py             # NEW: Message routing framework (D-06, D-08)
  cogs/
    question_handler.py  # REWORK: Listens in agent channels, triggers PM, posts replies
    strategist.py        # MODIFY: Uses routing framework for message filtering
    commands.py          # MINOR: Uses routing framework
tools/
  ask_discord.py         # REWRITE: Discord REST API client (post + poll replies)
```

### Pattern 1: Message Routing Framework (`routing.py`)
**What:** A module that implements D-06 routing rules as a reusable function/class consumed by all Cogs.
**When to use:** Every on_message listener calls the router to determine if the message is addressed to that Cog's entity.

```python
# Recommended structure for src/vcompany/bot/routing.py
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class RouteTarget(Enum):
    """Who should process this message."""
    STRATEGIST = "strategist"
    AGENT = "agent"
    PM = "pm"
    OWNER_UNADDRESSED = "owner_unaddressed"
    IGNORE = "ignore"

@dataclass
class RouteResult:
    target: RouteTarget
    entity_id: str | None = None  # e.g., agent ID for AGENT target
    is_reply_to: int | None = None  # message ID being replied to
    is_mention_of: str | None = None  # entity being @mentioned

def route_message(
    message,  # discord.Message
    *,
    channel_name: str,
    bot_user_id: int,
    entity_prefixes: dict[str, str],  # entity_id -> prefix like "[PM]"
) -> RouteResult:
    """Determine who should process this message per D-06 rules.

    Rules (in priority order):
    1. Reply-based: Check message.reference -> find original author entity -> route to that entity
    2. @mention-based: If message starts with @entity, route to that entity
    3. Channel-owner default: In #agent-{id}, unaddressed -> channel-owning agent
    4. #strategist default: In #strategist, unaddressed -> Strategist
    """
    ...
```

**Confidence:** HIGH -- this is a straightforward dispatch function. The routing rules are fully specified in D-06.

### Pattern 2: Hook Discord REST API Client
**What:** The rewritten hook uses stdlib urllib.request to: (1) resolve channel by name, (2) post question message, (3) poll for replies.
**When to use:** ask_discord.py hook execution.

```python
# Discord REST API pattern for hook (stdlib only)
DISCORD_API = "https://discord.com/api/v10"

def resolve_channel(bot_token: str, guild_id: str, channel_name: str) -> str | None:
    """Find channel ID by name. Returns channel_id or None."""
    url = f"{DISCORD_API}/guilds/{guild_id}/channels"
    req = urllib.request.Request(url, headers={"Authorization": f"Bot {bot_token}"})
    resp = urllib.request.urlopen(req, timeout=10)
    channels = json.loads(resp.read())
    for ch in channels:
        if ch.get("name") == channel_name:
            return ch["id"]
    return None

def post_question(bot_token: str, channel_id: str, content: str, embed: dict) -> str | None:
    """Post question to channel. Returns message_id for reply polling."""
    url = f"{DISCORD_API}/channels/{channel_id}/messages"
    payload = json.dumps({"content": content, "embeds": [embed]}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    return data.get("id")  # message ID

def poll_for_reply(bot_token: str, channel_id: str, question_msg_id: str, ...) -> str | None:
    """Poll channel messages for a reply to question_msg_id.

    Uses GET /channels/{channel_id}/messages?after={question_msg_id}&limit=10
    Checks each message's message_reference.message_id == question_msg_id
    """
    url = f"{DISCORD_API}/channels/{channel_id}/messages?after={question_msg_id}&limit=10"
    req = urllib.request.Request(url, headers={"Authorization": f"Bot {bot_token}"})
    resp = urllib.request.urlopen(req, timeout=10)
    messages = json.loads(resp.read())
    for msg in messages:
        ref = msg.get("message_reference", {})
        if ref.get("message_id") == question_msg_id:
            return msg.get("content", "")
    return None
```

**Confidence:** HIGH -- Discord REST API is well-documented. The `after` parameter + message_reference check is the correct approach.

### Pattern 3: Bot-Side Question Detection and PM Routing
**What:** QuestionHandlerCog listens for bot-posted question embeds in `#agent-*` channels, triggers PM evaluation, posts answer as reply.
**When to use:** When the hook posts a question embed to an agent channel.

The bot detects its own messages with question embeds (the hook posts using the bot token, so messages appear as from the bot). The Cog identifies these by embed structure (title pattern, footer with request ID), then triggers PM evaluation. The PM's answer (or escalation result) is posted as a reply to the original question message.

### Anti-Patterns to Avoid
- **Polling all channel messages:** Use `after={question_msg_id}` parameter to only fetch messages newer than the question. Never fetch the full channel history.
- **Writing answer files:** D-13 explicitly prohibits file-based IPC. All answers flow through Discord replies.
- **Bot responding to its own question posts:** The QuestionHandlerCog must NOT process the question message as a regular user message. Filter by checking if the message is a question embed (has specific structure) vs. a human/PM response.
- **Race between hook poll and bot answer:** The hook polls Discord API every N seconds. The bot posts a reply. There's a natural race window. Use a reasonable poll interval (5s) and always check `message_reference.message_id` to match the correct reply.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Discord channel lookup | Custom channel discovery | Reuse `_find_agent_channel` pattern from `report_cmd.py` | Already proven, handles category scoping |
| Message routing rules | Per-Cog filtering logic | Shared `routing.py` module | D-08 requires a reusable framework |
| Confidence scoring | New scoring system | Existing `PMTier.evaluate_question()` | Already built in Phase 6, proven |
| Embed parsing | Custom JSON parsing | discord.py `message.embeds[0]` access | discord.py already parses embeds |

**Key insight:** The hook-side work is mostly stdlib HTTP calls (well-understood). The bot-side work is message routing (new framework) + reworking QuestionHandlerCog (existing code to modify). Neither requires new libraries.

## Common Pitfalls

### Pitfall 1: Hook Reads VCO_AGENT_ID but Dispatch Sets AGENT_ID
**What goes wrong:** The current hook reads `VCO_AGENT_ID` (line 241 of ask_discord.py) but agent_manager.py dispatch exports `AGENT_ID` (lines 113, 179). These are different env var names.
**Why it happens:** CONTEXT.md D-16 says "VCO_AGENT_ID (already set by dispatch)" but dispatch actually sets `AGENT_ID`.
**How to avoid:** Either: (a) add `VCO_AGENT_ID` export to dispatch alongside `AGENT_ID`, or (b) change the hook to read `AGENT_ID`. Option (a) is safer -- add the export without removing the existing one, so both `report_cmd.py` (reads `AGENT_ID`) and the hook (reads `VCO_AGENT_ID`) work.
**Warning signs:** Hook falls back to "unknown-agent" and can't find the channel.

### Pitfall 2: Bot Messages Appear as Bot User (Not Agent Identity)
**What goes wrong:** The hook posts using `Bot {token}`, so the message author is the bot user, not the agent. The QuestionHandlerCog must distinguish between "bot posted a question on behalf of agent-x" vs. "bot posted a PM answer" vs. "bot posted a system message".
**Why it happens:** All messages from the hook appear as from the same bot user.
**How to avoid:** Use the `[agent-x]` prefix in message content (D-05) AND embed structure (title contains agent ID) to identify question messages. The prefix system is the authoritative identity layer.
**Warning signs:** Bot enters infinite loop processing its own question messages as needing answers.

### Pitfall 3: Discord API Rate Limits on Reply Polling
**What goes wrong:** If many agents ask questions simultaneously, the hook's polling (GET /channels/{id}/messages every 5s per agent) could hit Discord rate limits.
**Why it happens:** Discord rate limits GET /channels/{id}/messages at roughly 5 requests per 5 seconds per channel.
**How to avoid:** Use exponential backoff starting at 5s. With the `after` parameter, payloads are small. Since each agent polls its own channel, rate limits are per-channel (not global), so concurrent agents don't compound.
**Warning signs:** HTTP 429 responses from Discord API.

### Pitfall 4: First Reply Detection Ambiguity
**What goes wrong:** The "first reply = the answer" rule (D-10/D-12) could break if the bot posts a non-answer reply to the question (e.g., "Evaluating..." or an error message).
**Why it happens:** Any message with `message_reference.message_id == question_msg_id` counts as a "reply".
**How to avoid:** Bot MUST only reply to the question message with the final answer. All intermediate communication (PM evaluating, escalation notices) should be posted as non-reply messages in the channel. Use Pattern B (D-10): only the resolver replies.
**Warning signs:** Hook picks up "Evaluating your question..." as the answer.

### Pitfall 5: Hook Timeout vs Owner Indefinite Wait
**What goes wrong:** D-17 says PM auto-answers have 10-minute timeout, but D-18 says owner escalations wait indefinitely. The hook is a blocking process -- it can't wait indefinitely without being killed by the settings.json timeout (600s).
**Why it happens:** settings.json.j2 sets `"timeout": 600` for the hook command.
**How to avoid:** The hook's 10-minute polling timeout covers PM auto-answers. For owner escalation (indefinite wait), the hook must continue polling beyond 10 minutes. The settings.json timeout (600s = 10min) would kill the hook process. Either: (a) increase settings.json timeout significantly for owner escalations, or (b) have the hook detect "escalated to owner" replies and switch to a longer/infinite poll mode.
**Warning signs:** Hook process killed by timeout during owner escalation, agent gets fallback answer instead of owner's decision.

### Pitfall 6: Channel Name Resolution for Projects
**What goes wrong:** Multiple projects could have channels named `agent-frontend`. The hook must find the channel in the correct project category.
**Why it happens:** Channel names are only unique within a category, not across the guild.
**How to avoid:** Use the `PROJECT_NAME` env var (already set by dispatch) to scope channel lookup to `vco-{project_name}` category, matching the pattern in `report_cmd.py`'s `_find_agent_channel`.
**Warning signs:** Question posted to wrong project's agent channel.

## Code Examples

### Discord REST API: Post Message and Get ID (stdlib)
```python
# Source: Discord API docs + report_cmd.py pattern
import json
import urllib.request

DISCORD_API = "https://discord.com/api/v10"

def post_message(bot_token: str, channel_id: str, content: str, embeds: list | None = None) -> str | None:
    """Post a message and return its ID for reply tracking."""
    url = f"{DISCORD_API}/channels/{channel_id}/messages"
    payload: dict = {"content": content}
    if embeds:
        payload["embeds"] = embeds
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        },
    )
    resp = urllib.request.urlopen(req, timeout=10)
    msg = json.loads(resp.read())
    return msg.get("id")
```

### Discord REST API: Poll for Replies (stdlib)
```python
# Source: Discord API docs (GET /channels/{channel_id}/messages)
def poll_for_reply(
    bot_token: str,
    channel_id: str,
    question_msg_id: str,
    poll_interval: int = 5,
    max_polls: int = 120,
) -> str | None:
    """Poll for a reply to the question message. Returns answer text or None."""
    url = f"{DISCORD_API}/channels/{channel_id}/messages?after={question_msg_id}&limit=10"
    headers = {"Authorization": f"Bot {bot_token}"}

    for _ in range(max_polls):
        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=10)
            messages = json.loads(resp.read())
            for msg in messages:
                ref = msg.get("message_reference", {})
                if ref.get("message_id") == question_msg_id:
                    return msg.get("content", "")
        except Exception:
            pass  # Retry on any error
        time.sleep(poll_interval)
    return None
```

### Bot-Side: Reply to Original Question Message
```python
# Source: discord.py API -- message.reply() creates a message_reference
async def answer_question(channel: discord.TextChannel, question_msg_id: int, answer: str, entity_prefix: str):
    """Post an answer as a reply to the original question."""
    question_msg = await channel.fetch_message(question_msg_id)
    await question_msg.reply(f"{entity_prefix} {answer}")
```

### Routing Framework Usage in Cog
```python
# How a Cog uses the routing framework
from vcompany.bot.routing import route_message, RouteTarget

class SomeCog(commands.Cog):
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        route = route_message(message, channel_name=message.channel.name, ...)
        if route.target != RouteTarget.MY_ENTITY:
            return  # Not for me
        # Process the message
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Webhook + file IPC (Phase 5) | Bot token REST API + Discord reply IPC (Phase 9) | Phase 9 | Hook becomes Discord-native; eliminates /tmp/vco-answers entirely |
| All questions to #strategist | Questions to #agent-{id} channels | Phase 9 | Better audit trail, per-agent conversation context |
| Per-Cog message filtering | Shared routing framework | Phase 9 | Consistent message routing across all Cogs, D-06 rules enforced centrally |
| Button UI for answers (AnswerView) | PM auto-answer via reply | Phase 9 | Automated Q&A flow; buttons become fallback only |

**Deprecated/outdated:**
- `AnswerView` button UI: Replaced by PM auto-answer flow. May keep as fallback for cases where PM/Strategist are unavailable, but primary flow is automated replies.
- File-based IPC (`/tmp/vco-answers/`): Completely removed per D-13.
- `DISCORD_AGENT_WEBHOOK_URL` env var: Replaced by `DISCORD_BOT_TOKEN` + `DISCORD_GUILD_ID` (already done in dispatch by VO1 task, but hook still reads it).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml |
| Quick run command | `uv run python -m pytest tests/test_ask_discord.py tests/test_question_handler.py -x -v` |
| Full suite command | `uv run python -m pytest tests/ -x -v` |

### Phase Requirements -> Test Map

Since this phase was added after initial requirements (TBD requirement IDs), mapping to CONTEXT.md decisions:

| Decision | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|-------------|
| D-01/D-02 | Hook posts to #agent-{id} via REST API | unit | `uv run python -m pytest tests/test_ask_discord.py -x` | Needs rewrite |
| D-12 | Hook polls Discord API for replies | unit | `uv run python -m pytest tests/test_ask_discord.py -x` | Needs rewrite |
| D-06 | Routing framework dispatches correctly | unit | `uv run python -m pytest tests/test_routing.py -x` | New file |
| D-09/D-10 | PM auto-answers as reply, escalation as non-reply | unit | `uv run python -m pytest tests/test_question_handler.py -x` | Needs rewrite |
| D-13 | No file-based IPC remains | unit | `grep -r "vco-answers" tools/ src/ tests/` | Verification |

### Sampling Rate
- **Per task commit:** `uv run python -m pytest tests/test_ask_discord.py tests/test_routing.py tests/test_question_handler.py -x -v`
- **Per wave merge:** `uv run python -m pytest tests/ -x -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_routing.py` -- covers routing framework (D-06 rules)
- [ ] `tests/test_ask_discord.py` -- needs complete rewrite for new Discord REST API approach
- [ ] `tests/test_question_handler.py` -- needs rewrite for agent-channel-based flow

## Open Questions

1. **Settings.json timeout vs owner indefinite wait**
   - What we know: settings.json.j2 sets `"timeout": 600` (10 minutes). D-18 says owner escalations wait indefinitely.
   - What's unclear: Does Claude Code kill the hook process after 600s? If so, the hook can't wait indefinitely for owner responses.
   - Recommendation: Increase timeout in settings.json to a very high value (e.g., 86400s = 24h) to effectively support indefinite wait. The hook's own internal timeout logic handles the 10-minute PM case; the settings.json timeout is just a safety net.

2. **Bot detecting its own question messages**
   - What we know: Hook posts using bot token, so messages come from bot user. Bot needs to distinguish "question from agent" vs. "answer from PM" vs. "system message".
   - What's unclear: Exact filtering logic to avoid processing loops.
   - Recommendation: Use embed structure (title pattern "Question from {agent}") as the signal. Messages with this embed pattern trigger PM evaluation. All other bot messages are ignored by QuestionHandlerCog.

3. **Existing QuestionHandlerCog: rework vs replace**
   - What we know: Current Cog is tightly coupled to webhook messages in #strategist and file-based IPC.
   - What's unclear: How much of the existing code is salvageable.
   - Recommendation: In-place rewrite of QuestionHandlerCog. Keep the class name and Cog registration. Gut the internals: remove AnswerView, remove file writes, add agent-channel listening and reply-based answer delivery.

## Sources

### Primary (HIGH confidence)
- Discord REST API docs (https://docs.discord.com/developers/resources/message) -- message_reference field structure, GET /channels/{id}/messages parameters (after, limit)
- Existing codebase: `tools/ask_discord.py`, `src/vcompany/bot/cogs/question_handler.py`, `src/vcompany/bot/cogs/strategist.py`, `src/vcompany/cli/report_cmd.py` (VO1 direct posting pattern)

### Secondary (MEDIUM confidence)
- Discord API rate limits for channel message endpoints (~5 req/5s per channel) -- based on community documentation and developer experience

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, no new dependencies
- Architecture: HIGH -- routing framework is well-specified by D-06, Discord API endpoints verified
- Pitfalls: HIGH -- identified from code analysis (env var mismatch, bot self-detection, rate limits, timeout conflict)

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable domain, Discord API versioned)
