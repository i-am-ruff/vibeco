# Phase 8: CompanyRoot Wiring and Migration - Research

**Researched:** 2026-03-28
**Domain:** Discord bot migration, supervision tree integration, v1 module removal
**Confidence:** HIGH

## Summary

Phase 8 is the capstone migration phase that wires the v2 supervision tree into the bot startup path, removes v1 modules, and prepares the communication layer for v3 abstraction. The codebase is in excellent shape for this migration: all v2 modules (Phases 1-7) are built and tested (999 tests, 19 plans completed), all Discord commands already use slash syntax (`@app_commands.command`), and the `CommunicationPort` Protocol is defined but has no Discord implementation yet.

The core work is: (1) replace VcoBot.on_ready()'s flat initialization of AgentManager/MonitorLoop/CrashTracker with CompanyRoot supervision tree startup, (2) formally remove the `command_prefix="!"` since all commands are already slash commands, (3) delete the four v1 modules and all their imports throughout the codebase, and (4) implement a `DiscordCommunicationPort` that satisfies the existing Protocol.

**Primary recommendation:** Execute in 3-4 plans: first wire CompanyRoot into bot startup, then remove v1 modules and update all imports, then implement DiscordCommunicationPort, and finally update tests.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- auto-generated infrastructure phase, all at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion. Key technical anchors from requirements:
- CompanyRoot initializes full supervision tree on bot startup, replacing VcoBot.on_ready() (MIGR-01)
- All Discord commands converted to slash commands, no more `!` prefix (MIGR-02)
- v1 MonitorLoop, CrashTracker, WorkflowOrchestrator, AgentManager fully removed (MIGR-03)
- Communication layer has clean abstract interface for v3 channel abstraction (MIGR-04)

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MIGR-01 | CompanyRoot replaces flat VcoBot.on_ready() -- supervision tree initializes all containers | CompanyRoot.start() already registers types, starts scheduler, degraded mode. VcoBot.on_ready() currently initializes AgentManager, MonitorLoop, CrashTracker, WorkflowOrchestrator -- all replaced by v2 equivalents. |
| MIGR-02 | All Discord commands converted to slash commands (no more `!` prefix) | Already done -- all 11 commands use `@app_commands.command`. Only cleanup: remove `command_prefix="!"` from VcoBot constructor and update test assertion. |
| MIGR-03 | v1 modules fully removed after v2 passes regression tests | 4 modules: `monitor/loop.py`, `orchestrator/crash_tracker.py`, `orchestrator/workflow_orchestrator.py`, `orchestrator/agent_manager.py`. 14 import sites across bot, CLI, and cogs need updating. |
| MIGR-04 | Communication layer designed with clean interface for v3 channel abstraction | CommunicationPort Protocol exists with `send_message()` and `receive_message()`. Need Discord implementation class. |
</phase_requirements>

## Standard Stack

No new libraries needed. This phase uses existing project dependencies only.

### Core (Already Installed)
| Library | Version | Purpose | Role in Phase |
|---------|---------|---------|---------------|
| discord.py | 2.7.x | Discord bot | VcoBot, slash commands, CommunicationPort implementation |
| python-statemachine | 3.0.x | FSM | GsdLifecycle, ContainerLifecycle (existing, untouched) |
| pydantic | 2.11.x | Models | Config models (existing, untouched) |

## Architecture Patterns

### Pattern 1: Bot Startup with Supervision Tree (MIGR-01)

**What:** Replace the flat VcoBot.on_ready() initialization chain with CompanyRoot.start() in setup_hook or on_ready.

**Current flow (v1):**
```
VcoBot.on_ready()
  -> create vco-owner role
  -> setup system channels
  -> init Strategist
  -> init WorkflowMaster
  -> detect active project
  -> init AgentManager (v1)
  -> init CrashTracker (v1)
  -> init MonitorLoop (v1)
  -> init PM/PlanReviewer
  -> init WorkflowOrchestrator (v1)
  -> send boot notifications
```

**New flow (v2):**
```
VcoBot.on_ready()
  -> create vco-owner role
  -> setup system channels
  -> init Strategist (kept -- always-available)
  -> init WorkflowMaster (kept -- always-available)
  -> detect active project
  -> IF project detected:
      -> create CompanyRoot with callbacks
      -> await company_root.start()
      -> company_root.add_project() with ChildSpecs built from agents.yaml
      -> wire HealthCog notifications
      -> wire PlanReviewCog (now using GsdAgent's internal FSM)
  -> send boot notifications
```

