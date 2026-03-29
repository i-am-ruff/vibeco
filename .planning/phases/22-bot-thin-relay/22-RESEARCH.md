# Phase 22: Bot Thin Relay - Research

**Researched:** 2026-03-29
**Domain:** Discord bot cog refactoring -- import boundary enforcement and event relay
**Confidence:** HIGH

## Summary

Phase 22 completes the bot-as-thin-relay architecture by eliminating all remaining prohibited imports from cog modules and wiring daemon event subscription for Discord formatting. The codebase is already 60-70% there: Phase 20 established the RuntimeAPI pattern, StrategistCog already routes through RuntimeAPI, AlertsCog is clean, and the import boundary test exists but covers only 4 of 9 cog files.

The primary work is: (1) rewriting slash commands in CommandsCog to delegate to RuntimeAPI instead of accessing CompanyRoot directly, (2) rewiring ChannelRelayCog (task_relay.py) to use CommunicationPort instead of container._pane_id and TmuxManager, (3) cleaning up HealthCog, PlanReviewCog, WorkflowOrchestratorCog, and StrategistCog to remove direct container/supervisor access, and (4) extending test_import_boundary.py to cover all 9 cog files.

**Primary recommendation:** Work file-by-file through each cog, replacing direct CompanyRoot/container access with RuntimeAPI method calls. Add new RuntimeAPI methods as needed (dispatch, kill, relaunch, relay_channel_message). The existing pattern from Phase 20 (StrategistCog using `runtime_api.relay_strategist_message()`) is the template for all remaining cogs.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion (infrastructure refactoring phase).

### Claude's Discretion
All implementation choices are at Claude's discretion. Key patterns:
- Phase 20 already gutted on_ready and rewired CommandsCog/StrategistCog/PlanReviewCog through RuntimeAPI
- Phase 21 added CLI equivalents for all management commands
- This phase completes the remaining cog cleanup and adds event formatting + message relay
- test_import_boundary.py already exists with PROHIBITED_PREFIXES -- extend coverage to all cog modules

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BOT-01 | All slash commands (/new-project, /dispatch, /kill, /relaunch, /health) call RuntimeAPI | Audit found 5 commands still accessing CompanyRoot directly via `_get_company_root()`. RuntimeAPI needs dispatch/kill/relaunch/remove_project methods. |
| BOT-02 | No container module imports in bot cogs | Audit found violations in 7 of 9 cog files. Module-level and function-level imports both need cleanup. |
| BOT-03 | Bot implements DiscordCommunicationPort and registers with daemon on startup | Already done in client.py on_ready. This requirement is about daemon->bot event formatting (health changes, agent transitions as embeds/threads/reactions). |
| BOT-04 | Bot cogs are pure I/O adapters: Discord events -> daemon, daemon events -> Discord formatting | StrategistCog partially done. CommandsCog, HealthCog, WorkflowOrchestratorCog, PlanReviewCog, ChannelRelayCog still access containers directly. |
| BOT-05 | Message relay handlers (on_message for agent/task channels) convert to generic messages and send to daemon | ChannelRelayCog currently accesses container._pane_id and TmuxManager directly. Needs to route through RuntimeAPI/CommunicationPort. |
</phase_requirements>

## Standard Stack

No new libraries needed. This phase uses only existing project dependencies:

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.7.x | Bot framework, cog system | Already in project |
| pydantic | 2.11.x | Payload models for CommunicationPort | Already in project |

This is a pure refactoring phase -- no new dependencies.

## Architecture Patterns

### The RuntimeAPI Gateway Pattern (established Phase 20)

Every cog accesses business logic exclusively through `self.bot._daemon.runtime_api`. The pattern:

```python
# In cog method:
runtime_api = _get_runtime_api(self.bot)
if runtime_api is None:
    await interaction.response.send_message("Daemon not ready.", ephemeral=True)
    return
result = await runtime_api.some_method(args)
# Format result as Discord embed/message
```

