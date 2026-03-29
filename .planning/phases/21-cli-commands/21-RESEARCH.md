# Phase 21: CLI Commands - Research

**Researched:** 2026-03-29
**Domain:** Click CLI commands -> Unix socket -> daemon RuntimeAPI
**Confidence:** HIGH

## Summary

Phase 21 is pure CLI plumbing. The daemon already exposes socket method handlers for `hire`, `give_task`, `dismiss`, `status`, and `health_tree` (registered in `Daemon._register_socket_endpoints()`). The `DaemonClient` already has `connect()`, `call()`, and context manager support. The task is to write Click commands that use `DaemonClient.call()` to invoke these methods and format the results with Rich.

The one significant gap is `new_project` -- it is NOT registered as a socket endpoint. Currently `new_project` is called internally by `Daemon._init_project()` during boot. To support `vco new-project` from CLI, a new socket handler `_handle_new_project` must be added to the daemon that accepts `project_dir` (and optionally `config_path`), loads the config, and calls `RuntimeAPI.new_project()`.

**Primary recommendation:** Create one Click command file per CLI requirement, each following the established pattern (connect DaemonClient, call method, format result with Rich, handle connection errors). Register all commands in `cli/main.py`. Add `new_project` socket endpoint to daemon.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion (CLI plumbing phase).

### Claude's Discretion
All implementation choices are at Claude's discretion. Key patterns:
- All CLI commands use DaemonClient (Phase 18) to talk to daemon over socket
- Daemon needs new socket method handlers that call RuntimeAPI methods
- CLI commands are Click commands registered in cli/main.py
- Output formatting via Rich (existing dependency)
- Error handling: connect failure -> "daemon not running, run vco up first"

### Deferred Ideas (OUT OF SCOPE)
None -- CLI plumbing phase with clear scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CLI-01 | `vco hire <type> <name>` creates agent container via socket API | DaemonClient.call("hire", {"agent_id": name, "template": type}) -> daemon handler already exists |
| CLI-02 | `vco give-task <agent> <task>` queues task for agent via socket API | DaemonClient.call("give_task", {"agent_id": agent, "task": task}) -> daemon handler already exists |
| CLI-03 | `vco dismiss <agent>` stops and cleans up agent via socket API | DaemonClient.call("dismiss", {"agent_id": agent}) -> daemon handler already exists |
| CLI-04 | `vco status` shows supervision tree and agent states via socket API | DaemonClient.call("status") -> daemon handler already exists, returns projects + company_agents dict |
| CLI-05 | `vco health` shows health tree with per-agent status via socket API | DaemonClient.call("health_tree") -> daemon handler already exists, returns CompanyHealthTree dict |
| CLI-06 | `vco new-project` composite: init + clone + add_project via socket API | Needs new socket handler -- RuntimeAPI.new_project() exists but is not exposed over socket |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| click | 8.2.x | CLI framework | Already used for all existing vco commands (up, down, init, etc.) |
| Rich | 14.x | Terminal output formatting | Already a project dependency, used for tables and status display |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| DaemonClient | N/A (internal) | Socket RPC | Every CLI command uses this to talk to daemon |
| Pydantic | 2.11.x | Data models | Health tree and status responses are Pydantic model dicts |

No new dependencies required. All libraries are already in the project.

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/cli/
  main.py             # Click group -- add_command() for each new command
  up_cmd.py           # existing
  down_cmd.py         # existing
  hire_cmd.py         # NEW (CLI-01)
  give_task_cmd.py    # NEW (CLI-02)
  dismiss_cmd.py      # NEW (CLI-03)
  status_cmd.py       # NEW (CLI-04)
  health_cmd.py       # NEW (CLI-05)
  new_project_cmd.py  # NEW (CLI-06)

src/vcompany/daemon/
  daemon.py           # MODIFY: add _handle_new_project, register in _register_socket_endpoints
```

### Pattern 1: CLI Command Structure (established)
**What:** Each command is a Click function in its own file, uses DaemonClient context manager, handles connection errors.
**When to use:** Every CLI command that talks to the daemon.
**Example:**
```python
# Source: established pattern from down_cmd.py and daemon/client.py
import click
from rich.console import Console
from vcompany.daemon.client import DaemonClient
from vcompany.shared.paths import VCO_SOCKET_PATH