**Key mapping:**
| v1 Component | v2 Replacement | Notes |
|---|---|---|
| AgentManager | Supervisor + GsdAgent containers | Supervisor manages lifecycle; containers spawn tmux panes |
| MonitorLoop | Supervisor health tree + callbacks | Event-driven via on_state_change, not polling |
| CrashTracker | RestartTracker + BulkFailureDetector | Per-supervisor restart intensity tracking |
| WorkflowOrchestrator | GsdAgent internal FSM | Phase transitions are per-container state machine |

**Critical detail:** CompanyRoot already calls `register_defaults()` in its `start()` method, opens scheduler memory, and starts the degraded mode manager. The bot just needs to create it with the right callbacks and call `start()`.

### Pattern 2: DiscordCommunicationPort (MIGR-04)

**What:** Implement the CommunicationPort Protocol with Discord as the transport.

**Design:**
```python
class DiscordCommunicationPort:
    """Discord-backed implementation of CommunicationPort.

    Uses Discord channels as the transport layer. Each container's
    communication port routes to its agent's Discord channel.
    Designed for v3 swappability -- no Discord types leak through
    the CommunicationPort Protocol interface.
    """

    def __init__(
        self,
        bot: VcoBot,
        agent_id: str,
        guild_id: int,
    ) -> None:
        self._bot = bot
        self._agent_id = agent_id
        self._guild_id = guild_id
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()

    async def send_message(self, target: str, content: str) -> bool:
        """Send message to target agent's Discord channel."""
        ...

    async def receive_message(self) -> Message | None:
        """Pop next message from inbox queue."""
        ...
```

**Key v3 preparation principle:** The Protocol interface (`send_message`, `receive_message`) is channel-agnostic. Only the implementation class knows about Discord. v3 will add `SlackCommunicationPort`, `TeamSpeakCommunicationPort`, etc. No container code changes needed.

### Pattern 3: v1 Module Removal (MIGR-03)

**What:** Delete v1 modules and update all import sites.

**Modules to delete:**
1. `src/vcompany/monitor/loop.py`
2. `src/vcompany/orchestrator/crash_tracker.py`
3. `src/vcompany/orchestrator/workflow_orchestrator.py`
4. `src/vcompany/orchestrator/agent_manager.py`

**Import sites to update (14 total):**

| File | Imports | Action |
|------|---------|--------|
| `bot/client.py` | MonitorLoop, AgentManager, CrashTracker, WorkflowOrchestrator | Remove imports, replace with CompanyRoot wiring |
| `bot/cogs/commands.py` | AgentManager, WorkflowOrchestrator, MonitorLoop | Update /new-project and /remove-project to use CompanyRoot |
| `bot/cogs/workflow_orchestrator_cog.py` | WorkflowOrchestrator types | Replace with GsdAgent FSM integration or remove cog |
| `cli/dispatch_cmd.py` | AgentManager | Needs rethinking -- dispatch now goes through supervision tree |
| `cli/kill_cmd.py` | AgentManager | Same -- kill goes through supervisor |
| `cli/relaunch_cmd.py` | AgentManager | Same -- relaunch via supervisor restart |
| `cli/monitor_cmd.py` | MonitorLoop | Remove or replace with health tree query |

**Tests to update/remove:**
- `tests/test_monitor_loop.py` -- remove (v1 module)
- `tests/test_crash_tracker.py` -- remove (v1 module)
- `tests/test_workflow_orchestrator.py` -- remove (v1 module)
- `tests/test_dispatch.py` -- remove or rewrite for v2 dispatch
- `tests/test_kill.py` -- remove or rewrite for v2 kill
- `tests/test_relaunch.py` -- remove or rewrite
- `tests/test_bot_client.py` -- update (removes v1 references)
- `tests/test_commands_cog.py` -- update (removes v1 references)
- `tests/test_workflow_orchestrator_cog.py` -- update or remove

### Pattern 4: Cog Cleanup

**Cogs to update:**
| Cog | Current State | Migration Action |
|-----|---------------|------------------|
| CommandsCog | References AgentManager, MonitorLoop directly | Route through CompanyRoot for dispatch/kill/relaunch |
| WorkflowOrchestratorCog | Bridges to v1 WorkflowOrchestrator | Replace with GsdAgent FSM event handling or remove |
| AlertsCog | Creates sync callbacks for MonitorLoop | Replace with health change notifications from supervisor |
| PlanReviewCog | Uses bot.agent_manager and bot.monitor_loop | Route through CompanyRoot |
| HealthCog | Already uses CompanyRoot via getattr | Wire in on_ready properly |
| QuestionHandlerCog | PM-only, no v1 deps | No changes needed |
| StrategistCog | No v1 deps | No changes needed |

