# Architecture Patterns: v3.0 CLI-First Runtime Daemon

**Domain:** CLI-first runtime daemon rewrite for multi-agent orchestration system
**Researched:** 2026-03-29
**Confidence:** HIGH (based on direct codebase inspection + Python stdlib documentation)

## Current Architecture (What Exists)

```
vco up
  └── VcoBot (discord.py commands.Bot)
        ├── on_ready() -- owns ALL initialization (~300 lines)
        │   ├── Creates CompanyRoot + supervision tree
        │   ├── Wires ~15 callback closures inline
        │   ├── Creates TmuxManager, MessageQueue, Strategist
        │   └── Wires PM backlog, event sinks, review gates
        ├── Cogs (9 loaded)
        │   ├── CommandsCog -- /new-project duplicates on_ready wiring
        │   ├── StrategistCog -- forwards messages to CompanyAgent
        │   ├── PlanReviewCog, HealthCog, TaskRelayCog, etc.
        │   └── WorkflowOrchestratorCog, WorkflowMasterCog
        └── close() -- tears down message queue + company_root

vco CLI (click) -- 10 commands, mostly disconnected
  ├── vco up       -- starts bot (blocking bot.run())
  ├── vco init     -- project scaffolding (standalone)
  ├── vco clone    -- git clone per agent (standalone)
  ├── vco report   -- agent posts to Discord (standalone, no runtime)
  └── ... (monitor, preflight, sync-context, new-milestone, restart, bot)
```

### Specific Problems to Solve

1. **Bot owns CompanyRoot.** `VcoBot.on_ready()` creates and owns the supervision tree. Bot crash = total system failure. No graceful degradation.
2. **CLI cannot reach the tree.** No `vco hire`, `vco status`, `vco give-task`. The CLI has zero access to running containers or their state.
3. **Callback closure explosion.** on_ready() defines 15+ inline closures for PM events, health changes, escalations, task assignment, agent recruitment, etc. CommandsCog.new_project() duplicates most of it (~100 lines copy-paste).
4. **Strategist cannot act.** Runs `claude -p` with Bash but has no CLI commands to hire/task/dismiss agents. The `[CMD:hire ...]` tag parsing approach is confirmed broken and wrong.
5. **No state persistence.** Container states, task queues, pane IDs are in-memory. Daemon restart = rebuild everything from scratch.

## Recommended Architecture

```
                    ┌─────────────────────────┐
                    │     vco CLI (click)      │
                    │  hire, give-task, dismiss │
                    │  status, health, up      │
                    │  new-project             │
                    └───────────┬──────────────┘
                                │ Unix socket (NDJSON)
                    ┌───────────▼──────────────┐
                    │    Runtime Daemon (vcod)  │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │  Socket Server      │  │
                    │  │  asyncio.start_     │  │
                    │  │  unix_server()      │  │
                    │  └─────────┬───────────┘  │
                    │            │               │
                    │  ┌─────────▼───────────┐  │
                    │  │  RuntimeAPI          │  │
                    │  │  (single gateway)    │  │
                    │  └─────────┬───────────┘  │
                    │            │               │
                    │  ┌─────────▼───────────┐  │
                    │  │  CompanyRoot         │  │
                    │  │  (existing, moved)   │  │
                    │  │  ├─ Scheduler        │  │
                    │  │  ├─ CompanyAgents    │  │
                    │  │  └─ ProjectSupvs     │  │
                    │  └─────────────────────┘  │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │  StatePersistence    │  │
                    │  │  (aiosqlite)         │  │
                    │  └─────────────────────┘  │
                    │                           │
                    │  ┌─────────────────────┐  │
                    │  │  VcoBot (in-process) │  │
                    │  │  (thin relay)        │  │
                    │  └─────────────────────┘  │
                    └───────────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                   │
    ┌─────────▼──────┐  ┌──────▼───────┐  ┌───────▼──────┐
    │  Discord API   │  │  Strategist  │  │  Future UIs  │
    │  (via bot)     │  │  (Bash:      │  │              │
    │                │  │  vco hire)   │  │              │
    └────────────────┘  └──────────────┘  └──────────────┘
```

### Component Boundaries

