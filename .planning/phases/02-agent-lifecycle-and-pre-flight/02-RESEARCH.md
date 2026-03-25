# Phase 2: Agent Lifecycle and Pre-flight - Research

**Researched:** 2026-03-25
**Domain:** Process lifecycle management (tmux + Claude Code headless), crash recovery, pre-flight validation
**Confidence:** HIGH

## Summary

Phase 2 builds the agent lifecycle layer: dispatching Claude Code sessions into tmux panes, killing them gracefully, relaunching with resume, and automatically recovering from crashes with exponential backoff and circuit breaker logic. It also includes a pre-flight test suite that validates Claude Code headless behavior before real projects run.

The existing Phase 1 codebase provides solid building blocks: `TmuxManager` for tmux operations, `write_atomic` for state file writes, `load_config` for agent roster parsing, and `GitResult`-pattern subprocess wrappers. Phase 2 adds an `orchestrator/` module layer between the CLI commands and the low-level wrappers.

Key technical finding: Claude Code's `--max-turns` flag exits with an error when the limit is reached (not a clean exit), which affects how the monitor classifies that exit. The `--resume` flag accepts session IDs and can continue from checkpoints. The `--output-format stream-json` produces newline-delimited JSON events suitable for heartbeat monitoring. These behaviors must be empirically validated by pre-flight tests since they are central to the monitor strategy.

**Primary recommendation:** Build the orchestrator layer (`agent_manager.py`, `crash_tracker.py`) as pure Python modules independent of CLI/Discord, with CLI commands as thin wrappers. Use JSON state files with atomic writes for all runtime state. Pre-flight tests should be real Claude Code invocations against a temp directory.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** `vco dispatch {agent-id}` launches `claude --dangerously-skip-permissions --append-system-prompt {agent_prompt_file}` in a tmux pane via the TmuxManager wrapper from Phase 1.
- **D-02:** `vco dispatch all` creates a tmux session named after the project, one pane per agent plus a monitor pane. Uses the tmux wrapper's create_session() and create_pane().
- **D-03:** Initial command sent to each pane: `claude --dangerously-skip-permissions --append-system-prompt {context/agents/{id}.md} -p '/gsd:new-project'` for fresh starts, or `-p '/gsd:resume-work'` for relaunches.
- **D-04:** Environment variables set per pane before launch: DISCORD_AGENT_WEBHOOK_URL, PROJECT_NAME, AGENT_ID, AGENT_ROLE.
- **D-05:** Dispatch records each agent's PID and tmux pane ID in a `{project}/state/agents.json` file for monitor/kill/relaunch to reference.
- **D-06:** `vco kill {agent-id}` first sends SIGTERM to the Claude Code process, waits 10s, then SIGKILL if still alive. Falls back to killing the tmux pane.
- **D-07:** `vco relaunch {agent-id}` runs kill then dispatch with `-p '/gsd:resume-work'` flag.
- **D-08:** Both kill and relaunch update agents.json state file atomically.
- **D-09:** Crash detection: monitor (Phase 3) checks tmux pane liveness. When dead, triggers recovery in this module.
- **D-10:** Crash classification before retry: transient (clean exit with checkpoint, non-zero exit but no corrupt state) vs persistent (same error in last 2 crash logs, corrupt .planning/ directory).
- **D-11:** Exponential backoff between retries: 30s, 2min, 10min.
- **D-12:** Circuit breaker: max 3 crashes/hour per agent. On 4th crash, stop relaunch, alert Discord #alerts, require manual `!relaunch` to reset.
- **D-13:** Crash state tracked in `{project}/state/crash_log.json` with timestamps, exit codes, classification, and retry count.
- **D-14:** Pre-flight test suite is a standalone Python script: `vco preflight` command.
- **D-15:** Tests run against a dummy project (temp dir with minimal agents.yaml).
- **D-16:** 4 tests: stream-json heartbeat, permission hang behavior, --max-turns exit, --resume recovery.
- **D-17:** Results written to `{project}/state/preflight_results.json`. Monitor strategy determined by results.

