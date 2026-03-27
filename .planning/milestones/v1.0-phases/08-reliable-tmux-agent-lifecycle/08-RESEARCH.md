# Phase 8: Reliable tmux Agent Lifecycle - Research

**Researched:** 2026-03-27
**Domain:** tmux session management, Claude Code readiness detection, asyncio/thread interop
**Confidence:** HIGH

## Summary

Phase 8 fixes reliability issues in the tmux-based agent lifecycle: work commands not reaching agents, false timeouts waiting for Claude readiness, and libtmux Pane objects being used incorrectly across async boundaries. The codebase already has the architecture (TmuxManager, AgentManager, MonitorLoop) -- this phase hardens it.

The core finding is that **libtmux is already thread-safe at the subprocess level** -- every operation calls `subprocess.Popen` under the hood. The real issues are: (1) callers passing string `pane_id` where libtmux `Pane` objects are expected, (2) `_wait_for_claude_ready` using unreliable prompt detection heuristics with a 30-second post-ready delay that wastes time, and (3) the `_panes` dict in AgentManager being the only source of Pane objects but not being shared with the monitor or bot cogs that need them.

**Primary recommendation:** Fix the pane reference architecture so all callers (AgentManager, MonitorLoop, PlanReviewCog, StandupSession) reliably resolve pane_id strings to Pane objects via TmuxManager.get_pane_by_id(). Improve readiness detection to look for specific Claude Code UI markers. Reduce post-ready delay from 30s to 2-5s.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LIFE-01 | `vco dispatch` launches Claude Code sessions in tmux panes with `--dangerously-skip-permissions` and `--append-system-prompt` | Already implemented. Phase 8 fixes the FOLLOW-UP: work command delivery after launch. Readiness detection and send_work_command must work reliably. |
| MON-02 | Liveness check verifies tmux pane alive AND actual process PID inside pane | Already implemented in checks.py. Phase 8 ensures the pane reference passed to check_liveness is a valid Pane object (not None due to lookup failures). |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| libtmux | 0.55.0 | tmux Python API | Already in use. Thread-safe at subprocess level. Pane objects are lightweight wrappers that shell out to tmux CLI for every operation. |
| tmux | 3.4 | Terminal multiplexer | Already installed. Provides send-keys, capture-pane CLI that libtmux wraps. |
| asyncio (stdlib) | N/A | Async coordination | Already used by MonitorLoop and bot. asyncio.to_thread is the correct bridge for calling libtmux from async code. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| subprocess (stdlib) | N/A | Direct tmux CLI fallback | Use ONLY if libtmux Pane object is unavailable (e.g., pane_id known but Pane lookup fails). Not a replacement for libtmux. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| libtmux Pane objects | Raw subprocess tmux calls everywhere | The reverted commits (a032bba, 87cb7ae) tried this approach. It duplicates libtmux's functionality, loses type safety, and creates a parallel code path. NOT recommended. |
| libtmux | tmux control mode (-CC) | Would allow event-driven tmux interaction but adds massive complexity. Overkill for send-keys + capture-pane. |

## Architecture Patterns

### Current Architecture (with identified issues)

```
AgentManager._panes: dict[str, Pane]  <-- Only source of Pane objects
    |
    |- dispatch() stores Pane after create_pane()
    |- send_work_command() reads from _panes
    |- dispatch_fix() reads from _panes
    |
    (BUT: _panes is in-memory only, lost on restart)

agents.json (persisted)
    |
    |- Stores pane_id as STRING (e.g., "%5")
    |- MonitorLoop reads this, resolves via get_pane_by_id()
    |- PlanReviewCog reads this, passes STRING to send_command() <-- BUG
    |- StandupSession receives STRING, passes to send_command() <-- BUG
```

### Pattern 1: Centralized Pane Resolution
**What:** All callers resolve pane_id strings to Pane objects via TmuxManager.get_pane_by_id() before calling send_command().
**When to use:** Always. Never pass a string where a Pane object is expected.
**Example:**
```python
# CORRECT: resolve pane_id to Pane object first
pane = tmux.get_pane_by_id(entry.pane_id)
if pane:
    tmux.send_command(pane, command)
else:
    logger.error("Pane %s not found for agent %s", entry.pane_id, agent_id)

# WRONG: passing string pane_id directly
tmux.send_command(entry.pane_id, feedback_cmd)  # TypeError at runtime
```

