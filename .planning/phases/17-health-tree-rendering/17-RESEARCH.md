# Phase 17: Health Tree Rendering - Research

**Researched:** 2026-03-28
**Domain:** Discord embed rendering, supervision tree traversal, agent health data
**Confidence:** HIGH

## Summary

Phase 17 is a pure rendering phase. The supervision tree data model (`CompanyHealthTree`, `HealthTree`, `HealthNode`, `HealthReport`) is already complete and correct. The `HealthReport` already carries `inner_state`, `uptime`, and `last_activity` fields. The gap is entirely in the `build_health_tree_embed` function in `src/vcompany/bot/embeds.py` and the tests in `tests/test_health_cog.py`.

**Current state vs required state:**

HLTH-05 gap: The embed does not render CompanyRoot as an explicit root node. The title is "Health Tree" but there is no line showing `company-root` at the top with its lifecycle state. The hierarchy is implicitly present via sections but not visually explicit.

HLTH-06 gap: `uptime` and `last_activity` are present in `HealthReport` but `build_health_tree_embed` does not render them. Each agent line currently shows only `{emoji} **{id}**: {state} ({inner_state})`. The architecture requires adding uptime (formatted as human-readable duration) and last_activity (formatted as time-ago or timestamp).

The fix is surgical: update `build_health_tree_embed` to (1) add a CompanyRoot header line as the embed description, and (2) add uptime and last_activity to each agent line. Tests for both behaviors need to be added to `tests/test_health_cog.py`.

**Primary recommendation:** Modify `build_health_tree_embed` only — no changes to container, health model, supervisor, or cog code needed.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None — discuss phase skipped per user setting.

### Claude's Discretion
All implementation choices are at Claude's discretion. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HLTH-05 | Health tree shows CompanyRoot at top with its state, Strategist/CompanyAgents as children, then ProjectSupervisors with their agents | `CompanyHealthTree.supervisor_id` and `.state` are already populated; embed description can show CompanyRoot header; existing field structure covers company_agents and projects |
| HLTH-06 | Health tree shows inner_state, uptime, and last_activity per agent matching the architecture doc's example format | `HealthReport.uptime` (float seconds) and `HealthReport.last_activity` (datetime) are already present; embed rendering just needs to include them in each agent line |
</phase_requirements>

---

## Standard Stack

This phase uses no new libraries. All needed tools are already in the project.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.7.x | Embed construction (`discord.Embed`) | Already installed; embeds have 4096-char description, 1024-char field values, 25-field limit |
| pydantic | 2.11.x | `HealthReport`, `CompanyHealthTree` models | Already installed; models are already defined and correct |
| Python stdlib `datetime` | 3.12 | Format `last_activity` timestamps | `datetime.now(timezone.utc) - report.last_activity` gives timedelta |

**Installation:** None needed.

---

## Architecture Patterns

### Files in scope for this phase

```
src/vcompany/bot/embeds.py          # Primary change: build_health_tree_embed
tests/test_health_cog.py            # New tests for HLTH-05 and HLTH-06
```

All other files (container/health.py, supervisor/company_root.py, bot/cogs/health.py) are correct and require no changes.

### Current embed structure (before Phase 17)

```
Embed title: "Health Tree"
  Field: "Company Agents"          (if company_agents present)
    {emoji} **strategist**: running (listening)
  Field: "Project: project-{id}"
    {emoji} **agent-1**: running (PLAN)
    {emoji} **agent-2**: running (idle)
```

### Required embed structure (after Phase 17)

HLTH-05: CompanyRoot must appear as the explicit root of the tree.
HLTH-06: Each agent line must show inner_state, uptime, and last_activity.

```
Embed title: "Health Tree"
Embed description: "{emoji} company-root: running"   ← HLTH-05 new root header

  Field: "Company Agents"          (company-root direct children)
    {emoji} **strategist**: running (listening) | up 2h 3m | active 30s ago

  Field: "Project: project-{id}"
    {emoji} **agent-1**: running (PLAN) | up 45m | active 2m ago
    {emoji} **agent-2**: running (idle) | up 45m | active 10m ago
```

### Pattern 1: CompanyRoot header as embed description (HLTH-05)