| Component | Responsibility | New/Modified | Communicates With |
|-----------|---------------|--------------|-------------------|
| **VcoRuntime** (`vcompany/runtime/daemon.py`) | Daemon lifecycle: start/stop CompanyRoot, socket server, bot. PID file, signal handling. | NEW | All components (owns them) |
| **VcoSocketServer** (`vcompany/runtime/server.py`) | Accept Unix socket connections, parse NDJSON requests, route to RuntimeAPI, return responses, push events to subscribers | NEW | RuntimeAPI (calls), clients (socket) |
| **RuntimeAPI** (`vcompany/runtime/api.py`) | Single gateway for ALL operations. dispatch() routes method to handler. Both socket and in-process bot use this. | NEW | CompanyRoot (calls), StatePersistence (calls) |
| **VcoClient** (`vcompany/runtime/client.py`) | Async + sync socket client library. Used by CLI commands. | NEW | VcoSocketServer (socket) |
| **StatePersistence** (`vcompany/runtime/persistence.py`) | Snapshot/restore container identity, config, task queues to SQLite. Recovery on daemon restart. | NEW | CompanyRoot (hooks), aiosqlite |
| **CompanyRoot** (existing) | Supervision tree, agent lifecycle, health, scheduling. Unchanged core logic. | MINOR MODS | RuntimeAPI (called by), tmux, per-agent SQLite |
| **VcoBot** (existing) | Discord API skin. Slash commands and message handlers call RuntimeAPI. No CompanyRoot ownership. | MAJOR MODS | RuntimeAPI (calls), Discord API |
| **CLI commands** (existing + new) | Thin clients: parse args, call VcoClient, format output. | EXTENDED | VcoClient (calls) |

### Data Flow

**CLI command flow (`vco hire researcher market-scout`):**
```
1. CLI parses args, creates VcoClientSync
2. VcoClientSync connects to /tmp/vco-runtime.sock
3. Sends: {"method":"hire","params":{"agent_id":"market-scout","template":"researcher"}}\n
4. Daemon's RuntimeAPI.hire() calls CompanyRoot.hire()
5. CompanyRoot creates scratch dir, deploys artifacts, starts tmux
6. StatePersistence snapshots the new container
7. Response: {"ok":true,"result":{"agent_id":"market-scout","state":"running"}}\n
8. CLI prints: "Hired market-scout (researcher template)"
```

**Bot slash command flow (`/health`):**
```
1. User invokes /health in Discord
2. HealthCog calls self.bot.runtime_api.health_tree() (in-process, no socket)
3. RuntimeAPI calls CompanyRoot.health_tree(), serializes via Pydantic .model_dump()
4. HealthCog formats as Discord embed, sends to channel
```

**Strategist autonomy flow (`vco hire` via Bash tool):**
```
1. Strategist's Claude session runs: vco hire researcher market-scout
2. Identical to CLI flow -- Unix socket, same RuntimeAPI method
3. No callback parsing, no [CMD:...] tags, no special wiring
```

**Event subscription flow (bot receives state changes):**
```
1. Bot connects to socket, sends: {"method":"subscribe","params":{"events":["health_change","escalation"]}}\n
2. Connection stays open (long-lived)
3. When agent state changes, RuntimeAPI pushes: {"event":"health_change","data":{...}}\n
4. Bot's event loop reads the push, posts to Discord
```

## New Modules to Create

### `vcompany/runtime/__init__.py`

Package marker for the runtime daemon subsystem.

### `vcompany/runtime/daemon.py` -- VcoRuntime

The daemon process lifecycle manager.

```python
class VcoRuntime:
    """Long-lived runtime daemon managing CompanyRoot + socket API + bot."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.company_root: CompanyRoot | None = None
        self.api: RuntimeAPI | None = None
        self.server: VcoSocketServer | None = None
        self.persistence: StatePersistence | None = None
        self.bot: VcoBot | None = None

    async def start(self) -> None:
        """1. Open persistence DB
        2. Create CompanyRoot
        3. Restore state from DB (re-add projects, re-hire agents)
        4. Start socket server
        5. Create and start bot (in-process, same event loop)
        6. Write PID file"""
        ...

    async def stop(self) -> None:
        """1. Persist current state
        2. Stop bot
        3. Stop socket server
        4. Stop CompanyRoot (stops all agents, kills tmux panes)
        5. Remove PID file"""
        ...
```