**WorkflowOrchestratorCog decision:** This cog is the most complex migration. It bridges Discord messages to the v1 WorkflowOrchestrator state machine. In v2, GsdAgent has its own internal FSM. Options:
1. **Adapt the cog** to talk to GsdAgent containers via CompanyRoot instead of WorkflowOrchestrator
2. **Remove the cog entirely** and let GsdAgent handle its own phase transitions internally

Recommendation: **Adapt the cog** -- it still needs to bridge Discord signal detection (vco report messages) to container phase advances. The cog becomes a thin adapter from Discord events to CompanyRoot container operations.

### Anti-Patterns to Avoid
- **Incremental half-migration:** Do not leave both v1 and v2 paths active. Remove v1 completely in this phase.
- **Leaking Discord types through CommunicationPort:** The Protocol interface must remain channel-agnostic. Implementation details (guild_id, channel objects) stay inside DiscordCommunicationPort.
- **Breaking CLI commands:** The `vco dispatch/kill/relaunch/monitor` CLI commands currently import AgentManager/MonitorLoop directly. These need updating to work through the new architecture or be marked as deprecated.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slash command registration | Manual command tree sync | discord.py's `setup_hook` + `tree.sync()` | Already implemented correctly in VcoBot.setup_hook() |
| Container lifecycle management | Custom restart logic | Supervisor + RestartTracker | Already built in Phase 2/6 with Erlang semantics |
| Rate-limited Discord sends | Manual backoff | MessageQueue (Phase 6) | RESL-01 already handles debouncing and prioritization |

## Common Pitfalls

### Pitfall 1: on_ready Fires on Reconnect
**What goes wrong:** Initialization code runs twice, duplicating CompanyRoot
**Why it happens:** discord.py fires on_ready on every reconnect, not just first connection
**How to avoid:** The existing `_initialized` guard already handles this. Keep it.
**Warning signs:** Duplicate "CompanyRoot started" log messages

### Pitfall 2: Circular Import Between Bot and CompanyRoot
**What goes wrong:** CompanyRoot needs bot reference for callbacks; bot needs CompanyRoot for health commands
**Why it happens:** Tight coupling between bot and supervision tree
**How to avoid:** Store CompanyRoot as `bot.company_root` attribute (already done in HealthCog pattern). Pass async callbacks to CompanyRoot constructor, not the bot object itself.
**Warning signs:** ImportError during module loading

### Pitfall 3: Removing v1 Tests Breaks Test Count
**What goes wrong:** Tests that import v1 modules will fail at collection time, not just at runtime
**Why it happens:** pytest collects all test files before running any
**How to avoid:** Delete v1 test files in the same commit that deletes v1 source modules
**Warning signs:** "ERROR during collection" messages in pytest output

### Pitfall 4: CLI Commands Become Broken
**What goes wrong:** `vco dispatch/kill/relaunch/monitor` stop working after AgentManager removal
**Why it happens:** CLI commands import AgentManager directly
**How to avoid:** Either update CLI to route through CompanyRoot (requires running bot), or keep a thin AgentManager-like facade for CLI-only use. The CLI dispatch path (`vco dispatch`) is separate from the bot's supervision tree.
**How to handle:** For Phase 8, the CLI commands can remain but import from new locations. The supervision tree handles lifecycle when the bot is running; CLI commands are for manual operator use when the bot is not running.

### Pitfall 5: WorkflowOrchestratorCog Removal Breaks PlanReviewCog
**What goes wrong:** PlanReviewCog has `_workflow_cog: WorkflowOrchestratorCog` reference for plan approval/rejection notifications
**Why it happens:** Tight coupling between cogs
**How to avoid:** Either keep an adapted WorkflowOrchestratorCog or move notification logic into PlanReviewCog itself
**Warning signs:** Plan approval/rejection no longer triggers agent phase advances

## Code Examples

### CompanyRoot Wiring in VcoBot.on_ready()

