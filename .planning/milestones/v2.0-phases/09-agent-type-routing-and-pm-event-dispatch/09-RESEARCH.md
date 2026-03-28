# Phase 9: Agent Type Routing and PM Event Dispatch - Research

**Researched:** 2026-03-28
**Domain:** AgentConfig type field, container factory routing, PM event dispatch, dead code cleanup
**Confidence:** HIGH

## Summary

This phase closes 3 integration gaps and 4 tech debt items identified in the v2.0 milestone audit. The root cause of the type routing gap is simple: `AgentConfig` in `models/config.py` has no `type` field, so the `hasattr(agent_cfg, "type")` guards in `client.py:275` and `commands.py:201` always fall back to `"gsd"`. The container factory (`factory.py`) already registers all four agent types correctly -- adding the field to `AgentConfig` and removing the `hasattr` guards is all that is needed for TYPE-04 and TYPE-05.

The PM event dispatch gap (AUTO-05) requires a caller that invokes `gsd_agent.make_completion_event()` and routes the result to `bot._pm_container.post_event()`. The natural home is `WorkflowOrchestratorCog._handle_phase_complete()`, which already detects phase completion signals but currently only logs/posts to Discord. The `/new-project` command is missing PM backlog wiring that exists in `on_ready`. Dead code includes `HealthCog.setup_notifications()` (no-op), `build_status_embed` (deprecated), and the `hasattr` fallback guards.

**Primary recommendation:** Add `type` field to `AgentConfig`, replace all `hasattr` guards with direct attribute access, add event dispatch to `_handle_phase_complete`, duplicate PM wiring from `on_ready` into `/new-project`, and delete dead code.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure/gap-closure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions. Key constraints from milestone audit:
- AgentConfig needs a `type` field (Literal["gsd", "continuous", "fulltime", "company"] default "gsd")
- `hasattr(agent_cfg, "type")` guards in client.py:275 and commands.py:201 must be replaced with direct attribute access
- GsdAgent.make_completion_event() and make_failure_event() exist but need a caller
- bot._pm_container is stored but never read by any cog
- /new-project needs same BacklogQueue/ProjectStateManager wiring as on_ready
- Dead code: HealthCog.setup_notifications() no-op, build_status_embed deprecated

### Deferred Ideas (OUT OF SCOPE)
None -- gap closure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TYPE-04 | FulltimeAgent (PM) is event-driven -- reacts to agent state transitions, health changes, escalations, briefings, milestone completion | AgentConfig.type field addition + hasattr removal enables config-driven FulltimeAgent instantiation; factory.py already registers "fulltime" -> FulltimeAgent |
| TYPE-05 | CompanyAgent (Strategist) is event-driven, alive for company duration, holds cross-project state, survives project restarts | Same AgentConfig.type fix; factory.py already registers "company" -> CompanyAgent |
| AUTO-05 | Project state owned by PM -- agents read assignments and write completions. Agent crash never corrupts project state | WorkflowOrchestratorCog._handle_phase_complete must call make_completion_event() and route to PM; /new-project must wire BacklogQueue/ProjectStateManager |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.12+, pydantic v2 for all models
- discord.py 2.7.x for all bot interaction
- All state in files (YAML/Markdown) or per-agent SQLite -- no shared database
- subprocess for git (not GitPython)
- pytest + pytest-asyncio for testing
- ruff for linting
- Agent isolation: agents never share working directories
- No `hasattr` fallback guards for well-defined Pydantic model fields

## Architecture Patterns

### Change Map

```
src/vcompany/
  models/config.py          # ADD: type field to AgentConfig
  bot/client.py             # FIX: remove hasattr guards (lines 275, 278-280)
  bot/cogs/commands.py      # FIX: remove hasattr guards (lines 201, 204)
                            # ADD: PM backlog wiring in /new-project
  bot/cogs/workflow_orchestrator_cog.py  # ADD: event dispatch in _handle_phase_complete
  bot/cogs/health.py        # DELETE: setup_notifications() no-op method
  bot/embeds.py             # DELETE: build_status_embed deprecated function
```

### Pattern 1: AgentConfig.type Field

**What:** Add a `type` field to `AgentConfig` with `Literal["gsd", "continuous", "fulltime", "company"]` and default `"gsd"`.

**Why default "gsd":** Backward compatibility. Existing agents.yaml files without `type` should continue working, defaulting to GsdAgent creation. This is a Pydantic field with a default value, so it is optional in YAML but always present on the model instance.

**Example:**
```python
# models/config.py
class AgentConfig(BaseModel):
    id: str
    role: str
    owns: list[str]
    consumes: str
    gsd_mode: Literal["full", "quick"]
    system_prompt: str
    type: Literal["gsd", "continuous", "fulltime", "company"] = "gsd"
```

### Pattern 2: Direct Attribute Access (hasattr Removal)

**What:** Replace `hasattr(agent_cfg, "type")` guards with direct `agent_cfg.type` access.