### Pattern 2: Subprocess Fallback for send_command
**What:** TmuxManager.send_command() accepts either a Pane object or a pane_id string, falling back to subprocess when given a string.
**When to use:** When callers only have a pane_id string and the pane might not be resolvable.
**Example:**
```python
def send_command(self, pane_or_id: libtmux.Pane | str, command: str) -> bool:
    """Send a command to a tmux pane. Accepts Pane object or pane_id string."""
    if isinstance(pane_or_id, str):
        # Fallback: use raw tmux send-keys with pane_id target
        import subprocess as sp
        result = sp.run(
            ["tmux", "send-keys", "-t", pane_or_id, command, "Enter"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    pane_or_id.send_keys(command)
    return True
```

### Pattern 3: Reliable Readiness Detection
**What:** Detect Claude Code readiness by looking for specific UI markers in pane output.
**When to use:** Before sending first work command after dispatch.
**Example:**
```python
def _wait_for_claude_ready(self, pane, agent_id, timeout=120, poll_interval=2):
    """Poll pane for Claude Code ready markers."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        output = self._tmux.get_output(pane, lines=30)
        text = "\n".join(output).lower()
        # Claude Code 2.1.x shows these when ready:
        # 1. "bypass permissions" in status bar (if --dangerously-skip-permissions)
        # 2. The input prompt character
        # 3. "type a message" or "what can i help" type text
        if any(marker in text for marker in [
            "bypass permissions",
            "what can i help",
            "type your prompt",
            "tips:",
        ]):
            logger.info("Claude ready for %s", agent_id)
            time.sleep(2)  # Brief settle time, NOT 30 seconds
            return True
        time.sleep(poll_interval)
    logger.warning("Timeout waiting for Claude ready on %s", agent_id)
    return False
```

### Anti-Patterns to Avoid
- **Passing pane_id strings to send_command():** Current bug in PlanReviewCog._handle_rejection and StandupSession.route_message_to_agent. These pass the string pane_id from agents.json directly to tmux.send_command() which expects a Pane object.
- **30-second post-ready delay:** Current _wait_for_claude_ready waits 30s AFTER detecting the prompt. Claude Code is ready when the prompt appears -- 2-3 seconds settle time is sufficient.
- **Checking for ">" as readiness marker:** Too generic. The ">" character appears in many contexts (file paths, shell prompts, markdown). Use Claude-specific markers.
- **Replacing libtmux with raw subprocess everywhere:** The reverted commits (a032bba, 87cb7ae) tried this. It duplicates functionality and loses the benefits of the typed API.
- **Storing Pane objects across process boundaries:** Pane objects contain a reference to the libtmux Server which opens a connection. They work fine within a single process across threads (since they just shell out to tmux CLI), but cannot be serialized.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pane targeting | Custom session:window:pane string parsing | libtmux's Pane.cmd() auto-targeting via pane_id | libtmux already handles the -t flag correctly |
| Tmux output capture | Raw subprocess capture-pane | libtmux Pane.capture_pane() | Handles encoding, line joining, edge cases |
| Process tree walking | Custom /proc scanner for readiness | pane.capture_pane() output inspection | Process PIDs tell you if something is running, not if it's ready for input |

## Common Pitfalls

### Pitfall 1: String pane_id vs Pane Object Confusion
**What goes wrong:** Code passes a pane_id string (e.g., "%5") where a libtmux Pane object is expected. send_keys() fails silently or raises AttributeError.
**Why it happens:** agents.json stores pane_id as a string. Callers that load from JSON forget to resolve it.
**How to avoid:** Make TmuxManager.send_command() accept both types (Pane | str) with runtime type checking. Or always resolve before calling.
**Warning signs:** "Failed to send" errors in logs; agents not receiving commands despite appearing alive.

### Pitfall 2: False Readiness Detection
**What goes wrong:** _wait_for_claude_ready detects a ">" in pane output and thinks Claude is ready, but it's actually a shell prompt or file content.
**Why it happens:** The ">" character is too generic as a readiness marker.
**How to avoid:** Use Claude Code-specific markers: "bypass permissions", "what can i help", "tips:". These are unique to Claude Code's TUI.
**Warning signs:** Work commands sent to shell prompt instead of Claude prompt; commands appearing as shell errors.

### Pitfall 3: Excessive Post-Ready Delay
**What goes wrong:** 30-second delay after detecting readiness causes dispatch of 3 agents to take 90+ seconds just in wait time.
**Why it happens:** Original implementation was conservative, unsure how long Claude needs after showing prompt.
**How to avoid:** Claude Code is ready to accept input as soon as the prompt appears. 2-3 seconds settle time is sufficient. Total dispatch time for 3 agents should be under 2 minutes.
**Warning signs:** "Waiting Xs for full init" logs with large X values; slow dispatch.

