# Quick Task: Implement vco up and Strategist-first Architecture - Research

**Researched:** 2026-03-26
**Domain:** discord.py slash commands, tmux session management, CLI architecture
**Confidence:** HIGH

## Summary

This task converts vCompany from a project-required bot to a Strategist-first system where `vco up` starts the Discord bot + Strategist + monitor without needing an initialized project. The bot's prefix commands (!) become slash commands (/), and the Strategist runs as a persistent Claude Code session in a tmux pane with Discord messages relayed to/from it.

**Primary recommendation:** Use discord.py `app_commands.command()` decorator in Cogs (not hybrid commands), create a new `vco up` CLI command that manages a `vco-system` tmux session with named windows, and make the Strategist a tmux-backed Claude Code interactive session instead of CLI `-p` invocations.

## Project Constraints (from CLAUDE.md)

- discord.py 2.7.x (confirmed installed: 2.7.1)
- click 8.2.x for CLI
- libtmux 0.55.x via TmuxManager (single import boundary in `src/vcompany/tmux/session.py`)
- No web UI -- Discord is the interface
- Single machine operation

## 1. Converting Prefix Commands to Slash Commands

### Pattern: app_commands.command() in Cogs

discord.py 2.x supports `app_commands.command()` decorator directly in Cogs. When a Cog is loaded via `add_cog()`, its app commands are automatically added to the bot's `CommandTree`.

**Confidence:** HIGH (official discord.py docs + community examples)

```python
from discord import app_commands
from discord.ext import commands

class CommandsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="status", description="Show project status")
    async def status_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Status...")
```

### Key Differences from Prefix Commands

| Prefix (`commands.command`) | Slash (`app_commands.command`) |
|---|---|
| `ctx: commands.Context` | `interaction: discord.Interaction` |
| `await ctx.send(...)` | `await interaction.response.send_message(...)` |
| Multiple `ctx.send()` calls OK | One `response`, then `interaction.followup.send()` |
| `@is_owner()` custom check | `@app_commands.check()` or `app_commands.default_permissions()` |
| No registration needed | Must call `bot.tree.sync()` once |

### Syncing the Command Tree

Slash commands must be synced to Discord's API. Do this in `setup_hook` or `on_ready`:

```python
async def setup_hook(self) -> None:
    for ext in _COG_EXTENSIONS:
        await self.load_extension(ext)
    # Sync to specific guild for instant availability (global takes ~1hr)
    guild = discord.Object(id=self._guild_id)
    self.tree.copy_global_to(guild=guild)
    await self.tree.sync(guild=guild)
```

**Pitfall:** Global command sync takes up to 1 hour to propagate. Always use guild-specific sync for development/single-guild bots. `copy_global_to()` + `sync(guild=...)` makes commands appear instantly.

### Permission Check Migration

Replace `@is_owner()` with `app_commands.default_permissions()` or a custom check:

```python
@app_commands.command(name="dispatch")
@app_commands.default_permissions(administrator=True)
async def dispatch_cmd(self, interaction: discord.Interaction, agent_id: str) -> None:
    ...
```

Or keep the role-based check with `app_commands.check()`:

```python
def is_owner_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        return any(r.name == "vco-owner" for r in interaction.user.roles)
    return app_commands.check(predicate)
```

### Intents Change

Slash commands do NOT require `message_content` intent. However, the Strategist on_message listener still needs it to relay messages from #strategist channel. Keep `intents.message_content = True`.

## 2. Bot Without a Project

### Current State

`VcoBot.__init__` requires `project_dir: Path` and `config: ProjectConfig`. The `vco bot` command fails if `agents.yaml` doesn't exist. All cogs assume `self.bot.project_config` is populated.

### Approach: Make project_config Optional

```python
class VcoBot(commands.Bot):
    def __init__(self, guild_id: int, project_dir: Path | None = None, config: ProjectConfig | None = None):
        ...
        self.project_dir = project_dir
        self.project_config = config
```