**Where (exhaustive):**
1. `client.py:275` -- `agent_type=agent_cfg.type if hasattr(agent_cfg, "type") else "gsd"` becomes `agent_type=agent_cfg.type`
2. `client.py:278` -- `owned_dirs=agent_cfg.owns if hasattr(agent_cfg, "owns") else []` becomes `owned_dirs=agent_cfg.owns`
3. `client.py:279` -- `gsd_mode=agent_cfg.gsd_mode if hasattr(agent_cfg, "gsd_mode") else ""` becomes `gsd_mode=agent_cfg.gsd_mode`
4. `client.py:280` -- `system_prompt=agent_cfg.system_prompt if hasattr(agent_cfg, "system_prompt") else ""` becomes `system_prompt=agent_cfg.system_prompt`
5. `commands.py:201` -- `agent_type=agent.type if hasattr(agent, "type") else "gsd"` becomes `agent_type=agent.type`
6. `commands.py:204` -- `owned_dirs=agent.owns if hasattr(agent, "owns") else []` becomes `owned_dirs=agent.owns`

**Note:** `owns`, `gsd_mode`, and `system_prompt` are already defined fields on `AgentConfig`. The `hasattr` guards were cargo-cult safety -- Pydantic models always have their declared fields. Once `type` is added, all guards are unnecessary.

### Pattern 3: PM Event Dispatch

**What:** In `WorkflowOrchestratorCog._handle_phase_complete()`, call `gsd_agent.make_completion_event()` and route to PM via `bot._pm_container.post_event()`.

**Example:**
```python
async def _handle_phase_complete(self, agent_id: str) -> None:
    logger.info("Agent %s completed current phase", agent_id)
    await self._send_system_event(agent_id, "PHASE COMPLETE -- all stages passed")

    # Route completion event to PM (AUTO-05)
    if self.bot._pm_container is not None:
        container = await self.bot.company_root._find_container(agent_id)
        if container is not None and hasattr(container, "make_completion_event"):
            # Get the backlog item_id from agent's assignment
            assignment = await container.get_assignment()
            item_id = assignment.get("item_id", agent_id) if assignment else agent_id
            event = container.make_completion_event(item_id)
            await self.bot._pm_container.post_event(event)
            logger.info("Routed completion event for %s to PM", agent_id)
```

### Pattern 4: /new-project PM Backlog Wiring

**What:** After `add_project()` in the `/new-project` command, duplicate the PM wiring block from `on_ready`.

**Key code from on_ready (lines 290-308) to replicate:**
```python
pm_container: FulltimeAgent | None = None
for child in project_sup.children.values():
    if isinstance(child, FulltimeAgent):
        pm_container = child
        break

if pm_container is not None:
    backlog = BacklogQueue(pm_container.memory)
    await backlog.load()
    state_mgr = ProjectStateManager(backlog, pm_container.memory)
    pm_container.backlog = backlog
    pm_container._project_state = state_mgr
    self.bot._pm_container = pm_container
```

### Anti-Patterns to Avoid
- **hasattr on Pydantic models:** Pydantic v2 models always have declared fields. Using `hasattr` to check for defined fields masks schema errors.
- **Duplicated wiring without extraction:** The PM wiring code appears in both `on_ready` and `/new-project`. Consider extracting to a helper method on VcoBot, but do not over-engineer -- two call sites is acceptable.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Agent type routing | Custom type dispatch logic | Pydantic Literal type + existing ContainerFactory registry | Factory already maps type strings to classes; just need the field to carry the value |
| Event routing to PM | Custom event bus | Direct `post_event()` call on FulltimeAgent | The event queue already exists on FulltimeAgent; no middleware needed for 1 producer |

## Common Pitfalls

### Pitfall 1: Breaking Existing agents.yaml Files
**What goes wrong:** Adding a required `type` field breaks all existing agents.yaml without the field.
**Why it happens:** Pydantic requires all fields without defaults.
**How to avoid:** Use `type: Literal[...] = "gsd"` with default. All existing configs produce GsdAgent as before.
**Warning signs:** `ValidationError` on `load_config()` with existing YAML files.

### Pitfall 2: /new-project Missing add_project Return Value
**What goes wrong:** `/new-project` calls `add_project()` but does not capture the returned `ProjectSupervisor`, so PM wiring cannot iterate children.
**Why it happens:** Current code at `commands.py:208` discards the return value: `await self.bot.company_root.add_project(...)`.
**How to avoid:** Capture the return: `project_sup = await self.bot.company_root.add_project(...)` then iterate `project_sup.children`.
**Warning signs:** PM never receives events despite FulltimeAgent being in the tree.

### Pitfall 3: Circular Import from FulltimeAgent in commands.py
**What goes wrong:** Adding `from vcompany.agent.fulltime_agent import FulltimeAgent` at module level in commands.py creates import chain.
**Why it happens:** commands.py is loaded as a Cog extension; importing agent types can trigger container/supervisor imports.
**How to avoid:** Use local import inside the wiring block (same pattern as `on_ready` uses), or use `isinstance` with a late import.
**Warning signs:** `ImportError` or circular import exception at cog load time.

