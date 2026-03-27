# Phase 3: Monitor Loop and Coordination - Research

**Researched:** 2026-03-25
**Domain:** Async monitoring loop, filesystem-based IPC, agent coordination
**Confidence:** HIGH

## Summary

Phase 3 builds the monitor loop that continuously supervises agents (liveness, stuck detection, plan gate), generates and distributes PROJECT-STATUS.md, implements the INTERFACES.md contract change request flow, the `vco sync-context` CLI command, and creates the central INTERACTIONS.md reference document for known interaction patterns.

The existing codebase from Phases 1-2 provides strong foundations: `TmuxManager.is_alive()` for liveness, `git.ops.log()` for commit history, `write_atomic()` for safe coordination file writes, `AgentManager` for agent enumeration via agents.json, and `CrashTracker` with its callback pattern for alert hooks. The monitor is a new `asyncio` loop that composes these existing primitives, adds plan gate detection via file mtime polling, and generates/distributes cross-agent status files.

**Primary recommendation:** Build the monitor as an asyncio task runner with independent per-agent checks (each wrapped in try/except), a heartbeat file watchdog, and placeholder callbacks for Discord integration in Phase 4. Use the established Pydantic model pattern for interface_changes.json. Add `vco monitor` and `vco sync-context` Click commands following the existing CLI structure.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Monitor runs as an asyncio loop, checking each agent every 60 seconds with independent try/except per agent check (one agent's failure doesn't crash the monitor).
- **D-02:** Liveness check: uses TmuxManager.is_alive() from Phase 1 to verify pane exists, plus /proc PID validation from Phase 2's AgentManager pattern.
- **D-03:** Stuck detection: check git log in each clone for commits in last 30 minutes. No commits = stuck. Alert to Discord #alerts (placeholder callback until Phase 4).
- **D-04:** Monitor runs under a watchdog: writes a heartbeat file every cycle with timestamp. A simple secondary process (or systemd WatchdogSec) checks the heartbeat file age. If stale > 3 minutes, restarts monitor.
- **D-05:** When monitor detects new PLAN.md files in an agent's clone (by scanning .planning/phases/ for files newer than last check), it does NOT trigger execute-phase.
- **D-06:** Instead, monitor posts plans to Discord #plan-review channel (placeholder callback until Phase 4). Agent sits idle at the prompt -- no spinning, no lock files.
- **D-07:** On PM approval (received via callback from Phase 4's Discord bot), monitor sends the /gsd:execute-phase {N} command to the agent's tmux pane via TmuxManager.send_command().
- **D-08:** On PM rejection, monitor sends the rejection feedback to the agent's tmux pane as a new prompt instructing it to re-plan with the given feedback.
- **D-09:** Plan detection uses file modification time comparison, not filesystem watchers (inotify). Polling at 60s is sufficient and more reliable.
- **D-10:** Monitor reads each clone's .planning/ROADMAP.md (phase progress), git log --oneline -5 (recent activity), and agents.json (agent state) every cycle.
- **D-11:** Assembles into PROJECT-STATUS.md using the exact format from VCO-ARCHITECTURE.md (per-agent phase list with emoji status, Key Dependencies section, Notes section).
- **D-12:** Writes to {project}/context/PROJECT-STATUS.md using write_atomic, then copies to each clone's root directory using write_atomic.
- **D-13:** vco sync-context command pushes updated INTERFACES.md, MILESTONE-SCOPE.md, and STRATEGIST-PROMPT.md to all clones (also using write_atomic).
- **D-14:** Agent proposes exact diff to INTERFACES.md via AskUserQuestion (routed through Discord in Phase 5).
- **D-15:** PM/Strategist reviews the proposal -- approves or rejects with reasoning. PM's role is judgment only, not editing.
- **D-16:** On approval, orchestrator applies the agent's proposed diff to the canonical {project}/context/INTERFACES.md and distributes to all clones via sync-context.
- **D-17:** Change requests are logged in a {project}/context/interface_changes.json file (append-only) for audit trail.
- **D-18:** Heartbeat file: {project}/state/monitor_heartbeat -- updated with ISO timestamp every monitor cycle.
- **D-19:** Watchdog check: separate lightweight process or cron job checks heartbeat age. If > 180 seconds (3 missed cycles), restart monitor and alert.

### Claude's Discretion
- Internal monitor state management (how to track "last check time" per agent)
- Exact PROJECT-STATUS.md generation implementation (template vs string building)
- sync-context file copy strategy (parallel vs sequential per clone)
- Interface change diff application method (text patch vs full replacement)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MON-01 | Monitor loop runs every 60s per agent with independent try/except per check | asyncio loop with per-agent gather + try/except; D-01 |
| MON-02 | Liveness check verifies tmux pane alive AND actual process PID inside pane | Reuse TmuxManager.is_alive() which already does pane_pid + os.kill(pid,0); D-02 |
| MON-03 | Stuck detection alerts when agent has no git commits for 30+ minutes | git.ops.log() with --since flag or timestamp comparison; D-03 |
| MON-04 | Monitor detects new PLAN.md files and triggers plan gate flow | File mtime polling per D-09; scan .planning/phases/ for new PLAN.md files |
| MON-05 | Monitor reads each clone's .planning/ROADMAP.md and git log to track phase progress | Parse ROADMAP.md for phase status markers + git log --oneline -5; D-10 |
| MON-06 | Monitor generates PROJECT-STATUS.md from all clones' state every cycle | String-build from template per VCO-ARCHITECTURE.md format; D-11 |
| MON-07 | Monitor distributes PROJECT-STATUS.md to all agent clones after generation | write_atomic to each clone's root directory; D-12 |
| MON-08 | Monitor runs under a watchdog (heartbeat file) to detect if monitor itself dies | Heartbeat file at {project}/state/monitor_heartbeat; D-18, D-19 |
| COORD-01 | INTERFACES.md is the single source of truth for API contracts | Canonical copy at {project}/context/INTERFACES.md; distributed via sync-context |
| COORD-02 | Interface change request flow: agent asks, PM approves, orchestrator distributes | Pydantic model for interface_changes.json; callback hooks for Phase 4/5; D-14-D-17 |
| COORD-03 | vco sync-context pushes INTERFACES.md, MILESTONE-SCOPE.md, STRATEGIST-PROMPT.md to all clones | Click command, iterates clones, write_atomic per file; D-13 |
| SAFE-03 | Known interaction patterns documented in central INTERACTIONS.md reference | New document at {project}/context/INTERACTIONS.md listing concurrent scenarios |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Project-agnostic**: No hardcoded assumptions about what agents build -- everything comes from blueprint + agents.yaml
- **Agent isolation**: Agents never share working directories, never write outside owned paths
- **Discord-first**: All human interaction happens through Discord, not terminal
- **GSD compatibility**: Agents run standard GSD pipelines -- vCompany orchestrates, not replaces, GSD
- **Single machine**: All agents, monitor, and bot run on one machine for v1
- **Stack**: Python 3.12+, click CLI, libtmux 0.55.x (pinned), pydantic v2, write_atomic for all coordination writes
- **No database**: All state is filesystem-based (YAML/Markdown/JSON)
- **GSD workflow enforcement**: Use GSD entry points for file changes

## Standard Stack

### Core (already installed, no additions needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio (stdlib) | N/A | Monitor loop, parallel agent checks | D-01 requires async loop; established in stack doc |
| libtmux | 0.55.0 | Liveness check, send_command for plan gate | Already used in Phase 1; single import in session.py |
| pydantic | 2.12.5 | interface_changes.json model, monitor state | Established pattern from agents.json, crash_log.json |
| click | 8.3.1 | vco monitor, vco sync-context commands | Existing CLI group in main.py |
| pathlib (stdlib) | N/A | Clone path iteration, file operations | Established pattern |
| datetime (stdlib) | N/A | Heartbeat timestamps, stuck detection | Established pattern (timezone-aware UTC) |

### Supporting (no new dependencies)

| Library | Purpose | When to Use |
|---------|---------|-------------|
| shutil (stdlib) | File copy operations in sync-context | When copying files to clones |
| json (stdlib) | interface_changes.json read/write | Pydantic handles serialization |
| os (stdlib) | Process checks, file mtime | Used by is_alive pattern |
| subprocess (stdlib) | git log calls via git.ops module | Existing wrapper |

### No New Dependencies Required

This phase uses only existing dependencies. No `pip install` or `uv add` needed.

## Architecture Patterns

### Recommended Project Structure

```
src/vcompany/
  monitor/
    __init__.py
    loop.py              # MonitorLoop class (asyncio-based)
    checks.py            # Individual check functions (liveness, stuck, plan_gate)
    status_generator.py  # PROJECT-STATUS.md builder
    heartbeat.py         # Heartbeat file writer + watchdog checker
  coordination/
    __init__.py
    sync_context.py      # sync-context logic (copy files to clones)
    interfaces.py        # INTERFACES.md change request handling
    interactions.py      # INTERACTIONS.md generation/management
  models/
    monitor_state.py     # Pydantic models for monitor state, interface changes
  cli/
    monitor_cmd.py       # vco monitor command
    sync_context_cmd.py  # vco sync-context command
```

### Pattern 1: Monitor Loop as Async Task Runner

**What:** The monitor loop runs as a single asyncio event loop that spawns independent per-agent check tasks every 60 seconds. Each agent's checks are wrapped in try/except so one failure does not affect others.

**When to use:** This is THE pattern for the monitor (D-01).

**Example:**
```python
import asyncio
from datetime import datetime, timezone
from pathlib import Path

class MonitorLoop:
    """Main monitor loop. Checks all agents every cycle."""

    CYCLE_INTERVAL = 60  # seconds

    def __init__(
        self,
        project_dir: Path,
        config: ProjectConfig,
        tmux: TmuxManager,
        *,
        on_agent_dead: Callable[[str], None] | None = None,
        on_agent_stuck: Callable[[str], None] | None = None,
        on_plan_detected: Callable[[str, Path], None] | None = None,
    ) -> None:
        self._project_dir = project_dir
        self._config = config
        self._tmux = tmux
        self._on_agent_dead = on_agent_dead
        self._on_agent_stuck = on_agent_stuck
        self._on_plan_detected = on_plan_detected
        self._last_check: dict[str, datetime] = {}
        self._last_plan_mtimes: dict[str, float] = {}
        self._running = False

    async def run(self) -> None:
        """Run the monitor loop indefinitely."""
        self._running = True
        while self._running:
            await self._run_cycle()
            await asyncio.sleep(self.CYCLE_INTERVAL)

    async def _run_cycle(self) -> None:
        """Run one complete monitor cycle."""
        # Check all agents in parallel, each independently
        tasks = [
            self._check_agent(agent.id)
            for agent in self._config.agents
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Generate and distribute PROJECT-STATUS.md
        self._generate_project_status()
        self._distribute_project_status()

        # Write heartbeat
        self._write_heartbeat()

    async def _check_agent(self, agent_id: str) -> None:
        """Run all checks for a single agent. Errors are caught here."""
        try:
            self._check_liveness(agent_id)
            self._check_stuck(agent_id)
            self._check_plan_gate(agent_id)
        except Exception:
            logger.exception("Monitor check failed for %s", agent_id)
```

### Pattern 2: Callback Injection for Phase 4 Integration

**What:** Monitor accepts optional callback functions for alert/notification actions. Phase 3 provides no-op or logging defaults. Phase 4 injects Discord callbacks.

**When to use:** All alert/notification points (dead agent, stuck agent, plan detected).

**Example:**
```python
# Phase 3: default callback logs only
def _default_alert(agent_id: str) -> None:
    logger.warning("Alert: agent %s needs attention", agent_id)

# Phase 4 will inject:
# monitor = MonitorLoop(..., on_agent_dead=discord_alert_dead)
```

This follows the established `CrashTracker.on_circuit_open` callback pattern from Phase 2.

### Pattern 3: Pydantic Model for interface_changes.json

**What:** Append-only log of INTERFACES.md change requests, following the CrashLog pattern.

**When to use:** COORD-02 implementation.

**Example:**
```python
from pydantic import BaseModel
from datetime import datetime

class InterfaceChangeRecord(BaseModel):
    """Single interface change request record."""
    timestamp: datetime
    agent_id: str
    action: Literal["proposed", "approved", "rejected", "applied"]
    description: str
    diff: str  # The proposed change content
    reviewer_note: str = ""

class InterfaceChangeLog(BaseModel):
    """Append-only log of interface changes."""
    project: str
    records: list[InterfaceChangeRecord] = []
```

### Pattern 4: Heartbeat File + Watchdog

**What:** Monitor writes ISO timestamp to heartbeat file every cycle. A separate lightweight script checks staleness.

**When to use:** MON-08 implementation.

**Example:**
```python
# In monitor loop, end of each cycle:
def _write_heartbeat(self) -> None:
    heartbeat_path = self._project_dir / "state" / "monitor_heartbeat"
    write_atomic(heartbeat_path, datetime.now(timezone.utc).isoformat())

# Watchdog script (standalone, run via cron or systemd):
def check_heartbeat(project_dir: Path, max_age_seconds: int = 180) -> bool:
    heartbeat_path = project_dir / "state" / "monitor_heartbeat"
    if not heartbeat_path.exists():
        return False
    content = heartbeat_path.read_text().strip()
    ts = datetime.fromisoformat(content)
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return age <= max_age_seconds
```

### Pattern 5: Plan Gate via File Mtime Polling

**What:** Monitor tracks last-seen mtime of PLAN.md files per agent. If a new PLAN.md has a newer mtime than last check, trigger plan gate flow.

**When to use:** MON-04 implementation (D-05 through D-09).

**Example:**
```python
def _check_plan_gate(self, agent_id: str) -> None:
    """Detect new PLAN.md files by comparing mtimes."""
    clone_dir = self._project_dir / "clones" / agent_id
    phases_dir = clone_dir / ".planning" / "phases"
    if not phases_dir.exists():
        return

    for phase_dir in phases_dir.iterdir():
        if not phase_dir.is_dir():
            continue
        for plan_file in phase_dir.glob("*-PLAN.md"):
            mtime = plan_file.stat().st_mtime
            key = str(plan_file)
            if key not in self._last_plan_mtimes or mtime > self._last_plan_mtimes[key]:
                self._last_plan_mtimes[key] = mtime
                if self._on_plan_detected:
                    self._on_plan_detected(agent_id, plan_file)
```

### Pattern 6: PROJECT-STATUS.md Generation

**What:** Read each clone's ROADMAP.md, parse phase statuses, combine with git log, output formatted markdown per VCO-ARCHITECTURE.md spec.

**When to use:** MON-05, MON-06 implementation.

**Recommendation (Claude's Discretion):** Use string building rather than Jinja2 templates. The format is well-defined and simple enough that f-string formatting is clearer and avoids template debugging. The emoji status markers (check-mark, cycle, hourglass) map to ROADMAP.md phase states.

### Anti-Patterns to Avoid

- **Sequential blocking checks:** Do NOT check agents sequentially with blocking subprocess calls. Use asyncio.gather for parallel agent checks, and asyncio.create_subprocess_exec for git commands within the monitor.
- **inotify/watchfiles for plan detection:** D-09 explicitly locks polling. Do not use filesystem watchers -- they add complexity and are less reliable for the 60s cycle.
- **Shared mutable state between checks:** Each agent check should work with its own data snapshot. Do not share mutable state between concurrent agent check tasks.
- **Catching Exception too broadly:** Wrap per-agent checks in try/except, but log the full traceback. Never silently swallow errors.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic file writes | Custom rename logic | `write_atomic()` from shared/file_ops.py | Already handles tmp+rename, mkdir, cleanup |
| Git log parsing | Custom git subprocess | `git.ops.log()` with args | Established wrapper with timeout and error handling |
| Agent enumeration | Walk filesystem for clones | `AgentManager._load_registry()` pattern reading agents.json | State file is canonical, avoids filesystem race |
| Tmux liveness | Raw tmux subprocess | `TmuxManager.is_alive()` | Already does pane_pid + os.kill(pid, 0) |
| Tmux command sending | Raw tmux send-keys | `TmuxManager.send_command()` | Abstraction layer for libtmux API stability |
| JSON state persistence | Manual json.dumps | Pydantic `.model_dump_json()` + `write_atomic()` | Established pattern from agents.json, crash_log.json |

**Key insight:** Phase 3's monitor is primarily a composition layer that wires together Phase 1-2 primitives. The main new code is the loop orchestration, status generation, and coordination commands -- not low-level infrastructure.

## Common Pitfalls

### Pitfall 1: Plan Gate Reads Partial PLAN.md

**What goes wrong:** Monitor detects a new PLAN.md via mtime but reads it before the agent's GSD pipeline finishes writing it.
**Why it happens:** File creation and content completion are not atomic. Mtime updates on open, not on close.
**How to avoid:** GSD writes plans via atomic write (tmp + rename). The mtime check captures the rename moment, which is after content is complete. Additionally, only process plans that have a recognizable complete marker (e.g., the standard GSD PLAN.md footer section). If the plan lacks expected structure, skip it and recheck next cycle.
**Warning signs:** Truncated plans, missing closing sections.

### Pitfall 2: Monitor Loop Blocks on Git Subprocess

**What goes wrong:** `git log` in a large repo takes several seconds. If checked sequentially for 5+ agents, one cycle could take 30+ seconds, eating into the 60s interval.
**Why it happens:** `subprocess.run` is blocking. Even with asyncio, calling sync git wrapper blocks the event loop.
**How to avoid:** Use `asyncio.create_subprocess_exec("git", "log", ...)` for git calls within the monitor, or run `git.ops.log()` via `asyncio.to_thread()`. Set a timeout on all subprocess calls (already 60s default in git.ops, but consider lowering to 10s for monitor-context checks).
**Warning signs:** Monitor cycles taking longer than expected, heartbeat file becoming stale.

### Pitfall 3: Stuck Detection False Positives During Planning

**What goes wrong:** Agent is legitimately in GSD discuss/plan phase (no commits expected). Monitor flags it as stuck after 30 minutes.
**Why it happens:** Stuck detection only checks git commits. Planning phases don't produce commits.
**How to avoid:** Check the agent's current status from agents.json. If status indicates planning/idle, suppress stuck alerts. Alternatively, check for ANY file changes in the clone's .planning/ directory (not just git commits) as a secondary liveness signal.
**Warning signs:** Alerts firing for agents that are actively producing plan files.

### Pitfall 4: ROADMAP.md Parse Failures

**What goes wrong:** Different agent projects may have different ROADMAP.md formats. Monitor fails to parse one and crashes the status generation.
**Why it happens:** GSD produces ROADMAP.md but format can vary. If an agent hasn't started planning yet, ROADMAP.md may not exist.
**How to avoid:** Wrap ROADMAP.md parsing in try/except. Use defensive regex matching for phase status lines. If missing or unparseable, show "Status unknown" for that agent. Never let one agent's parse failure crash status generation for all agents.
**Warning signs:** PROJECT-STATUS.md showing "Status unknown" frequently.

### Pitfall 5: Race Condition on PROJECT-STATUS.md Distribution

**What goes wrong:** Monitor writes PROJECT-STATUS.md to a clone while the agent is reading it. Agent reads partial content.
**Why it happens:** write_atomic prevents partial writes (rename is atomic), but if the agent opens the OLD file, reads some, then the rename happens, it finishes reading -- this is safe because rename replaces the directory entry atomically. The old fd continues reading old content.
**How to avoid:** write_atomic already handles this correctly. The rename swaps the directory entry atomically. Any process that already has the old file open continues reading the old version. No additional protection needed.
**Warning signs:** None expected -- atomic rename handles this.

### Pitfall 6: Heartbeat Watchdog Restarts During Long Cycle

**What goes wrong:** A legitimate long cycle (many agents, slow git operations) takes >180 seconds. Watchdog kills the healthy monitor.
**Why it happens:** Heartbeat is written at end of cycle. If cycle takes longer than watchdog threshold, it looks stale.
**How to avoid:** Write heartbeat at the START of each cycle (indicating "I'm alive and starting a cycle") rather than at the end. Or write at both start and end. 180 seconds (3 missed 60s cycles) provides reasonable buffer, but for safety, write at cycle start.
**Warning signs:** Monitor being restarted by watchdog despite being healthy.

## Code Examples

### Monitor State Models

```python
# src/vcompany/models/monitor_state.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class InterfaceChangeRecord(BaseModel):
    """Single interface change request record (append-only log)."""
    timestamp: datetime
    agent_id: str
    action: Literal["proposed", "approved", "rejected", "applied"]
    description: str
    diff: str
    reviewer_note: str = ""


class InterfaceChangeLog(BaseModel):
    """Append-only audit trail for INTERFACES.md changes."""
    project: str
    records: list[InterfaceChangeRecord] = []


class AgentMonitorState(BaseModel):
    """Per-agent state tracked by the monitor between cycles."""
    agent_id: str
    last_commit_time: datetime | None = None
    last_plan_mtimes: dict[str, float] = {}
    current_phase: str = "unknown"
    phase_status: str = "unknown"
```

### sync-context CLI Command

```python
# src/vcompany/cli/sync_context_cmd.py
import click
from pathlib import Path
from vcompany.coordination.sync_context import sync_context_files

@click.command("sync-context")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path))
def sync_context(project_dir: Path) -> None:
    """Push updated context files to all agent clones."""
    result = sync_context_files(project_dir)
    click.echo(f"Synced to {result.clones_updated} clones")
```

### sync-context Implementation

```python
# src/vcompany/coordination/sync_context.py
from dataclasses import dataclass
from pathlib import Path
from vcompany.shared.file_ops import write_atomic

SYNC_FILES = [
    "INTERFACES.md",
    "MILESTONE-SCOPE.md",
    "STRATEGIST-PROMPT.md",
]

@dataclass
class SyncResult:
    clones_updated: int
    files_synced: int
    errors: list[str]

def sync_context_files(project_dir: Path) -> SyncResult:
    """Copy context files from canonical location to all clones."""
    context_dir = project_dir / "context"
    clones_dir = project_dir / "clones"
    errors: list[str] = []
    clones_updated = 0
    files_synced = 0

    for clone_dir in clones_dir.iterdir():
        if not clone_dir.is_dir():
            continue
        clone_updated = False
        for filename in SYNC_FILES:
            src = context_dir / filename
            if not src.exists():
                continue
            dst = clone_dir / filename
            try:
                write_atomic(dst, src.read_text())
                files_synced += 1
                clone_updated = True
            except Exception as e:
                errors.append(f"{clone_dir.name}/{filename}: {e}")
        if clone_updated:
            clones_updated += 1

    return SyncResult(
        clones_updated=clones_updated,
        files_synced=files_synced,
        errors=errors,
    )
```

### Stuck Detection

```python
from datetime import datetime, timedelta, timezone
from vcompany.git import ops as git_ops

STUCK_THRESHOLD = timedelta(minutes=30)

def check_stuck(clone_dir: Path, *, now: datetime | None = None) -> bool:
    """Return True if agent appears stuck (no commits in 30+ min)."""
    if now is None:
        now = datetime.now(timezone.utc)

    # Get recent git log with timestamps
    result = git_ops.log(clone_dir, args=[
        "--format=%aI",  # Author date in ISO format
        "-1",            # Most recent commit only
    ])
    if not result.success or not result.stdout.strip():
        return True  # No commits at all = stuck

    last_commit_str = result.stdout.strip().split("\n")[0]
    try:
        last_commit_time = datetime.fromisoformat(last_commit_str)
        return (now - last_commit_time) > STUCK_THRESHOLD
    except ValueError:
        return True  # Can't parse = treat as stuck
```

### INTERACTIONS.md Content Structure

```markdown
# Known Interaction Patterns

## Monitor reads while agent writes

**Scenario:** Monitor reads ROADMAP.md, agents.json, or git log while an agent is actively modifying these files.
**Safe?** Yes -- write_atomic ensures readers see complete old or complete new content. Git operations are atomic at the commit level.
**Mitigation:** None needed beyond existing write_atomic pattern.

## Simultaneous git operations across clones

**Scenario:** Monitor runs git log on clone A while agent A is committing.
**Safe?** Yes -- each clone is an independent git repository. git log is read-only and does not conflict with concurrent commits.
**Mitigation:** None needed.

## PROJECT-STATUS.md distribution during agent read

**Scenario:** Monitor distributes PROJECT-STATUS.md via write_atomic while an agent reads the file.
**Safe?** Yes -- atomic rename. Agent reading old file continues reading old content (open fd). Agent opening after rename gets new content.
**Mitigation:** None needed beyond write_atomic.

## Plan gate approve while agent is idle

**Scenario:** Monitor sends execute-phase command to tmux pane while agent is at idle prompt.
**Safe?** Yes -- agent is waiting at prompt. send_keys delivers the command.
**Mitigation:** None needed.

## sync-context during agent execution

**Scenario:** vco sync-context copies INTERFACES.md while agent is reading it.
**Safe?** Yes -- write_atomic. Same atomic rename protection.
**Mitigation:** None needed.

## Multiple monitors (accidental)

**Scenario:** Two monitor instances running against the same project.
**Safe?** No -- duplicate alerts, duplicate plan gate triggers, heartbeat file contention.
**Mitigation:** Check for existing monitor PID on startup. Write PID to {project}/state/monitor.pid. Refuse to start if PID is alive.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| inotify/watchfiles for plan detection | Polling with mtime comparison | D-09 (user decision) | Simpler, more reliable at 60s cycle |
| Database for state tracking | Filesystem (JSON/YAML/Markdown) | Project constraint | No database dependency; write_atomic for safety |
| Sequential agent checks | asyncio.gather for parallel checks | D-01 | One agent's slow check doesn't delay others |

## Open Questions

1. **ROADMAP.md format parsing**
   - What we know: GSD generates ROADMAP.md with phase listings, but exact format may vary
   - What's unclear: Exact regex/parsing needed to extract phase status (emoji markers, "executing"/"planning" text)
   - Recommendation: Implement defensive parsing with fallback to "unknown" status. Test against actual GSD-generated ROADMAP.md from Phase 1-2 clones.

2. **Plan gate: initial mtime seeding**
   - What we know: Monitor tracks mtimes to detect NEW plans. On first startup, all existing plans appear "new."
   - What's unclear: Should monitor process all existing plans on first run, or seed mtimes without triggering?
   - Recommendation: On first run, seed all current mtimes without triggering plan gate. Only trigger on changes detected AFTER monitor starts.

3. **Interface change diff application**
   - What we know: D-16 says "orchestrator applies the agent's proposed diff"
   - What's unclear: Whether to use text patching (difflib) or full file replacement
   - Recommendation (Claude's Discretion): Use full file replacement. The agent proposes the complete new content (not a patch), and the orchestrator writes it atomically. Simpler and more reliable than applying patches that may fail on content drift.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All code | Yes | 3.12.3 | -- |
| tmux | Liveness checks, plan gate | Yes | 3.4 | -- |
| git | Stuck detection, status | Yes | 2.43.0 | -- |
| libtmux | TmuxManager | Yes | 0.55.0 | -- |
| pydantic | Models | Yes | 2.12.5 | -- |
| click | CLI commands | Yes | 8.3.1 | -- |

**Missing dependencies with no fallback:** None
**Missing dependencies with fallback:** None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24.x |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `pytest tests/test_monitor.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MON-01 | Monitor cycle runs, checks agents independently | unit | `pytest tests/test_monitor_loop.py::test_cycle_independent_checks -x` | Wave 0 |
| MON-02 | Liveness detects dead pane | unit | `pytest tests/test_monitor_checks.py::test_liveness_dead_agent -x` | Wave 0 |
| MON-03 | Stuck detection fires after 30min no commits | unit | `pytest tests/test_monitor_checks.py::test_stuck_detection -x` | Wave 0 |
| MON-04 | Plan gate detects new PLAN.md via mtime | unit | `pytest tests/test_monitor_checks.py::test_plan_gate_detection -x` | Wave 0 |
| MON-05 | ROADMAP.md parsed for phase progress | unit | `pytest tests/test_status_generator.py::test_roadmap_parsing -x` | Wave 0 |
| MON-06 | PROJECT-STATUS.md generated correctly | unit | `pytest tests/test_status_generator.py::test_status_generation -x` | Wave 0 |
| MON-07 | PROJECT-STATUS.md distributed to clones | unit | `pytest tests/test_status_generator.py::test_status_distribution -x` | Wave 0 |
| MON-08 | Heartbeat file updated each cycle, watchdog detects stale | unit | `pytest tests/test_heartbeat.py -x` | Wave 0 |
| COORD-01 | INTERFACES.md canonical copy management | unit | `pytest tests/test_coordination.py::test_interfaces_canonical -x` | Wave 0 |
| COORD-02 | Interface change flow logged | unit | `pytest tests/test_coordination.py::test_interface_change_log -x` | Wave 0 |
| COORD-03 | sync-context copies files to all clones | unit | `pytest tests/test_sync_context.py -x` | Wave 0 |
| SAFE-03 | INTERACTIONS.md covers known patterns | manual-only | Review INTERACTIONS.md content | -- |

### Sampling Rate
- **Per task commit:** `pytest tests/test_monitor_loop.py tests/test_monitor_checks.py tests/test_status_generator.py tests/test_heartbeat.py tests/test_coordination.py tests/test_sync_context.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before /gsd:verify-work

### Wave 0 Gaps
- [ ] `tests/test_monitor_loop.py` -- covers MON-01 (cycle independence, error isolation)
- [ ] `tests/test_monitor_checks.py` -- covers MON-02, MON-03, MON-04 (liveness, stuck, plan gate)
- [ ] `tests/test_status_generator.py` -- covers MON-05, MON-06, MON-07 (roadmap parse, status gen, distribution)
- [ ] `tests/test_heartbeat.py` -- covers MON-08 (heartbeat write, watchdog check)
- [ ] `tests/test_coordination.py` -- covers COORD-01, COORD-02 (interfaces, change log)
- [ ] `tests/test_sync_context.py` -- covers COORD-03 (sync files to clones)
- [ ] Async test setup: pytest-asyncio already in dev dependencies

## Sources

### Primary (HIGH confidence)
- Existing codebase: `src/vcompany/tmux/session.py` -- TmuxManager API (is_alive, send_command)
- Existing codebase: `src/vcompany/orchestrator/agent_manager.py` -- AgentManager pattern, agents.json
- Existing codebase: `src/vcompany/orchestrator/crash_tracker.py` -- callback injection pattern
- Existing codebase: `src/vcompany/shared/file_ops.py` -- write_atomic implementation
- Existing codebase: `src/vcompany/git/ops.py` -- git log wrapper
- `VCO-ARCHITECTURE.md` lines 260-298 -- PROJECT-STATUS.md format specification
- `VCO-ARCHITECTURE.md` lines 936-956 -- Monitor loop specification
- `.planning/research/PITFALLS.md` -- Pitfall 1 (partial reads), Pitfall 7 (tmux drift), Pitfall 8 (monitor SPOF)

### Secondary (MEDIUM confidence)
- Python asyncio documentation -- asyncio.gather with return_exceptions pattern
- Python os.path.getmtime / pathlib.stat().st_mtime -- mtime-based polling

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and used in Phase 1-2
- Architecture: HIGH -- follows established patterns from existing codebase, all decisions locked
- Pitfalls: HIGH -- most identified in pre-existing PITFALLS.md research, verified against codebase

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable domain, no external dependency changes expected)