console = Console()

@click.command()
@click.argument("agent_name")
def hire(agent_name: str, template: str = "generic") -> None:
    """Hire a new agent."""
    try:
        with DaemonClient(VCO_SOCKET_PATH) as client:
            result = client.call("hire", {"agent_id": agent_name, "template": template})
            console.print(f"[green]Hired agent: {result['agent_id']}[/green]")
    except (ConnectionRefusedError, FileNotFoundError):
        console.print("[red]Daemon not running. Run 'vco up' first.[/red]", style="bold")
        raise SystemExit(1)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
```

### Pattern 2: Connection Error Helper
**What:** Shared error handling for daemon connection failures.
**When to use:** To avoid duplicating try/except in every command.
**Example:**
```python
# Helper that wraps DaemonClient calls with consistent error handling
import contextlib
from vcompany.daemon.client import DaemonClient
from vcompany.shared.paths import VCO_SOCKET_PATH

@contextlib.contextmanager
def daemon_client():
    """Connect to daemon with user-friendly error on failure."""
    try:
        with DaemonClient(VCO_SOCKET_PATH) as client:
            yield client
    except (ConnectionRefusedError, FileNotFoundError):
        click.echo("Error: Daemon not running. Start with: vco up", err=True)
        raise SystemExit(1)
```

### Pattern 3: Rich Table for Status/Health Output
**What:** Use Rich tables to display structured daemon responses.
**When to use:** `vco status` and `vco health` commands.
**Example:**
```python
from rich.table import Table
from rich.console import Console

console = Console()

def render_status(data: dict) -> None:
    table = Table(title="vCompany Status")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Info")

    for pid, info in data.get("projects", {}).items():
        table.add_row("Project", pid, f"{info['agents']} agents")
    for agent_id in data.get("company_agents", []):
        table.add_row("Company Agent", agent_id, "")

    console.print(table)
```

### Pattern 4: Health Tree Rendering
**What:** Recursive rendering of CompanyHealthTree with color-coded states.
**When to use:** `vco health` command.
**Example:**
```python
# CompanyHealthTree dict structure from RuntimeAPI.health_tree():
# {
#   "supervisor_id": "company-root",
#   "state": "running",
#   "projects": [
#     {"supervisor_id": "proj-x", "state": "running", "children": [
#       {"report": {"agent_id": "agent-1", "state": "running", ...}}
#     ]}
#   ],
#   "company_agents": [
#     {"report": {"agent_id": "strategist", "state": "running", ...}}
#   ]
# }

