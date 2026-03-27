# Phase 7: Integration Pipeline and Communications - Research

**Researched:** 2026-03-25
**Domain:** Git merge automation, test attribution, Discord interactive communications
**Confidence:** HIGH

## Summary

Phase 7 builds three major subsystems: (1) an integration pipeline that merges agent branches, runs tests, attributes failures, and creates PRs; (2) a checkin ritual that auto-posts after phase completion; and (3) a standup ritual with blocking interlock and owner control via Discord threads. All three build on established patterns from prior phases -- callback injection, ConfirmView buttons, asyncio.to_thread for blocking ops, and atomic file writes.

The integration pipeline is the most complex piece. It requires extending `git/ops.py` with merge/push/fetch/diff operations, implementing N+1 test runs for failure attribution (D-06), AI conflict resolution via PMTier (D-04/D-05), and automatic fix dispatch via AgentManager (D-07). The standup system requires a new discord.py View with Release buttons per agent thread and bidirectional tmux communication (questions routed to panes, answers routed back to threads).

**Primary recommendation:** Structure implementation as: (1) git ops extensions, (2) integration pipeline core, (3) integration interlock in MonitorLoop, (4) checkin ritual, (5) standup ritual with blocking interlock, (6) interaction regression tests.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Integration uses interlock model -- agents finish current phase, then integration triggers when ALL agents idle
- D-02: Integration waits for natural synchronization point (all agents idle after phase completion)
- D-03: `vco integrate` creates integration branch from main, merges all agent branches (agent/{id.lower()})
- D-04: AI-assisted conflict resolution via PM tier (stateless, fast). Falls back to Discord escalation on low confidence
- D-05: Non-overlapping changes auto-merge via git. Only overlapping-line conflicts invoke PM resolver
- D-06: Per-branch test runs for attribution: merge all -> if fail -> test each branch individually -> attribute
- D-07: Fix dispatch automatic via /gsd:quick. Owner notified in #alerts
- D-08: On test success, create PR to main using `gh pr create`
- D-09: /vco:checkin runs automatically after phase completion, detected by monitor
- D-10: Checkin posts to #agent-{id} with commit count, summary, gaps/notes, next phase, dependency status
- D-11: /vco:standup uses blocking interlock -- agents blocked until owner clicks Release per thread
- D-12: Full owner control during standup -- reprioritize, reassign, ask questions, change scope
- D-13: Agent updates ROADMAP.md or STATE.md based on owner feedback during standup
- D-14: Interaction regression tests derived from INTERACTIONS.md critical patterns
- D-15: Tests marked @pytest.mark.integration -- only run during `vco integrate`
- D-16: Tests use mocks/fakes for tmux and subprocess

### Claude's Discretion
- Integration branch naming convention
- PR description template format
- Exact INTERACTIONS.md patterns to extract for regression tests
- Standup thread creation and formatting details
- Checkin embed format and content structure
- How to send questions from standup threads to agent tmux panes
- Retry logic for integration after fix dispatch

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTG-01 | Each agent commits to its own branch (branch-per-agent) | Already implemented in Phase 1 (agent/{id.lower()}). Integration reads these branches. |
| INTG-02 | `vco integrate` creates integration branch from main, merges all agent branches | New git ops (merge, fetch, push) + IntegrationPipeline class |
| INTG-03 | Integration runs full test suite after merge | subprocess pytest execution in integration branch working directory |
| INTG-04 | Test failures attributed to specific agent branches | N+1 test attribution algorithm per D-06 |
| INTG-05 | On test failure, orchestrator dispatches /gsd:quick fix to responsible agent | AgentManager.dispatch_fix() method + tmux send_command |
| INTG-06 | On success, creates PR to main | `gh pr create` via subprocess |
| INTG-07 | Merge conflict detection reports to Discord with file list and details | Git merge stderr parsing + Discord embed |
| INTG-08 | Conflict resolver agent attempts automatic resolution | PMTier Claude API call with conflict hunks as context |
| COMM-01 | /vco:checkin posts phase completion status to #agent-{id} channel | Monitor detects phase completion -> sends /vco:checkin to tmux -> agent posts to webhook |
| COMM-02 | Checkin includes commits count, summary, gaps/notes, next phase, dependency status | Checkin embed builder with structured fields |
| COMM-03 | /vco:standup posts structured status to #standup, creates thread per agent | StandupCog or extension to CommandsCog, thread creation per agent |
| COMM-04 | Standup listens for owner replies in threads | on_message listener filtering by thread parent + agent mapping |
| COMM-05 | Owner can reprioritize agents, change scope, ask questions via standup threads | Route thread messages to agent tmux panes, agent responses back to thread |
| COMM-06 | Agent updates ROADMAP.md or STATE.md based on owner feedback | Part of /gsd:quick prompt instructions sent to agent |
| SAFE-04 | Integration regression tests for critical concurrent scenarios | pytest.mark.integration tests using mocks from INTERACTIONS.md patterns |
</phase_requirements>

