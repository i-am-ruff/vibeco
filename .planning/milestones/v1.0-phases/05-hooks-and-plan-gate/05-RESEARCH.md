# Phase 5: Hooks and Plan Gate - Research

**Researched:** 2026-03-25
**Domain:** Claude Code hook protocol, Discord bot interactive components, file-based IPC, plan gate state machine
**Confidence:** HIGH

## Summary

Phase 5 implements two major features: (1) the `ask_discord.py` hook that intercepts Claude Code's AskUserQuestion tool calls and routes questions through Discord for human answers, and (2) the full plan gate workflow in PlanReviewCog that pauses agents on plan completion, posts plans for review, and handles approve/reject flows.

The hook uses Claude Code's PreToolUse hook protocol -- it receives JSON on stdin with the question data, posts to Discord via webhook, polls a file for the answer, and returns a `deny` response with `permissionDecisionReason` carrying the answer text back to Claude. The plan gate extends existing infrastructure: MonitorLoop's `check_plan_gate` already detects new plans, AlertsCog already has `on_plan_detected` callbacks, and PlanReviewCog is an empty placeholder ready to be expanded.

**Primary recommendation:** Build the hook as a standalone Python script using only stdlib (per D-03/HOOK-06). Build the plan gate by expanding PlanReviewCog with discord.py View/Modal components following the ConfirmView pattern established in Phase 4. Track plan gate state in a per-agent field on the monitor state model.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** `ask_discord.py` posts questions to #strategist via Discord webhook (using `DISCORD_AGENT_WEBHOOK_URL` env var from Phase 2 D-04). Uses urllib from stdlib -- no external dependencies.
- **D-02:** Answer delivery uses file-based polling. Bot writes answer to a known file path (e.g., `/tmp/vco-answers/{request-id}.json`). Hook polls the file every 5s with a 10-minute timeout. Clean IPC boundary -- no shared runtime state.
- **D-03:** Hook is self-contained (HOOK-06) -- no imports from main vcompany codebase. Only uses Python stdlib (urllib, json, os, time, uuid).
- **D-04:** Phase 5 routes all questions to humans in #strategist. Phase 6's Strategist will add AI auto-answering as an intercept layer -- no integration points needed in Phase 5.
- **D-05:** Timeout behavior is configurable per project with two modes: Block mode (pauses agent) and Continue mode (falls back to recommended/first option, notes assumption, alerts #alerts).
- **D-06:** Timeout mode configured in project-level config (agents.yaml or a vco config file). Default is "continue" mode to match HOOK-04 spec.
- **D-07:** Plans posted to #plan-review as a rich embed summary (agent ID, phase, plan number, task count, goal) with the full PLAN.md content attached as a file or posted in a thread.
- **D-08:** Approve/reject via Discord button components (Approve and Reject). On reject, bot prompts for feedback text in a modal. Matches Phase 4 D-03 confirmation pattern.
- **D-09:** Rejection feedback sent as a new prompt to the agent's tmux pane via TmuxManager.send_command() (per Phase 3 D-08).
- **D-10:** Agents are monitor-commanded, not auto-advancing. GSD config template gets explicit `"auto_advance": false` in the workflow section.
- **D-11:** After planning completes, agent naturally returns to prompt and sits idle. Monitor is the gate controller -- it sends `/gsd:execute-phase {N}` only after all plans for the phase are approved.
- **D-12:** Per-phase execution trigger: monitor sends one `/gsd:execute-phase {N}` when ALL plans for a phase are approved, not per-plan.
- **D-13:** Per-agent plan gate state tracked in state file with field `plan_gate_status`. Values: `idle`, `awaiting_review`, `approved`, `rejected`.
- **D-14:** Monitor uses this state to prevent double-sending execute commands and to report status in `!status` output.
- **D-15:** Every PLAN.md must include an `## Interaction Safety` section with a markdown table using the 6 columns: Agent/Component, Circumstance, Action, Concurrent With, Safe?, Mitigation.
- **D-16:** Validation runs as part of plan gate review. When monitor detects a plan, it checks for the safety table before posting to #plan-review.
- **D-17:** Strictness is configurable per project: Warn mode (adds warning, can still approve) or Block mode (cannot approve without safety table).
- **D-18:** Default strictness is "warn" for v1.

### Claude's Discretion
- Request ID generation strategy (UUID vs sequential)
- Answer file cleanup policy (TTL, on-read deletion, periodic sweep)
- Exact embed formatting and color coding for plan review
- Plan gate state persistence format (extend existing agents.json or separate file)
- Safety table validation heuristics (regex for heading + table structure)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HOOK-01 | ask_discord.py intercepts AskUserQuestion tool calls via PreToolUse hook | Hook protocol research: PreToolUse receives JSON on stdin with `tool_name` and `tool_input`, returns deny+reason |
| HOOK-02 | Hook posts formatted question with agent ID and options to #strategist channel | Webhook POST via urllib to DISCORD_AGENT_WEBHOOK_URL with embed payload |
| HOOK-03 | Hook polls for reply every 5s with 10-minute timeout | File-based polling at `/tmp/vco-answers/{request-id}.json`, 120 iterations at 5s |
| HOOK-04 | On timeout, hook falls back to recommended/first option, notes assumption, alerts #alerts | Configurable timeout_mode (continue/block), webhook alert to #alerts on timeout |
| HOOK-05 | Hook returns deny + permissionDecisionReason carrying the answer back to Claude | JSON stdout with `hookSpecificOutput.permissionDecision: "deny"` and reason containing answer |
| HOOK-06 | Hook is self-contained (no imports from main codebase) | Only stdlib: urllib, json, os, time, uuid, sys, pathlib |
| HOOK-07 | Hook wrapped in try/except with guaranteed fallback response (never hangs) | Top-level try/except returning deny with fallback reason on any error |
| GATE-01 | Plan gate detects PLAN.md completion (atomic write marker) | Already implemented in `check_plan_gate()` using mtime comparison |
| GATE-02 | Plan gate posts plans to #plan-review with agent ID, plan descriptions, task counts | PlanReviewCog expansion with rich embed builder + file attachment |
| GATE-03 | Plan gate pauses agent execution until PM/owner approves or rejects | Agent naturally idle after planning (D-11); monitor gate state prevents execution trigger |
| GATE-04 | On rejection, agent receives feedback and re-plans | TmuxManager.send_command() sends rejection feedback to agent tmux pane |
| SAFE-01 | Every phase plan includes Interaction Safety Table | Safety table validation in plan gate before posting |
| SAFE-02 | Plan checker validates interaction safety table completeness | Regex-based validation for heading + 6-column table structure |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.12+, uv for package management
- discord.py 2.7.x for bot (no nextcord/disnake)
- No database -- all state in filesystem (YAML/Markdown/JSON)
- No GitPython -- use subprocess for git
- httpx for HTTP client in main codebase, but hook uses urllib (stdlib-only constraint)
- libtmux 0.55.x pinned tightly, single-file isolation in tmux/session.py
- Pydantic v2 for data models
- asyncio.to_thread() for all blocking operations in async context
- TYPE_CHECKING imports for VcoBot in cogs to avoid circular imports
- Atomic file writes via write_atomic() for coordination files
- ruff for linting, pytest + pytest-asyncio for testing

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.7.x | Bot views, modals, embeds, button components | Already used in Phase 4 |
| Python stdlib | 3.12 | ask_discord.py hook (urllib, json, os, time, uuid) | D-03/HOOK-06: self-contained |
| pydantic | 2.11.x | Plan gate state models | Established pattern for all models |

### Supporting (already in project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| libtmux (via TmuxManager) | 0.55.x | Send rejection feedback / execute commands to agent panes | D-09, D-11 |
| rich | 14.2.x | CLI output for plan gate status | `!status` command output |

No new dependencies needed for Phase 5.

## Architecture Patterns

### Component Layout
```
src/vcompany/
  bot/
    cogs/
      plan_review.py       # EXPAND: full plan gate Cog
      alerts.py             # MODIFY: add timeout alert method
    views/
      plan_review.py        # NEW: Approve/Reject buttons view
      reject_modal.py       # NEW: Rejection feedback modal
    embeds.py               # MODIFY: add plan review embed builder
  monitor/
    checks.py               # EXISTS: check_plan_gate already works
    loop.py                 # MODIFY: route on_plan_detected to PlanReviewCog
  models/
    monitor_state.py        # MODIFY: add plan_gate_status field
  templates/
    gsd_config.json.j2      # MODIFY: add auto_advance: false
    settings.json.j2        # EXISTS: already configured for hook
tools/
  ask_discord.py            # NEW: self-contained hook script
```

### Pattern 1: PreToolUse Hook Protocol (ask_discord.py)

**What:** Claude Code sends JSON on stdin when AskUserQuestion is called. Hook reads it, extracts questions, posts to Discord, waits for answer, returns deny + reason.

**When to use:** Every time an agent calls AskUserQuestion.

**Protocol flow:**
```
Claude Code -> stdin JSON -> ask_discord.py
  1. Parse stdin: tool_name="AskUserQuestion", tool_input.questions=[...]
  2. Generate request_id (UUID4)
  3. POST to DISCORD_AGENT_WEBHOOK_URL with formatted question embed
  4. Poll /tmp/vco-answers/{request_id}.json every 5s, up to 120 times (10 min)
  5a. Answer found -> return deny + permissionDecisionReason with answer text
  5b. Timeout -> return deny + permissionDecisionReason with fallback answer
  6. On ANY error -> return deny + permissionDecisionReason with safe fallback
```

**Input JSON (received on stdin):**
```json
{
  "session_id": "abc123",
  "hook_event_name": "PreToolUse",
  "tool_name": "AskUserQuestion",
  "tool_input": {
    "questions": [
      {
        "question": "Which database should we use?",
        "header": "Database",
        "multiSelect": false,
        "options": [
          {"label": "PostgreSQL", "description": "Relational database"},
          {"label": "MongoDB", "description": "Document store"}
        ]
      }
    ]
  }
}
```

**Output JSON (written to stdout):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Human answered via Discord: PostgreSQL - Relational database"
  }
}
```

**Confidence:** HIGH -- protocol verified from official Claude Code hooks documentation and the AskUserQuestion bug fix in v2.0.76. Current system runs v2.1.81.

### Pattern 2: Discord Webhook POST (from hook)

**What:** Hook posts question to #strategist via Discord webhook using urllib (stdlib).

**Example:**
```python
import json
import urllib.request