```python
# In VcoBot.on_ready(), replacing v1 initialization:
from vcompany.supervisor.company_root import CompanyRoot
from vcompany.container.child_spec import ChildSpec
from vcompany.container.context import ContainerContext

# Create escalation callback for Discord alerts
async def on_escalation(msg: str) -> None:
    alerts_ch = self._system_channels.get("alerts")
    if alerts_ch:
        await alerts_ch.send(f"ESCALATION: {msg}")

# Create health change callback for HealthCog
health_cog = self.get_cog("HealthCog")
on_health_change = health_cog._notify_state_change if health_cog else None

self.company_root = CompanyRoot(
    on_escalation=on_escalation,
    max_restarts=3,
    window_seconds=600,
    data_dir=self.project_dir / "state" / "supervision",
    on_health_change=on_health_change,
)
await self.company_root.start()

# Build child specs from agents.yaml
specs = []
for agent_cfg in self.project_config.agents:
    ctx = ContainerContext(
        agent_id=agent_cfg.id,
        agent_type="gsd",
        parent_id="project-supervisor",
        project_id=self.project_config.project,
        owned_dirs=agent_cfg.owns,
        gsd_mode=agent_cfg.gsd_mode,
        system_prompt=agent_cfg.system_prompt,
    )
    specs.append(ChildSpec(child_id=agent_cfg.id, agent_type="gsd", context=ctx))

await self.company_root.add_project(
    project_id=self.project_config.project,
    child_specs=specs,
)
```

### DiscordCommunicationPort

```python
from vcompany.container.communication import CommunicationPort, Message
from datetime import datetime, timezone

class DiscordCommunicationPort:
    """Discord implementation of CommunicationPort Protocol."""

    def __init__(self, bot, agent_id: str, guild_id: int) -> None:
        self._bot = bot
        self._agent_id = agent_id
        self._guild_id = guild_id
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()

    async def send_message(self, target: str, content: str) -> bool:
        guild = self._bot.get_guild(self._guild_id)
        if not guild:
            return False
        channel = discord.utils.get(guild.text_channels, name=f"agent-{target}")
        if not channel:
            return False
        try:
            await channel.send(f"[from:{self._agent_id}] {content}")
            return True
        except Exception:
            return False

    async def receive_message(self) -> Message | None:
        try:
            return self._inbox.get_nowait()
        except asyncio.QueueEmpty:
            return None
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | pyproject.toml |
| Quick run command | `uv run python -m pytest tests/ -x -q` |
| Full suite command | `uv run python -m pytest tests/ -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MIGR-01 | CompanyRoot starts supervision tree on bot startup | unit | `uv run python -m pytest tests/test_bot_client.py -x -q` | Exists but needs rewrite |
| MIGR-02 | No `!` prefix, all slash commands | unit | `uv run python -m pytest tests/test_bot_client.py::TestVcoBotInit -x -q` | Exists, needs update |
| MIGR-03 | v1 modules removed, no import errors | smoke | `uv run python -m pytest --co -q` (collection succeeds with 0 errors) | Wave 0 |
| MIGR-04 | DiscordCommunicationPort satisfies Protocol | unit | `uv run python -m pytest tests/test_discord_comm_port.py -x -q` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run python -m pytest tests/ -x -q`
- **Per wave merge:** `uv run python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_discord_comm_port.py` -- covers MIGR-04
- [ ] Update `tests/test_bot_client.py` -- covers MIGR-01, MIGR-02

## Open Questions

1. **CLI command fate after AgentManager removal**
   - What we know: `vco dispatch/kill/relaunch/monitor` CLI commands import AgentManager directly
   - What's unclear: Whether CLI should route through CompanyRoot (requires running bot) or maintain independent CLI dispatch capability
   - Recommendation: Keep AgentManager functionality available for CLI by moving essential dispatch/kill/relaunch logic to a new thin module (e.g., `tmux_dispatch.py`) that both CLI and supervision tree can use. The supervision tree wraps it with restart semantics; CLI calls it directly.

2. **WorkflowOrchestratorCog adaptation scope**
   - What we know: It bridges Discord vco-report messages to v1 WorkflowOrchestrator state machine
   - What's unclear: How much of this bridge is still needed with GsdAgent's internal FSM
   - Recommendation: Keep the cog but adapt it to find the GsdAgent container via CompanyRoot and call `advance_phase()` instead of WorkflowOrchestrator methods. The signal detection logic (`detect_stage_signal`) is still useful.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: All 10 source files read, 14 import sites identified
- `tests/` directory: 999 tests collected, key test files identified for migration
- discord.py patterns: Already correctly using `app_commands.command` and `setup_hook` for slash commands

### Secondary (MEDIUM confidence)
- Phase 2 decisions (from STATE.md): Supervisor is standalone class, event-driven monitoring via asyncio.Event
- Phase 3 decisions (from STATE.md): GsdLifecycle is standalone StateMachine with compound states

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all existing
- Architecture: HIGH -- v2 modules are fully built, wiring patterns clear from existing code
- Pitfalls: HIGH -- identified from direct codebase analysis of import chains and test dependencies

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable -- internal migration, no external dependency changes)