## Standard Stack

### Core (Already Installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.7.x | Standup threads, Release buttons, checkin embeds | Already in use. Thread support built-in. |
| anthropic | 0.86.x | PM conflict resolution | Already in use via PMTier |
| subprocess (stdlib) | N/A | Git operations, pytest execution, gh pr create | Project convention: no GitPython |
| asyncio (stdlib) | N/A | Async orchestration, to_thread wrapping | All blocking ops wrapped per DISC-11 |
| pytest | 8.0+ | Test execution and integration regression tests | Already in dev deps |

### Supporting (Already Installed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.11.x | IntegrationResult, StandupState models | All structured data |
| Rich | 14.2.x | CLI output for `vco integrate` progress | Terminal feedback |

No new dependencies needed for this phase.

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
├── git/
│   └── ops.py                  # Extend: merge, fetch, push, diff, checkout
├── integration/
│   ├── __init__.py
│   ├── pipeline.py             # IntegrationPipeline: merge + test + PR flow
│   ├── attribution.py          # Test failure attribution (N+1 algorithm)
│   └── conflict_resolver.py    # AI conflict resolution via PMTier
├── communication/
│   ├── __init__.py
│   ├── checkin.py              # Checkin logic: gather data, format, post
│   └── standup.py              # Standup session state, blocking interlock
├── bot/
│   ├── cogs/
│   │   └── commands.py         # Extend: !integrate, !standup full implementation
│   ├── views/
│   │   └── standup_release.py  # Release button View for standup threads
│   └── embeds.py               # Extend: build_checkin_embed, build_standup_embed, build_integration_embed
├── monitor/
│   └── loop.py                 # Extend: integration pending state, checkin trigger
└── orchestrator/
    └── agent_manager.py        # Extend: dispatch_fix() for INTG-05
tests/
├── test_integration_pipeline.py
├── test_attribution.py
├── test_conflict_resolver.py
├── test_checkin.py
├── test_standup.py
└── test_interaction_regression.py  # @pytest.mark.integration
```

### Pattern 1: Integration Pipeline as Orchestrator Class
**What:** A single IntegrationPipeline class that orchestrates the full merge-test-PR flow
**When to use:** Called from CommandsCog.integrate_cmd and from MonitorLoop integration interlock

```python
class IntegrationPipeline:
    """Orchestrates: create branch -> merge all -> test -> attribute -> PR or fix."""

    def __init__(
        self,
        project_dir: Path,
        config: ProjectConfig,
        pm: PMTier | None = None,
    ) -> None:
        self._project_dir = project_dir
        self._config = config
        self._pm = pm

    async def run(self) -> IntegrationResult:
        """Full integration cycle. Returns structured result."""
        branch_name = f"integrate/{int(time.time())}"
        # 1. Create integration branch from main
        # 2. Merge each agent branch (git merge agent/{id})
        # 3. If conflict: try PM resolution, else escalate
        # 4. Run tests
        # 5. If failures: attribute per D-06
        # 6. If success: gh pr create
        ...
