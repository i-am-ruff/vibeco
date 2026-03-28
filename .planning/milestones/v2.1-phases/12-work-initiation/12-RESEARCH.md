# Phase 12: Work Initiation - Research

**Researched:** 2026-03-28
**Domain:** tmux prompt detection, GSD command injection, AgentContainer lifecycle
**Confidence:** HIGH

## Summary

Phase 12 adds two behaviors to the existing `AgentContainer._launch_tmux_session()` flow: (1) detect when Claude Code is ready at its interactive prompt before injecting a GSD command, and (2) send that GSD command once readiness is confirmed.

The codebase already has all the infrastructure required. `TmuxManager.get_output()` reads pane content and already has a subprocess fallback. `TmuxManager.send_command()` sends keystrokes. `AgentContainer._launch_tmux_session()` launches Claude Code and is the correct insertion point for both features. No new libraries are needed.

The readiness signal for Claude Code is a known pane-content pattern: Claude Code renders a `>` prompt on an otherwise empty line when it is idle and waiting for input. The current code does a blind `asyncio.sleep(3)` then sends an Enter keypress to accept a workspace trust dialog — this needs to be replaced with a poll loop that reads pane output and waits for the readiness indicator.

The GSD command to send (e.g., `/gsd:discuss-phase 1`) must be configurable per agent. The natural location for it is the `ChildSpec` or `ContainerContext`, since `_launch_tmux_session` already has access to the context. `ContainerContext` already has a `gsd_mode` field, establishing precedent for GSD-related config there.

**Primary recommendation:** Add `gsd_command: str | None = None` to `ContainerContext`. In `AgentContainer._launch_tmux_session()`, replace the blind `sleep(3)` with a poll loop that calls `TmuxManager.get_output()` and checks for the Claude Code ready prompt, then `send_command` the GSD command if one is configured.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Claude's Discretion
All implementation choices are at Claude's discretion.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WORK-01 | After container starts and tmux launches Claude Code, the system sends a GSD command (`/gsd:discuss-phase N`) to the agent's tmux pane — agent begins working autonomously | Add `gsd_command` to `ContainerContext`. Send it from `_launch_tmux_session()` after readiness is confirmed. |
| WORK-02 | Container detects Claude Code readiness (prompt available) before sending the GSD command — no blind timing-based waits | Replace `asyncio.sleep(3)` in `_launch_tmux_session()` with a poll loop on `TmuxManager.get_output()` checking for the Claude Code idle prompt pattern. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| libtmux | 0.55.x | tmux pane control | Already the project's tmux abstraction layer — all tmux ops go through `TmuxManager` |
| asyncio (stdlib) | N/A | Async poll loop | Already used throughout; `asyncio.sleep` for poll intervals, `asyncio.wait_for` for timeout |
| pydantic | 2.11.x | `ContainerContext` model | Already the data model for container config |

No new libraries are needed. This phase is pure wiring of existing capabilities.

**Installation:** No new dependencies required.

## Architecture Patterns

### Recommended Project Structure

No new files or directories. Changes are confined to:

```
src/vcompany/
├── container/
│   ├── context.py          # Add gsd_command field
│   └── container.py        # Replace sleep(3) + Enter with readiness poll
tests/
├── test_container_tmux_bridge.py    # Add work initiation tests
└── test_gsd_agent.py               # Add tests for gsd_command injection
```

### Pattern 1: Readiness Poll Loop

**What:** Poll `TmuxManager.get_output()` in a loop until the pane shows the Claude Code ready indicator, with a configurable timeout.

**When to use:** After sending the `claude` launch command, before sending the GSD command.

**Claude Code ready indicator:** When Claude Code is idle at its prompt, the last non-empty line in the pane contains `>` (the Claude Code prompt character). The workspace trust prompt also shows before Claude Code's own prompt — the current code sends Enter to accept it, then needs to re-poll for the GSD-ready state.

**Example:**
```python
# Source: codebase analysis of TmuxManager.get_output() + existing dispatch_cmd.py pattern
async def _wait_for_claude_ready(
    self,
    pane: libtmux.Pane,
    timeout: float = 60.0,
    poll_interval: float = 1.0,
) -> bool:
    """Poll pane output until Claude Code shows its ready prompt.

    Returns True when ready, False if timeout elapsed.
    The Claude Code idle indicator is a '>' character on the last
    non-empty line of pane output.
    """
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        lines = await asyncio.to_thread(self._tmux.get_output, pane)
        # Find last non-empty line
        for line in reversed(lines):
            stripped = line.strip()
            if stripped:
                if stripped.endswith(">") or stripped == ">":
                    return True
                break  # last non-empty line is not the ready prompt yet
        await asyncio.sleep(poll_interval)
    return False
```