### Claude's Discretion
- Crash log format and rotation policy
- Pre-flight test timeout values
- Exact tmux session naming convention
- Whether to support `vco dispatch --dry-run` for validation without launching

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LIFE-01 | `vco dispatch` launches Claude Code sessions in tmux panes with `--dangerously-skip-permissions` and `--append-system-prompt` | Verified: both flags exist in Claude Code CLI. `--append-system-prompt` appends to default prompt (does not replace). Use with `-p` for non-interactive print mode. |
| LIFE-02 | `vco dispatch all` creates tmux session with one pane per agent plus monitor pane | TmuxManager.create_session() + create_pane() from Phase 1 provide this. Use separate windows for agents vs monitor per architecture doc. |
| LIFE-03 | `vco kill` terminates a specific agent session (graceful then forced) | SIGTERM -> 10s wait -> SIGKILL pattern. Need PID of Claude Code process (child of pane shell), not just pane PID. |
| LIFE-04 | `vco relaunch` restarts an agent with `/gsd:resume-work` | `--resume` flag accepts session ID. Relaunch runs kill then fresh dispatch with `-p '/gsd:resume-work'`. |
| LIFE-05 | Crash recovery auto-relaunches with exponential backoff (30s, 2min, 10min) | Backoff schedule is fixed (not computed). Recovery module exposes `get_next_retry_delay()` based on crash count. |
| LIFE-06 | Circuit breaker stops relaunch after 3 crashes/hour and alerts Discord | Sliding window: count crashes in last 60 minutes. On 4th, set agent state to "circuit_open" and emit alert event. |
| LIFE-07 | Crash classification distinguishes transient from persistent failures | Check: exit code, checkpoint file existence, last N pane output lines for repeated error patterns, .planning/ directory integrity. |
| PRE-01 | Pre-flight test suite validates Claude Code headless behavior | `vco preflight` runs 4 empirical tests against real Claude Code in a temp directory. |
| PRE-02 | Tests cover: stream-json heartbeat, permission hang, --max-turns exit, --resume recovery | All 4 flags verified to exist. `--max-turns` exits with error (not clean exit). stream-json emits newline-delimited JSON events. |
| PRE-03 | Results determine monitor strategy (stream-json liveness vs git-commit fallback) | If stream-json heartbeat is reliable, monitor reads stream for liveness. If not, falls back to checking git log for recent commits. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Project-agnostic**: No hardcoded assumptions about what agents build
- **Agent isolation**: Agents never share working directories
- **Discord-first**: All human interaction through Discord, not terminal
- **GSD compatibility**: Agents run standard GSD pipelines
- **Single machine**: All agents, monitor, and bot run on one machine for v1
- **GSD Workflow Enforcement**: Use GSD entry points for code changes
- **uv for package management** with pyproject.toml
- **libtmux pinned to 0.55.x** (pre-1.0 API instability)

## Standard Stack

### Core (already in pyproject.toml)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| libtmux | 0.55.0 | tmux pane lifecycle | Already wrapped in TmuxManager. Pin tightly. |
| click | 8.2.x | CLI commands (dispatch, kill, relaunch, preflight) | Phase 1 pattern. Add subcommands to existing group. |
| pydantic | 2.11.x | State file models (agents.json, crash_log.json, preflight_results.json) | Validation on load, serialization to JSON. |