Cogs that require a project (CommandsCog commands like /dispatch, /status, /integrate) should check `self.bot.project_config is not None` and respond with "No project loaded. Use /new-project first."

StrategistCog and AlertsCog should work without a project.

### on_ready Split

Current `on_ready` initializes AgentManager, MonitorLoop, CrashTracker -- all require a project. Split into:
- **Always:** Role creation, channel resolution, StrategistCog initialization
- **If project loaded:** AgentManager, MonitorLoop, CrashTracker, PM injection

## 3. Strategist as tmux-backed Claude Code Session

### Current Implementation

`StrategistConversation` runs `claude -p --output-format json` per message (non-interactive, stateless invocations with session resume). This works but doesn't give the Strategist a visible, inspectable tmux pane.

### New Approach: Interactive Claude Code in tmux

Instead of using `-p` (print mode), run an interactive Claude Code session in a dedicated tmux pane. Messages are relayed by sending keystrokes to the pane and capturing output.

**Architecture:**

```
Discord #strategist  <-->  StrategistCog  <-->  tmux pane (claude --resume $SESSION)
```

**Two implementation options:**

**Option A: Keep current `-p` approach, add tmux pane for visibility only.**
Run a `claude` interactive session in a tmux pane purely for the owner to watch, but actual message processing still uses `-p` invocations with `--session-id`/`--resume`. This is simpler and more reliable -- tmux pane output parsing is fragile.

**Option B: Full tmux relay -- send keystrokes, parse pane output.**
Send user messages via `pane.send_keys()`, capture response by polling `pane.capture_pane()`. This is fragile -- you'd need to detect when Claude finishes responding, handle multi-line output, deal with terminal control characters, etc.

**Recommendation: Option A.** Keep the current CLI-based conversation mechanism (it already works with session persistence via `--session-id`/`--resume`). Add a tmux pane that runs an interactive `claude` session the owner can optionally inspect, but don't relay through it. The StrategistCog continues to use `StrategistConversation` (CLI `-p` mode) for reliable programmatic interaction.

**If the user specifically wants relay-through-tmux**, here's the pattern:

```python
# Send message to tmux pane
pane.send_keys(f"/user:message {user_message}")

# Poll for response (fragile)
import time
time.sleep(1)  # wait for processing
output = pane.capture_pane()
# Parse output to extract response...
```

This is unreliable. Stick with Option A unless explicitly required.

## 4. tmux Session Layout for `vco up`

### Session Structure

```
vco-system (tmux session)
  |-- strategist (window) -- Claude Code interactive session
  |-- monitor (window) -- Monitor loop with Rich log output
  |-- [agent-{id}] (windows) -- Added dynamically when dispatched
```

### TmuxManager Extensions Needed

Current `TmuxManager` supports `create_session`, `create_pane`, `send_command`. Need:

```python
def get_session(self, name: str) -> libtmux.Session | None:
    """Get existing session by name."""
    return self._server.sessions.get(session_name=name)

def get_or_create_session(self, name: str) -> libtmux.Session:
    """Get existing session or create new one."""
    session = self.get_session(name)
    if session:
        return session
    return self.create_session(name)
```

### vco up Command Implementation

```python
@click.command()
@click.option("--log-level", default="INFO")
def up(log_level: str) -> None:
    """Start vCompany system: Discord bot + Strategist + Monitor."""
    from vcompany.tmux.session import TmuxManager

    tmux = TmuxManager()
    session = tmux.create_session("vco-system")

    # Window 1: Strategist (interactive Claude Code)
    strat_window = session.active_window
    strat_window.rename_window("strategist")
    strat_pane = strat_window.active_pane
    tmux.send_command(strat_pane, "claude --resume vco-strategist --system-prompt-file ...")

    # Window 2: Monitor (placeholder until project loaded)
    mon_window = session.new_window(window_name="monitor")
    mon_pane = mon_window.active_pane
    tmux.send_command(mon_pane, "echo 'Monitor: waiting for project...'")

    # Run bot in foreground (blocking)
    # Bot connects to Discord, StrategistCog handles message relay
    bot_config = BotConfig()
    bot = VcoBot(guild_id=bot_config.discord_guild_id)
    bot.run(bot_config.discord_bot_token)
```