def post_question(webhook_url: str, agent_id: str, request_id: str, questions: list) -> None:
    embed = {
        "title": f"Question from {agent_id}",
        "description": questions[0]["question"],
        "fields": [
            {"name": opt["label"], "value": opt["description"], "inline": True}
            for opt in questions[0].get("options", [])
        ],
        "footer": {"text": f"Request: {request_id}"}
    }
    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)
```

### Pattern 3: File-Based IPC for Answer Delivery

**What:** Bot writes answer to `/tmp/vco-answers/{request_id}.json`. Hook polls for this file.

**Answer file format:**
```json
{
  "request_id": "uuid-here",
  "agent_id": "frontend",
  "answer": "PostgreSQL - Relational database",
  "answered_by": "owner#1234",
  "answered_at": "2026-03-25T12:00:00Z"
}
```

**Recommendation for Claude's discretion items:**
- **Request ID:** Use UUID4 -- collision-proof, no coordination needed between processes.
- **Cleanup policy:** Delete on read (hook deletes after consuming). Periodic sweep as backup: a cron-like check in monitor loop deletes files older than 30 minutes.
- **State persistence:** Add `plan_gate_status` field to `AgentMonitorState` in monitor_state.py rather than creating a separate file. This is consistent with the existing per-agent state pattern.

### Pattern 4: Plan Review View (discord.py Button + Modal)

**What:** Approve/Reject buttons on plan review embed. Reject triggers a Modal for feedback text.

**Example (following ConfirmView pattern from Phase 4):**
```python
class PlanReviewView(discord.ui.View):
    def __init__(self, agent_id: str, plan_path: str, *, timeout: float = 3600.0):
        super().__init__(timeout=timeout)
        self.agent_id = agent_id
        self.plan_path = plan_path
        self.result: str | None = None  # "approved" or "rejected"
        self.feedback: str = ""

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = "approved"
        await interaction.response.send_message(
            f"Plan approved for **{self.agent_id}**.", ephemeral=True
        )
        self.stop()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RejectFeedbackModal(title="Rejection Feedback")
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.result = "rejected"
        self.feedback = modal.feedback_text
        self.stop()