### Supporting (no new dependencies needed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| subprocess (stdlib) | N/A | Launching Claude Code, sending signals | For PID-level process control (SIGTERM/SIGKILL) |
| signal (stdlib) | N/A | Signal constants (SIGTERM, SIGKILL) | In kill logic |
| os (stdlib) | N/A | os.kill() for signal delivery, os.getpgid() for process groups | Kill and liveness checking |
| json (stdlib) | N/A | State file serialization | agents.json, crash_log.json, preflight_results.json |
| time/datetime (stdlib) | N/A | Timestamps, backoff timing | Crash tracking sliding window |
| tempfile (stdlib) | N/A | Pre-flight test dummy project directory | Isolated test environment |
| pathlib (stdlib) | N/A | All path operations | Established pattern from Phase 1 |

### No New Dependencies
This phase requires zero new pip packages. All functionality is built on Phase 1 foundations plus stdlib.

## Architecture Patterns

### Recommended Project Structure (additions for Phase 2)
```
src/vcompany/
    orchestrator/           # NEW: core orchestration logic
        __init__.py
        agent_manager.py    # AgentProcess dataclass, dispatch/kill/relaunch logic
        crash_tracker.py    # CrashRecord, CrashTracker with backoff + circuit breaker
        preflight.py        # Pre-flight test runner
    cli/
        dispatch_cmd.py     # NEW: vco dispatch
        kill_cmd.py         # NEW: vco kill
        relaunch_cmd.py     # NEW: vco relaunch
        preflight_cmd.py    # NEW: vco preflight
    models/
        agent_state.py      # NEW: AgentState, AgentsRegistry pydantic models
```

### Pattern 1: Orchestrator as Pure Logic Layer
**What:** The `orchestrator/` module contains all business logic for agent lifecycle. It has no CLI or Discord dependencies. CLI commands are thin wrappers that call orchestrator functions.
**When to use:** Always. This is the established Phase 1 pattern (git/ops.py returns GitResult, CLI handles display).
**Example:**
```python
# src/vcompany/orchestrator/agent_manager.py
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class AgentProcess:
    """Runtime state for a single agent process."""
    agent_id: str
    pane_id: str
    pid: int | None = None
    session_name: str = ""
    status: str = "starting"  # starting, running, stopped, crashed, circuit_open

@dataclass
class DispatchResult:
    """Result of dispatching an agent."""
    success: bool
    agent_id: str
    pane_id: str = ""
    pid: int | None = None
    error: str = ""
```

### Pattern 2: State Files with Pydantic Models
**What:** Runtime state (agents.json, crash_log.json) is modeled with Pydantic for validation, serialized to JSON, and written atomically via `write_atomic`.
**When to use:** For all shared state files that the monitor (Phase 3) or CLI will read.
**Example:**
```python
# src/vcompany/models/agent_state.py
from pydantic import BaseModel
from datetime import datetime

class AgentEntry(BaseModel):
    agent_id: str
    pane_id: str
    pid: int | None = None
    session_name: str
    status: str  # running, stopped, crashed, circuit_open
    launched_at: datetime
    last_crash: datetime | None = None

class AgentsRegistry(BaseModel):
    project: str
    agents: dict[str, AgentEntry] = {}
```

### Pattern 3: Crash Tracker with Sliding Window
**What:** Crash tracking uses a sliding window (last 60 minutes) to count crashes per agent. The tracker is a stateless module that reads/writes crash_log.json.
**When to use:** In the recovery module, called by monitor (Phase 3) when a dead pane is detected.
**Example:**
```python
# src/vcompany/orchestrator/crash_tracker.py
from datetime import datetime, timedelta

BACKOFF_SCHEDULE = [30, 120, 600]  # seconds: 30s, 2min, 10min
MAX_CRASHES_PER_HOUR = 3

class CrashTracker:
    def __init__(self, crash_log_path: Path):
        self.path = crash_log_path

    def record_crash(self, agent_id: str, exit_code: int, classification: str) -> None:
        """Record a crash event with timestamp."""
        ...

    def recent_crash_count(self, agent_id: str) -> int:
        """Count crashes in the last hour."""
        ...

    def should_retry(self, agent_id: str) -> bool:
        """Return True if circuit breaker allows retry."""
        return self.recent_crash_count(agent_id) < MAX_CRASHES_PER_HOUR

    def get_retry_delay(self, agent_id: str) -> int:
        """Return backoff delay in seconds based on recent crash count."""
        count = self.recent_crash_count(agent_id)
        if count >= len(BACKOFF_SCHEDULE):
            return BACKOFF_SCHEDULE[-1]
        return BACKOFF_SCHEDULE[count]
```

