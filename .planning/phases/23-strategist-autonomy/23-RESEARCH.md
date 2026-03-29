# Phase 23: Strategist Autonomy - Research

**Researched:** 2026-03-29
**Domain:** Bot cog cleanup, persona update, action tag removal
**Confidence:** HIGH

## Summary

Phase 23 is a cleanup/simplification phase. The Strategist Claude session already has Bash tool access (`allowed_tools: "Bash Read Write"` in conversation.py line 166), and the `vco hire`, `vco give-task`, and `vco dismiss` CLI commands already exist and work via socket API (Phase 21). The work is: (1) delete the `[CMD:...]` parsing code from StrategistCog, (2) update both the STRATEGIST-PERSONA.md file and the DEFAULT_PERSONA constant in conversation.py to tell the Strategist to use `vco` CLI commands via Bash tool instead of action tags, and (3) verify the Strategist can actually run those commands.

The `_execute_actions` method in StrategistCog is dead code -- nothing calls it after the Phase 22 refactor moved conversation management to the daemon layer. The persona documents (both the file and the inline constant) still reference `[CMD:...]` syntax in the "Agent Management" section. Both need updating.

**Primary recommendation:** This is a straightforward deletion + text replacement phase. Three files change: `strategist.py` (delete ~50 lines), `STRATEGIST-PERSONA.md` (rewrite Agent Management section), `conversation.py` (update DEFAULT_PERSONA constant to match).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion -- final cleanup phase.

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STRAT-01 | Strategist calls `vco hire`, `vco give-task`, `vco dismiss` via Bash tool | Strategist already has Bash tool access. CLI commands exist from Phase 21. Persona needs updating to instruct use of CLI instead of action tags. |
| STRAT-02 | `[CMD:...]` action tag parsing removed from StrategistCog | Lines 343-393 of strategist.py contain dead code: `_CMD_PATTERN`, `_execute_actions`. Delete them. |
| STRAT-03 | Strategist persona updated to reference `vco` CLI commands instead of action tags | Two locations: STRATEGIST-PERSONA.md "Agent Management" section and DEFAULT_PERSONA constant in conversation.py. |
</phase_requirements>

## Standard Stack

No new dependencies. This phase only modifies existing files.

## Architecture Patterns

### Files to Modify

```
src/vcompany/bot/cogs/strategist.py     # Delete [CMD:...] parsing code
src/vcompany/strategist/conversation.py  # Update DEFAULT_PERSONA constant
STRATEGIST-PERSONA.md                    # Update Agent Management section
tests/test_strategist_cog.py             # Update stale tests
```

### Pattern: Persona Update for CLI Usage

The persona's "Agent Management" section currently tells the Strategist to use `[CMD:hire ...]` action tags. Replace with instructions to use Bash tool to run `vco` commands directly.

**Current persona (to replace):**
```markdown
## Agent Management

You can hire, task, and dismiss company-level agents by including action tags in your responses. The system executes these automatically.

**Hire an agent:**
`[CMD:hire <template> <agent-id>]`
...
```

**New persona pattern:**
```markdown
## Agent Management

You manage company-level agents using `vco` CLI commands through your Bash tool.

**Hire an agent:**
```bash
vco hire <template> <agent-id>
```
Templates: `researcher` (deep research with citations), `generic` (general purpose)
Example: `vco hire researcher market-analyst`

**Give a task to an existing agent:**
```bash
vco give-task <agent-id> "<task description>"
```
Example: `vco give-task market-analyst "Research AI developer tools market gaps for solo developers"`

**Dismiss an agent when done:**
```bash
vco dismiss <agent-id>
```

Hired agents get their own Discord channel (#task-{id}) for communication...
```

### Pattern: Dead Code Removal in StrategistCog

The following are safe to delete from `strategist.py`:
- `import re` (line 17) -- only used by `_CMD_PATTERN`
- `_CMD_PATTERN` class attribute (lines 345-347)
- `_execute_actions` method (lines 349-393)

Verify `re` is not used elsewhere in the file before removing the import.

### Anti-Patterns to Avoid
- **Leaving DEFAULT_PERSONA out of sync with STRATEGIST-PERSONA.md:** Both must be updated. The DEFAULT_PERSONA constant in conversation.py is the fallback when the persona file is not found. They should contain identical content.
- **Quoting issues in vco give-task:** The task description is a single argument. The persona should show quoting: `vco give-task agent-id "task description here"`. Without quotes, only the first word becomes the task.

## Don't Hand-Roll