```

```python
class RejectFeedbackModal(discord.ui.Modal):
    feedback = discord.ui.TextInput(
        label="Why is this plan rejected?",
        style=discord.TextStyle.paragraph,
        placeholder="Describe what needs to change...",
        required=True,
        max_length=2000,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.feedback_text: str = ""

    async def on_submit(self, interaction: discord.Interaction):
        self.feedback_text = self.feedback.value
        await interaction.response.send_message("Feedback recorded.", ephemeral=True)
```

**Confidence:** HIGH -- discord.py Modal API verified from official docs. Pattern follows existing ConfirmView in `bot/views/confirm.py`.

### Pattern 5: Safety Table Validation

**What:** Regex-based check for `## Interaction Safety` heading followed by a markdown table with the required 6 columns.

**Validation heuristic:**
```python
import re

def validate_safety_table(plan_content: str) -> tuple[bool, str]:
    """Check PLAN.md for Interaction Safety section with required columns."""
    # Check heading exists
    if not re.search(r'^##\s+Interaction Safety', plan_content, re.MULTILINE):
        return False, "Missing '## Interaction Safety' section"

    # Check for table header with required columns
    required_cols = ["Agent/Component", "Circumstance", "Action", "Concurrent With", "Safe?", "Mitigation"]
    header_pattern = r'\|.*' + r'.*\|.*'.join(re.escape(c) for c in required_cols) + r'.*\|'
    if not re.search(header_pattern, plan_content, re.IGNORECASE):
        return False, "Safety table missing required columns"

    # Check for at least one data row (line with | after header + separator)
    safety_section = plan_content[plan_content.index("## Interaction Safety"):]
    table_rows = re.findall(r'^\|(?!\s*[-:]+\s*\|).+\|$', safety_section, re.MULTILINE)
    if len(table_rows) < 2:  # header + at least 1 data row
        return False, "Safety table has no data rows"

    return True, "Safety table validated"
```

### Anti-Patterns to Avoid

- **Shared memory/queue between hook and bot:** The hook runs in agent clone context (separate process tree). File-based IPC is the correct boundary.
- **Importing vcompany modules in ask_discord.py:** HOOK-06 requires complete self-containment. No imports from main codebase.
- **Using httpx in the hook:** D-03 mandates stdlib only. Use urllib.request.
- **Blocking the asyncio event loop:** Answer file writes in the bot must use `asyncio.to_thread()` for file I/O.
- **Auto-advancing agents after planning:** D-10 explicitly disables this. Agents sit idle until monitor sends execute command.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Discord button interactions | Raw message reactions | discord.ui.View + discord.ui.Button | Built-in callback routing, timeout handling, interaction validation |
| Discord modal dialogs | Multi-message Q&A flow | discord.ui.Modal + discord.ui.TextInput | Native form UX, single interaction, validated input |
| Webhook posting (in hook) | Raw socket HTTP | urllib.request | Stdlib, handles encoding/headers, timeout support |
| Atomic file writes | open() + write() | write_atomic() from shared/file_ops.py | Prevents partial reads from polling hook |
| UUID generation | Timestamp + counter | uuid.uuid4() | Collision-proof across concurrent agents |

## Common Pitfalls

### Pitfall 1: Hook Hanging on Error
**What goes wrong:** Any unhandled exception in ask_discord.py causes the hook to hang (no stdout output), which blocks Claude Code for the full 600s timeout.
**Why it happens:** Hook protocol requires JSON on stdout. No output = Claude Code waits forever.
**How to avoid:** Wrap the ENTIRE script in a top-level try/except that always outputs valid JSON with a deny + fallback reason.
**Warning signs:** Agent appears stuck but tmux pane shows no new output.

### Pitfall 2: stdin Not Fully Read
**What goes wrong:** Hook reads partial stdin or reads from wrong source, gets malformed JSON.
**Why it happens:** Hook receives JSON on stdin from Claude Code. Must read ALL of stdin before parsing.
**How to avoid:** Use `sys.stdin.read()` (not readline) to get the full JSON payload.
**Warning signs:** JSON parse errors in hook output.

### Pitfall 3: Race Between Answer Write and Poll
**What goes wrong:** Hook polls for file, finds partial content (mid-write), parses garbage JSON.
**Why it happens:** Bot writes answer file non-atomically while hook polls.
**How to avoid:** Bot must use write_atomic() (or equivalent tmp+rename pattern) for answer files. Hook should catch JSON parse errors and retry on next poll cycle.
**Warning signs:** Intermittent JSON decode errors in hook logs.

### Pitfall 4: Modal Timeout vs View Timeout
**What goes wrong:** PlanReviewView timeout (e.g., 1 hour) expires while user is typing in reject modal.
**Why it happens:** View timeout and modal interaction are independent timers.
**How to avoid:** Use long timeout for PlanReviewView (3600s or more). Modal has its own 15-minute timeout from Discord.
**Warning signs:** "Interaction failed" errors after clicking Reject.

### Pitfall 5: Double Execution After Approval
**What goes wrong:** Monitor detects same plan twice (mtime changes on git operations), sends execute command twice.
**Why it happens:** `check_plan_gate` fires on mtime changes, which can happen on git pull/merge.
**How to avoid:** D-14: plan_gate_status tracks state. Monitor only sends execute when transitioning from `approved` to `idle` (all plans approved). Never re-sends for already-approved plans.
**Warning signs:** Agent receives `/gsd:execute-phase` twice, starts executing same plan from the beginning.

### Pitfall 6: Webhook URL Not Available in Agent Clone
**What goes wrong:** ask_discord.py can't post to Discord because env var is missing in the agent's tmux pane.
**Why it happens:** Env vars set in bot process don't propagate to agent tmux panes.
**How to avoid:** The webhook URL must be set in the agent's environment during dispatch (already handled by Phase 2 dispatch which chains env vars with `&&` in send_keys).
**Warning signs:** urllib.error.URLError in hook execution.

### Pitfall 7: Plan File Read as Attachment Exceeds Discord Limits
**What goes wrong:** PLAN.md attached to Discord message exceeds 8MB file limit or embed exceeds 6000 char limit.
**Why it happens:** Large plans with many tasks and code examples.
**How to avoid:** Post plan summary in embed, full PLAN.md as file attachment. If file > 8MB (unlikely), truncate with note.
**Warning signs:** Discord API 413 errors.

## Code Examples

### Complete Hook Output (Success Case)
```python
# ask_discord.py stdout for successful answer delivery
import json
import sys

def output_deny(reason: str) -> None:
    """Write deny response to stdout and exit."""
    response = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    json.dump(response, sys.stdout)
    sys.stdout.flush()
    sys.exit(0)
```

### Complete Hook Output (Error Fallback)
```python
# Top-level error handler -- MUST be outermost try/except
try:
    main()
except Exception as exc:
    output_deny(f"Hook error (auto-fallback): {exc}. Proceeding with first available option.")
```

### Answer File Atomic Write (Bot Side)
```python
import json
import os
import tempfile
from pathlib import Path

ANSWER_DIR = Path("/tmp/vco-answers")

async def write_answer(request_id: str, answer_data: dict) -> None:
    """Write answer file atomically for hook to poll."""
    ANSWER_DIR.mkdir(parents=True, exist_ok=True)
    answer_path = ANSWER_DIR / f"{request_id}.json"
    content = json.dumps(answer_data)

    # Atomic write: tmp file then rename
    fd, tmp_path = tempfile.mkstemp(dir=ANSWER_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmp_path, answer_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

### GSD Config Template Update
```json
{
  "mode": "yolo",
  "granularity": "standard",
  "model_profile": "balanced",
  "workflow": {
    "research": true,
    "plan_check": true,
    "verifier": true,
    "nyquist_validation": true,
    "discuss_mode": "assumptions",
    "skip_discuss": false,
    "auto_advance": false
  },
  "git": {
    "branching_strategy": "milestone",
    "milestone_branch_template": "gsd/{milestone}-{slug}"
  }
}
```

### Plan Gate State Extension (AgentMonitorState)
```python
class AgentMonitorState(BaseModel):
    agent_id: str
    last_commit_time: datetime | None = None
    last_plan_mtimes: dict[str, float] = {}
    current_phase: str = "unknown"
    phase_status: str = "unknown"
    # NEW for Phase 5
    plan_gate_status: Literal["idle", "awaiting_review", "approved", "rejected"] = "idle"
    pending_plans: list[str] = []  # plan paths awaiting review
    approved_plans: list[str] = []  # plan paths approved this phase
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PreToolUse + AskUserQuestion broken | Fixed in Claude Code 2.0.76 | Jan 2026 | Hook approach is viable -- stdin/stdout conflict resolved |
| No hook for AskUserQuestion | PreToolUse matcher on "AskUserQuestion" with deny pattern | Always existed, bug-fixed Jan 2026 | Deny + permissionDecisionReason is the official mechanism |

**Deprecated/outdated:**
- Claude Code < 2.0.76: PreToolUse hooks broke AskUserQuestion responses. System runs 2.1.81 -- no issue.

## Open Questions

1. **How does the bot know which question maps to which request_id?**
   - What we know: Hook posts question to #strategist via webhook. Bot needs to know the request_id to write the answer file.
   - What's unclear: Webhook messages are "fire and forget" -- the bot receives them as regular messages, not as structured API calls.
   - Recommendation: Include the request_id in the webhook embed footer. When a user replies (or the bot provides a way to answer), the bot extracts the request_id from the original message's embed footer. Alternatively, PlanReviewCog could listen for messages in #strategist and use button components to capture answers -- buttons carry custom_id which can embed the request_id.

2. **How does the user answer a question in #strategist?**
   - What we know: Question is posted via webhook as an embed.
   - What's unclear: The answer mechanism. Webhook messages can't have interactive components (buttons/views). The bot must send a follow-up message with answer buttons.
   - Recommendation: The bot (not the webhook) should listen for webhook messages in #strategist and immediately follow up with a View containing option buttons + "Other" text input. This requires the bot to detect incoming webhook messages and react to them. Alternative: the hook could also notify the bot via a different channel (e.g., write a pending-question file that the bot monitors, then the bot posts the interactive message itself).

3. **Per-phase vs per-plan tracking granularity**
   - What we know: D-12 says execute only when ALL plans approved. D-13 says per-agent plan_gate_status.
   - What's unclear: How to track which plans within a phase are approved vs pending.
   - Recommendation: Track `pending_plans` and `approved_plans` lists in AgentMonitorState. When `pending_plans` is empty and `approved_plans` is non-empty, all plans are approved -- trigger execution.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24.x |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x --tb=short` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HOOK-01 | Hook reads stdin JSON, detects AskUserQuestion | unit | `uv run pytest tests/test_ask_discord.py::test_parse_stdin -x` | Wave 0 |
| HOOK-02 | Hook posts webhook with formatted question | unit | `uv run pytest tests/test_ask_discord.py::test_post_webhook -x` | Wave 0 |
| HOOK-03 | Hook polls answer file with 5s interval | unit | `uv run pytest tests/test_ask_discord.py::test_poll_answer -x` | Wave 0 |
| HOOK-04 | Hook falls back on timeout with alert | unit | `uv run pytest tests/test_ask_discord.py::test_timeout_fallback -x` | Wave 0 |
| HOOK-05 | Hook returns deny + reason JSON | unit | `uv run pytest tests/test_ask_discord.py::test_deny_response -x` | Wave 0 |
| HOOK-06 | Hook uses only stdlib imports | unit | `uv run pytest tests/test_ask_discord.py::test_no_external_imports -x` | Wave 0 |
| HOOK-07 | Hook never hangs on errors | unit | `uv run pytest tests/test_ask_discord.py::test_error_fallback -x` | Wave 0 |
| GATE-01 | Plan detection via mtime | unit | `uv run pytest tests/test_monitor_checks.py::test_check_plan_gate -x` | Exists |
| GATE-02 | Plan posted to #plan-review with embed | unit | `uv run pytest tests/test_plan_review_cog.py::test_post_plan -x` | Wave 0 |
| GATE-03 | Agent paused until approval | unit | `uv run pytest tests/test_plan_review_cog.py::test_gate_pauses -x` | Wave 0 |
| GATE-04 | Rejection sends feedback to tmux | unit | `uv run pytest tests/test_plan_review_cog.py::test_reject_feedback -x` | Wave 0 |
| SAFE-01 | Safety table validation passes valid plans | unit | `uv run pytest tests/test_safety_validator.py::test_valid_table -x` | Wave 0 |
| SAFE-02 | Safety table validation rejects invalid plans | unit | `uv run pytest tests/test_safety_validator.py::test_missing_table -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x --tb=short`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_ask_discord.py` -- covers HOOK-01 through HOOK-07
- [ ] `tests/test_plan_review_cog.py` -- covers GATE-02, GATE-03, GATE-04
- [ ] `tests/test_safety_validator.py` -- covers SAFE-01, SAFE-02

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Claude Code | Hook protocol | Yes | 2.1.81 | -- |
| Python 3.12 | Hook + all code | Yes | 3.12+ | -- |
| tmux | Agent pane commands | Yes | 3.4+ | -- |
| /tmp filesystem | Answer file IPC | Yes | -- | -- |
| Discord webhook URL | Hook question posting | Config-dependent | -- | Hook falls back to first option |

**Missing dependencies with no fallback:** None

**Missing dependencies with fallback:** None

## Sources

### Primary (HIGH confidence)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks) -- PreToolUse JSON protocol, exit codes, hookSpecificOutput schema
- [Claude Code Issue #13439](https://github.com/anthropics/claude-code/issues/13439) -- AskUserQuestion + PreToolUse bug, fixed in v2.0.76
- [Claude Code Issue #12605](https://github.com/anthropics/claude-code/issues/12605) -- AskUserQuestion hook feature request, documents tool_input.questions schema
- [AskUserQuestion tool schema gist](https://gist.github.com/bgauryy/0cdb9aa337d01ae5bd0c803943aa36bd) -- questions array with header, multiSelect, options structure
- discord.py source code and existing Phase 4 codebase -- View, Button, Modal patterns
- Existing codebase: `src/vcompany/bot/views/confirm.py`, `src/vcompany/bot/cogs/alerts.py`, `src/vcompany/monitor/checks.py`

### Secondary (MEDIUM confidence)
- [discord.py Modal examples](https://github.com/Rapptz/discord.py/blob/master/examples/modals/basic.py) -- Modal + TextInput pattern
- [Claude Code hooks guide](https://claudefa.st/blog/tools/hooks/hooks-guide) -- deny + permissionDecisionReason behavior

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all libraries already in project
- Architecture: HIGH -- extends existing patterns (ConfirmView, AlertsCog callbacks, CheckResult)
- Hook protocol: HIGH -- verified from official docs, bug fix confirmed in current Claude Code version
- Pitfalls: HIGH -- documented from official GitHub issues and codebase analysis

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable domain, Claude Code hook protocol unlikely to change)