### Pattern 4: PID Discovery for Kill
**What:** When killing an agent, find the actual Claude Code process PID (child of the shell in the tmux pane), not the pane's shell PID.
**When to use:** In `vco kill` to send SIGTERM to the correct process.
**Example:**
```python
import os
import signal

def find_child_pids(parent_pid: int) -> list[int]:
    """Find child PIDs of a process using /proc filesystem."""
    children = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                stat = (entry / "stat").read_text()
                fields = stat.split()
                ppid = int(fields[3])
                if ppid == parent_pid:
                    children.append(int(entry.name))
            except (FileNotFoundError, IndexError, ValueError):
                continue
    return children

def kill_agent_process(pid: int, timeout: int = 10) -> bool:
    """SIGTERM, wait, SIGKILL if needed."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True  # Already dead

    # Poll for process exit
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)  # Check if alive
            time.sleep(0.5)
        except ProcessLookupError:
            return True

    # Force kill
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return True
```

### Pattern 5: Environment Variable Injection Before Launch
**What:** Set per-agent environment variables in the tmux pane before launching Claude Code.
**When to use:** Every dispatch. Variables are set via `send_keys("export VAR=value")` before the claude command.
**Example:**
```python
def dispatch_agent(tmux: TmuxManager, pane, agent, project_name: str, webhook_url: str):
    """Set env vars then launch Claude Code in the pane."""
    env_vars = {
        "DISCORD_AGENT_WEBHOOK_URL": webhook_url,
        "PROJECT_NAME": project_name,
        "AGENT_ID": agent.id,
        "AGENT_ROLE": agent.role,
    }
    for key, value in env_vars.items():
        tmux.send_command(pane, f"export {key}='{value}'")

    # Build and send the claude command
    prompt_file = f"context/agents/{agent.id}.md"
    cmd = (
        f"claude --dangerously-skip-permissions "
        f"--append-system-prompt-file {prompt_file} "
        f"-p '/gsd:new-project'"
    )
    tmux.send_command(pane, cmd)
```

### Anti-Patterns to Avoid
- **Storing PID in memory only:** PIDs must persist in agents.json so that kill/relaunch work across CLI invocations. The monitor is a separate process.
- **Using TmuxManager.is_alive() alone for crash detection:** This checks if the pane's shell is alive, not the Claude Code process inside it. A dead Claude process leaves a live bash shell.
- **Immediate relaunch without classification:** Always check crash classification first. Persistent failures burn API tokens on retry.
- **Blocking the CLI waiting for backoff:** The backoff delay is for the monitor/recovery system, not the CLI. `vco relaunch` should be immediate (manual override). Only auto-recovery uses backoff.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic file writes | Custom rename logic | `write_atomic` from Phase 1 | Already tested, handles edge cases (same filesystem, cleanup on failure) |
| tmux operations | Direct subprocess tmux calls | `TmuxManager` from Phase 1 | Single abstraction boundary for libtmux |
| Config parsing | Manual YAML dict access | `load_config` + pydantic models | Validation on construction, type safety |
| Process signal handling | Custom signal module | `os.kill()` + `signal` stdlib | Standard Linux process management |
| JSON state serialization | Custom serializers | Pydantic `model_dump_json()` / `model_validate_json()` | Handles datetime serialization, validation |

**Key insight:** Phase 2 builds ON Phase 1 primitives. Every low-level operation already has a wrapper. The new code is orchestration logic that composes these wrappers.

## Common Pitfalls