### Pitfall 4: asyncio.to_thread and libtmux Safety
**What goes wrong:** Concern that libtmux Pane objects are not thread-safe when used from asyncio.to_thread.
**Why it happens:** Misunderstanding of libtmux internals. Each libtmux operation (send_keys, capture_pane) creates a NEW subprocess.Popen call. There is no shared mutable state in the Pane object itself -- it's just a container for pane_id + server reference.
**How to avoid:** libtmux Pane objects ARE safe to use from asyncio.to_thread because each operation is a stateless subprocess call. The pane_id string is immutable. The only risk is if the pane is killed between lookup and use, which is a race condition, not a thread safety issue.
**Warning signs:** None -- this is actually fine. The reverted commits were solving a non-problem.

### Pitfall 5: _panes Dict Not Shared
**What goes wrong:** AgentManager._panes stores Pane objects in memory, but PlanReviewCog and MonitorLoop don't have access to it. They read pane_id from agents.json and must resolve separately.
**Why it happens:** AgentManager is created in the CLI or bot context, but its _panes dict is private and not accessible to all consumers.
**How to avoid:** Either: (a) use TmuxManager.get_pane_by_id() everywhere (already works), or (b) expose a method on AgentManager for pane lookup. Option (a) is simpler and already implemented.

### Pitfall 6: Pane Gone Between Lookup and Use
**What goes wrong:** get_pane_by_id returns a Pane, but by the time send_command runs, the pane has been killed.
**Why it happens:** Race between agent crash/kill and command send.
**How to avoid:** Wrap send_command in try/except. Log the failure. The monitor will detect the dead pane on next cycle.
**Warning signs:** Sporadic "pane not found" errors in logs.

## Code Examples

### Fix 1: Make send_command Accept Both Types
```python
# In TmuxManager (src/vcompany/tmux/session.py)
def send_command(self, pane: libtmux.Pane | str, command: str) -> bool:
    """Send a command string to a tmux pane.

    Accepts either a libtmux Pane object or a pane_id string.
    Returns True if command was sent, False on error.
    """
    try:
        if isinstance(pane, str):
            # Resolve string to Pane object
            resolved = self.get_pane_by_id(pane)
            if resolved is None:
                logger.error("Cannot resolve pane_id %s", pane)
                return False
            pane = resolved
        pane.send_keys(command)
        return True
    except Exception:
        logger.exception("Failed to send command to pane")
        return False
```

### Fix 2: Improved Readiness Detection
```python
# Claude Code 2.1.x ready markers (case-insensitive matching)
CLAUDE_READY_MARKERS = [
    "bypass permissions",    # Status bar when --dangerously-skip-permissions
    "what can i help",       # Welcome message
    "type your prompt",      # Input hint
    "tips:",                 # Tips section in welcome screen
]

def _wait_for_claude_ready(self, pane, agent_id, timeout=120, poll_interval=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            output = self._tmux.get_output(pane, lines=30)
            text = "\n".join(output).lower()
            if any(marker in text for marker in CLAUDE_READY_MARKERS):
                logger.info("Claude ready for %s (detected marker in output)", agent_id)
                time.sleep(2)  # Brief settle, NOT 30s
                return True
        except Exception:
            pass
        time.sleep(poll_interval)
    logger.warning("Timeout (%ds) waiting for Claude ready on %s", timeout, agent_id)
    return False
```

