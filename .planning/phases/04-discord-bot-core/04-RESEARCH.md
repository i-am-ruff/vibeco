# Phase 4: Discord Bot Core - Research

**Researched:** 2026-03-25
**Domain:** Discord bot framework (discord.py), async Python, bot-to-library integration
**Confidence:** HIGH

## Summary

Phase 4 delivers the Discord bot that serves as the operator interface to the entire vCompany agent fleet. The bot runs as `vco bot`, imports the vcompany library directly (same process), creates per-project Discord categories with channels, exposes operator commands (!new-project, !dispatch, !status, !standup, !kill, !relaunch, !integrate), enforces role-based access via a `vco-owner` role, and injects real callbacks into MonitorLoop and CrashTracker for alert routing.

The existing codebase provides all the building blocks: AgentManager (dispatch/kill/relaunch), MonitorLoop (callback injection for on_agent_dead, on_agent_stuck, on_plan_detected), CrashTracker (on_circuit_open callback), generate_project_status (for !status embed content), and the Click CLI group (for adding `vco bot`). The bot Cog architecture maps cleanly: CommandsCog wraps AgentManager, AlertsCog receives monitor callbacks, PlanReviewCog and StrategistCog are placeholders for Phases 5 and 6.

discord.py 2.7.1 is the correct and only choice. It is not yet in pyproject.toml and must be added as a dependency. All blocking operations (AgentManager.dispatch, kill, relaunch, file I/O, git calls) must use `asyncio.to_thread()` since these are synchronous methods. discord.py's built-in reconnect handling covers DISC-12, but the bot must never block the event loop for this to work.

**Primary recommendation:** Build 4 Cogs (CommandsCog, AlertsCog, PlanReviewCog stub, StrategistCog stub), wire them via discord.py extensions with `setup_hook`, use `asyncio.to_thread()` for all AgentManager calls, and implement confirmation Views for destructive commands.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** `!new-project` is a conversation starter, not a file uploader. Creates a thread + category/channels.
- **D-02:** `!new-project [optional-name]` creates project thread + Discord category + channels. If no name, bot asks.
- **D-03:** All destructive commands (!kill, !integrate) require confirmation via reaction buttons (View/Button components, not raw reactions).
- **D-04:** `!status` returns rich embed from PROJECT-STATUS.md.
- **D-05:** `!dispatch [agent-id | all]`, `!kill agent-id`, `!relaunch agent-id` are thin wrappers calling AgentManager methods.
- **D-06:** `!standup` scaffolded in Phase 4, full implementation in Phase 7.
- **D-07:** `!integrate` scaffolded in Phase 4, full implementation in Phase 7.
- **D-08:** Two permission tiers: Owner (vco-owner role) = all commands, Viewer (default) = read-only.
- **D-09:** Role check is a decorator on each command. Unauthorized = polite message.
- **D-10:** Bot creates `vco-owner` role on startup if it doesn't exist.
- **D-11:** Bot imports vcompany library directly (same process). No subprocess calls.
- **D-12:** discord.py Cog architecture with 4 Cogs: CommandsCog, AlertsCog, PlanReviewCog (placeholder), StrategistCog (placeholder).
- **D-13:** Bot startup: load config, init AgentManager + MonitorLoop + CrashTracker, inject Discord callbacks, start monitor as asyncio background task.
- **D-14:** All blocking operations use `asyncio.to_thread()`.
- **D-15:** Auto-reconnect via discord.py built-in. Monitor loop continues during disconnects. Alerts buffered and sent on reconnect.
- **D-16:** Discord category per project: `vco-{project-name}`.
- **D-17:** Channels: #strategist, #plan-review, #standup, #alerts, #decisions, #agent-{id} per agent.
- **D-18:** Channel creation happens on `!new-project` confirmation.
- **D-19:** Viewer role gets read-only. Owner role gets send permissions.
- **D-20:** Bot runs as `vco bot` Click command.
- **D-21:** Token from `DISCORD_BOT_TOKEN` env var. Guild from `DISCORD_GUILD_ID`.
- **D-22:** Single guild bot.