**Key decision: Bot runs in-process as a coroutine, not as a subprocess.** Rationale:
- discord.py is asyncio-native, shares the event loop naturally
- Avoids IPC complexity (no need for bot-to-daemon socket connection)
- Bot crash can be caught and restarted without killing the daemon (wrap in try/except + asyncio.Task)
- Bot calls RuntimeAPI directly through a shared reference (fast, no serialization)
- The architectural boundary is enforced by the RuntimeAPI abstraction, not by process isolation

### `vcompany/runtime/server.py` -- VcoSocketServer

```python
SOCKET_PATH = Path(os.environ.get("VCO_SOCKET", "/tmp/vco-runtime.sock"))

class VcoSocketServer:
    """Newline-delimited JSON (NDJSON) protocol over Unix domain socket."""

    def __init__(self, api: RuntimeAPI, socket_path: Path = SOCKET_PATH):
        self.api = api
        self.socket_path = socket_path
        self._server: asyncio.Server | None = None
        self._subscribers: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        self.socket_path.unlink(missing_ok=True)
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self.socket_path)
        )
        os.chmod(str(self.socket_path), 0o600)  # owner read/write only

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                request = json.loads(line.decode())
                # Subscribe requests keep connection open
                if request.get("method") == "subscribe":
                    self._subscribers.add(writer)
                    continue
                response = await self.api.dispatch(request)
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self._subscribers.discard(writer)
            writer.close()

    async def push_event(self, event: str, data: dict) -> None:
        """Push event to all subscribers. Remove dead connections."""
        msg = json.dumps({"event": event, "data": data}).encode() + b"\n"
        dead: list[asyncio.StreamWriter] = []
        for writer in self._subscribers:
            try:
                writer.write(msg)
                await writer.drain()
            except (ConnectionResetError, BrokenPipeError):
                dead.append(writer)
        for w in dead:
            self._subscribers.discard(w)
```

### `vcompany/runtime/api.py` -- RuntimeAPI

The single gateway. This is the most important new abstraction. It replaces the 300 lines of inline wiring in on_ready().

```python
class RuntimeAPI:
    """Single gateway for all runtime operations.

    Both the socket server and the in-process bot call these methods.
    This is the ONLY way to interact with CompanyRoot from outside.
    """

    def __init__(
        self,
        company_root: CompanyRoot,
        persistence: StatePersistence,
        event_callback: Callable[[str, dict], Awaitable[None]] | None = None,
    ):
        self._root = company_root
        self._persistence = persistence
        self._emit = event_callback  # pushes to socket subscribers + bot
        self._handlers: dict[str, Callable] = {
            "ping": self.ping,
            "hire": self.hire,
            "give_task": self.give_task,
            "dismiss": self.dismiss,
            "status": self.status,
            "health_tree": self.health_tree,
            "new_project": self.new_project,
            "add_project": self.add_project,
            "remove_project": self.remove_project,
        }

    async def dispatch(self, request: dict) -> dict:
        method = request.get("method")
        params = request.get("params", {})
        handler = self._handlers.get(method)
        if handler is None:
            return {"ok": False, "error": f"Unknown method: {method}"}
        try:
            result = await handler(**params)
            return {"ok": True, "result": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def ping(self) -> dict:
        return {"pong": True, "state": self._root.state}

    async def hire(self, agent_id: str, template: str = "generic") -> dict:
        container = await self._root.hire(agent_id, template=template)
        await self._persistence.save_container_state(
            agent_id=agent_id, agent_type="task", template=template
        )
        return {"agent_id": agent_id, "state": container.state}

    async def give_task(self, agent_id: str, task: str) -> dict:
        container = await self._root._find_container(agent_id)
        if container is None:
            raise ValueError(f"Agent {agent_id} not found")
        await container.give_task(task)
        return {"agent_id": agent_id, "queued": True}

    async def dismiss(self, agent_id: str) -> dict:
        await self._root.dismiss(agent_id)
        await self._persistence.remove_container_state(agent_id)
        return {"agent_id": agent_id, "dismissed": True}

    async def health_tree(self) -> dict:
        tree = self._root.health_tree()
        return tree.model_dump(mode="json")

    async def status(self, agent_id: str | None = None) -> dict:
        if agent_id:
            container = await self._root._find_container(agent_id)
            if container is None:
                raise ValueError(f"Agent {agent_id} not found")
            report = container.health_report()
            return report.model_dump(mode="json")
        # All agents
        tree = self._root.health_tree()
        return tree.model_dump(mode="json")

    async def new_project(self, name: str) -> dict:
        """Composite: load config + init structure + clone repos + add to tree."""
        # This replaces both /new-project and the future vco new-project
        ...

    async def add_project(self, project_id: str, config_path: str) -> dict:
        """Add an existing project directory to the supervision tree."""
        ...

    async def remove_project(self, project_id: str) -> dict:
        await self._root.remove_project(project_id)
        await self._persistence.remove_project(project_id)
        return {"project_id": project_id, "removed": True}
```

