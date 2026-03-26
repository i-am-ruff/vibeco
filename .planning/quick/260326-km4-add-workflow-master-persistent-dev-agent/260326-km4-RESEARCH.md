# Quick Task: Add workflow-master Persistent Dev Agent - Research

**Researched:** 2026-03-26
**Domain:** Discord bot Cog extension, git worktree management, Claude CLI --resume pattern
**Confidence:** HIGH

---

## Summary

workflow-master is a second persistent agent alongside Strategist — same `StrategistConversation` plumbing, different persona, different channel, different worktree. The implementation is straightforward because the pattern is already proven: `StrategistConversation` handles `--resume` persistence, `StrategistCog` handles channel routing, and `client.py` handles initialization. This task is essentially "replicate Strategist with a developer persona and a git worktree."

The only genuinely new surface area is (1) worktree lifecycle in `vco up`, (2) the system prompt content, and (3) the graceful-restart signal path. None of these are complex.

**Primary recommendation:** Create `WorkflowMasterCog` as a new Cog (not extending StrategistCog), sharing `StrategistConversation` directly. Wire it in `client.py` alongside the existing Strategist init block.

---

## Architecture Patterns

### Component Map

```
src/vcompany/
├── strategist/
│   ├── conversation.py          # REUSE — WorkflowMasterConversation is identical
│   └── workflow_master_persona.py  # NEW — persona constant + session UUID
├── bot/
│   ├── cogs/
│   │   ├── strategist.py        # UNCHANGED
│   │   └── workflow_master.py   # NEW — WorkflowMasterCog (mirrors StrategistCog)
│   ├── channel_setup.py         # MODIFY — add "workflow-master" to _SYSTEM_CHANNELS
│   └── client.py                # MODIFY — load cog + initialize WorkflowMasterCog
└── cli/
    └── up_cmd.py                # MODIFY — add worktree create/ensure
```

### Pattern 1: Reuse StrategistConversation Directly