```

### Pattern 2: Test Attribution Algorithm (D-06)
**What:** N+1 test runs to identify which agent branch caused failures
**When to use:** Only when merged test run fails

```python
async def attribute_failures(
    integration_dir: Path,
    failed_tests: list[str],
    agent_ids: list[str],
) -> dict[str, list[str]]:
    """Map test failures to responsible agents.

    Algorithm:
    1. Record which tests fail on full merge
    2. For each agent: checkout main + only that agent's branch
    3. Re-run ONLY the failing tests (not full suite)
    4. If tests fail with just agent-A -> agent-A owns it
    5. If tests pass with every individual branch -> interaction failure

    Returns: {agent_id: [test_names]} or {"interaction": [test_names]}
    """
```

### Pattern 3: Standup Blocking Interlock
**What:** Per-agent blocking with Release buttons in Discord threads
**When to use:** !standup command

```python
class StandupSession:
    """Tracks active standup state across all agents."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[None]] = {}  # agent_id -> release future

    async def block_agent(self, agent_id: str) -> None:
        """Block until owner releases this agent."""
        future = asyncio.get_event_loop().create_future()
        self._pending[agent_id] = future
        await future  # Blocks until release() called

    def release_agent(self, agent_id: str) -> None:
        """Unblock a specific agent."""
        if agent_id in self._pending:
            self._pending[agent_id].set_result(None)
            del self._pending[agent_id]
```

### Pattern 4: Monitor Integration Interlock (D-01, D-02)
**What:** Extend MonitorLoop with "integration pending" state
**When to use:** When !integrate triggers, monitor tracks all agents reaching idle

```python
# In AgentMonitorState, add:
integration_pending: bool = False

# In MonitorLoop._run_cycle, after agent checks:
if self._integration_pending:
    all_idle = all(
        state.phase_status == "completed" and state.plan_gate_status == "idle"
        for state in self._agent_states.values()
    )
    if all_idle:
        # Fire integration callback
        if self._on_integration_ready:
            self._on_integration_ready()
```

### Pattern 5: Checkin Auto-Trigger
**What:** Monitor detects phase completion -> sends /vco:checkin to agent tmux pane
**When to use:** After each agent's phase completion is detected

```python
# In MonitorLoop._check_agent, when phase completion detected:
if phase_completed and not state.checkin_sent:
    self._tmux.send_command(pane, "/vco:checkin")
    state.checkin_sent = True
```

### Anti-Patterns to Avoid
- **Running full test suite N+1 times:** Only re-run the failing tests for attribution (D-06 explicitly says this)
- **Blocking event loop during git merge:** All git/subprocess calls MUST go through asyncio.to_thread
- **Standup timeout:** D-11 explicitly says NO timeout -- owner decides when to release
- **Direct git merge without integration branch:** Always create a separate branch (D-03) to keep main clean
- **Interrupting agents mid-work for integration:** D-02 says wait for natural idle point

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Git merge | Custom diff/patch | `git merge` subprocess | Git handles 3-way merge, rename detection, binary files |
| PR creation | GitHub API calls | `gh pr create` subprocess | Auth already configured, handles edge cases |
| Conflict detection | Parse diff output | `git merge` exit code + stderr | Git reports conflicts in stderr with file paths |
| Test execution | Custom test runner | `pytest` subprocess with `--tb=short` | Pytest handles collection, execution, reporting |
| Discord threads | Manual API calls | `discord.py channel.create_thread()` | Built-in thread support in discord.py 2.x |
| Button interactions | Polling for reactions | `discord.ui.View` with buttons | ConfirmView pattern already established |

## Common Pitfalls

### Pitfall 1: Git Merge in Wrong Working Directory
**What goes wrong:** Integration tries to merge in a clone directory instead of a dedicated integration working directory
**Why it happens:** Each agent clone has its own branch. You need a separate checkout to merge all branches.
**How to avoid:** Create integration in project_dir/integration/ (not in any agent clone). Clone fresh or use a dedicated integration clone.
**Warning signs:** Agent clones getting dirty, merge state leaking between agents.

### Pitfall 2: Pytest Subprocess Output Parsing
**What goes wrong:** Parsing pytest output for test names is fragile (different output formats)
**Why it happens:** pytest output varies by verbosity level and plugins
**How to avoid:** Use `pytest --tb=line -q` for parseable output. Or use `--json-report` if pytest-json-report is available. Alternatively, capture exit code (0/1) and parse the summary line.
**Warning signs:** Attribution tests working locally but failing with different pytest configs.

### Pitfall 3: Discord Thread Permission Gotcha
**What goes wrong:** Bot cannot create threads or post in threads due to missing permissions
**Why it happens:** Thread permissions are separate from channel permissions in Discord
**How to avoid:** Bot needs `create_public_threads`, `send_messages_in_threads`, and `manage_threads` permissions. These should already be granted by the bot's role setup but verify.
**Warning signs:** 403 Forbidden errors when creating threads.

### Pitfall 4: Standup Release Race Condition
**What goes wrong:** Owner clicks Release but agent is already being killed/relaunched by another command
**Why it happens:** Multiple commands can target the same agent concurrently
**How to avoid:** Check agent state before sending resume command. Use the existing AgentMonitorState to track standup blocking status.
**Warning signs:** Agent receives contradictory commands (resume + kill).

### Pitfall 5: Integration Branch Naming Collision
**What goes wrong:** Two integration attempts create branches with the same name
**Why it happens:** If using timestamps with second granularity and two requests come in the same second
**How to avoid:** Use `integrate/{timestamp}` with millisecond precision or include a counter. Or check if branch exists before creating.
**Warning signs:** Git checkout fails with "branch already exists".

### Pitfall 6: Merge Conflict Resolution Context Size
**What goes wrong:** Sending entire conflicting files to PMTier exceeds Claude's useful context
**Why it happens:** Large files with small conflicts still get sent in full
**How to avoid:** Extract only the conflict markers and surrounding context (10-20 lines). Use `git diff` to get the specific conflict hunks, not full file contents.
**Warning signs:** Slow conflict resolution, poor quality resolutions.

### Pitfall 7: Agent Not at Prompt When Receiving Commands
**What goes wrong:** Monitor sends /vco:checkin or standup commands to agent pane while agent is mid-execution
**Why it happens:** Phase completion detection may fire before agent has fully returned to prompt
**How to avoid:** D-02 already addresses this -- integration waits for agents to be idle (blocked by plan gate). For checkin, the command template approach means the agent executes it as a GSD command when it naturally reaches the prompt.
**Warning signs:** Commands appearing in tmux output but not being executed.

### Pitfall 8: N+1 Attribution with Many Agents
**What goes wrong:** Attribution takes too long with many agents (each requiring a separate merge + test run)
**Why it happens:** Linear cost with agent count
**How to avoid:** Only re-run the FAILING tests (not full suite) per D-06. This keeps individual attribution runs fast. For a typical 2-5 agent setup, this is manageable.
**Warning signs:** Integration pipeline taking >10 minutes.

## Code Examples

### Extending git/ops.py with Merge Operations

```python
# Add to src/vcompany/git/ops.py

def merge(branch: str, cwd: Path, no_ff: bool = False) -> GitResult:
    """Merge a branch into the current branch.

    Args:
        branch: Branch name to merge.
        cwd: Repository working directory.
        no_ff: If True, always create a merge commit.
    """
    args = ["merge", branch]
    if no_ff:
        args.append("--no-ff")
    return _run_git(*args, cwd=cwd, timeout=120)

def fetch(cwd: Path, remote: str = "origin") -> GitResult:
    """Fetch from remote."""
    return _run_git("fetch", remote, cwd=cwd, timeout=120)

def push(cwd: Path, remote: str = "origin", branch: str | None = None) -> GitResult:
    """Push to remote."""
    args = ["push", remote]
    if branch:
        args.append(branch)
    return _run_git(*args, cwd=cwd, timeout=120)

def diff(cwd: Path, args: list[str] | None = None) -> GitResult:
    """Get diff output."""
    extra = args or []
    return _run_git("diff", *extra, cwd=cwd)

def merge_abort(cwd: Path) -> GitResult:
    """Abort an in-progress merge."""
    return _run_git("merge", "--abort", cwd=cwd)

def checkout(branch: str, cwd: Path) -> GitResult:
    """Checkout an existing branch."""
    return _run_git("checkout", branch, cwd=cwd)
```

### Release Button View for Standup

```python
class ReleaseView(discord.ui.View):
    """Release button for standup threads. No timeout per D-11."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(timeout=None)  # No timeout -- owner decides
        self.agent_id = agent_id
        self.released = False
        self._callback: Callable[[str], None] | None = None

    def set_release_callback(self, callback: Callable[[str], None]) -> None:
        self._callback = callback

    @discord.ui.button(label="Release", style=discord.ButtonStyle.success, emoji=None)
    async def release(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.released = True
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"Agent **{self.agent_id}** released.", ephemeral=True)
        if self._callback:
            self._callback(self.agent_id)
        self.stop()