### `vcompany/runtime/client.py` -- VcoClient

```python
class VcoClient:
    """Async client for the vco runtime socket API."""

    def __init__(self, socket_path: Path = SOCKET_PATH):
        self.socket_path = socket_path

    async def call(self, method: str, **params) -> dict:
        reader, writer = await asyncio.open_unix_connection(str(self.socket_path))
        request = {"method": method, "params": params}
        writer.write(json.dumps(request).encode() + b"\n")
        await writer.drain()
        line = await reader.readline()
        writer.close()
        await writer.wait_closed()
        response = json.loads(line.decode())
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "Unknown error"))
        return response.get("result", {})

    # Convenience methods
    async def hire(self, agent_id: str, template: str = "generic") -> dict:
        return await self.call("hire", agent_id=agent_id, template=template)

    async def give_task(self, agent_id: str, task: str) -> dict:
        return await self.call("give_task", agent_id=agent_id, task=task)

    async def dismiss(self, agent_id: str) -> dict:
        return await self.call("dismiss", agent_id=agent_id)

    async def health_tree(self) -> dict:
        return await self.call("health_tree")

    async def status(self, agent_id: str | None = None) -> dict:
        params = {"agent_id": agent_id} if agent_id else {}
        return await self.call("status", **params)

    async def ping(self) -> dict:
        return await self.call("ping")


class VcoClientSync:
    """Synchronous wrapper for CLI commands (click is sync)."""

    def __init__(self, socket_path: Path = SOCKET_PATH):
        self._path = socket_path

    def call(self, method: str, **params) -> dict:
        async def _do():
            client = VcoClient(self._path)
            return await client.call(method, **params)
        return asyncio.run(_do())

    def hire(self, agent_id: str, template: str = "generic") -> dict:
        return self.call("hire", agent_id=agent_id, template=template)

    # ... same pattern for all methods
```

### `vcompany/runtime/persistence.py` -- StatePersistence

Uses aiosqlite (already a project dependency for MemoryStore).

```python
class StatePersistence:
    """Persist daemon state to SQLite for restart recovery.

    This is daemon-level state, separate from per-agent MemoryStores.

    Tables:
    - containers: agent_id, agent_type, template, project_id, config_json
    - projects: project_id, config_path, agents_yaml_content
    - task_queue: agent_id, task_text, queued_at
    - scheduler: agent_id, interval_seconds, next_wake
    """

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()

    async def save_container_state(self, agent_id: str, agent_type: str,
                                    template: str = "", project_id: str | None = None,
                                    config_json: str = "{}") -> None: ...

    async def remove_container_state(self, agent_id: str) -> None: ...

    async def save_project(self, project_id: str, config_path: str) -> None: ...

    async def remove_project(self, project_id: str) -> None: ...

    async def save_pending_task(self, agent_id: str, task: str) -> None: ...

    async def get_pending_tasks(self, agent_id: str) -> list[str]: ...

    async def restore_all(self) -> tuple[list[dict], list[dict]]:
        """Return (projects, containers) for recovery."""
        ...

    async def close(self) -> None:
        if self._db:
            await self._db.close()
```

**What to persist vs what to rebuild:**

