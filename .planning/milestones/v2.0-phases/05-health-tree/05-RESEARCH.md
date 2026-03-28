# Phase 5: Health Tree - Research

**Researched:** 2026-03-28
**Domain:** Health aggregation, Discord rendering, event-driven notifications
**Confidence:** HIGH

## Summary

Phase 5 builds three capabilities on top of existing infrastructure: (1) supervisors aggregate children's HealthReport objects into a tree structure queryable at any level, (2) a Discord `/health` slash command renders the full tree with color-coded state indicators, and (3) state transitions automatically push notifications to Discord without polling.

The foundation is solid. HealthReport (Pydantic model) already exists and is emitted on every state transition via `AgentContainer._on_state_change()`. Supervisor already receives these via `_make_state_change_callback()` but currently only uses them for error/stopped detection. The key work is: (a) making Supervisor store the latest HealthReport per child, (b) adding a `health_tree()` method that recursively collects reports, (c) building a new Discord cog with `/health`, and (d) wiring state-change callbacks to push notifications to a Discord channel.

**Primary recommendation:** Add health aggregation to Supervisor base class (not CompanyRoot-specific), create a new `HealthCog` in `src/vcompany/bot/cogs/health.py`, and use the existing `on_state_change` callback path to push notifications. No new dependencies needed.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion for this infrastructure phase.