### Claude's Discretion
- Embed formatting for !status (colors, fields, layout)
- Error message wording
- Whether to add !help command
- Alert message formatting in #alerts
- Buffer implementation for alerts during disconnect

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DISC-01 | Discord bot uses discord.py Cogs architecture | Cog pattern documented below with setup_hook extension loading |
| DISC-02 | Bot creates channel structure on project init | guild.create_category_channel + create_text_channel with permission overwrites |
| DISC-03 | `!new-project` triggers init + clone | CommandsCog wraps load_config + creates thread + channels |
| DISC-04 | `!dispatch` triggers dispatch | CommandsCog wraps AgentManager.dispatch/dispatch_all via asyncio.to_thread |
| DISC-05 | `!status` shows aggregate view | Embed built from generate_project_status output |
| DISC-06 | `!standup` triggers interactive standup | Scaffold command + channel, full impl in Phase 7 |
| DISC-07 | `!kill` terminates agent | CommandsCog wraps AgentManager.kill via asyncio.to_thread with confirmation View |
| DISC-08 | `!relaunch` restarts agent | CommandsCog wraps AgentManager.relaunch via asyncio.to_thread |
| DISC-09 | `!integrate` triggers merge | Scaffold command, full impl in Phase 7 |
| DISC-10 | Role-based access control | `commands.has_role("vco-owner")` decorator or custom check |
| DISC-11 | All blocking calls use asyncio.to_thread() | Pattern documented below for wrapping sync AgentManager |
| DISC-12 | Bot monitors connectivity and auto-reconnects | discord.py built-in reconnect + alert buffer pattern |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.7.1 | Discord bot framework | The standard Python Discord library. Async-native, prefix commands, Cogs, Views/Buttons, auto-reconnect. No alternative exists for Python. |

### Supporting (already in pyproject.toml)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| click | 8.2.x | CLI `vco bot` command | Add bot subcommand to existing CLI group |
| pydantic-settings | 2.13.x | Bot config (token, guild ID) | Load DISCORD_BOT_TOKEN, DISCORD_GUILD_ID from env |
| rich | 14.2.x | CLI output for bot startup | Startup messages, connection status |

### New Dependency
discord.py is NOT in pyproject.toml yet. Must be added:

```bash
uv add "discord.py>=2.7,<3"
```

**Intents required:** `discord.Intents.default()` plus `message_content=True` (privileged intent, must be enabled in Discord Developer Portal).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Prefix commands (!) | Slash commands (/) | Slash commands have autocomplete but require syncing and guild registration. Prefix commands are simpler for an operator tool. CONTEXT.md specifies ! prefix. |
| discord.py Views | Raw reaction collectors | Views are the modern pattern, CONTEXT.md specifies View/Button components. |

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
  bot/
    __init__.py
    client.py           # VcoBot(commands.Bot) subclass, setup_hook
    cogs/
      __init__.py
      commands.py       # CommandsCog — all operator commands
      alerts.py         # AlertsCog — receives monitor callbacks, posts to #alerts
      plan_review.py    # PlanReviewCog — placeholder for Phase 5
      strategist.py     # StrategistCog — placeholder for Phase 6
    views/
      __init__.py
      confirm.py        # ConfirmView — reusable confirm/cancel buttons
    embeds.py           # Embed builders (status, alerts, etc.)
    channel_setup.py    # Category + channel creation logic
    config.py           # BotConfig pydantic-settings model
  cli/
    bot_cmd.py          # Click command: vco bot
```

### Pattern 1: Bot Client with setup_hook
**What:** Subclass `commands.Bot`, load Cogs in `setup_hook`, pass shared state.
**When to use:** Always for discord.py bots with Cogs.
**Example:**
```python
# Source: discord.py docs + cogs pattern
import discord
from discord.ext import commands