| Persist (survives restart) | Rebuild (transient) |
|---|---|
| Container identity: agent_id, type, template | Tmux pane IDs (panes die with daemon) |
| Container config: ContainerContext fields | FSM state (containers restart from creating) |
| Task queue contents (pending, undelivered) | Callback closures (rewired by RuntimeAPI) |
| Project association (project_id to agents) | Discord connections (bot reconnects) |
| Scheduler entries (interval, next wake) | In-memory health reports |

**Recovery flow on daemon restart:**
1. StatePersistence.open() -- connect to existing DB
2. StatePersistence.restore_all() -- read projects and containers
3. For each project: RuntimeAPI.add_project() with persisted config
4. For each company agent: RuntimeAPI.hire() with persisted template
5. For each agent with pending tasks: re-queue via RuntimeAPI.give_task()
6. Containers launch fresh tmux sessions -- agents resume from their own MemoryStore checkpoints (existing mechanism, no changes needed)

## Existing Modules: Modification Plan

### `vcompany/bot/client.py` (VcoBot) -- MAJOR CHANGES

**Remove from on_ready() (~250 lines):**
- CompanyRoot creation and startup
- TmuxManager creation
- All 15+ inline callback closures (on_escalation, on_health_change, claude_health_check, on_degraded, on_recovered, pm_event_sink, _on_strategist_response, _on_hire, _on_give_task, _on_dismiss, _on_assign_task, _on_trigger_integration_review, _on_recruit_agent, _on_remove_agent, _on_escalate_to_strategist, _on_send_intervention)
- ChildSpec building and add_project call
- PM backlog wiring
- PM event sink wiring
- Review gate callback wiring

**Keep in on_ready() (~30 lines):**
- Role creation (vco-owner)
- System channel setup
- Strategist channel initialization
- WorkflowMaster initialization
- Boot notifications

**Add:**
- `self.runtime_api: RuntimeAPI` -- injected by VcoRuntime on creation
- Event subscription setup (subscribe to health_change, escalation, etc.)

**New on_ready():**
```python
async def on_ready(self) -> None:
    if self._initialized:
        return
    guild = self.get_guild(self._guild_id)
    if guild is None:
        self._initialized = True
        return

    # Discord-only setup (roles, channels)
    await self._setup_roles_and_channels(guild)

    # Subscribe to runtime events for Discord notifications
    # (health_change -> post to #health, escalation -> post to #alerts)
    self._event_task = asyncio.create_task(self._process_runtime_events())

    self._initialized = True
    self._ready_flag = True
    await self._send_boot_notifications(guild)
```

**Remove attributes:**
- `self.company_root` -- owned by daemon now
- `self._tmux_manager` -- owned by daemon now
- `self._pm_container` -- accessed through RuntimeAPI
- `self.message_queue` -- stays but wiring simplifies

### `vcompany/bot/cogs/commands.py` (CommandsCog) -- MAJOR CHANGES

**/new-project simplifies from ~200 lines to ~10:**
```python
@app_commands.command(name="new-project")
async def new_project(self, interaction, name: str):
    await interaction.response.defer()
    result = await self.bot.runtime_api.new_project(name)
    await interaction.followup.send(
        f"Project **{name}** created with {result['agents']} agents."
    )
```

**/dispatch, /kill, /relaunch all simplify similarly.**

**Remove:**
- All CompanyRoot direct access
- All container direct access
- Duplicated supervision tree wiring

### `vcompany/bot/cogs/strategist.py` (StrategistCog) -- MODERATE CHANGES

**Remove:**
- `_execute_actions()` and `_CMD_PATTERN` regex
- CompanyAgent callback wiring (`set_company_agent()`)

**Simplify:** Strategist conversation management stays (it runs in-process), but agent management commands go through RuntimeAPI.

### `vcompany/agent/company_agent.py` (CompanyAgent) -- MODERATE CHANGES

**Remove:**
- `_on_hire`, `_on_give_task`, `_on_dismiss` callback attributes
- These operations go through RuntimeAPI now

### `vcompany/supervisor/company_root.py` (CompanyRoot) -- MINOR CHANGES