```

### Checkin Embed Builder

```python
def build_checkin_embed(
    agent_id: str,
    commit_count: int,
    summary: str,
    gaps: str,
    next_phase: str,
    dependency_status: str,
) -> discord.Embed:
    """Build checkin embed per COMM-01/COMM-02."""
    embed = discord.Embed(
        title=f"Checkin: {agent_id}",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Commits", value=str(commit_count), inline=True)
    embed.add_field(name="Summary", value=summary[:1024], inline=False)
    if gaps:
        embed.add_field(name="Gaps / Notes", value=gaps[:1024], inline=False)
    embed.add_field(name="Next Phase", value=next_phase, inline=True)
    embed.add_field(name="Dependencies", value=dependency_status[:1024], inline=False)
    return embed
```

### Integration Result Model

```python
from pydantic import BaseModel
from typing import Literal

class IntegrationResult(BaseModel):
    """Result of a full integration pipeline run."""
    status: Literal["success", "test_failure", "merge_conflict", "error"]
    branch_name: str
    merged_agents: list[str] = []
    test_results: dict[str, bool] = {}  # test_name -> passed
    attribution: dict[str, list[str]] = {}  # agent_id -> [failing_tests]
    pr_url: str | None = None
    conflict_files: list[str] = []
    error: str = ""
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| GitPython for merge ops | subprocess git calls | Project convention | Simpler, more reliable |
| discord.py Reactions for approval | discord.ui.View buttons | discord.py 2.0 (2022) | Better UX, interaction callbacks |
| Polling for thread replies | on_message listener with thread filtering | discord.py 2.0 | More efficient than polling |

## Open Questions

1. **Integration clone directory strategy**
   - What we know: Integration needs a working directory separate from agent clones
   - What's unclear: Use project_dir/integration/ as permanent dir, or create temp dirs per integration?
   - Recommendation: Use `project_dir/integration/` as a persistent directory. Reset it each integration run with git checkout + clean. Avoids repeated clones.

2. **How to detect phase completion in monitor**
   - What we know: Monitor reads clone ROADMAP.md and git log (MON-05). Plan gate status tracked.
   - What's unclear: Exact signal that a phase is "complete" vs "in progress"
   - Recommendation: Phase completion = all plans for current phase have been executed (plan_gate_status cycles through approved->idle for all plans). Or parse ROADMAP.md for phase status markers.

3. **Routing owner thread messages to agent tmux panes (COMM-05)**
   - What we know: TmuxManager.send_command can send to panes. Agents are blocked during standup.
   - What's unclear: What format to use for the prompt sent to the agent
   - Recommendation: Send as a /gsd:quick prompt: `"/gsd:quick Owner asks: {message}. Please respond with your answer."` Agent's response captured from tmux output or posted back via webhook.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| git | Integration pipeline | Yes | 2.43.0+ | -- |
| gh (GitHub CLI) | PR creation (INTG-06) | Yes | 2.88.1 | -- |
| Python 3.12 | Runtime | Yes | 3.12.3 | -- |
| pytest | Test execution (INTG-03) | Yes | 8.0+ (via uv) | -- |
| tmux | Agent session mgmt | Yes | 3.4+ | -- |

**Missing dependencies with no fallback:** None
**Missing dependencies with fallback:** None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 0.24+ |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INTG-01 | Branch-per-agent (already impl) | -- | -- | N/A (Phase 1) |
| INTG-02 | Create integration branch, merge all | unit | `uv run pytest tests/test_integration_pipeline.py::test_create_and_merge -x` | Wave 0 |
| INTG-03 | Run test suite after merge | unit | `uv run pytest tests/test_integration_pipeline.py::test_run_tests -x` | Wave 0 |
| INTG-04 | Test failure attribution | unit | `uv run pytest tests/test_attribution.py -x` | Wave 0 |
| INTG-05 | Auto-dispatch fix to responsible agent | unit | `uv run pytest tests/test_integration_pipeline.py::test_fix_dispatch -x` | Wave 0 |
| INTG-06 | Create PR on success | unit | `uv run pytest tests/test_integration_pipeline.py::test_pr_creation -x` | Wave 0 |
| INTG-07 | Conflict detection and reporting | unit | `uv run pytest tests/test_conflict_resolver.py::test_conflict_detection -x` | Wave 0 |
| INTG-08 | AI conflict resolution | unit | `uv run pytest tests/test_conflict_resolver.py::test_ai_resolution -x` | Wave 0 |
| COMM-01 | Checkin posts to #agent-{id} | unit | `uv run pytest tests/test_checkin.py::test_checkin_post -x` | Wave 0 |
| COMM-02 | Checkin includes required fields | unit | `uv run pytest tests/test_checkin.py::test_checkin_fields -x` | Wave 0 |
| COMM-03 | Standup creates threads per agent | unit | `uv run pytest tests/test_standup.py::test_standup_threads -x` | Wave 0 |
| COMM-04 | Standup listens for replies in threads | unit | `uv run pytest tests/test_standup.py::test_reply_listening -x` | Wave 0 |
| COMM-05 | Owner reprioritize/question via threads | unit | `uv run pytest tests/test_standup.py::test_owner_interaction -x` | Wave 0 |
| COMM-06 | Agent updates ROADMAP/STATE from feedback | unit | `uv run pytest tests/test_standup.py::test_agent_updates -x` | Wave 0 |
| SAFE-04 | Interaction regression tests | integration | `uv run pytest tests/test_interaction_regression.py -m integration -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_integration_pipeline.py` -- covers INTG-02, INTG-03, INTG-05, INTG-06
- [ ] `tests/test_attribution.py` -- covers INTG-04
- [ ] `tests/test_conflict_resolver.py` -- covers INTG-07, INTG-08
- [ ] `tests/test_checkin.py` -- covers COMM-01, COMM-02
- [ ] `tests/test_standup.py` -- covers COMM-03 through COMM-06
- [ ] `tests/test_interaction_regression.py` -- covers SAFE-04
- [ ] Add `pytest.mark.integration` marker to pyproject.toml: `markers = ["integration: interaction regression tests (run during vco integrate)"]`

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `src/vcompany/git/ops.py` -- existing git wrapper pattern (GitResult, _run_git, subprocess)
- Codebase analysis: `src/vcompany/bot/cogs/commands.py` -- placeholder !integrate and !standup commands
- Codebase analysis: `src/vcompany/bot/views/confirm.py` -- ConfirmView button pattern for reuse
- Codebase analysis: `src/vcompany/monitor/loop.py` -- MonitorLoop callback injection pattern
- Codebase analysis: `src/vcompany/orchestrator/agent_manager.py` -- dispatch/kill/relaunch lifecycle
- Codebase analysis: `src/vcompany/strategist/pm.py` -- PMTier for conflict resolution
- Codebase analysis: `src/vcompany/coordination/interactions.py` -- INTERACTIONS.md patterns for SAFE-04
- Codebase analysis: `src/vcompany/bot/embeds.py` -- Embed builder pattern
- Codebase analysis: `src/vcompany/models/monitor_state.py` -- AgentMonitorState with plan_gate tracking

### Secondary (MEDIUM confidence)
- discord.py 2.x Thread API -- `channel.create_thread()`, `Thread.send()`, on_message in threads (well-established API)
- Git merge behavior -- exit codes, stderr conflict reporting (standard git behavior)
- `gh pr create` -- `--title`, `--body`, `--base`, `--head` flags (standard GitHub CLI)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and used in prior phases
- Architecture: HIGH -- patterns extend established codebase conventions (callback injection, GitResult, ConfirmView)
- Pitfalls: HIGH -- identified from codebase analysis and git merge behavior (well-understood domain)

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable domain, all internal codebase patterns)