Use `embed.description` for the CompanyRoot root-node line (not a field). This reserves the 25 field slots for company_agents and projects, and visually anchors the top of the hierarchy.

```python
# Source: src/vcompany/bot/embeds.py — build_health_tree_embed
root_emoji = STATE_INDICATORS.get(tree.state, _DEFAULT_INDICATOR)
embed.description = f"{root_emoji} **{tree.supervisor_id}**: {tree.state}"
```

### Pattern 2: Uptime and last_activity formatting (HLTH-06)

`HealthReport.uptime` is a `float` (seconds since creation). Format as human-readable: `up {H}h {M}m` or `up {M}m` for shorter durations.

`HealthReport.last_activity` is a `datetime` with timezone. Format as `active {N}s ago` / `active {N}m ago` using `datetime.now(timezone.utc) - report.last_activity`.

```python
# Source: pattern from existing embeds.py — stays within 1024-char field value limit
def _fmt_uptime(seconds: float) -> str:
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    if h > 0:
        return f"up {h}h {m}m"
    elif m > 0:
        return f"up {m}m"
    return f"up {s}s"

def _fmt_last_activity(last: datetime) -> str:
    diff = (datetime.now(timezone.utc) - last).total_seconds()
    if diff < 60:
        return f"active {int(diff)}s ago"
    elif diff < 3600:
        return f"active {int(diff // 60)}m ago"
    return f"active {int(diff // 3600)}h ago"
```

Agent line then becomes:
```python
uptime_str = _fmt_uptime(r.uptime)
activity_str = _fmt_last_activity(r.last_activity)
inner = f" ({r.inner_state})" if r.inner_state else ""
blocked = f" -- {r.blocked_reason}" if r.blocked_reason else ""
lines.append(f"{emoji} **{r.agent_id}**: {r.state}{inner} | {uptime_str} | {activity_str}{blocked}")
```

### Pattern 3: Discord field character budget

The 1024-char field limit is already guarded. Adding uptime + last_activity per line adds ~25 chars per agent. For typical projects (2-5 agents), this is well within budget. The existing `if len(value) > 1024: value = value[:1021] + "..."` guard already handles overflow.

### Anti-Patterns to Avoid

- **Modifying HealthReport model:** Not needed — uptime and last_activity are already present.
- **Changing supervisor.health_tree() or CompanyRoot.health_tree():** Not needed — data is already correct.
- **Adding a new "CompanyRoot" embed field:** Use embed.description instead to avoid burning a field slot on the root node.
- **Importing `time` module:** Use `datetime.now(timezone.utc)` (already in embeds.py imports) not `time.time()` for last_activity comparison.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Duration formatting | Custom complex formatter | Simple integer division (`//`) on `.total_seconds()` | All precision needed: hours, minutes, seconds |
| Datetime comparison | Complex timezone handling | `datetime.now(timezone.utc) - report.last_activity` | Both datetimes are UTC-aware; subtraction works directly |

---

## Common Pitfalls

### Pitfall 1: last_activity is timezone-aware
**What goes wrong:** `datetime.now()` (without tz) - `report.last_activity` (UTC-aware) raises `TypeError: can't subtract offset-naive and offset-aware datetimes`.
**Why it happens:** `AgentContainer._created_at` and `_last_activity` are set with `datetime.now(timezone.utc)` — they are UTC-aware.
**How to avoid:** Always use `datetime.now(timezone.utc)` not `datetime.now()` in `_fmt_last_activity`.
**Warning signs:** `TypeError` in tests that compare timestamps.

### Pitfall 2: uptime can be 0.0 for freshly-started agents
**What goes wrong:** Rendering shows "up 0s" which looks odd.
**Why it happens:** `health_report()` computes `(now - self._created_at).total_seconds()` which can be < 1s.
**How to avoid:** Show "up 0s" — this is correct and acceptable. Do not special-case.

### Pitfall 3: embed.description gets overwritten
**What goes wrong:** Setting `embed.description = "No projects active"` elsewhere overwrites the CompanyRoot line.
**Why it happens:** `build_health_tree_embed` currently sets `embed.description = "No projects active"` in two places when filters return no results.
**How to avoid:** When showing the CompanyRoot line, keep it as part of the description even when no projects exist, e.g., `{root_line}\nNo projects active`.