**Modify `hire()`:** Remove `guild` parameter. Discord channel creation is a bot concern, not a supervision tree concern. The RuntimeAPI can coordinate channel creation separately.

**Add:** Optional hooks for state persistence events (emit when container added/removed/state-changed).

### `vcompany/cli/main.py` -- EXTENDED

```python
# New commands added:
cli.add_command(hire)         # vco hire <agent-id> [--template researcher]
cli.add_command(give_task)    # vco give-task <agent-id> "<task>"
cli.add_command(dismiss)      # vco dismiss <agent-id>
cli.add_command(status)       # vco status [agent-id]
cli.add_command(health)       # vco health
cli.add_command(new_project)  # vco new-project <name>
cli.add_command(down)         # vco down (stop daemon)
```

### `vcompany/cli/up_cmd.py` -- MODIFIED

Currently creates VcoBot directly and calls `bot.run()`. Changes to:
1. Create VcoRuntime (which creates CompanyRoot + RuntimeAPI + bot internally)
2. Call `runtime.start()` (which starts socket server + bot)
3. Handle SIGTERM/SIGINT for graceful shutdown

## Patterns to Follow

### Pattern 1: NDJSON Request-Response Protocol

**What:** Every message is a single JSON object terminated by `\n`. Newline-delimited JSON (NDJSON) is simple to parse with `readline()`, debuggable with netcat/socat, and sufficient for this use case.

**Protocol:**
```
Request:  {"method": "string", "params": {}}\n
Success:  {"ok": true, "result": {}}\n
Error:    {"ok": false, "error": "message"}\n
Event:    {"event": "string", "data": {}}\n
```

**Why not JSON-RPC:** JSON-RPC adds request IDs and batch semantics we do not need. This is an internal API, not a public one. If multiplexing is needed later, add request IDs.

**Why not HTTP:** Adds HTTP parsing overhead and dependency (would need aiohttp or similar). Unix socket + NDJSON is lighter, faster, and perfectly suited for local IPC.

**Why not protobuf/msgpack:** JSON is human-readable and debuggable (`echo '{"method":"ping"}' | socat - UNIX-CONNECT:/tmp/vco-runtime.sock`). Performance is not a concern at <100 req/s.

### Pattern 2: RuntimeAPI as Single Gateway

**What:** All operations go through RuntimeAPI methods. The bot, CLI, socket server, and Strategist all use the same interface. Nobody holds a direct reference to CompanyRoot internals.

**Why this matters:** This is the architectural fix for the current problem. Today, VcoBot.on_ready() reaches into CompanyRoot._company_agents, wires callbacks into container._on_hire, accesses pm_container._project_state directly. RuntimeAPI encapsulates all of this behind a clean method interface.

**Enforcement:** VcoBot receives a `runtime_api: RuntimeAPI` reference. It never receives a `company_root: CompanyRoot` reference. Cogs access `self.bot.runtime_api`, never `self.bot.company_root`.

### Pattern 3: Event Push via Subscription

**What:** Clients subscribe to event streams over the socket. The daemon pushes events when state changes occur. This replaces the 15+ inline callback closures.

**How it works:**
1. Bot (or any client) sends `{"method": "subscribe", "params": {"events": ["health_change", "escalation"]}}` over a persistent socket connection
2. RuntimeAPI registers the subscriber's StreamWriter
3. When CompanyRoot emits a state change, RuntimeAPI serializes it and writes to all subscribers
4. Bot's event loop reads pushed events and routes to Discord

**For the in-process bot:** Since the bot runs in the same process, it can alternatively register a direct async callback instead of going through the socket. Both approaches work; the callback is simpler and avoids self-connection overhead.

### Pattern 4: PID File for Daemon Management

**What:** Write PID to `/tmp/vco-runtime.pid` on start. `vco up` checks for existing daemon. `vco down` sends SIGTERM.

```python
PID_PATH = Path("/tmp/vco-runtime.pid")

def is_daemon_running() -> int | None:
    """Return PID if daemon is running, None otherwise."""
    if not PID_PATH.exists():
        return None
    pid = int(PID_PATH.read_text().strip())
    try:
        os.kill(pid, 0)  # Check if process exists
        return pid
    except ProcessLookupError:
        PID_PATH.unlink()
        return None
```