### Claude's Discretion
All implementation choices are at Claude's discretion. Key technical anchors from requirements:
- Supervisors aggregate children's health into a tree queryable at company/project/individual levels (HLTH-02)
- Discord `/health` slash command renders full supervision tree with color-coded state indicators (HLTH-03)
- State transitions push notifications to Discord automatically without polling (HLTH-04)

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HLTH-02 | Supervisors aggregate children's health into a tree -- queryable at any level (company-wide, project, individual) | Supervisor base class gets `_health_reports` dict + `health_tree()` recursive method; CompanyRoot.health_tree() returns full tree; ProjectSupervisor.health_tree() returns project subtree |
| HLTH-03 | Discord slash command `/health` renders the full status tree with state indicators | New HealthCog with `/health` command; `build_health_tree_embed()` in embeds.py; color mapping per state; tree rendered as embed fields |
| HLTH-04 | State transitions push notifications to Discord automatically | Extend existing `on_state_change` callback to also push to a Discord channel (e.g., #alerts or #health); only notify on significant transitions (RUNNING->ERRORED, ERRORED->RUNNING, etc.) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.12+, discord.py 2.7.x, Pydantic 2.11.x
- Discord-first: all human interaction through Discord
- No web UI, no database -- filesystem + YAML state
- Use `asyncio.to_thread` for blocking calls in bot context
- Cog pattern for Discord commands (existing: CommandsCog, AlertsCog, etc.)
- `is_owner_app_check()` decorator for slash command access control
- Rich embeds for Discord output (build_*_embed pattern in embeds.py)
- No GitPython, no requests, no Flask/FastAPI
- pytest + pytest-asyncio for testing

## Standard Stack

### Core (already installed -- no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.7.x | Slash commands, embeds, channel messaging | Already in use for all Discord interaction |
| pydantic | 2.11.x | HealthReport model, tree data models | Already used for HealthReport |
| python-statemachine | 3.0.x | Lifecycle FSM with after_transition hooks | Already drives state change callbacks |

### No New Dependencies Required
This phase uses only existing libraries. Health aggregation is pure Python dict/list operations. Discord rendering uses discord.py Embed. Notifications use existing callback patterns.

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
  container/
    health.py              # Existing HealthReport model (HLTH-01) -- ADD HealthTree model
  supervisor/
    supervisor.py          # ADD: _health_reports dict, health_tree() method
    company_root.py        # ADD: health_tree() override for full tree
    project_supervisor.py  # Inherits health_tree() from Supervisor
  bot/
    cogs/
      health.py            # NEW: HealthCog with /health command
    embeds.py              # ADD: build_health_tree_embed()
```

### Pattern 1: Health Aggregation in Supervisor
**What:** Supervisor stores latest HealthReport per child in `_health_reports: dict[str, HealthReport]`. Updated via the existing `_make_state_change_callback`. A `health_tree()` method returns a structured tree.
**When to use:** Every Supervisor (base class pattern -- CompanyRoot and ProjectSupervisor inherit it).
**Example:**
```python
# In Supervisor.__init__:
self._health_reports: dict[str, HealthReport] = {}

# In _make_state_change_callback:
def callback(report: HealthReport) -> None:
    self._health_reports[child_id] = report  # Always store latest
    if self._restarting:
        return
    if report.state in ("errored", "stopped"):
        event = self._child_events.get(child_id)
        if event is not None:
            event.set()

# New method:
def health_tree(self) -> HealthTree:
    """Aggregate children's health into a tree structure."""
    children = []
    for child_id, report in self._health_reports.items():
        children.append(HealthNode(report=report))
    return HealthTree(
        supervisor_id=self.supervisor_id,
        state=self.state,
        children=children,
    )
```

### Pattern 2: HealthTree Data Model
**What:** Pydantic models for the tree structure. HealthNode wraps a HealthReport. HealthTree wraps a supervisor + its children. CompanyHealthTree wraps the full company view.
**When to use:** Returned by health_tree() methods, consumed by embed builders.
**Example:**
```python
class HealthNode(BaseModel):
    """A single agent's health in the tree."""
    report: HealthReport

class HealthTree(BaseModel):
    """A supervisor's aggregated health view."""
    supervisor_id: str
    state: str  # supervisor state
    children: list[HealthNode] = []

class CompanyHealthTree(BaseModel):
    """Full company health tree (CompanyRoot view)."""
    supervisor_id: str
    state: str
    projects: list[HealthTree] = []
```

### Pattern 3: CompanyRoot health_tree() with Project Nesting
**What:** CompanyRoot overrides health_tree() to include ProjectSupervisors, each with their own children.
**When to use:** Called by /health command for the full view.
**Example:**
```python
# In CompanyRoot:
def health_tree(self) -> CompanyHealthTree:
    project_trees = []
    for project_id, ps in self._projects.items():
        project_trees.append(ps.health_tree())
    return CompanyHealthTree(
        supervisor_id=self.supervisor_id,
        state=self.state,
        projects=project_trees,
    )
```

### Pattern 4: Discord Embed Tree Rendering
**What:** Convert HealthTree into a discord.Embed with color-coded fields. Use emoji/color mapping for states.
**When to use:** `/health` command response.
**Example:**
```python
# State -> color/emoji mapping
STATE_INDICATORS: dict[str, str] = {
    "running": "\U0001f7e2",    # green circle
    "sleeping": "\U0001f535",    # blue circle
    "errored": "\U0001f534",    # red circle
    "stopped": "\u26ab",         # black circle
    "creating": "\U0001f7e1",   # yellow circle
    "destroyed": "\u2b1b",       # black square
}

def build_health_tree_embed(tree: CompanyHealthTree) -> discord.Embed:
    embed = discord.Embed(
        title="Health Tree",
        color=discord.Color.green() if tree.state == "running" else discord.Color.red(),
        timestamp=datetime.now(timezone.utc),
    )
    for project in tree.projects:
        lines = []
        for node in project.children:
            r = node.report
            indicator = STATE_INDICATORS.get(r.state, "\u2753")
            inner = f" ({r.inner_state})" if r.inner_state else ""
            lines.append(f"{indicator} **{r.agent_id}**: {r.state}{inner}")
        embed.add_field(
            name=f"Project: {project.supervisor_id}",
            value="\n".join(lines) or "No agents",
            inline=False,
        )
    return embed
```

### Pattern 5: State Transition Notifications (HLTH-04)
**What:** Extend `on_state_change` callback chain to push significant transitions to Discord. Use an async notification callback on CompanyRoot.
**When to use:** Automatically on every significant state transition.
**Key design:** The existing `_make_state_change_callback` is synchronous (called from FSM `after_transition`). For async Discord notification, schedule it via `asyncio.get_event_loop().create_task()` or store transitions in a queue that an async consumer processes.
**Example:**
```python
# Option A: Fire-and-forget async task from sync callback
def _make_state_change_callback(self, child_id: str) -> Callable[[HealthReport], None]:
    def callback(report: HealthReport) -> None:
        self._health_reports[child_id] = report
        # Notify on significant transitions
        if self._on_health_change is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._on_health_change(report))
            except RuntimeError:
                pass  # No running loop
        if self._restarting:
            return
        if report.state in ("errored", "stopped"):
            event = self._child_events.get(child_id)
            if event is not None:
                event.set()
    return callback