### Pitfall 1: PID Stale After Process Exit
**What goes wrong:** agents.json records a PID at dispatch time. The process dies. The OS recycles the PID for an unrelated process. Kill sends SIGTERM to the wrong process.
**Why it happens:** PIDs wrap around. On Linux, `/proc/sys/kernel/pid_max` is typically 32768 or 4194304.
**How to avoid:** Before sending a signal, verify the PID belongs to a `claude` or `node` process by reading `/proc/{pid}/cmdline`. If the command doesn't match, treat the agent as already dead.
**Warning signs:** `vco kill` succeeds but something unrelated dies.

### Pitfall 2: tmux send_keys Is Asynchronous
**What goes wrong:** Dispatch sends environment variable exports via `send_keys`, then immediately sends the claude command. The exports haven't been processed yet, so Claude launches without env vars.
**Why it happens:** `tmux send-keys` queues keystrokes. Processing depends on the shell's readline speed.
**How to avoid:** Add a small sleep (0.1-0.3s) between send_keys calls, or chain commands with `&&` in a single send_keys call: `export VAR1=x && export VAR2=y && claude ...`.
**Warning signs:** Agents launching with missing environment variables.

### Pitfall 3: --max-turns Exits With Error, Not Clean Exit
**What goes wrong:** Pre-flight test for `--max-turns` expects exit code 0. Gets a non-zero exit code and classifies the behavior as broken.
**Why it happens:** Claude Code documentation states "--max-turns: Exits with an error when the limit is reached." This is by design, not a bug.
**How to avoid:** Pre-flight test for `--max-turns` should expect a non-zero exit code and validate that the session completed the expected number of turns before exiting. The crash classifier must NOT treat max-turns exits as crashes.
**Warning signs:** All max-turns exits triggering crash recovery.

### Pitfall 4: --append-system-prompt vs --append-system-prompt-file
**What goes wrong:** CONTEXT.md decision D-01 says `--append-system-prompt {agent_prompt_file}`. But `--append-system-prompt` takes inline text, not a file path.
**Why it happens:** Confusion between the flag and its file variant.
**How to avoid:** Use `--append-system-prompt-file {path}` to load from a file, or read the file content and pass it via `--append-system-prompt "$(cat file)"`. The file variant is cleaner.
**Warning signs:** Agent launching with a literal file path as its system prompt text.

### Pitfall 5: Claude Code Session Not Persisted in -p Mode
**What goes wrong:** Agent launched with `-p` flag. On crash, `--resume` cannot find the session because `-p` mode does not persist sessions by default.
**Why it happens:** Official docs state `--no-session-persistence` is "print mode only" -- but `-p` mode sessions ARE persisted by default. The flag explicitly disables it. However, `--resume` works by session ID, which must be captured.
**How to avoid:** When dispatching, capture the session ID from the initial output (use `--output-format json` to get `session_id` in the response). Store it in agents.json. For relaunch, use `--resume {session_id}` or `--continue` if in the same directory. Alternatively, use `--name` flag to set a named session that can be resumed by name.
**Warning signs:** Relaunch unable to find previous session.

### Pitfall 6: Crash Classification Reads Empty Pane Output
**What goes wrong:** Agent crashes. Crash classifier tries to read pane output for error patterns. But the pane was already killed or the output buffer was cleared.
**Why it happens:** tmux pane capture only works while the pane exists. If the pane died, its output is gone.
**How to avoid:** Capture pane output periodically (on each monitor cycle) and store the last N lines in crash_log.json. When a crash is detected, classify based on the stored output, not a fresh capture.
**Warning signs:** All crashes classified as "unclassified" because no output was available.

## Code Examples