### Pattern 5: Composite Commands via RuntimeAPI

**What:** `new_project` is a multi-step operation (load config, init dirs, clone repos, add to tree, wire callbacks). It lives as a single RuntimeAPI method, not spread across CLI and bot.

**Current duplication:** VcoBot.on_ready() does project init. CommandsCog.new_project() duplicates it. Both are ~200 lines. With RuntimeAPI.new_project(), there is one implementation called from everywhere.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Bot Holding Direct CompanyRoot References

**What:** `self.bot.company_root.hire(...)` or `self.bot.company_root._find_container(...)` from Cog code.
**Why bad:** Couples bot to supervision tree ownership. Prevents extracting bot to separate process later. Makes testing require full CompanyRoot setup.
**Instead:** `self.bot.runtime_api.hire(...)`. Always go through RuntimeAPI.

### Anti-Pattern 2: Inline Callback Closures for Cross-Component Wiring

**What:** The current pattern of 15+ `async def _on_*(...)` closures defined inside on_ready() and assigned to container attributes.
**Why bad:** Untestable (closures capture VcoBot state), duplicated (CommandsCog copies them), fragile (closures go stale if bot reconnects).
**Instead:** RuntimeAPI owns the wiring. Events flow through the event bus. Bot subscribes to events it cares about.

### Anti-Pattern 3: Persisting Tmux Pane IDs

**What:** Saving pane_id strings to disk for restart recovery.
**Why bad:** Tmux panes do not survive daemon restart. The old panes are orphaned or gone.
**Instead:** Persist container identity (agent_id, type, template, project). On restart, kill orphaned tmux sessions (`tmux kill-session -t vco-*`), then create fresh ones. Agents resume from their own MemoryStore checkpoints.

### Anti-Pattern 4: Subprocess for Bot-to-Daemon Communication

**What:** Bot Cogs shelling out to `vco hire ...` via `subprocess.run()`.
**Why bad:** Process spawn overhead, loses async context, error handling is stringly-typed, and it is a round-trip through the socket when the bot is in the same process.
**Instead:** Bot calls `self.runtime_api.hire(...)` directly (same process, same event loop). The RuntimeAPI abstraction provides the boundary, not process isolation.

### Anti-Pattern 5: Trying to Persist Everything

**What:** Saving FSM state, health reports, callback references, Discord connection state.
**Why bad:** These are transient by nature. FSM state is rebuilt when the container restarts. Health reports are regenerated on demand. Callbacks are rewired by the daemon. Discord state is owned by Discord.
**Instead:** Persist only what is needed to recreate containers: identity, config, and pending tasks.

## JSON Protocol Method Catalog

| Method | Params | Returns | Notes |
|--------|--------|---------|-------|
| `ping` | (none) | `{pong: true, state: "running"}` | Liveness check |
| `hire` | `agent_id`, `template?` | `{agent_id, state}` | Creates scratch dir, starts tmux |
| `give_task` | `agent_id`, `task` | `{agent_id, queued}` | Idle-gated delivery |
| `dismiss` | `agent_id` | `{agent_id, dismissed}` | Stops container, kills pane |
| `status` | `agent_id?` | `{agents: [...]}` or `{agent_id, state, ...}` | One or all |
| `health_tree` | (none) | CompanyHealthTree as JSON | Full tree via Pydantic |
| `new_project` | `name` | `{project, agents}` | Composite: init+clone+add |
| `add_project` | `project_id`, `config_path` | `{project_id, agent_count}` | Add existing to tree |
| `remove_project` | `project_id` | `{project_id, removed}` | Stop + clean up |
| `subscribe` | `events: [str]` | (stream of events) | Keeps connection open |

## Socket Path and PID File Conventions

```
Socket:   /tmp/vco-runtime.sock   (override: VCO_SOCKET env var)
PID:      /tmp/vco-runtime.pid    (override: VCO_PID env var)
State DB: ~/.vco/state/daemon.db  (override: VCO_STATE_DIR env var)
```

Use `/tmp/` for socket and PID because:
- Simple, universally writable on Linux
- Single-machine, single-user system
- Agent subprocesses (Claude Code hooks, Strategist Bash) can find it without config
- Cleaned up automatically on reboot