STATE_COLORS = {
    "running": "green",
    "idle": "blue",
    "sleeping": "dim",
    "error": "red",
    "blocked": "yellow",
    "creating": "cyan",
}
```

### Anti-Patterns to Avoid
- **Direct CompanyRoot imports in CLI:** CLI commands MUST go through socket API, never import daemon internals.
- **Async CLI commands:** DaemonClient is synchronous by design (Phase 18 decision). Do NOT use asyncio in CLI commands.
- **Hardcoded socket paths:** Always use `VCO_SOCKET_PATH` from `shared.paths`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Socket communication | Raw socket code in CLI | DaemonClient context manager | Already built, handles handshake, NDJSON, errors |
| Terminal tables | print() formatting | Rich Table/Console | Already a dependency, handles column sizing, colors |
| Config loading for new-project | Custom YAML parsing | `load_config()` from `models.config` | Already handles Pydantic validation, error messages |
| Argument validation | Manual checks | Click argument/option types | Click has built-in path, choice, string validation |

## Common Pitfalls

### Pitfall 1: new_project Socket Handler Complexity
**What goes wrong:** `new_project` is a complex orchestration method that requires `ProjectConfig` (a Pydantic model), `Path` objects, and persona_path. These cannot be trivially serialized as JSON params over the socket.
**Why it happens:** All other socket methods take simple string/dict params. new_project needs config objects.
**How to avoid:** The socket handler should accept `project_dir` as a string path param, then load the config from `project_dir/agents.yaml` server-side. The CLI does `vco init` first (already exists), then calls `new_project` with just the path.
**Warning signs:** If you're trying to serialize ProjectConfig over the socket, you're overcomplicating it.

### Pitfall 2: DaemonClient Timeout on Long Operations
**What goes wrong:** `new_project` involves creating tmux sessions, channels, etc. Default 30s timeout may be tight.
**Why it happens:** DaemonClient default timeout is 30s.
**How to avoid:** For `new_project`, consider using a longer timeout or making the CLI pass a timeout option.
**Warning signs:** ConnectionError during project initialization.

### Pitfall 3: Missing hire template Parameter
**What goes wrong:** `vco hire` requires both a type/template and a name, but the requirement says `<type> <name>`.
**Why it happens:** RuntimeAPI.hire() takes `agent_id` and `template` params. The daemon handler maps `params["agent_id"]` and `params.get("template", "generic")`.
**How to avoid:** Click command should have two arguments: `type` (maps to template) and `name` (maps to agent_id).
**Warning signs:** If hire always uses "generic" template, you forgot to wire the type argument.

### Pitfall 4: Connection Error Not Caught for Socket Missing
**What goes wrong:** `FileNotFoundError` when socket file doesn't exist (daemon never started), `ConnectionRefusedError` when socket exists but daemon stopped.
**Why it happens:** Two different error paths for "daemon not running".
**How to avoid:** Catch both `FileNotFoundError` and `ConnectionRefusedError` with a single user-friendly message.
**Warning signs:** Stack trace when running `vco status` without daemon running.

### Pitfall 5: new_project Needs Strategist Cog Wiring
**What goes wrong:** `Daemon._init_project()` does extra wiring after `RuntimeAPI.new_project()` -- specifically `strategist_cog.set_company_agent()`. A socket-based new_project handler must also do this.
**Why it happens:** The current code path goes through `_init_project` which has daemon-level wiring beyond what RuntimeAPI handles.
**How to avoid:** The daemon's `_handle_new_project` socket handler should replicate the full `_init_project` flow, not just call `RuntimeAPI.new_project()`.
**Warning signs:** Strategist not responding after `vco new-project`.

## Code Examples

### Existing Socket Handler Pattern (from daemon.py)
```python
# Source: src/vcompany/daemon/daemon.py lines 269-295
async def _handle_hire(self, params: dict) -> dict:
    if not self._runtime_api:
        raise RuntimeError("RuntimeAPI not initialized")
    agent_id = await self._runtime_api.hire(
        params["agent_id"], params.get("template", "generic")
    )
    return {"agent_id": agent_id}
```

### DaemonClient Usage Pattern (from client.py)
```python
# Source: src/vcompany/daemon/client.py
with DaemonClient(VCO_SOCKET_PATH) as client:
    result = client.call("method_name", {"param": "value"})
    # result is a dict (the "result" field from Response)