### Pitfall 4: setup_notifications Removal Side Effects
**What goes wrong:** `setup_notifications()` is called in the `setup()` function of health.py (line 117). Removing the method without updating `setup()` causes AttributeError.
**Why it happens:** The `setup()` function at module scope is what discord.py calls to load the Cog.
**How to avoid:** Remove both the method AND the call in `setup()`.
**Warning signs:** Cog fails to load at startup.

### Pitfall 5: Existing Test Fixtures Lack type Field
**What goes wrong:** `conftest.py:sample_agents_yaml` fixture has no `type` key. After making `type` a field, the fixture still works (default "gsd"), but tests that explicitly test type routing need new fixtures.
**Why it happens:** Fixture was written before type field existed.
**How to avoid:** Add type-specific fixtures for testing fulltime/company routing. Verify existing tests still pass with the default.
**Warning signs:** Tests pass but no coverage of non-gsd type routing.

## Code Examples

### AgentConfig with type field
```python
# src/vcompany/models/config.py
class AgentConfig(BaseModel):
    """Configuration for a single agent."""
    id: str
    role: str
    owns: list[str]
    consumes: str
    gsd_mode: Literal["full", "quick"]
    system_prompt: str
    type: Literal["gsd", "continuous", "fulltime", "company"] = "gsd"
```

### Direct attribute access (client.py)
```python
# Before (lines 273-282):
ctx = ContainerContext(
    agent_id=agent_cfg.id,
    agent_type=agent_cfg.type if hasattr(agent_cfg, "type") else "gsd",
    parent_id="project-supervisor",
    project_id=self.project_config.project,
    owned_dirs=agent_cfg.owns if hasattr(agent_cfg, "owns") else [],
    gsd_mode=agent_cfg.gsd_mode if hasattr(agent_cfg, "gsd_mode") else "",
    system_prompt=agent_cfg.system_prompt if hasattr(agent_cfg, "system_prompt") else "",
)

# After:
ctx = ContainerContext(
    agent_id=agent_cfg.id,
    agent_type=agent_cfg.type,
    parent_id="project-supervisor",
    project_id=self.project_config.project,
    owned_dirs=agent_cfg.owns,
    gsd_mode=agent_cfg.gsd_mode,
    system_prompt=agent_cfg.system_prompt,
)
```

### Dead code to remove
```python
# embeds.py: Delete build_status_embed function (lines 35-76)
# Also update module docstring (line 3) to remove "build_status_embed (for !status)"

# health.py: Delete setup_notifications method (lines 101-110)
# Also delete the call in setup() (line 117): await cog.setup_notifications()
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24.x |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TYPE-04 | AgentConfig with type="fulltime" produces FulltimeAgent via factory | unit | `uv run pytest tests/test_config.py tests/test_factory.py -x` | test_config.py exists, test_factory.py needs new tests |
| TYPE-05 | AgentConfig with type="company" produces CompanyAgent via factory | unit | `uv run pytest tests/test_config.py tests/test_factory.py -x` | test_config.py exists, test_factory.py needs new tests |
| AUTO-05 | _handle_phase_complete routes event to PM container | unit | `uv run pytest tests/test_event_dispatch.py -x` | No -- Wave 0 |
| SC-1 | AgentConfig.type field accepts all 4 values, defaults to "gsd" | unit | `uv run pytest tests/test_config.py -x` | Exists but needs new test cases |
| SC-2 | No hasattr(..., "type") guards remain in codebase | grep | `rg 'hasattr.*type' src/` returns 0 matches | N/A (manual check) |
| SC-6 | build_status_embed removed, setup_notifications removed | unit | `uv run pytest tests/ -x` (import errors caught) | Exists (regression) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_config.py` -- add tests for type field (default, all 4 values, invalid rejected)
- [ ] `tests/test_event_dispatch.py` -- covers AUTO-05 (event routing from cog to PM)
- [ ] Existing `tests/test_fulltime_agent.py` and `tests/test_company_agent.py` already cover agent behavior

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection of all affected files
- `models/config.py` -- AgentConfig has no `type` field (confirmed)
- `container/factory.py` -- all 4 types registered in `register_defaults()` (confirmed)
- `bot/client.py:275` -- `hasattr` guard confirmed
- `bot/cogs/commands.py:201` -- `hasattr` guard confirmed
- `bot/cogs/commands.py:208` -- `add_project()` return value discarded (confirmed)
- `bot/cogs/health.py:101-110` -- `setup_notifications()` no-op (confirmed: company_root is None at cog load)
- `bot/embeds.py:35-76` -- `build_status_embed` marked DEPRECATED (confirmed)
- `v2.0-MILESTONE-AUDIT.md` -- gaps documented with evidence

### Secondary (MEDIUM confidence)
- None needed -- all findings from direct code inspection

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, pure code changes to existing modules
- Architecture: HIGH - all patterns follow existing codebase conventions
- Pitfalls: HIGH - all identified from direct code inspection of exact line numbers

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable -- internal codebase changes only)