RuntimeAPI methods that exist:
- `hire()`, `give_task()`, `dismiss()` -- agent lifecycle
- `status()`, `health_tree()` -- read-only queries
- `new_project()` -- project initialization
- `relay_strategist_message()` -- inbound strategist messages
- `handle_plan_approval()`, `handle_plan_rejection()` -- plan gate

RuntimeAPI methods that need to be **added** for Phase 22:
- `dispatch(agent_id)` -- dispatch/restart agent
- `kill(agent_id)` -- stop agent with confirmation already handled by cog
- `relaunch(agent_id)` -- stop agent for supervisor restart
- `remove_project(name)` -- tear down project
- `relay_channel_message(agent_id, content, channel_type)` -- BOT-05 message relay
- `get_agent_states()` -- for /dispatch "all" listing

### Event Flow: Daemon -> Bot (BOT-03)

The daemon emits events via CommunicationPort (already implemented). The bot receives them through DiscordCommunicationPort (already implemented in comm_adapter.py). The remaining work is formatting: daemon sends generic payloads, bot formats as Discord embeds/threads/reactions.

Current `send_embed` support in CommunicationPort:
```python
class SendEmbedPayload(BaseModel):
    channel_id: str
    title: str
    description: str = ""
    color: int | None = None
    fields: list[EmbedField] = Field(default_factory=list)
```

This already supports rich embed formatting from the daemon side.

### Message Relay: Discord -> Daemon (BOT-05)

Current ChannelRelayCog pattern (WRONG -- accesses containers directly):
```python
container = self._find_container(agent_id)  # accesses company_root
pane_id = container._pane_id  # accesses container internals
tmux.send_command(pane_id, content)  # accesses TmuxManager
```

Target pattern:
```python
runtime_api = _get_runtime_api(self.bot)
await runtime_api.relay_channel_message(agent_id, content, "agent")
```

### Anti-Patterns to Avoid
- **Direct CompanyRoot access from cogs:** Use `_get_runtime_api()` helper, never `_get_company_root()`
- **Function-level lazy imports of prohibited modules:** While technically passing module-level import tests, function-level imports of `vcompany.tmux.session`, `vcompany.models.agent_state`, `vcompany.agent.gsd_agent` in cogs must be eliminated
- **`bot.company_root` attribute access:** Multiple cogs use `self.bot.company_root` -- this attribute should not exist on VcoBot

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Message relay to agents | Custom container lookup + tmux pane send in each cog | RuntimeAPI.relay_channel_message() | Centralizes container lookup, pane resolution, and tmux management in daemon |
| Health tree rendering | Direct CompanyRoot.health_tree() call from cog | RuntimeAPI.health_tree() (already exists) | Already returns serialized dict, no container imports needed |
| Agent lifecycle from slash commands | _get_company_root() + direct container manipulation | RuntimeAPI.dispatch/kill/relaunch methods | Matches CLI pattern from Phase 21 |

## Common Pitfalls

### Pitfall 1: Incomplete Import Cleanup
**What goes wrong:** Module-level imports are cleaned but function-level lazy imports remain (e.g., `from vcompany.tmux.session import TmuxManager` inside `_send_tmux_command`).
**Why it happens:** test_import_boundary.py currently only checks module-level imports.
**How to avoid:** Extend test to check ALL imports (not just module-level), or at minimum add all cog files to BOT_FILES list and add all prohibited prefixes.
**Warning signs:** Grep for `from vcompany.` inside function bodies in cog files.

### Pitfall 2: Missing RuntimeAPI Methods
**What goes wrong:** Cog is rewritten to call RuntimeAPI method that doesn't exist yet.
**Why it happens:** Rewriting cogs and adding RuntimeAPI methods happen in parallel.
**How to avoid:** Add RuntimeAPI methods FIRST in the same task, then rewrite the cog to use them.
**Warning signs:** AttributeError at runtime when slash command is invoked.