Not applicable -- this phase is pure deletion and text editing.

## Common Pitfalls

### Pitfall 1: DEFAULT_PERSONA and STRATEGIST-PERSONA.md Drift
**What goes wrong:** One gets updated, the other doesn't. Depending on which code path runs, the Strategist gets different instructions.
**Why it happens:** Two copies of the same content in different files.
**How to avoid:** Update both in the same plan/task. Verify content matches.
**Warning signs:** Grep for `[CMD:` in the codebase after changes -- should return zero hits.

### Pitfall 2: Stale Test File
**What goes wrong:** `tests/test_strategist_cog.py` references `cog._conversation` and `cog.decision_logger` which no longer exist on StrategistCog (removed in Phase 22). Tests will fail.
**Why it happens:** Tests were not updated during Phase 22 refactor.
**How to avoid:** Update or remove tests that reference old attributes. Tests for `_execute_actions` should be deleted. Tests that mock `_conversation` need to mock `runtime_api` instead.
**Warning signs:** `pytest tests/test_strategist_cog.py` fails before any Phase 23 changes.

### Pitfall 3: vco give-task Argument Quoting
**What goes wrong:** Strategist runs `vco give-task agent Research market gaps` and only "Research" becomes the task.
**Why it happens:** Click treats each word as a separate argument. The task description must be a single quoted string.
**How to avoid:** Persona instructions must explicitly show quoting: `vco give-task agent-id "full task description here"`.
**Warning signs:** Agents receive truncated task descriptions.

### Pitfall 4: Session Version Bump
**What goes wrong:** Existing Strategist sessions still have the old persona with `[CMD:...]` instructions cached in conversation history.
**Why it happens:** Claude `--resume` reuses the full conversation history. The persona was baked into the first message.
**How to avoid:** Bump `_SESSION_VERSION` in conversation.py (currently `"vco-strategist-v10"`) to force a new session that picks up the updated persona.
**Warning signs:** Strategist still uses `[CMD:...]` tags despite code changes.

## Code Examples

### Deletion Target in strategist.py (lines 343-393)
```python
# DELETE everything below this comment in the class:

    # --- Action Tag Execution ---

    _CMD_PATTERN = re.compile(
        r"\[CMD:(hire|give-task|dismiss)\s+(.*?)\]", re.IGNORECASE
    )

    async def _execute_actions(
        self, response: str, channel: discord.TextChannel
    ) -> None:
        # ... entire method
```

### Session Version Bump in conversation.py
```python
# Change from:
_SESSION_VERSION = "vco-strategist-v10"
# To:
_SESSION_VERSION = "vco-strategist-v11"
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24.x |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_strategist_cog.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STRAT-01 | vco CLI commands work from Bash tool | manual-only | N/A -- requires live daemon + Claude session | N/A |
| STRAT-02 | [CMD:...] parsing code removed | unit | `uv run pytest tests/test_strategist_cog.py -x` | Exists but stale |
| STRAT-03 | Persona references vco CLI commands | unit (grep-based) | `grep -c '[CMD:' STRATEGIST-PERSONA.md src/vcompany/strategist/conversation.py` should return 0 | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_strategist_cog.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_strategist_cog.py` -- needs overhaul: remove tests referencing `_conversation`/`decision_logger`, remove action tag tests, update mocks to use RuntimeAPI pattern
- [ ] Verification that `[CMD:` string appears nowhere in codebase post-change

## Sources

### Primary (HIGH confidence)
- Direct code inspection of `src/vcompany/bot/cogs/strategist.py` -- confirmed dead code at lines 343-393
- Direct code inspection of `src/vcompany/strategist/conversation.py` -- confirmed `allowed_tools: "Bash Read Write"` and DEFAULT_PERSONA with [CMD:...] instructions
- Direct code inspection of `STRATEGIST-PERSONA.md` -- confirmed [CMD:...] Agent Management section
- Direct code inspection of CLI commands: `hire_cmd.py`, `give_task_cmd.py`, `dismiss_cmd.py` -- confirmed working Phase 21 implementations
- Direct code inspection of `tests/test_strategist_cog.py` -- confirmed stale tests referencing removed attributes

### Secondary (MEDIUM confidence)
- None needed -- all findings from direct code inspection

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies
- Architecture: HIGH - straightforward deletion and text replacement
- Pitfalls: HIGH - identified from direct code inspection

**Research date:** 2026-03-29
**Valid until:** Indefinite (code-only findings, no external dependencies)