Use `~/.vco/` for persistent state because:
- Survives reboot (unlike /tmp)
- Per-user isolation
- Standard XDG-adjacent convention

## Scalability Considerations

| Concern | Current (v2) | After v3 | Notes |
|---------|-------------|----------|-------|
| Bot crash impact | Total system loss | Bot restarts, agents continue | Key improvement |
| CLI access | None | Full control via socket | Unblocks Strategist autonomy |
| Client connections | 1 (bot internal) | 3-5 (bot + CLI + Strategist) | Unix socket handles thousands |
| State recovery | None (rebuild everything) | SQLite snapshots | Resume in seconds |
| Socket throughput | N/A | Easily >100 req/s | Not a bottleneck for <10 agents |
| Testing | Requires Discord bot | RuntimeAPI testable in isolation | Major DX improvement |

## Suggested Build Order

### Phase 1: Runtime daemon + socket server (foundation)
- Create `vcompany/runtime/` package
- VcoRuntime, VcoSocketServer, RuntimeAPI with `ping` + `health_tree`
- PID file management
- Modify `vco up` to start daemon (bot still runs in same process, still owns CompanyRoot temporarily)
- Validation: `echo '{"method":"ping"}' | socat - UNIX-CONNECT:/tmp/vco-runtime.sock`

### Phase 2: Extract CompanyRoot from bot to daemon
- VcoRuntime creates CompanyRoot (not VcoBot.on_ready())
- RuntimeAPI gets `hire`, `give_task`, `dismiss`, `status` methods
- Bot receives `runtime_api` reference instead of owning company_root
- Remove CompanyRoot creation from on_ready() and CommandsCog
- Replace callback closures with RuntimeAPI event routing

### Phase 3: CLI as API client
- VcoClient (async) and VcoClientSync (sync wrapper)
- New CLI commands: `vco hire`, `vco give-task`, `vco dismiss`, `vco status`, `vco health`
- **Strategist can now use `vco hire` via Bash** -- this is the highest-value deliverable

### Phase 4: Bot as thin relay
- CommandsCog gutted: all slash commands call RuntimeAPI
- StrategistCog simplified: no callback wiring
- on_ready() reduced to Discord-only setup (~30 lines from ~300)
- Event subscriptions replace callback closures

### Phase 5: State persistence
- StatePersistence class with aiosqlite
- Hooks into RuntimeAPI methods (save on hire, remove on dismiss)
- Recovery flow on daemon restart
- Test: kill daemon, restart, verify agents relaunch from persisted state

### Phase 6: `vco new-project` unification
- RuntimeAPI.new_project() as composite command
- Replaces both /new-project slash command and `vco new-project` CLI
- Single code path: load config, init dirs, clone repos, add to tree

**Phase ordering rationale:**
- Phase 1 is purely additive -- new package, no existing code changes, lowest risk
- Phase 2 is the hardest refactor but unblocks all subsequent phases
- Phase 3 is what the Strategist needs most urgently (vco hire via Bash)
- Phase 4 depends on Phase 2 (bot needs RuntimeAPI to exist first)
- Phase 5 is independent of 3/4 but lower priority (restart resilience < Strategist autonomy)
- Phase 6 builds on all previous work and eliminates the worst code duplication

## Sources

- [Python asyncio Streams documentation](https://docs.python.org/3/library/asyncio-stream.html) -- asyncio.start_unix_server(), StreamReader.readline() for NDJSON protocol (HIGH confidence)
- [PEP 3143 -- Standard daemon process library](https://peps.python.org/pep-3143/) -- daemon best practices, PID file conventions (HIGH confidence)
- [aiosqlite documentation](https://aiosqlite.omnilib.dev/) -- async SQLite, already used by MemoryStore in the project (HIGH confidence)
- Existing codebase: VcoBot.on_ready() at `src/vcompany/bot/client.py:107-614`, CompanyRoot at `src/vcompany/supervisor/company_root.py`, CLI at `src/vcompany/cli/main.py` (HIGH confidence -- direct code inspection)
- v3.0 scope document at `.planning/v3.0-cli-first-rewrite.md` (HIGH confidence -- project planning artifact)