### Pitfall 3: StrategistCog Still Has CompanyAgent Reference
**What goes wrong:** StrategistCog has `_company_agent: CompanyAgent` attribute and `set_company_agent()` method, plus direct `CompanyAgent.post_event()` calls in fallback paths.
**Why it happens:** Phase 20 added RuntimeAPI path but kept backward-compat fallback.
**How to avoid:** Remove the fallback path entirely -- RuntimeAPI is now the only path.
**Warning signs:** `from vcompany.agent.company_agent import CompanyAgent` in TYPE_CHECKING block.

### Pitfall 4: WorkflowOrchestratorCog Deeply Coupled
**What goes wrong:** WorkflowOrchestratorCog accesses `self.bot.company_root._find_container()` in 4 places and calls container methods directly.
**Why it happens:** MIGR-01 adapted this cog to use CompanyRoot but didn't go through RuntimeAPI.
**How to avoid:** Add stage-signal handling to RuntimeAPI, or convert WorkflowOrchestratorCog to be a pure Discord event formatter that delegates all container interaction to RuntimeAPI.
**Warning signs:** Any `_find_container` call in a cog file.

### Pitfall 5: PlanReviewCog Has Mixed Concerns
**What goes wrong:** PlanReviewCog uses `self.bot.company_root._find_container()` in `_handle_review_response()` to resolve GsdAgent gate futures directly.
**Why it happens:** The review response flow was wired before RuntimeAPI existed.
**How to avoid:** Add `resolve_review()` to RuntimeAPI and route through it.
**Warning signs:** `from vcompany.agent.gsd_agent import GsdAgent` lazy import.

## Detailed Import Violation Audit

### Module-Level Violations (in non-TYPE_CHECKING scope)

| File | Import | Replacement Strategy |
|------|--------|---------------------|
| commands.py | `from vcompany.communication.checkin import gather_checkin_data` | Move checkin logic to RuntimeAPI |
| commands.py | `from vcompany.communication.standup import StandupSession` | Move standup logic to RuntimeAPI |
| commands.py | `from vcompany.integration.pipeline import IntegrationPipeline` | Move integration to RuntimeAPI |
| health.py | `from vcompany.resilience.message_queue import MessagePriority, QueuedMessage` | Use CommunicationPort send_message |
| plan_review.py | `from vcompany.monitor.safety_validator import validate_safety_table` | Move to RuntimeAPI or keep as utility (no container deps) |
| strategist.py | `from vcompany.strategist.conversation import StrategistConversation` | Remove -- conversation is in daemon now |
| strategist.py | `from vcompany.strategist.decision_log import DecisionLogger` | Remove -- decision logging is in daemon now |
| workflow_master.py | `from vcompany.strategist.conversation import StrategistConversation` | Keep or move -- WorkflowMaster may need separate treatment |
| workflow_orchestrator_cog.py | `from vcompany.shared.workflow_types import ...` | Keep -- shared utilities are not prohibited |

### Function-Level Violations (lazy imports inside methods)

| File | Method | Import | Replacement Strategy |
|------|--------|--------|---------------------|
| commands.py | new_project | `from vcompany.shared.paths`, `vcompany.models.config`, `vcompany.shared.file_ops`, `vcompany.shared.templates` | Move project init to RuntimeAPI.new_project() |
| commands.py | new_project | `from vcompany.cli.clone_cmd`, `vcompany.git` | Move clone logic to RuntimeAPI |
| commands.py | _on_checkin | `from vcompany.communication.checkin` | Move to RuntimeAPI |
| commands.py | remove_project | `from vcompany.tmux.session` | Move tmux kill to RuntimeAPI.remove_project() |
| commands.py | remove_project | `from vcompany.shared.paths` | Move to RuntimeAPI |
| plan_review.py | _verify_agent_execution | `from vcompany.git import ops` | Move to RuntimeAPI |
| plan_review.py | _send_tmux_command | `from vcompany.models.agent_state`, `vcompany.tmux.session` | Move to RuntimeAPI |
| plan_review.py | _log_plan_decision | `from vcompany.strategist.models` | Move to RuntimeAPI |
| plan_review.py | _handle_review_response | `from vcompany.agent.gsd_agent` | Move to RuntimeAPI.resolve_review() |
| task_relay.py | _relay_to_pane | `from vcompany.tmux.session` | Use RuntimeAPI.relay_channel_message() |