`StrategistConversation` is already parameterized by `session_id` and `persona_path`. workflow-master
needs its own session UUID (deterministic, separate from Strategist's) and its own persona.

```python
# workflow_master_persona.py
import uuid

_SESSION_VERSION = "vco-workflow-master-v1"
WORKFLOW_MASTER_SESSION_UUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, _SESSION_VERSION))

DEFAULT_WORKFLOW_MASTER_PERSONA = """..."""
```

Then in `WorkflowMasterCog.__init__`:

```python
from vcompany.strategist.conversation import StrategistConversation
from vcompany.strategist.workflow_master_persona import (
    WORKFLOW_MASTER_SESSION_UUID,
    DEFAULT_WORKFLOW_MASTER_PERSONA,
)

self._conversation = StrategistConversation(
    persona_path=persona_path,  # None falls back to DEFAULT_WORKFLOW_MASTER_PERSONA
    session_id=WORKFLOW_MASTER_SESSION_UUID,
)
```

This gives workflow-master a completely separate conversation history from Strategist.

### Pattern 2: WorkflowMasterCog Structure

Mirror `StrategistCog` exactly but with:
- `channel.name == "workflow-master"` filter instead of `"strategist"`
- No PM escalation methods (not needed)
- A `/wm-restart` slash command that triggers graceful bot restart
- `--allowedTools` expanded: `Bash Read Write Edit Glob Grep` (needs code editing tools)

```python
# In WorkflowMasterCog._resume_command():
return [
    "claude", "-p",
    "--output-format", "text",
    "--allowedTools", "Bash Read Write Edit Glob Grep",
    "--resume", self._session_id,
]
```

The Strategist uses `Bash Read Write`. workflow-master needs `Edit` and `Glob`/`Grep` too since it
actively edits source files.

### Pattern 3: Channel Setup

`channel_setup.py` line 24-27 defines `_SYSTEM_CHANNELS`. Add `"workflow-master"` to the list:

```python
_SYSTEM_CHANNELS: list[str] = [
    "strategist",
    "alerts",
    "readme",
    "workflow-master",   # NEW
]
```

Channel is in the `vco-system` category, same permissions as the others (owner can write, everyone
else read-only).

### Pattern 4: Git Worktree in vco up

`vco up` already creates the `vco-system` tmux session. Add worktree creation before the bot starts.

**Worktree path:** `~/vco-workflow-master-worktree` (sibling of the main repo, not inside it)

**Shell equivalent:**
```bash
git -C /path/to/vcompany worktree add ~/vco-workflow-master-worktree -b worktree/workflow-master
```

In Python (`up_cmd.py`):
```python
import subprocess
from pathlib import Path

WORKTREE_PATH = Path.home() / "vco-workflow-master-worktree"
WORKTREE_BRANCH = "worktree/workflow-master"

def _ensure_worktree(repo_root: Path) -> Path:
    """Create worktree if it doesn't exist. Idempotent."""
    if WORKTREE_PATH.exists():
        return WORKTREE_PATH  # already set up

    # Check if branch already exists (e.g., leftover from previous run)
    branch_check = subprocess.run(
        ["git", "-C", str(repo_root), "branch", "--list", WORKTREE_BRANCH],
        capture_output=True, text=True,
    )
    has_branch = bool(branch_check.stdout.strip())

    cmd = ["git", "-C", str(repo_root), "worktree", "add"]
    if not has_branch:
        cmd += ["-b", WORKTREE_BRANCH]
    cmd.append(str(WORKTREE_PATH))
    if has_branch:
        cmd.append(WORKTREE_BRANCH)

    subprocess.run(cmd, check=True)
    return WORKTREE_PATH
```

**Determining repo root from up_cmd.py:** Use `Path(__file__).parents[3]` (up from
`src/vcompany/cli/up_cmd.py` to repo root) or detect via `git rev-parse --show-toplevel`.

**Idempotency:** `if WORKTREE_PATH.exists(): return` handles restarts. No error on second call.

### Pattern 5: Persona / System Prompt Content

The persona needs to cover:

```
You are workflow-master — the self-improving development agent for vCompany.

## Your job
You develop vCompany itself. You work in a git worktree at ~/vco-workflow-master-worktree
on branch worktree/workflow-master.

## Codebase layout
- src/vcompany/ — main package (bot, cli, strategist, monitor, orchestrator, tmux, models)
- tests/ — pytest test suite (pytest-asyncio for async tests)
- pyproject.toml — uv-managed project
- CLAUDE.md — coding conventions (READ THIS FIRST for any task)

## Development workflow
1. Read CLAUDE.md at ~/vco-workflow-master-worktree/CLAUDE.md before touching code
2. Make changes in ~/vco-workflow-master-worktree/
3. Run tests: cd ~/vco-workflow-master-worktree && uv run pytest tests/ -x -q
4. Commit: git -C ~/vco-workflow-master-worktree commit -am "feat: ..."
5. Merge back to main ONLY when tests pass:
   git -C ~/vco-workflow-master-worktree checkout main
   git -C ~/vco-workflow-master-worktree merge worktree/workflow-master
   (Or via PR if the owner prefers review)

## Safety rules
- NEVER force-push to main
- NEVER skip tests before merging
- NEVER edit files outside ~/vco-workflow-master-worktree/ (your owned path)
- If unsure about a design decision, say so rather than guessing

## Bot restart
After merging changes that affect the running bot, say exactly:
  RESTART_REQUESTED
The owner will run `vco restart` to pick up changes.
```

The `RESTART_REQUESTED` sentinel approach is simpler than a programmatic restart signal.
The bot can optionally detect this string in `WorkflowMasterCog.on_message` and trigger
`asyncio.create_task(bot.close())` followed by a process restart via `os.execv`.

### Pattern 6: Graceful Bot Restart

Two options:

**Option A (simple): Sentinel detection**
- workflow-master outputs `RESTART_REQUESTED` somewhere in its response
- `WorkflowMasterCog._send_to_channel` checks response for the sentinel
- Posts a Discord message: "Restart triggered. Back in ~5s."
- Calls `os.execv(sys.executable, [sys.executable] + sys.argv)` to re-exec the bot process in-place

```python
_RESTART_SENTINEL = "RESTART_REQUESTED"

async def _send_to_channel(self, channel, content):
    response = await self._send_to_channel_base(channel, content)
    if _RESTART_SENTINEL in response:
        await channel.send("Restarting bot to pick up changes...")
        asyncio.create_task(self._do_restart())

async def _do_restart(self):
    await asyncio.sleep(1)  # let the message flush
    import os, sys
    os.execv(sys.executable, [sys.executable] + sys.argv)
```

**Option B (slash command): `/wm-restart`**
- Owner types `/wm-restart` in #workflow-master
- `WorkflowMasterCog` handles it with `os.execv` restart
- workflow-master just asks the owner to run it after merging

Option A is more autonomous (matches the feature intent). Option B is safer and avoids restart loops
if the bot crashes on startup. **Recommend Option B first** — add Option A later when the safety story
is clearer.

### Pattern 7: Wiring in client.py

Add `"vcompany.bot.cogs.workflow_master"` to `_COG_EXTENSIONS`.

In `on_ready`, after the Strategist init block:

```python
# Initialize WorkflowMaster (always available, like Strategist)
try:
    from vcompany.bot.config import BotConfig
    wm_cog = self.get_cog("WorkflowMasterCog")
    if wm_cog:
        worktree_path = Path.home() / "vco-workflow-master-worktree"
        await wm_cog.initialize(
            persona_path=None,  # uses DEFAULT_WORKFLOW_MASTER_PERSONA
            worktree_path=worktree_path,
        )
    logger.info("WorkflowMasterCog initialized")
except Exception:
    logger.exception("Failed to initialize WorkflowMasterCog")
```

The `worktree_path` is passed so the persona can be injected with the correct absolute path at
runtime (avoiding hardcoded `~` expansion issues across different users/deployments).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Persistent conversation | Custom session storage | `StrategistConversation` with different `session_id` — already works |
| Git worktree management | Custom subprocess wrappers | `git worktree add` directly via `subprocess.run` — 2 lines |
| Channel permissions | Custom Discord permission logic | Copy existing `setup_system_channels` pattern exactly |
| Process restart | Systemd unit, supervisor, watchdog | `os.execv(sys.executable, sys.argv)` — re-execs in place |

---

## Common Pitfalls

### Pitfall 1: Worktree branch conflict on restart
**What goes wrong:** `vco up` fails because `worktree/workflow-master` branch already exists (from previous run) but the worktree directory was deleted manually.
**How to avoid:** Check `WORKTREE_PATH.exists()` first. If missing but branch exists, use `git worktree add <path> <existing-branch>` (no `-b` flag).

### Pitfall 2: Session ID collision with Strategist
**What goes wrong:** workflow-master accidentally resumes the Strategist's session (or vice versa).
**How to avoid:** Use a distinct `_SESSION_VERSION` string for workflow-master's UUID (already shown above). The two UUIDs will be different by construction.

### Pitfall 3: workflow-master edits files in main checkout
**What goes wrong:** workflow-master runs `Edit` tool on `/home/developer/vcompany/src/...` (the main checkout) instead of the worktree.
**How to avoid:** Persona must explicitly state the worktree path. Inject it at runtime from `worktree_path` arg so it's an absolute path with no ambiguity.

### Pitfall 4: Restart loop
**What goes wrong:** Bot restarts, `on_ready` re-initializes WorkflowMasterCog, which resumes session, which contains `RESTART_REQUESTED` in history, triggering another restart.
**How to avoid:** The sentinel check only fires when the response to a *new* message contains it — not on session resume. The `--resume` path returns the response to the resumed message, not the full history. This is safe. But prefer Option B (slash command) for the first implementation to be certain.

### Pitfall 5: on_message fires for workflow-master's own messages
**What goes wrong:** Bot posts "Thinking..." → workflow-master's response → bot edits the "Thinking..." message. But if for any reason the response message is processed again, it creates a loop.
**How to avoid:** The `message.author.id == self.bot.user.id` filter (already in StrategistCog) catches this. Copy it exactly.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map

| Behavior | Test Type | Automated Command | File |
|----------|-----------|-------------------|------|
| WorkflowMasterConversation sends with correct session UUID | unit | `uv run pytest tests/test_workflow_master.py::test_session_uuid -x` | Wave 0 |
| WorkflowMasterCog routes #workflow-master messages only | unit | `uv run pytest tests/test_workflow_master.py::test_channel_filter -x` | Wave 0 |
| WorkflowMasterCog ignores bot's own messages | unit | `uv run pytest tests/test_workflow_master.py::test_ignores_self -x` | Wave 0 |
| _ensure_worktree is idempotent (path exists = no-op) | unit | `uv run pytest tests/test_workflow_master.py::test_worktree_idempotent -x` | Wave 0 |
| _ensure_worktree creates worktree when missing | unit (mocked subprocess) | `uv run pytest tests/test_workflow_master.py::test_worktree_create -x` | Wave 0 |
| channel_setup includes workflow-master in system channels | unit | `uv run pytest tests/test_channel_setup.py -x -k workflow` | existing file, new test |

### Wave 0 Gaps
- [ ] `tests/test_workflow_master.py` — covers all behaviors above (new file)
- [ ] New test in `tests/test_channel_setup.py` — verify `"workflow-master"` in `_SYSTEM_CHANNELS`

---

## Implementation Order

1. `src/vcompany/strategist/workflow_master_persona.py` — session UUID + persona text
2. `src/vcompany/bot/cogs/workflow_master.py` — WorkflowMasterCog (mirrors StrategistCog)
3. `src/vcompany/bot/channel_setup.py` — add "workflow-master" to `_SYSTEM_CHANNELS`
4. `src/vcompany/cli/up_cmd.py` — add `_ensure_worktree()` call before bot start
5. `src/vcompany/bot/client.py` — add cog to `_COG_EXTENSIONS`, init in `on_ready`
6. `tests/test_workflow_master.py` — test coverage

---

## Sources

### Primary (HIGH confidence)
- Codebase: `src/vcompany/strategist/conversation.py` — `StrategistConversation` pattern, `--resume` mechanics, session UUID derivation
- Codebase: `src/vcompany/bot/cogs/strategist.py` — `StrategistCog` structure to mirror
- Codebase: `src/vcompany/bot/channel_setup.py` — `_SYSTEM_CHANNELS` list, idempotent channel creation
- Codebase: `src/vcompany/bot/client.py` — Cog loading, `on_ready` init pattern, `_COG_EXTENSIONS`
- Codebase: `src/vcompany/cli/up_cmd.py` — where worktree creation fits
- Existing worktrees: `.claude/worktrees/agent-*` pattern confirms `git worktree add` is already used in this project

### Secondary (MEDIUM confidence)
- git worktree add --help: confirmed `--orphan`, `-b`, branch-without-flag syntax (HIGH, from local binary)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all code is in the repo, no new dependencies needed
- Architecture: HIGH — direct pattern replication of proven Strategist design
- Pitfalls: HIGH — derived from reading the actual code, not speculation

**Research date:** 2026-03-26
**Valid until:** 30 days (stable codebase)