```

### Existing CLI Registration Pattern (from main.py)
```python
# Source: src/vcompany/cli/main.py
from vcompany.cli.hire_cmd import hire
cli.add_command(hire)
```

### RuntimeAPI.status() Return Format
```python
# Source: src/vcompany/daemon/runtime_api.py lines 111-124
{
    "projects": {
        "project-id": {"agents": 3}
    },
    "company_agents": ["strategist"]
}
```

### CompanyHealthTree Return Format (via model_dump)
```python
# Source: src/vcompany/container/health.py
{
    "supervisor_id": "company-root",
    "state": "running",
    "projects": [
        {
            "supervisor_id": "project-x",
            "state": "running",
            "children": [
                {
                    "report": {
                        "agent_id": "agent-1",
                        "state": "running",
                        "inner_state": "IDLE",
                        "uptime": 120.5,
                        "last_heartbeat": "2026-03-29T12:00:00",
                        "error_count": 0,
                        "last_activity": "2026-03-29T11:58:00",
                        "blocked_reason": None,
                        "is_idle": True
                    }
                }
            ]
        }
    ],
    "company_agents": [
        {
            "report": {
                "agent_id": "strategist",
                "state": "running",
                ...
            }
        }
    ]
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Discord slash commands for agent management | CLI commands via socket API | v3.0 (Phase 21) | Agents can be managed from terminal without Discord |
| Bot on_ready() initializes project | RuntimeAPI.new_project() called from daemon | Phase 20 | Clean separation enables CLI-triggered project init |

## Open Questions

1. **new_project clone step**
   - What we know: CLI-06 says "init + clone + add_project". `vco init` already exists. `vco clone` already exists. The "add_project" is what `RuntimeAPI.new_project()` does.
   - What's unclear: Should `vco new-project` orchestrate all three steps (init, clone, then call daemon), or should it only call the daemon which handles everything?
   - Recommendation: `vco new-project` should be a composite CLI command that: (1) calls `vco init` logic locally (filesystem ops), (2) calls `vco clone` logic locally (git ops), (3) calls daemon `new_project` socket method to start supervision. This keeps expensive filesystem/git ops out of the daemon.

2. **RuntimeAPI not initialized during new_project**
   - What we know: RuntimeAPI is created during `_init_company_root` which requires bot to be ready. If called via socket, RuntimeAPI already exists.
   - What's unclear: Can `new_project` be called multiple times (second project)?
   - Recommendation: For v3.0, assume single project. The socket handler should check if a project is already loaded and error if so.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml |
| Quick run command | `uv run pytest tests/test_cli_commands.py -x` |
| Full suite command | `uv run pytest -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CLI-01 | `vco hire` calls daemon hire method | unit | `uv run pytest tests/test_cli_commands.py::test_hire_calls_daemon -x` | Wave 0 |
| CLI-02 | `vco give-task` calls daemon give_task | unit | `uv run pytest tests/test_cli_commands.py::test_give_task_calls_daemon -x` | Wave 0 |
| CLI-03 | `vco dismiss` calls daemon dismiss | unit | `uv run pytest tests/test_cli_commands.py::test_dismiss_calls_daemon -x` | Wave 0 |
| CLI-04 | `vco status` renders table from daemon status | unit | `uv run pytest tests/test_cli_commands.py::test_status_renders -x` | Wave 0 |
| CLI-05 | `vco health` renders health tree from daemon | unit | `uv run pytest tests/test_cli_commands.py::test_health_renders -x` | Wave 0 |
| CLI-06 | `vco new-project` orchestrates init+clone+daemon | unit | `uv run pytest tests/test_cli_commands.py::test_new_project_composite -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_cli_commands.py -x`
- **Per wave merge:** `uv run pytest -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_cli_commands.py` -- covers CLI-01 through CLI-06
- Strategy: Mock DaemonClient.call() to verify correct method/params, use Click CliRunner for invocation testing

## Project Constraints (from CLAUDE.md)

- **click 8.2.x** for CLI framework (not typer, not argparse)
- **Rich** for terminal output formatting
- **No database** -- filesystem state only
- **httpx** for HTTP (not requests, not aiohttp) -- not relevant for this phase
- **subprocess for git** (not GitPython) -- relevant for clone step in new-project
- **No discord.py imports** in CLI commands -- all through socket API
- **DaemonClient is sync** (stdlib socket) -- no asyncio in CLI commands

## Sources

### Primary (HIGH confidence)
- `src/vcompany/daemon/daemon.py` -- socket endpoint registration pattern, existing handlers
- `src/vcompany/daemon/client.py` -- DaemonClient API (sync, context manager)
- `src/vcompany/daemon/runtime_api.py` -- RuntimeAPI methods: hire(), give_task(), dismiss(), status(), health_tree(), new_project()
- `src/vcompany/daemon/server.py` -- SocketServer.register_method() API
- `src/vcompany/daemon/protocol.py` -- NDJSON Request/Response models
- `src/vcompany/cli/main.py` -- Click group and add_command() registration
- `src/vcompany/cli/down_cmd.py` -- CLI command pattern (error handling, click.echo)
- `src/vcompany/cli/init_cmd.py` -- Project initialization logic (reusable for new-project)
- `src/vcompany/container/health.py` -- CompanyHealthTree, HealthTree, HealthNode, HealthReport models

### Secondary (MEDIUM confidence)
- `src/vcompany/shared/paths.py` -- VCO_SOCKET_PATH, VCO_PID_PATH constants

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in use, no new dependencies
- Architecture: HIGH - clear established patterns from Phase 18/20
- Pitfalls: HIGH - derived from reading actual source code and data flow

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (stable -- internal plumbing with no external dependencies)