### Dispatch Command Implementation
```python
# src/vcompany/cli/dispatch_cmd.py
import click
from pathlib import Path
from vcompany.cli.init_cmd import PROJECTS_BASE
from vcompany.models.config import load_config
from vcompany.orchestrator.agent_manager import AgentManager

@click.command()
@click.argument("project_name")
@click.argument("agent_id", required=False, default=None)
@click.option("--all", "dispatch_all", is_flag=True, help="Dispatch all agents")
def dispatch(project_name: str, agent_id: str | None, dispatch_all: bool) -> None:
    """Launch agent Claude Code sessions in tmux panes."""
    project_dir = PROJECTS_BASE / project_name
    config = load_config(project_dir / "agents.yaml")
    manager = AgentManager(project_dir, config)

    if dispatch_all:
        results = manager.dispatch_all()
        for r in results:
            status = "OK" if r.success else f"FAILED: {r.error}"
            click.echo(f"  {r.agent_id}: {status}")
    elif agent_id:
        result = manager.dispatch(agent_id)
        if result.success:
            click.echo(f"Agent {agent_id} dispatched (PID: {result.pid})")
        else:
            click.echo(f"Failed to dispatch {agent_id}: {result.error}", err=True)
    else:
        click.echo("Specify agent ID or use --all", err=True)
```

### Kill Command with Graceful Shutdown
```python
# src/vcompany/cli/kill_cmd.py
import click
from pathlib import Path
from vcompany.cli.init_cmd import PROJECTS_BASE
from vcompany.orchestrator.agent_manager import AgentManager
from vcompany.models.config import load_config

@click.command()
@click.argument("project_name")
@click.argument("agent_id")
@click.option("--force", is_flag=True, help="Skip graceful shutdown, SIGKILL immediately")
def kill(project_name: str, agent_id: str, force: bool) -> None:
    """Terminate an agent session."""
    project_dir = PROJECTS_BASE / project_name
    config = load_config(project_dir / "agents.yaml")
    manager = AgentManager(project_dir, config)
    success = manager.kill(agent_id, force=force)
    if success:
        click.echo(f"Agent {agent_id} terminated")
    else:
        click.echo(f"Failed to terminate {agent_id}", err=True)
```