```

### Pattern 6: HealthCog Structure
**What:** New cog following existing patterns (CommandsCog, AlertsCog).
**When to use:** Slash command /health.
**Example:**
```python
class HealthCog(commands.Cog):
    def __init__(self, bot: VcoBot) -> None:
        self.bot = bot

    @app_commands.command(name="health", description="Show health tree")
    @is_owner_app_check()
    async def health_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        # Get CompanyRoot from bot (wired during v2 init)
        company_root = getattr(self.bot, 'company_root', None)
        if company_root is None:
            await interaction.followup.send("No supervision tree active.", ephemeral=True)
            return
        tree = company_root.health_tree()
        embed = build_health_tree_embed(tree)
        await interaction.followup.send(embed=embed)
```

### Anti-Patterns to Avoid
- **Polling for health:** Do NOT add a periodic health check loop. The existing event-driven `on_state_change` callback already fires on every transition. Aggregation should be lazy (collect on query).
- **Storing health in files:** HealthReport is transient runtime state. Do NOT persist to disk or memory_store. It is regenerated on demand via `health_report()` and cached in supervisor `_health_reports` dict.
- **One giant embed:** Discord embeds have a 25-field limit and 6000-character total limit. For large fleets, truncate or paginate. For v2 (single machine, few agents), this is unlikely to hit limits, but code defensively.
- **Synchronous Discord calls in FSM callback:** The `after_transition` hook is sync. Never call `await channel.send()` directly. Use `loop.create_task()` or queue-based approach.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| State color mapping | Custom color calculation | Static dict mapping state->emoji/color | 6 states, simple lookup |
| Tree serialization | Custom JSON builder | Pydantic `model_dump()` on HealthTree | Already Pydantic models |
| Embed field limits | Manual string counting | Check `len(embed.fields) < 25` and truncate | discord.py raises on >25 fields |
| Async from sync callback | Thread-based queue | `asyncio.get_running_loop().create_task()` | Standard asyncio pattern for fire-and-forget |

## Common Pitfalls

### Pitfall 1: Sync Callback Calling Async Discord API
**What goes wrong:** `after_transition` is synchronous. Calling `await channel.send()` raises RuntimeError or blocks.
**Why it happens:** FSM hooks are sync, Discord API is async.
**How to avoid:** Use `asyncio.get_running_loop().create_task()` to schedule the notification as a fire-and-forget coroutine. Alternatively, store the transition in a sync-safe structure (e.g., `asyncio.Queue`) and have an async consumer drain it.
**Warning signs:** RuntimeError about "no running event loop" or "cannot be called from a running event loop."

### Pitfall 2: Discord Embed Size Limits
**What goes wrong:** Embed exceeds 6000 total characters or 25 fields, causing discord.py to raise.
**Why it happens:** Large supervision tree with many agents.
**How to avoid:** Cap fields at 25. Truncate field values at 1024 chars. Check total embed size. For v2 this is unlikely (few agents per project), but add defensive guards.
**Warning signs:** HTTPException from Discord API with code 50035.

### Pitfall 3: Stale Health Reports After Restart
**What goes wrong:** After supervisor restarts a child, old HealthReport still in `_health_reports` dict showing previous state.
**How to avoid:** Clear the child's entry in `_health_reports` when starting a new container in `_start_child()`. The new container's first state change will populate it fresh.
**Warning signs:** `/health` shows "running" for an agent that just crashed.

### Pitfall 4: Notification Storms on Bulk Restart
**What goes wrong:** `all_for_one` or `rest_for_one` restart stops multiple children, generating N stopped + N running notifications.
**Why it happens:** `_restarting` flag suppresses error detection but state change callback still fires.
**How to avoid:** Check `self._restarting` in the notification path too. Only push notifications when `_restarting` is False. The existing callback already checks this for error handling; extend it to notification.
**Warning signs:** Discord channel flooded with rapid state change messages during a restart cascade.

### Pitfall 5: CompanyRoot Projects Not in _health_reports
**What goes wrong:** CompanyRoot manages ProjectSupervisors dynamically (not via child_specs). They are not AgentContainers, so they don't emit HealthReport.
**Why it happens:** ProjectSupervisor is a Supervisor, not an AgentContainer.
**How to avoid:** CompanyRoot.health_tree() iterates `self._projects` dict directly and calls `ps.health_tree()` on each. ProjectSupervisor health is derived from its children, not self-reported.
**Warning signs:** health_tree() returns empty tree because it only looks at `_health_reports`.

### Pitfall 6: VcoBot Missing company_root Attribute
**What goes wrong:** `/health` tries to access `self.bot.company_root` which doesn't exist yet (v2 wiring happens in Phase 8: MIGR-01).
**Why it happens:** Phase 5 is before Phase 8 integration.
**How to avoid:** Use `getattr(self.bot, 'company_root', None)` with a graceful fallback message. The HealthCog should work standalone when CompanyRoot is wired in, and fail gracefully before that.
**Warning signs:** AttributeError on bot object.

## Code Examples

### Building a HealthTree from Supervisor
```python
# Source: pattern derived from existing Supervisor._make_state_change_callback
from vcompany.container.health import HealthReport