### Pattern 2: gsd_command on ContainerContext

**What:** Store the GSD command to run as an optional field on `ContainerContext`, set at container creation time.

**When to use:** When creating a `ChildSpec` for a GSD agent that should auto-start work.

**Example:**
```python
# Source: src/vcompany/container/context.py pattern + REQUIREMENTS.md
class ContainerContext(BaseModel):
    agent_id: str
    agent_type: str
    parent_id: str | None = None
    project_id: str | None = None
    owned_dirs: list[str] = []
    gsd_mode: str = "full"
    system_prompt: str = ""
    gsd_command: str | None = None   # NEW: e.g. "/gsd:discuss-phase 1"
```

### Pattern 3: Revised _launch_tmux_session()

**What:** After launching Claude Code, accept the workspace trust prompt, then wait for readiness, then optionally send the GSD command.

**When to use:** Always, when `_tmux` is set and `_needs_tmux_session` is True.

**Example:**
```python
# Source: src/vcompany/container/container.py — replacing current sleep(3) pattern
async def _launch_tmux_session(self) -> None:
    session = await asyncio.to_thread(
        self._tmux.get_or_create_session, self._project_session_name
    )
    pane = await asyncio.to_thread(
        self._tmux.create_pane, session, window_name=self.context.agent_id
    )
    self._pane_id = pane.pane_id
    cmd = self._build_launch_command()
    await asyncio.to_thread(self._tmux.send_command, pane, cmd)

    # Accept workspace trust prompt (non-blind: wait briefly then send Enter)
    await asyncio.sleep(2)
    await asyncio.to_thread(pane.send_keys, "", enter=True)

    # Wait for Claude Code ready prompt before injecting GSD command
    if self.context.gsd_command:
        ready = await self._wait_for_claude_ready(pane)
        if ready:
            await asyncio.to_thread(self._tmux.send_command, pane, self.context.gsd_command)
            logger.info(
                "Sent GSD command to %s: %s",
                self.context.agent_id,
                self.context.gsd_command,
            )
        else:
            logger.warning(
                "Claude Code did not become ready within timeout for %s — GSD command not sent",
                self.context.agent_id,
            )
```

### Pattern 4: How gsd_command Gets Set

In `/new-project` (commands.py), the existing code creates `ContainerContext` objects for each agent. The GSD command needs to be populated based on the agent's assignment.

For v2.1 Phase 12, the command is `/gsd:discuss-phase 1` (the first phase). In a later phase (WORK-03), the PM will assign specific phase numbers. For now, a fixed default of phase 1 is appropriate.

**Setting gsd_command when building specs in commands.py:**
```python
ctx = ContainerContext(
    agent_id=agent.id,
    agent_type=agent.type,
    parent_id="project-supervisor",
    project_id=config.project,
    owned_dirs=agent.owns,
    gsd_command="/gsd:discuss-phase 1",  # auto-start Phase 1
)
```

### Anti-Patterns to Avoid

- **Blind sleep as readiness gate:** `await asyncio.sleep(3)` before sending the GSD command assumes Claude Code loads in under 3 seconds on any machine. This is the bug WORK-02 explicitly prohibits. Replace with the poll loop.
- **Sending GSD command without context:** The current `_launch_tmux_session()` sends an empty Enter but no GSD command. The GSD command must come from context, not be hardcoded in the container base class.
- **Bypassing TmuxManager for pane reads:** Do not call `subprocess.run(["tmux", ...])` directly for readiness polling. Use `TmuxManager.get_output()` which already has the subprocess fallback built in.
- **Blocking the asyncio event loop:** All `TmuxManager` calls must be wrapped in `asyncio.to_thread()` — this is already the pattern in `_launch_tmux_session()`.
- **Tight poll loop without sleep:** Always `await asyncio.sleep(poll_interval)` between pane reads to avoid busy-waiting on the event loop.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pane content reading | Custom subprocess tmux capture | `TmuxManager.get_output()` | Already implemented with libtmux + subprocess fallback |
| Sending commands to pane | Direct libtmux calls in container | `TmuxManager.send_command()` | Encapsulates libtmux; the project's isolation contract |
| Timeout on async wait | Manual `time.time()` loops | `asyncio.wait_for()` with `asyncio.sleep` poll | Clean async cancellation |