class VcoBot(commands.Bot):
    def __init__(self, project_dir: Path, config: ProjectConfig):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.project_dir = project_dir
        self.project_config = config
        self.agent_manager: AgentManager | None = None
        self.monitor_loop: MonitorLoop | None = None
        self.crash_tracker: CrashTracker | None = None
        self._alert_buffer: list[str] = []
        self._guild_id: int = int(os.environ["DISCORD_GUILD_ID"])

    async def setup_hook(self) -> None:
        """Load all Cogs as extensions."""
        await self.load_extension("vcompany.bot.cogs.commands")
        await self.load_extension("vcompany.bot.cogs.alerts")
        await self.load_extension("vcompany.bot.cogs.plan_review")
        await self.load_extension("vcompany.bot.cogs.strategist")

    async def on_ready(self) -> None:
        guild = self.get_guild(self._guild_id)
        # Ensure vco-owner role exists (D-10)
        if not discord.utils.get(guild.roles, name="vco-owner"):
            await guild.create_role(name="vco-owner", reason="vCompany operator role")
```

### Pattern 2: Cog with Extension setup() Function
**What:** Each Cog file has a module-level `async def setup(bot)` function for `load_extension`.
**When to use:** Every Cog file.
**Example:**
```python
# Source: discord.py Cogs documentation
from discord.ext import commands