### Pitfall 4: Test helper `_make_report` doesn't set uptime/last_activity consistently
**What goes wrong:** Tests for HLTH-06 fail with `AssertionError` because `_make_report` sets `uptime=100.0` but tests check exact format strings.
**Why it happens:** The helper uses a fixed `uptime=100.0` (1m 40s = "up 1m") and `last_activity=now` ("active 0s ago").
**How to avoid:** Test for format pattern (e.g., assert `"up " in field_value` and `"active " in field_value`) rather than exact strings, OR pass specific uptime values to `_make_report` in the tests.

---

## Code Examples

### Full updated build_health_tree_embed function signature

```python
# Source: src/vcompany/bot/embeds.py (current, to be modified)
def build_health_tree_embed(
    tree: CompanyHealthTree,
    *,
    project_filter: str | None = None,
    agent_filter: str | None = None,
) -> discord.Embed:
```

The function signature stays the same. Only the body changes.

### Imports needed (already present in embeds.py)

```python
from datetime import datetime, timezone
# datetime and timezone are already imported in embeds.py
```

### Test pattern for HLTH-05 (CompanyRoot header)

```python
def test_embed_description_shows_company_root():
    """Embed description shows company-root state as tree root (HLTH-05)."""
    tree = _make_tree(state="running")
    embed = build_health_tree_embed(tree)
    assert embed.description is not None
    assert "company-root" in embed.description
    assert STATE_INDICATORS["running"] in embed.description
```

### Test pattern for HLTH-06 (uptime and last_activity)

```python
def test_agent_line_shows_uptime_and_last_activity():
    """Agent lines include uptime and last_activity (HLTH-06)."""
    projects = [
        _make_project(agents=[("a1", "running", "PLAN")]),
    ]
    tree = _make_tree(projects=projects)
    embed = build_health_tree_embed(tree)
    field_value = embed.fields[0].value  # or fields[1] if company root field is fields[0]
    assert "up " in field_value
    assert "active " in field_value
    assert "ago" in field_value
```

---

## Runtime State Inventory

This is a rendering-only phase. No stored data, live service config, OS state, secrets, or build artifacts are involved. No runtime state inventory needed.

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies — pure Python/discord.py code change).

---

## Validation Architecture

`workflow.nyquist_validation` is `false` in `.planning/config.json` — validation section skipped.

---

## Open Questions

1. **Where exactly should the `_fmt_uptime` and `_fmt_last_activity` helpers live?**
   - What we know: They are only used by `build_health_tree_embed` in `embeds.py`.
   - What's unclear: Should they be module-level private functions or inline lambdas?
   - Recommendation: Module-level private functions (prefixed with `_`) in `embeds.py`. Consistent with `_ALERT_COLORS` and `_INTEGRATION_COLORS` pattern already in the file.

2. **Should the CompanyRoot line also show uptime/last_activity?**
   - What we know: `CompanyHealthTree` only has `supervisor_id` and `state` — no `uptime` or `last_activity`. CompanyRoot is a `Supervisor`, not an `AgentContainer`, so it has no `health_report()`.
   - What's unclear: HLTH-06 says "per agent" — CompanyRoot is a supervisor not an agent.
   - Recommendation: Show only state for CompanyRoot header line (consistent with current `HealthTree.state` pattern). Only agent nodes show uptime/last_activity.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `src/vcompany/bot/embeds.py` — current build_health_tree_embed implementation
- Direct codebase inspection: `src/vcompany/container/health.py` — HealthReport, CompanyHealthTree models
- Direct codebase inspection: `src/vcompany/supervisor/company_root.py` — health_tree() returns CompanyHealthTree
- Direct codebase inspection: `tests/test_health_cog.py` — existing test patterns (41 tests pass)
- Direct codebase inspection: `src/vcompany/container/container.py` — health_report() method, uptime/last_activity computation

### Secondary (MEDIUM confidence)
- discord.py embed limits: 4096 chars for description, 1024 for field values, 25 fields max — well-known and already respected in existing code

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and in use
- Architecture: HIGH — codebase read directly; changes are surgical (one function in one file)
- Pitfalls: HIGH — discovered from direct code reading and known Python datetime behavior

**Research date:** 2026-03-28
**Valid until:** 2026-04-27 (stable — no external library churn involved)