**Key insight:** The tmux interaction layer is fully built. Phase 12 is behavioral wiring — add the poll loop and the command send. Do not add new tmux abstractions.

## Common Pitfalls

### Pitfall 1: Workspace Trust Prompt Races with Claude Code Prompt

**What goes wrong:** After the `claude` command starts, Claude Code shows a workspace trust dialog _before_ its idle `>` prompt. If the poll loop detects a `>` that was part of the trust dialog rather than Claude Code's own prompt, the GSD command fires too early, before Claude Code is fully initialized.

**Why it happens:** The trust prompt text may also contain `>` characters (e.g., `Do you trust the files in this folder? >`). The detection pattern must be specific enough to distinguish Claude Code's idle prompt from other interactive prompts.

**How to avoid:** The current code sends a blank Enter after `sleep(2)` to accept the trust dialog. After that Enter is sent, re-poll for the Claude Code idle prompt. Claude Code's actual ready prompt is typically the `>` on its own line (or with leading spaces), not embedded in question text. A reliable pattern is: the last non-empty pane line is exactly `>` or ends with ` > ` in a recognizable position. If uncertain, a short additional `sleep(1)` after the Enter keypress before beginning the poll is a reasonable conservative measure.

**Warning signs:** Agent receives GSD command but Claude Code does not execute it (because Claude Code was still initializing).

### Pitfall 2: Poll Loop Never Terminates Without Timeout

**What goes wrong:** If Claude Code fails to start (binary not found, permissions error, env var missing), the poll loop waits forever, blocking the asyncio task that called `container.start()`.

**Why it happens:** No timeout on the readiness poll.

**How to avoid:** Always set a timeout (60 seconds is reasonable). If timeout elapses without readiness, log a warning and leave `gsd_command` unsent. The container's tmux liveness monitor will detect Claude Code process death and transition the container to `errored`, which triggers supervisor restart.

**Warning signs:** `container.start()` hangs indefinitely.

### Pitfall 3: pane Reference Goes Stale

**What goes wrong:** The `pane` object returned by `create_pane()` is a libtmux object. If the pane is killed between `_launch_tmux_session` being called and the poll loop running, `get_output()` will return empty or raise.

**Why it happens:** Short-lived sessions or race conditions during supervisor restarts.