class CommandsCog(commands.Cog):
    def __init__(self, bot: VcoBot):
        self.bot = bot

    @commands.command(name="status")
    @commands.has_role("vco-owner")
    async def status_cmd(self, ctx: commands.Context) -> None:
        status = await asyncio.to_thread(
            generate_project_status, self.bot.project_dir, self.bot.project_config
        )
        embed = build_status_embed(status)
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommandsCog(bot))
```

### Pattern 3: asyncio.to_thread() for Blocking Calls
**What:** Wrap all synchronous AgentManager/file operations to avoid blocking the gateway heartbeat.
**When to use:** Every call to AgentManager.dispatch, kill, relaunch, generate_project_status, load_config, and any file I/O.
**Example:**
```python
# DISC-11: Never block the event loop
result = await asyncio.to_thread(self.bot.agent_manager.dispatch, agent_id)
```

### Pattern 4: Confirmation View for Destructive Commands
**What:** discord.py View with Confirm/Cancel buttons. Waits for user interaction before executing.
**When to use:** !kill, !integrate (per D-03).
**Example:**
```python
# Source: discord.py examples/views/confirm.py
class ConfirmView(discord.ui.View):
    def __init__(self, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.value: bool | None = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Confirmed.", ephemeral=True)
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Cancelled.", ephemeral=True)
        self.value = False
        self.stop()
```

### Pattern 5: Channel Setup with Permission Overwrites
**What:** Create category + channels with role-based permissions.
**When to use:** `!new-project` after confirmation (D-18).
**Example:**
```python
# Source: discord.py guild.create_category_channel docs
async def setup_project_channels(
    guild: discord.Guild,
    project_name: str,
    owner_role: discord.Role,
    agents: list[AgentConfig],
) -> discord.CategoryChannel:
    viewer_overwrite = discord.PermissionOverwrite(
        view_channel=True, send_messages=False
    )
    owner_overwrite = discord.PermissionOverwrite(
        view_channel=True, send_messages=True, manage_messages=True
    )
    overwrites = {
        guild.default_role: viewer_overwrite,
        owner_role: owner_overwrite,
    }
    category = await guild.create_category_channel(
        f"vco-{project_name}", overwrites=overwrites
    )
    channel_names = ["strategist", "plan-review", "standup", "alerts", "decisions"]
    for name in channel_names:
        await category.create_text_channel(name)
    for agent in agents:
        await category.create_text_channel(f"agent-{agent.id}")
    return category
```

### Pattern 6: Monitor Loop as Background Task
**What:** Start MonitorLoop.run() as an asyncio task from the bot's on_ready.
**When to use:** Bot startup (D-13).
**Example:**
```python
async def on_ready(self) -> None:
    if self.monitor_loop and not self._monitor_task:
        self._monitor_task = asyncio.create_task(self.monitor_loop.run())
```

### Pattern 7: Alert Buffer for Disconnects
**What:** Queue alerts when bot is disconnected, flush on reconnect (D-15).
**When to use:** AlertsCog callback injection.
**Example:**
```python
class AlertsCog(commands.Cog):
    def __init__(self, bot: VcoBot):
        self.bot = bot
        self._alert_buffer: list[tuple[str, str]] = []  # (channel_name, message)
        self._alerts_channel: discord.TextChannel | None = None

    async def _send_or_buffer(self, message: str) -> None:
        if self.bot.is_closed() or not self.bot.is_ready():
            self._alert_buffer.append(message)
            return
        if self._alerts_channel:
            await self._alerts_channel.send(message)

    @commands.Cog.listener()
    async def on_resumed(self) -> None:
        """Flush buffered alerts after reconnect."""
        if self._alert_buffer and self._alerts_channel:
            for msg in self._alert_buffer:
                await self._alerts_channel.send(msg)
            self._alert_buffer.clear()
```

### Pattern 8: Role Check Decorator
**What:** Use `commands.has_role()` or custom check for permission gating (D-09).
**When to use:** Every operator command.
**Example:**
```python
def is_owner():
    """Custom check that verifies vco-owner role."""
    async def predicate(ctx: commands.Context) -> bool:
        role = discord.utils.get(ctx.guild.roles, name="vco-owner")
        if role is None or role not in ctx.author.roles:
            await ctx.send("You need the `vco-owner` role to use this command.")
            return False
        return True
    return commands.check(predicate)
```

Note: `commands.has_role("vco-owner")` is simpler but raises MissingRole on failure. A custom check allows the polite message per D-09.

### Anti-Patterns to Avoid
- **Synchronous API calls in event handlers:** Never call AgentManager methods directly without `asyncio.to_thread()`. This blocks the gateway heartbeat and causes disconnects (Pitfall 4).
- **Hardcoded channel IDs:** Always look up channels by name within the project category. Channel IDs change if channels are recreated.
- **Reaction-based confirmation:** Use View/Button components. Reactions are fragile (anyone can react, ordering issues, no ephemeral feedback).
- **Global bot state without guild scoping:** Even though D-22 specifies single guild, scope all lookups to the configured guild ID to prevent accidental cross-guild operations.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Permission checking | Custom role lookup in every command | `commands.has_role()` or a shared custom check decorator | Consistent behavior, DRY, automatic error handling |
| Reconnection logic | Manual WebSocket management | discord.py built-in `reconnect=True` (default) | discord.py handles all gateway reconnection, heartbeating, and session resumption |
| Rate limiting | Message queue with delays | discord.py internal rate limiter | discord.py automatically handles per-route rate limits for bot API calls |
| Embed building | Manual dict construction | `discord.Embed` class | Type-safe, field limits enforced, color support |
| Button/View lifecycle | Manual message component tracking | `discord.ui.View` with `timeout` parameter | Handles interaction routing, timeouts, and cleanup |

## Common Pitfalls

### Pitfall 1: Blocking the Event Loop (CRITICAL)
**What goes wrong:** Calling synchronous AgentManager.dispatch() (which does tmux operations, file I/O) directly in a command handler blocks the discord.py event loop. The bot misses gateway heartbeats and disconnects after ~41 seconds.
**Why it happens:** AgentManager was designed for CLI use (synchronous). All its methods do blocking I/O.
**How to avoid:** Wrap EVERY AgentManager call in `asyncio.to_thread()`. Also wrap `load_config()`, `generate_project_status()`, and any file reads.
**Warning signs:** "Heartbeat blocked for more than N seconds" in logs. Bot goes offline during command execution.

### Pitfall 2: Discord Message Length Limit (2000 chars)
**What goes wrong:** `!status` with many agents produces output exceeding 2000 characters. Discord silently truncates or rejects the message.
**Why it happens:** generate_project_status() output scales with agent count.
**How to avoid:** Use embeds (6000 char total limit, 1024 per field). For very long output, paginate or use threads. Always check length before sending.
**Warning signs:** HTTPException with code 50035 ("Invalid Form Body").

### Pitfall 3: Category Channel Limits
**What goes wrong:** Discord guilds have a 500 channel limit total and 50 channels per category.
**Why it happens:** Each project creates 6+ channels (5 standard + N agent channels).
**How to avoid:** For v1 single-project, this is not a real concern. But validate channel count before creation and provide clear error if limits are hit.

### Pitfall 4: MonitorLoop Callbacks Are Synchronous
**What goes wrong:** MonitorLoop.on_agent_dead and on_agent_stuck are synchronous callbacks (they accept `Callable[[str], None]`). But posting to Discord requires async. Using `asyncio.run()` inside the callback creates a nested event loop error.
**Why it happens:** The callbacks were designed for Phase 3 without knowing the consumer would be async.
**How to avoid:** The monitor loop already runs checks via `asyncio.to_thread()`. The callbacks fire from within those threads. Use `bot.loop.call_soon_threadsafe()` combined with `asyncio.run_coroutine_threadsafe()` to schedule the async Discord send from the sync callback context.
**Example:**
```python
def _make_sync_callback(coro_factory):
    """Wrap an async callback for use in sync MonitorLoop callbacks."""
    def sync_wrapper(*args, **kwargs):
        coro = coro_factory(*args, **kwargs)
        future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
        # Don't block waiting for result — fire and forget
    return sync_wrapper
```

### Pitfall 5: Bot Token Exposure
**What goes wrong:** Bot token committed to git or visible in agent clones.
**Why it happens:** Token loaded from env var but accidentally logged or included in config files.
**How to avoid:** Use pydantic-settings to load from `.env` (gitignored). Never log the token. Never pass it to agent clone environments.

### Pitfall 6: Race Between on_ready and Command Execution
**What goes wrong:** A user sends a command before `on_ready` finishes (role creation, channel lookup). Bot crashes or sends confusing errors.
**Why it happens:** discord.py fires `on_ready` after connecting, but commands are already registered.
**How to avoid:** Set a `self._ready` flag. Check it in `cog_check` or a global bot check. Return "Bot is starting up, please wait..." if not ready.

### Pitfall 7: on_ready Fires Multiple Times
**What goes wrong:** `on_ready` is called again after reconnection. Role creation, channel setup, or monitor task creation runs again, creating duplicates.
**Why it happens:** discord.py fires on_ready after every resume/reconnect.
**How to avoid:** Guard all one-time setup with a `self._initialized` flag. Check `if self._initialized: return` at the top of on_ready.

## Code Examples

### BotConfig with pydantic-settings
```python
# Source: pydantic-settings docs
from pydantic_settings import BaseSettings

class BotConfig(BaseSettings):
    discord_bot_token: str
    discord_guild_id: int
    project_dir: str = "."

    model_config = {"env_prefix": "", "env_file": ".env"}
```

### Click Command for vco bot
```python
# Add to cli/main.py or cli/bot_cmd.py
import click

@click.command()
@click.option("--project-dir", type=click.Path(exists=True), default=".")
def bot(project_dir: str) -> None:
    """Start the Discord bot."""
    from vcompany.bot.client import VcoBot
    from vcompany.bot.config import BotConfig

    cfg = BotConfig()
    bot_instance = VcoBot(Path(project_dir), load_config(Path(project_dir) / "agents.yaml"))
    bot_instance.run(cfg.discord_bot_token)
```

### Status Embed Builder
```python
# Source: discord.py Embed API
def build_status_embed(status_text: str) -> discord.Embed:
    embed = discord.Embed(
        title="Agent Fleet Status",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )
    # Split by agent sections (## AGENT_ID lines)
    sections = status_text.split("## ")[1:]  # skip header
    for section in sections[:25]:  # max 25 embed fields
        lines = section.strip().split("\n")
        name = lines[0][:256]  # field name max 256 chars
        value = "\n".join(lines[1:])[:1024]  # field value max 1024 chars
        if name and value:
            embed.add_field(name=name, value=value, inline=False)
    return embed
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw reactions for buttons | discord.ui.View + Button | discord.py 2.0 (2022) | Proper interaction handling, ephemeral responses, timeouts |
| `@bot.event` for everything | Cogs + setup_hook + load_extension | discord.py 2.0+ | Modular, hot-reloadable, testable |
| Sync `bot.run()` with subprocess | `asyncio.to_thread()` | Python 3.9+ | Clean bridge between sync library code and async bot |
| Manual heartbeat management | Built-in reconnect handling | discord.py 2.x | Automatic session resume, no custom WebSocket code needed |

## Open Questions

1. **MonitorLoop callback signature mismatch**
   - What we know: MonitorLoop callbacks are `Callable[[str], None]` (sync). AlertsCog needs async to post to Discord.
   - What's unclear: Whether to change the callback signature in MonitorLoop (breaking change) or bridge sync->async at the bot layer.
   - Recommendation: Bridge at bot layer using `asyncio.run_coroutine_threadsafe()`. Do NOT change MonitorLoop signatures -- that would break Phase 3's interface contract.

2. **on_plan_detected callback has different signature**
   - What we know: `on_plan_detected: Callable[[str, Path], None]` takes agent_id + plan path.
   - What's unclear: PlanReviewCog is a placeholder -- how much should it do?
   - Recommendation: Wire the callback to post a simple "New plan detected for {agent_id}" message to #plan-review. Phase 5 replaces this with full plan gate logic.

3. **Project directory discovery for vco bot**
   - What we know: CLI commands use `--project-dir` flag.
   - What's unclear: How does the bot know which project dir to use when started?
   - Recommendation: `vco bot --project-dir /path/to/project` or default to cwd. BotConfig can also accept `PROJECT_DIR` env var.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24.x |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_bot*.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DISC-01 | Cog architecture loads 4 cogs | unit | `uv run pytest tests/test_bot_client.py::test_cogs_loaded -x` | Wave 0 |
| DISC-02 | Channel structure created on new-project | unit | `uv run pytest tests/test_channel_setup.py -x` | Wave 0 |
| DISC-03 | !new-project creates thread + channels | unit | `uv run pytest tests/test_commands_cog.py::test_new_project -x` | Wave 0 |
| DISC-04 | !dispatch calls AgentManager.dispatch | unit | `uv run pytest tests/test_commands_cog.py::test_dispatch -x` | Wave 0 |
| DISC-05 | !status returns embed from project status | unit | `uv run pytest tests/test_commands_cog.py::test_status -x` | Wave 0 |
| DISC-06 | !standup scaffolded | unit | `uv run pytest tests/test_commands_cog.py::test_standup_scaffold -x` | Wave 0 |
| DISC-07 | !kill terminates agent with confirmation | unit | `uv run pytest tests/test_commands_cog.py::test_kill -x` | Wave 0 |
| DISC-08 | !relaunch restarts agent | unit | `uv run pytest tests/test_commands_cog.py::test_relaunch -x` | Wave 0 |
| DISC-09 | !integrate scaffolded | unit | `uv run pytest tests/test_commands_cog.py::test_integrate_scaffold -x` | Wave 0 |
| DISC-10 | Role check blocks unauthorized users | unit | `uv run pytest tests/test_commands_cog.py::test_role_check -x` | Wave 0 |
| DISC-11 | Blocking calls use asyncio.to_thread | unit | `uv run pytest tests/test_commands_cog.py::test_async_thread -x` | Wave 0 |
| DISC-12 | Reconnect flushes alert buffer | unit | `uv run pytest tests/test_alerts_cog.py::test_reconnect_flush -x` | Wave 0 |

### Testing Strategy for discord.py
Discord.py bots cannot be meaningfully integration-tested without a real Discord server. All tests use **mocked discord objects**:
- `MagicMock` for `discord.Guild`, `discord.TextChannel`, `discord.Role`, `discord.Member`
- `AsyncMock` for async methods (`guild.create_category_channel`, `channel.send`, etc.)
- `commands.Context` mocked with author, guild, and send attributes
- `VcoBot` instantiated with mocked intents, or individual Cog methods tested directly

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_bot*.py tests/test_channel_setup.py tests/test_commands_cog.py tests/test_alerts_cog.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before verify

### Wave 0 Gaps
- [ ] `tests/test_bot_client.py` -- covers DISC-01 (cog loading, setup_hook)
- [ ] `tests/test_channel_setup.py` -- covers DISC-02 (channel creation, permissions)
- [ ] `tests/test_commands_cog.py` -- covers DISC-03 through DISC-11 (all commands, role checks)
- [ ] `tests/test_alerts_cog.py` -- covers DISC-12 (buffer, flush on reconnect, callback wiring)
- [ ] `tests/test_confirm_view.py` -- covers D-03 (confirmation button interaction)
- [ ] `tests/test_bot_config.py` -- covers D-21 (env var loading)
- [ ] discord.py dependency: `uv add "discord.py>=2.7,<3"` -- must be installed before tests

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Everything | Yes | 3.12.3 | -- |
| discord.py | Bot framework | No (not installed) | -- | Must `uv add "discord.py>=2.7,<3"` |
| pytest-asyncio | Async tests | Yes (in dev deps) | 0.24.x | -- |
| Discord Bot Token | Bot runtime | Unknown | -- | Cannot run bot without token; tests use mocks |
| Discord Guild | Bot runtime | Unknown | -- | Cannot run bot without guild; tests use mocks |

**Missing dependencies with no fallback:**
- discord.py must be added to pyproject.toml before any bot code can be written or tested

**Missing dependencies with fallback:**
- Discord Bot Token and Guild ID: not needed for unit tests (mocked), but needed for manual integration testing

## Project Constraints (from CLAUDE.md)

- **Discord-first:** All human interaction through Discord
- **Project-agnostic:** No hardcoded assumptions about what agents build
- **Single machine:** All agents, monitor, and bot on one machine for v1
- **GSD workflow:** Use GSD entry points, not direct edits
- **uv for package management**
- **ruff for linting/formatting**
- **pytest + pytest-asyncio for testing**
- **src layout with hatchling build backend**

## Sources

### Primary (HIGH confidence)
- discord.py PyPI -- version 2.7.1 confirmed via `pip index versions`
- [discord.py Cogs documentation](https://discordpy.readthedocs.io/en/stable/ext/commands/cogs.html)
- [discord.py confirm View example](https://github.com/Rapptz/discord.py/blob/master/examples/views/confirm.py) -- official confirmation pattern
- Existing codebase: AgentManager, MonitorLoop, CrashTracker callback signatures examined directly

### Secondary (MEDIUM confidence)
- [discord.py guild.create_category_channel](https://github.com/Rapptz/discord.py/blob/master/discord/guild.py) -- permission overwrites pattern
- [discord.py has_role check](https://discordpy.readthedocs.io/en/stable/ext/commands/commands.html) -- role-based permission decorator

### Tertiary (LOW confidence)
- None -- all findings verified against official sources or codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- discord.py 2.7.1 is verified, well-documented, and already specified in STACK.md
- Architecture: HIGH -- Cog pattern is standard discord.py, all integration points verified in existing code
- Pitfalls: HIGH -- gateway disconnect and event loop blocking are well-documented in project PITFALLS.md and discord.py docs
- Testing: MEDIUM -- discord.py mock patterns are community-established but not officially documented

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable domain, discord.py 2.x is mature)