### Pre-flight Test Structure
```python
# src/vcompany/orchestrator/preflight.py
import subprocess
import tempfile
import json
from dataclasses import dataclass
from pathlib import Path

@dataclass
class PreflightResult:
    test_name: str
    passed: bool
    details: str
    duration_seconds: float

def test_stream_json_heartbeat(timeout: int = 30) -> PreflightResult:
    """Test: Does stream-json output produce regular events we can monitor?"""
    with tempfile.TemporaryDirectory() as tmpdir:
        proc = subprocess.Popen(
            ["claude", "-p", "--output-format", "stream-json",
             "--dangerously-skip-permissions", "echo hello"],
            cwd=tmpdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        )
        # Read lines with timeout, count JSON events
        ...

def test_max_turns_exit(timeout: int = 60) -> PreflightResult:
    """Test: Does --max-turns exit with non-zero code after N turns?"""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ["claude", "-p", "--max-turns", "1",
             "--dangerously-skip-permissions", "List files in current directory"],
            cwd=tmpdir, capture_output=True, text=True, timeout=timeout,
        )
        # Expect non-zero exit code (documented behavior)
        passed = result.returncode != 0
        ...

def test_resume_recovery(timeout: int = 120) -> PreflightResult:
    """Test: Can a session be resumed after termination?"""
    # Step 1: Start a named session, let it complete
    # Step 2: Resume by name with --resume
    # Step 3: Verify continuity
    ...

def test_permission_hang(timeout: int = 30) -> PreflightResult:
    """Test: Does Claude hang or error without --dangerously-skip-permissions?"""
    # Run WITHOUT permission skip, WITH --max-turns 1
    # Expect: either hangs (detected by timeout) or errors
    # This determines if the flag is strictly required
    ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `--max-turns` not available | `--max-turns N` exits with error at limit | Current Claude Code 2.1.x | Can limit runaway agents. Non-zero exit needs special handling in crash classifier. |
| No `--name` flag | `--name` + `--resume {name}` | Current Claude Code 2.1.x | Named sessions simplify resume after crash. Store name in agents.json instead of session UUID. |
| `--output-format json` only | `stream-json` with `--include-partial-messages` | Current Claude Code 2.1.x | Real-time heartbeat monitoring possible via stream events. |
| `--bare` mode not available | `--bare` skips hooks, plugins, CLAUDE.md auto-discovery | Current Claude Code 2.1.x | Faster startup for pre-flight tests. NOT for real agent dispatch (agents need hooks and CLAUDE.md). |
| `--append-system-prompt` inline only | `--append-system-prompt-file` reads from file | Current Claude Code 2.1.x | Cleaner dispatch command. Use file variant for agent prompts. |
| `--max-budget-usd` not available | `--max-budget-usd N` limits API spend | Current Claude Code 2.1.x | Future: can cap per-agent API costs. Not needed for Phase 2 but worth noting. |

**Deprecated/outdated:**
- Architecture doc references `--allowedTools` as `--dangerouslySkipPermissions` in some places -- the correct flag is `--dangerously-skip-permissions` (kebab-case)

## Open Questions

1. **How does Claude Code signal context exhaustion?**
   - What we know: Architecture doc says "Session exits, checkpoint exists" for context exhaustion. The session presumably exits with a specific code or message.
   - What's unclear: The exact exit code for context exhaustion vs API error vs other failures. Pre-flight cannot easily test this (would require filling the context window).
   - Recommendation: In crash classifier, check for known patterns in pane output ("context window", "token limit") and classify as transient. Refine after observing real crashes.

2. **Session ID capture from tmux pane**
   - What we know: `--output-format json` includes `session_id` in the output. But when launching inside a tmux pane, we cannot easily parse the output.
   - What's unclear: Whether `--name` flag creates a session that survives crashes and can be resumed.
   - Recommendation: Use `--name "vco-{project}-{agent_id}"` flag on dispatch. Resume by name. If `--name` doesn't persist, fall back to `--continue` in the same directory.

3. **Pre-flight test reliability**
   - What we know: Pre-flight tests invoke real Claude Code, which calls the Anthropic API.
   - What's unclear: How to make tests reliable across different API response times and rate limits.
   - Recommendation: Use generous timeouts (60-120s per test). Use `--bare` mode for pre-flight to minimize startup overhead. Accept that pre-flight may flake on API issues -- classify as "inconclusive" rather than "failed".

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | Yes | 3.12.3 | -- |
| tmux | Agent sessions | Yes | 3.4 | -- |
| Claude Code | Agent dispatch, pre-flight | Yes | 2.1.81 | -- |
| libtmux | TmuxManager | Yes (venv) | 0.55.0 | -- |
| uv | Package management | No | -- | pip3 in venv |

**Missing dependencies with no fallback:**
- None -- all required dependencies are available.

**Missing dependencies with fallback:**
- `uv` not installed globally. Project venv exists at `.venv/` and was likely created during Phase 1. Use `.venv/bin/python3` directly or install uv for new dependency management.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x (in dev dependencies) |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `/home/developer/vcompany/.venv/bin/python3 -m pytest tests/ -x -q` |
| Full suite command | `/home/developer/vcompany/.venv/bin/python3 -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LIFE-01 | dispatch launches Claude Code in tmux pane | integration | `.venv/bin/python3 -m pytest tests/test_dispatch.py -x` | No -- Wave 0 |
| LIFE-02 | dispatch all creates session with all panes | integration | `.venv/bin/python3 -m pytest tests/test_dispatch.py::TestDispatchAll -x` | No -- Wave 0 |
| LIFE-03 | kill terminates agent session gracefully | integration | `.venv/bin/python3 -m pytest tests/test_kill.py -x` | No -- Wave 0 |
| LIFE-04 | relaunch restarts with resume-work | integration | `.venv/bin/python3 -m pytest tests/test_relaunch.py -x` | No -- Wave 0 |
| LIFE-05 | crash recovery with exponential backoff | unit | `.venv/bin/python3 -m pytest tests/test_crash_tracker.py::TestBackoff -x` | No -- Wave 0 |
| LIFE-06 | circuit breaker stops after 3 crashes/hour | unit | `.venv/bin/python3 -m pytest tests/test_crash_tracker.py::TestCircuitBreaker -x` | No -- Wave 0 |
| LIFE-07 | crash classification (transient vs persistent) | unit | `.venv/bin/python3 -m pytest tests/test_crash_tracker.py::TestClassification -x` | No -- Wave 0 |
| PRE-01 | pre-flight test suite runs | integration | `.venv/bin/python3 -m pytest tests/test_preflight.py -x` | No -- Wave 0 |
| PRE-02 | 4 test behaviors validated | manual-only | `vco preflight test-project` (requires API key, real Claude invocation) | N/A |
| PRE-03 | results determine monitor strategy | unit | `.venv/bin/python3 -m pytest tests/test_preflight.py::TestResultInterpretation -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python3 -m pytest tests/ -x -q`
- **Per wave merge:** `.venv/bin/python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_agent_state.py` -- covers AgentsRegistry and AgentEntry models
- [ ] `tests/test_crash_tracker.py` -- covers LIFE-05, LIFE-06, LIFE-07 (backoff, circuit breaker, classification)
- [ ] `tests/test_dispatch.py` -- covers LIFE-01, LIFE-02 (tmux integration tests)
- [ ] `tests/test_kill.py` -- covers LIFE-03 (graceful + forced kill)
- [ ] `tests/test_relaunch.py` -- covers LIFE-04
- [ ] `tests/test_preflight.py` -- covers PRE-01, PRE-03 (result interpretation, not live Claude tests)