**How to avoid:** Wrap `get_output()` calls in try/except within the poll loop. An empty list from `get_output()` should be treated as "not ready yet" rather than an error (since it may just be that tmux hasn't flushed output yet). Only a genuine exception should trigger early exit.

### Pitfall 4: gsd_command Sent But Not Recognized (Stale Inner State)

**What goes wrong:** The GSD command `/gsd:discuss-phase 1` is sent but Claude Code is in a state where it cannot execute slash commands (e.g., mid-loading, or in a different interactive mode).

**Why it happens:** The readiness detection only checks for the `>` prompt but Claude Code may have other interactive flows (e.g., showing startup messages that happen to end with `>`).

**How to avoid:** After sending the GSD command, the agent container does not need to verify it was received — the supervision tree monitors tmux liveness and the agent's progress will be visible through GSD state files (which Phase 13-14 will track). For now, detecting the `>` prompt and logging the send is sufficient.

### Pitfall 5: Tests Hang Because _wait_for_claude_ready Polls Real tmux

**What goes wrong:** Unit tests for `AgentContainer` with injected mock `TmuxManager` hit the real poll loop, which calls `mock.get_output()`. If the mock returns empty lists, the loop runs until timeout (60s), making tests extremely slow.

**Why it happens:** The poll loop is inside `_launch_tmux_session()` which existing tests call.

**How to avoid:** In tests, mock `get_output` to return a list containing `">"` immediately, OR patch `_wait_for_claude_ready` to return `True` without looping. The existing test pattern in `test_container_tmux_bridge.py` already patches `asyncio.sleep` — extend that pattern to also configure `mock_tmux.get_output.return_value = [">"]`.

## Code Examples

### Checking TmuxManager.get_output() Return Value
```python
# Source: src/vcompany/tmux/session.py — get_output() returns list[str]
# Each string is one line of pane output (may have trailing whitespace)
# Example output when Claude Code is ready:
# ["", "  Welcome to Claude Code", "", "> "]
# The last non-empty element will be the prompt line.

lines = tmux.get_output(pane)  # returns list[str]
for line in reversed(lines):
    stripped = line.strip()
    if stripped:
        # Check if this is Claude Code's ready prompt
        is_ready = stripped == ">" or stripped.endswith(" >")
        break
```

### Wiring gsd_command in Supervisor._start_child (Already Passes Context Through)
```python
# Source: src/vcompany/supervisor/supervisor.py:_start_child
# container = create_container(spec, ...) — spec.context already flows through
# ContainerContext.gsd_command will be available inside _launch_tmux_session
# via self.context.gsd_command — no additional plumbing needed.
```

### Existing Test Helper to Extend
```python
# Source: tests/test_container_tmux_bridge.py:_mock_tmux()
def _mock_tmux():
    mock_tmux = MagicMock()
    mock_pane = MagicMock()
    mock_pane.pane_id = "%99"
    mock_pane.send_keys = MagicMock()
    mock_tmux.get_or_create_session.return_value = MagicMock()
    mock_tmux.create_pane.return_value = mock_pane
    mock_tmux.send_command.return_value = True
    mock_tmux.get_pane_by_id.return_value = mock_pane
    mock_tmux.is_alive.return_value = True
    # For Phase 12 tests, add:
    mock_tmux.get_output.return_value = [">"]  # simulate ready prompt immediately
    return mock_tmux
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `time.sleep()` blocking dispatch | `asyncio.to_thread()` for tmux ops | v2.0 | No event loop blocking |
| Blind `sleep(3)` trust dialog accept | Poll loop readiness detection | Phase 12 (this phase) | WORK-02 compliance |
| No GSD command post-launch | `gsd_command` from context | Phase 12 (this phase) | WORK-01 compliance |

**Deprecated/outdated:**
- Blind `asyncio.sleep(3)` + Enter in `_launch_tmux_session()`: replaced by readiness poll in this phase.

## Open Questions

1. **Claude Code prompt exact format**
   - What we know: Claude Code displays `>` when idle. The exact pane output format (leading spaces, ANSI escape codes, etc.) depends on the terminal and Claude Code version.
   - What's unclear: Whether `capture_pane` strips ANSI codes (it usually does for content), and whether the prompt always ends with a bare `>` or can have other text.
   - Recommendation: Use a loose check — any non-empty line whose stripped form is `">"` OR ends with `" >"`. If the first integration test fails, adjust the pattern. Do not over-engineer the detection.

2. **Trust dialog timing variation**
   - What we know: The current code sleeps 2-3 seconds before sending Enter for trust dialog acceptance. On a slow machine this may not be enough.
   - What's unclear: Whether the trust dialog also appears as a `>` prompt in pane capture, which would cause the readiness poll to fire before Claude Code is truly ready.
   - Recommendation: Send the Enter keypress after `sleep(2)`, then immediately begin polling for the Claude Code prompt. If the trust dialog `>` causes a false positive, add a second poll cycle after detecting the first `>` to confirm Claude Code's full initialization message has appeared.

## Environment Availability

Step 2.6: SKIPPED (no new external dependencies — phase uses existing tmux, libtmux, and asyncio infrastructure already present in the environment).

## Sources

### Primary (HIGH confidence)
- `src/vcompany/container/container.py` — `_launch_tmux_session()`, `_build_launch_command()`, `AgentContainer.__init__` — direct code inspection
- `src/vcompany/tmux/session.py` — `TmuxManager.get_output()`, `send_command()`, `get_pane_by_id()` — direct code inspection
- `src/vcompany/container/context.py` — `ContainerContext` model with `gsd_mode` precedent — direct code inspection
- `src/vcompany/agent/gsd_agent.py` — `GsdAgent` lifecycle, `gsd_command` wiring point — direct code inspection
- `src/vcompany/supervisor/supervisor.py` — `_start_child()` shows how context flows from spec to container — direct code inspection
- `src/vcompany/cli/dispatch_cmd.py` — existing dispatch pattern (blind sleep, no GSD command send) — direct code inspection
- `tests/test_container_tmux_bridge.py` — existing test helpers and mock patterns — direct code inspection
- `.planning/REQUIREMENTS.md` — WORK-01 and WORK-02 exact requirement text — direct read

### Secondary (MEDIUM confidence)
- `src/vcompany/coordination/interactions.py` — comment at line 55 confirms the agent is "at the prompt waiting for input" when idle — describes the expected ready state

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in use, no new dependencies
- Architecture: HIGH — change is confined to `context.py` (one field) and `container.py` (one method), both well-understood
- Pitfalls: HIGH — workspace trust prompt race and poll timeout are predictable failure modes from code inspection; test hang pitfall is directly visible in existing test patterns

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable domain — tmux behavior does not change; Claude Code prompt format is empirically observable)
