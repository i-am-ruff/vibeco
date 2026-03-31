---
status: awaiting_human_verify
trigger: "agent-readiness-timeout: None of the dispatched agents for test-v10 did anything — they are all stuck on empty Claude Code CLI prompts because the container readiness check timed out for every agent."
created: 2026-03-28T00:00:00Z
updated: 2026-03-28T00:00:00Z
---

## Current Focus

hypothesis: The readiness check looks for ASCII ">" but Claude Code v2.1.81 uses the Unicode character "❯" (U+276F HEAVY RIGHT-POINTING ANGLE QUOTATION MARK) as its prompt.
test: Captured actual tmux pane output and compared bytes against the pattern in _wait_for_claude_ready().
expecting: Fix is to update the pattern in _wait_for_claude_ready() to match "❯" (and possibly "❯ " with trailing space).
next_action: Apply fix to container.py

## Symptoms

expected: After vco dispatches agents, Claude Code should start in tmux panes, become "ready" (detected by the container), and then receive the GSD command to begin work.
actual: Claude Code starts but the readiness detection times out after ~63 seconds for each agent (backend, frontend, data-seeder). The warning "Claude Code did not become ready within timeout for {agent} -- GSD command not sent" fires, and agents sit on empty Claude Code prompts with no input.
errors:
  - WARNING vcompany.container.container: Claude Code did not become ready within timeout for backend -- GSD command not sent
  - WARNING vcompany.container.container: Claude Code did not become ready within timeout for frontend -- GSD command not sent
  - WARNING vcompany.container.container: Claude Code did not become ready within timeout for data-seeder -- GSD command not sent
reproduction: Dispatch agents via vco for any project (test-v10 in this case). All 3 agents fail identically.
started: Now. Likely started when Claude Code was updated to v2.1.81 which uses "❯" prompt instead of ">".

## Eliminated

- hypothesis: tmux pane output not being captured at all
  evidence: get_output() returns lines successfully — pane shows the full Claude Code startup UI
  timestamp: 2026-03-28

- hypothesis: timing issue (Claude Code starts too slow)
  evidence: The pane already shows the "❯" prompt and status bar; Claude Code IS ready, the detection just fails to recognize it
  timestamp: 2026-03-28

## Evidence

- timestamp: 2026-03-28
  checked: src/vcompany/container/container.py _wait_for_claude_ready()
  found: Pattern check is `stripped == ">" or stripped.endswith(" >")`
  implication: Only matches plain ASCII greater-than as the last non-empty line

- timestamp: 2026-03-28
  checked: tmux capture-pane for vco-test-v10:backend (Claude Code v2.1.81)
  found: Last non-empty prompt line is "❯" (U+276F) — NOT ">"
  implication: Pattern never matches; timeout always fires

- timestamp: 2026-03-28
  checked: All lines of backend pane output
  found: Line sequence: logo, version, path, separator, "❯", separator, status bar
  implication: The prompt IS present and Claude IS ready — the check just uses the wrong character

## Resolution

root_cause: _wait_for_claude_ready() checks for ASCII ">" but Claude Code v2.1.81 uses Unicode "❯" (U+276F HEAVY RIGHT-POINTING ANGLE QUOTATION MARK) as its idle prompt. The pattern never matches so every agent times out.
fix: Updated _wait_for_claude_ready() in container.py to match both "❯" (U+276F) and ">" as ready prompt indicators. Added _READY_PROMPTS tuple ("❯", ">") and updated the condition to check stripped in _READY_PROMPTS or any(stripped.endswith(f" {p}") for p in _READY_PROMPTS).
verification: Code change applied. 793 tests pass (2 pre-existing unrelated failures confirmed unchanged). Awaiting human verification that agents now receive GSD commands after dispatch.
files_changed: [src/vcompany/container/container.py]