### Fix 3: PlanReviewCog Correct Pane Usage
```python
# In PlanReviewCog._handle_rejection -- FIXED
if entry and entry.pane_id:
    pane = tmux.get_pane_by_id(entry.pane_id)
    if pane:
        await asyncio.to_thread(tmux.send_command, pane, feedback_cmd)
    else:
        logger.warning("Could not resolve pane for %s", agent_id)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `_panes` dict as sole pane source | `get_pane_by_id()` for persistent lookup | Phase 3 (added get_pane_by_id) | Allows any code with pane_id string to get Pane object |
| Fixed 15s startup delay | `_wait_for_claude_ready` polling | Added in dispatch_cmd.py | Correct approach, but ready markers need refinement |
| Raw subprocess tmux (reverted) | libtmux wrapper | Reverted in d2b2c44 | libtmux is correct approach; the bugs were elsewhere |

**Key insight about Claude Code 2.1.81:**
- `skipDangerousModePermissionPrompt: true` in `~/.claude/settings.json` prevents the permissions confirmation dialog. Already set on this machine. Agents should also have this set in their clone's `.claude/settings.json`.
- Claude Code shows "bypass permissions" in the status bar when running in dangerous mode -- this is a reliable ready marker.
- The welcome screen shows tips and a prompt -- these are reliable markers too.

## Open Questions

1. **What exact text does Claude Code 2.1.81 show when ready?**
   - What we know: "bypass permissions" appears in status bar; prompt area shows welcome text
   - What's unclear: Exact text varies by version; may change in updates
   - Recommendation: Use multiple markers, log which one triggered, so future debugging is easy

2. **Should send_work_command be async or remain sync?**
   - What we know: Currently sync, called via asyncio.to_thread. Works fine since libtmux uses subprocess internally.
   - What's unclear: Whether parallel sends to multiple agents would be faster with asyncio
   - Recommendation: Keep sync, use asyncio.to_thread. The subprocess calls are fast (< 100ms). Parallelism can be added with asyncio.gather wrapping to_thread calls in send_work_command_all.

3. **Should agents' .claude/settings.json include skipDangerousModePermissionPrompt?**
   - What we know: The host machine has it set. Agent clones get a settings.json during clone setup.
   - What's unclear: Whether the clone setup already includes this setting
   - Recommendation: Verify clone setup includes it. If not, add it to prevent permission dialog from blocking agents.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| tmux | Agent sessions | Yes | 3.4 | -- |
| libtmux | Python tmux API | Yes | 0.55.0 | subprocess tmux calls |
| Claude Code | Agent runtime | Yes | 2.1.81 | -- |
| asyncio (stdlib) | Async coordination | Yes | N/A | -- |

**Missing dependencies with no fallback:** None
**Missing dependencies with fallback:** None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24.x |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_tmux.py tests/test_dispatch.py tests/test_monitor_loop.py tests/test_monitor_checks.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LIFE-01 | send_work_command delivers commands to agent Claude sessions | unit | `uv run pytest tests/test_dispatch.py -x -q -k "send_work"` | Partially (dispatch tests exist, send_work_command tests missing) |
| LIFE-01 | _wait_for_claude_ready detects readiness correctly | unit | `uv run pytest tests/test_dispatch.py -x -q -k "wait_ready"` | Missing |
| MON-02 | Liveness check gets valid Pane from pane_id | unit | `uv run pytest tests/test_monitor_checks.py -x -q -k "liveness"` | Yes (but uses mock pane, not string resolution) |
| LIFE-01 | TmuxManager.send_command accepts Pane | str | unit | `uv run pytest tests/test_tmux.py -x -q -k "send"` | Partially (Pane only, no string test) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_tmux.py tests/test_dispatch.py tests/test_monitor_checks.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_dispatch.py::TestSendWorkCommand` -- tests for send_work_command, _wait_for_claude_ready
- [ ] `tests/test_tmux.py::TestSendCommandStringPaneId` -- tests for string pane_id acceptance
- [ ] `tests/test_dispatch.py::TestSendWorkCommandAll` -- tests for parallel send to all agents

## Sources

### Primary (HIGH confidence)
- libtmux 0.55.0 source code (inspected via Python inspect module) -- confirmed subprocess.Popen for every tmux operation
- Existing codebase inspection -- identified string vs Pane object bugs in plan_review.py and standup.py
- Git history (d2b2c44 revert) -- confirmed raw subprocess approach was reverted as unresearched
- Claude Code 2.1.81 (installed locally) -- confirmed bypass permissions behavior

### Secondary (MEDIUM confidence)
- [Claude Code bypass permissions issue](https://github.com/awslabs/cli-agent-orchestrator/issues/119) -- skipDangerousModePermissionPrompt setting confirmed
- [Claude Code agent teams stuck issue](https://github.com/anthropics/claude-code/issues/24108) -- confirms mailbox-based agents get stuck but our approach (tmux send-keys) is different
- [Claude Code permission mode docs](https://code.claude.com/docs/en/permission-modes) -- confirms --dangerously-skip-permissions flag behavior
- [libtmux documentation](https://libtmux.git-pull.com/) -- confirms pre-1.0 API status

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - libtmux 0.55.0 already in use, internals inspected via source
- Architecture: HIGH - bugs identified by direct code inspection, fixes are straightforward
- Pitfalls: HIGH - root causes confirmed by reading libtmux source and git history
- Readiness detection: MEDIUM - Claude Code UI markers may change between versions

**Research date:** 2026-03-27
**Valid until:** 2026-04-10 (libtmux 0.55.x is stable; Claude Code updates may change UI markers)