### Direct CompanyRoot/Container Access (via getattr/attribute)

| File | Access Pattern | Replacement |
|------|---------------|-------------|
| commands.py | `_get_company_root(bot)` -> `company_root.projects`, `_find_container()`, `container.stop()` | RuntimeAPI.dispatch(), kill(), relaunch() |
| health.py | `getattr(self.bot, "company_root")` -> `company_root.health_tree()` | RuntimeAPI.health_tree() (already exists) |
| task_relay.py | `self.bot.company_root._company_agents`, `._projects`, `container._pane_id` | RuntimeAPI.relay_channel_message() |
| workflow_orchestrator_cog.py | `self.bot.company_root._find_container()` in 4 places | RuntimeAPI methods |
| plan_review.py | `self.bot.company_root._find_container()` | RuntimeAPI.resolve_review() |

## Code Examples

### Pattern: Slash Command via RuntimeAPI

```python
# BEFORE (commands.py /kill):
company_root = _get_company_root(self.bot)
container = await company_root._find_container(agent_id)
await container.stop()

# AFTER:
runtime_api = _get_runtime_api(self.bot)
if runtime_api is None:
    await interaction.response.send_message("Daemon not ready.", ephemeral=True)
    return
await runtime_api.kill(agent_id)
await interaction.followup.send(f"Agent **{agent_id}** stopped.")
```

### Pattern: Message Relay via RuntimeAPI

```python
# BEFORE (task_relay.py):
container = self._find_container(agent_id)
pane_id = container._pane_id
tmux = TmuxManager()
tmux.send_command(pane_id, content)

# AFTER:
runtime_api = _get_runtime_api(self.bot)
if runtime_api is not None:
    await runtime_api.relay_channel_message(agent_id, content)
```

### Pattern: New RuntimeAPI Method

```python
# In runtime_api.py:
async def kill(self, agent_id: str) -> None:
    """Stop an agent container."""
    container = await self._root._find_container(agent_id)
    if container is None:
        raise KeyError(f"Agent {agent_id!r} not found")
    await container.stop()

async def relay_channel_message(self, agent_id: str, content: str) -> bool:
    """Relay a message to an agent's tmux pane."""
    container = await self._root._find_container(agent_id)
    if container is None:
        return False
    pane_id = getattr(container, '_pane_id', None)
    if pane_id is None:
        return False
    # Container handles tmux send internally
    from vcompany.tmux.session import TmuxManager
    tmux = TmuxManager()
    return tmux.send_command(pane_id, content)
```

## Scope Boundary Decision

### What IS a prohibited import

Per BOT-02, these module prefixes are prohibited in cog files:
- `vcompany.container.*`
- `vcompany.supervisor.*`
- `vcompany.agent.*`

### What MIGHT be acceptable (needs decision)

Some imports don't touch container/supervisor/agent internals:
- `vcompany.shared.*` (paths, templates, workflow_types) -- pure utilities
- `vcompany.models.*` (config, agent_state) -- data models only
- `vcompany.monitor.safety_validator` -- stateless validation function
- `vcompany.strategist.*` -- conversation, decision_log (these ARE daemon-layer now)
- `vcompany.communication.*` -- checkin, standup (these are domain logic)
- `vcompany.integration.*` -- pipeline (this is domain logic)
- `vcompany.tmux.*` -- session management (this is infrastructure)
- `vcompany.resilience.*` -- message queue (this is infrastructure)