Note: LIFE-01/02/03/04 integration tests will need real tmux (same as Phase 1 test_tmux.py pattern). PRE-02 tests require live API calls and should be marked with `@pytest.mark.slow` or run separately.

## Sources

### Primary (HIGH confidence)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference) -- verified --max-turns, --resume, --append-system-prompt-file, --output-format stream-json, --name, --bare flags
- [Claude Code headless/programmatic docs](https://code.claude.com/docs/en/headless) -- verified stream-json event format, --bare mode, session continuation patterns
- Phase 1 source code (src/vcompany/) -- TmuxManager, write_atomic, load_config, GitResult patterns
- VCO-ARCHITECTURE.md -- agent dispatch flow, crash recovery table, pre-flight test requirements

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` -- crash recovery anti-patterns (Pitfall 2, 7), tmux zombie detection
- `.planning/research/ARCHITECTURE.md` -- supervisor process pattern, filesystem-as-IPC pattern, tmux session layout

### Tertiary (LOW confidence)
- `--max-turns` exact exit code behavior -- documented as "exits with error" but exact code not specified. Pre-flight test will empirically determine this.
- Context exhaustion exit behavior -- no official documentation found. Must be determined empirically or by observing real agent crashes.
- `--name` flag session persistence after crash -- documented for `/resume` picker but unclear if the name survives process death. Pre-flight test should validate.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use from Phase 1, no new dependencies
- Architecture: HIGH -- patterns directly extend Phase 1 patterns with established orchestrator layer
- Pitfalls: HIGH -- most pitfalls identified from official docs and Phase 1 research, plus empirical verification via pre-flight
- Claude Code headless behavior: MEDIUM -- flags verified via official docs, but runtime behavior (exit codes, session persistence) must be validated by pre-flight tests

**Research date:** 2026-03-25
**Valid until:** 2026-04-24 (30 days -- stable domain, Claude Code may update CLI flags)