class HealthNode(BaseModel):
    report: HealthReport

class HealthTree(BaseModel):
    supervisor_id: str
    state: str
    children: list[HealthNode] = []

# In Supervisor.health_tree():
def health_tree(self) -> HealthTree:
    children = []
    for child_id in self._child_specs:
        report = self._health_reports.get(child_id.child_id)
        if report is None:
            # Child exists but hasn't transitioned yet -- generate fresh
            container = self._children.get(child_id.child_id)
            if container is not None:
                report = container.health_report()
        if report is not None:
            children.append(HealthNode(report=report))
    return HealthTree(
        supervisor_id=self.supervisor_id,
        state=self.state,
        children=children,
    )
```

### Discord Slash Command Pattern (from existing CommandsCog)
```python
# Source: src/vcompany/bot/cogs/commands.py pattern
@app_commands.command(name="health", description="Show supervision tree health")
@is_owner_app_check()
async def health_cmd(self, interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    company_root = getattr(self.bot, 'company_root', None)
    if company_root is None:
        await interaction.followup.send(
            "No supervision tree active.", ephemeral=True
        )
        return
    tree = company_root.health_tree()
    embed = build_health_tree_embed(tree)
    await interaction.followup.send(embed=embed)
```

### State Transition Notification
```python
# Notification callback type
from typing import Awaitable, Callable
OnHealthChange = Callable[[HealthReport], Awaitable[None]]

# In HealthCog -- wire notification to #alerts channel
async def _notify_state_change(self, report: HealthReport) -> None:
    """Push significant state transitions to Discord."""
    # Only notify on significant transitions
    if report.state not in ("errored", "running", "stopped"):
        return
    guild = self.bot.get_guild(self.bot._guild_id)
    if guild is None:
        return
    channel = discord.utils.get(guild.text_channels, name="alerts")
    if channel is None:
        return
    indicator = STATE_INDICATORS.get(report.state, "")
    await channel.send(
        f"{indicator} **{report.agent_id}** -> {report.state}"
        + (f" (was: {report.inner_state})" if report.inner_state else "")
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| v1 MonitorLoop polling | v2 event-driven on_state_change | Phase 1-2 (this milestone) | No polling needed; callbacks fire on transitions |
| v1 generate_project_status (file-based) | v2 health_tree() (runtime tree) | Phase 5 (this phase) | Real-time view from supervision tree, not stale files |

**Deprecated/outdated:**
- `MonitorLoop` health checking: replaced by supervision tree health aggregation. MonitorLoop stays as safety net until Phase 8 migration.
- `generate_project_status()`: v1 file-based status. Will be replaced by health_tree() for v2, but not removed until Phase 8.

## Open Questions

1. **Where should notifications go?**
   - What we know: Existing alerts go to #alerts channel. Health notifications could go there too.
   - What's unclear: Should there be a separate #health channel, or reuse #alerts?
   - Recommendation: Reuse #alerts for now (v2 is single-project). Add channel configurability later if needed.

2. **How will HealthCog access CompanyRoot before Phase 8 wiring?**
   - What we know: Phase 8 (MIGR-01) wires CompanyRoot into VcoBot. Phase 5 comes before that.
   - What's unclear: Whether to add `company_root` attribute to VcoBot now or rely on getattr.
   - Recommendation: Add a `company_root: CompanyRoot | None = None` attribute to VcoBot now (forward-compatible). HealthCog checks for None and returns graceful message. Phase 8 wires it.

3. **Should /health support filtering by project or agent?**
   - What we know: HLTH-02 says "queryable at any level (company-wide, project, individual)".
   - Recommendation: Add optional `project` and `agent_id` parameters to `/health` slash command. When omitted, show full tree. When provided, filter to that subtree.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 0.24+ |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HLTH-02 | Supervisor aggregates children health into tree | unit | `uv run pytest tests/test_health_tree.py::TestHealthAggregation -x` | Wave 0 |
| HLTH-02 | CompanyRoot returns full tree with project subtrees | unit | `uv run pytest tests/test_health_tree.py::TestCompanyHealthTree -x` | Wave 0 |
| HLTH-02 | Queryable at project and individual level | unit | `uv run pytest tests/test_health_tree.py::TestHealthTreeFiltering -x` | Wave 0 |
| HLTH-03 | /health renders embed with color-coded indicators | unit | `uv run pytest tests/test_health_cog.py::TestHealthEmbed -x` | Wave 0 |
| HLTH-03 | Embed respects 25-field and 6000-char limits | unit | `uv run pytest tests/test_health_cog.py::TestEmbedLimits -x` | Wave 0 |
| HLTH-04 | State transitions push notifications | unit | `uv run pytest tests/test_health_tree.py::TestStateNotifications -x` | Wave 0 |
| HLTH-04 | Notifications suppressed during bulk restart | unit | `uv run pytest tests/test_health_tree.py::TestNotificationSuppression -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_health_tree.py tests/test_health_cog.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_health_tree.py` -- covers HLTH-02, HLTH-04 (health aggregation, notifications)
- [ ] `tests/test_health_cog.py` -- covers HLTH-03 (Discord embed rendering, slash command)

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/vcompany/container/health.py` -- HealthReport Pydantic model
- Codebase inspection: `src/vcompany/container/container.py` -- AgentContainer.health_report(), _on_state_change()
- Codebase inspection: `src/vcompany/supervisor/supervisor.py` -- _make_state_change_callback(), children dict
- Codebase inspection: `src/vcompany/supervisor/company_root.py` -- _projects dict, dynamic project management
- Codebase inspection: `src/vcompany/bot/cogs/commands.py` -- Cog pattern, slash commands, is_owner_app_check
- Codebase inspection: `src/vcompany/bot/embeds.py` -- build_*_embed pattern, color mapping
- Codebase inspection: `src/vcompany/container/state_machine.py` -- after_transition hook, sync callback chain

### Secondary (MEDIUM confidence)
- discord.py embed limits: 25 fields max, 6000 total chars, 1024 per field value, 256 per field name (well-known discord.py constraints)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all existing libraries
- Architecture: HIGH - clear extension of existing Supervisor and Cog patterns
- Pitfalls: HIGH - directly derived from code inspection (sync/async boundary, embed limits, dynamic projects)

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable -- no external dependency changes)