### Agent Panes Added Dynamically

When `/dispatch` runs, it creates new windows in the `vco-system` session:

```python
agent_window = session.new_window(window_name=f"agent-{agent_id}")
```

## 5. Strategist System Prompt Content

The Strategist system prompt should cover:

1. **Identity:** "You are the Strategist for vCompany, an autonomous multi-agent development system."
2. **vCompany workflow overview:** Projects have a blueprint, agents.yaml defines agent roster, agents run GSD pipelines in isolated clones.
3. **Available commands the user can trigger:** `/new-project`, `/dispatch`, `/status`, `/kill`, `/relaunch`, `/standup`, `/integrate`
4. **Project creation flow:** User describes product -> Strategist helps define blueprint -> user runs `/new-project` -> defines agents.yaml -> `/dispatch all`
5. **Decision authority:** Strategist can answer agent questions, review plans, escalate to owner when uncertain
6. **What it can guide:** Architecture decisions, agent task decomposition, milestone scoping, interface contract design

The persona file already exists at a configurable path (`strategist_persona_path` in BotConfig). Extend it or replace it.

## Common Pitfalls

### Pitfall 1: Interaction Response Timeout
**What:** Slash command interactions expire after 3 seconds if not responded to.
**Prevention:** Use `await interaction.response.defer()` for slow operations, then `await interaction.followup.send()`.

### Pitfall 2: Double Sync
**What:** Calling `tree.sync()` on every `on_ready` (fires on reconnect) wastes rate limit.
**Prevention:** Sync in `setup_hook` (fires once) not `on_ready`.

### Pitfall 3: Global vs Guild Commands
**What:** Global commands take up to 1 hour to propagate after sync.
**Prevention:** Use `copy_global_to(guild=...)` + `sync(guild=...)` for immediate availability.

### Pitfall 4: cog_check Not Available for app_commands
**What:** `cog_check` only applies to prefix commands. App commands need their own check mechanism.
**Prevention:** Use `app_commands.check()` decorator or `interaction_check` method on the Cog.

### Pitfall 5: send_message vs followup
**What:** `interaction.response.send_message()` can only be called once. Second call raises `InteractionResponded`.
**Prevention:** Use `interaction.followup.send()` for subsequent messages. For streaming, defer first then use followup.

## Architecture Summary

```
vco up
  |
  +-- Creates tmux session "vco-system"
  |     |-- window "strategist": interactive claude session (visual only)
  |     |-- window "monitor": monitor loop output
  |     +-- window "agent-X": added by /dispatch (dynamic)
  |
  +-- Starts VcoBot (no project required)
        |-- StrategistCog: relays #strategist <-> StrategistConversation (CLI -p)
        |-- CommandsCog: slash commands, project-gated
        |-- AlertsCog: works without project (just no alerts)
        +-- PlanReviewCog: works without project (just no reviews)
```

## Sources

### Primary (HIGH confidence)
- discord.py 2.7.1 installed and verified
- [Discord.py Masterclass - Slash Commands](https://fallendeity.github.io/discord.py-masterclass/slash-commands/) - Cog patterns, GroupCog, sync
- [discord.py official Cogs docs](https://discordpy.readthedocs.io/en/stable/ext/commands/cogs.html)
- Existing codebase: `src/vcompany/bot/client.py`, `src/vcompany/bot/cogs/commands.py`, `src/vcompany/tmux/session.py`
- Claude CLI `--help` output (verified `--session-id`, `--resume`, `--system-prompt` flags)

### Secondary (MEDIUM confidence)
- [GitHub Discussion #8372 - app_commands in Cogs](https://github.com/Rapptz/discord.py/discussions/8372)
- [AbstractUmbra's discord.py examples](https://about.abstractumbra.dev/dpy) (community reference)