**Recommendation:** The strict interpretation for BOT-02 is: cogs should ONLY import from `vcompany.bot.*`, `vcompany.daemon.comm` (payloads), and stdlib. Everything else goes through RuntimeAPI. The current PROHIBITED_PREFIXES list should be expanded to include `vcompany.tmux`, `vcompany.resilience`, `vcompany.strategist`, `vcompany.communication`, `vcompany.integration`, `vcompany.models`, `vcompany.git`, and `vcompany.cli`. Keep `vcompany.shared` as allowed (pure utilities with no side effects).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | pyproject.toml |
| Quick run command | `cd /home/developer/vcompany && python -m pytest tests/test_import_boundary.py -x` |
| Full suite command | `cd /home/developer/vcompany && python -m pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BOT-01 | All slash commands call RuntimeAPI | unit (import boundary) | `pytest tests/test_import_boundary.py -x` | Partial (only 4 files checked) |
| BOT-02 | No container module imports in bot cogs | unit (import boundary) | `pytest tests/test_import_boundary.py -x` | Partial (PROHIBITED_PREFIXES incomplete) |
| BOT-03 | Bot registers DiscordCommunicationPort with daemon | smoke | Manual -- verify on_ready logs "CommunicationPort registered" | N/A |
| BOT-04 | Cogs are pure I/O adapters | unit (import boundary) | `pytest tests/test_import_boundary.py -x` | Partial |
| BOT-05 | Message relay via CommunicationPort/daemon | unit (import boundary) | `pytest tests/test_import_boundary.py -x` | Partial |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_import_boundary.py -x`
- **Per wave merge:** `python -m pytest tests/ -x`
- **Phase gate:** Full suite green before /gsd:verify-work

### Wave 0 Gaps
- [ ] Extend `tests/test_import_boundary.py` BOT_FILES to include ALL 9 cog files (currently only 4)
- [ ] Extend PROHIBITED_PREFIXES to include `vcompany.tmux`, `vcompany.resilience`, `vcompany.strategist`, `vcompany.communication`, `vcompany.integration`, `vcompany.models.agent_state`, `vcompany.git`, `vcompany.cli`, `vcompany.monitor`
- [ ] Add test for function-level imports (not just module-level) -- or decide that all function-level imports in cogs should also be prohibited
- [ ] Add test that `bot.company_root` attribute is not accessed from any cog file

## File-by-File Work Summary

Priority order (most violations first):

1. **commands.py** -- Heaviest: 3 module-level violations, 8+ function-level violations, `_get_company_root()` used by 4 commands. /new-project has the most logic to move.
2. **workflow_orchestrator_cog.py** -- 4 direct `company_root._find_container()` calls, PM container access.
3. **plan_review.py** -- 1 module-level, 4 function-level violations, `company_root._find_container()` in review response handler.
4. **task_relay.py** -- 1 function-level violation, direct container._pane_id access.
5. **health.py** -- 1 module-level violation (message_queue), direct company_root.health_tree() call.
6. **strategist.py** -- 2 module-level violations (conversation, decision_log), CompanyAgent reference (backward compat to remove).
7. **workflow_master.py** -- 1 module-level violation (conversation). May keep if WorkflowMaster stays bot-local.
8. **question_handler.py** -- 1 function-level violation (strategist.models). Mostly clean.
9. **alerts.py** -- Clean. No changes needed.

## Sources

### Primary (HIGH confidence)
- Direct codebase audit of all 9 cog files in `src/vcompany/bot/cogs/`
- Direct audit of `src/vcompany/daemon/runtime_api.py` for existing methods
- Direct audit of `src/vcompany/daemon/comm.py` for CommunicationPort protocol
- Direct audit of `tests/test_import_boundary.py` for current test coverage

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, pure refactoring
- Architecture: HIGH - RuntimeAPI pattern established in Phase 20, just extending it
- Pitfalls: HIGH - comprehensive codebase audit identifies all violations

**Research date:** 2026-03-29
**Valid until:** Indefinite (internal codebase analysis, not dependent on external sources)
