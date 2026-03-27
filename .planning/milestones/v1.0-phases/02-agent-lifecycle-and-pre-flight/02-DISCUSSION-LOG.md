# Phase 2: Agent Lifecycle and Pre-flight - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 02-agent-lifecycle-and-pre-flight
**Areas discussed:** Dispatch mechanics, Crash classification, Pre-flight scope, Circuit breaker behavior
**Mode:** Auto (all areas auto-selected, recommended defaults chosen)

---

## Dispatch Mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| claude CLI with flags | --dangerously-skip-permissions + --append-system-prompt per architecture doc | ✓ |
| Claude SDK subprocess | Use anthropic SDK directly instead of CLI | |

**User's choice:** [auto] claude CLI with flags (from architecture doc)
**Notes:** Architecture doc is explicit about using CLI with these flags.

---

## Crash Classification

| Option | Description | Selected |
|--------|-------------|----------|
| Exit code + filesystem | Classify by exit code AND .planning/ state integrity | ✓ |
| Log parsing only | Parse last N lines of output for known error patterns | |
| Simple retry count | Just count retries, don't classify | |

**User's choice:** [auto] Exit code + filesystem state (recommended)
**Notes:** Research pitfalls doc warns against blind retry without classification.

---

## Pre-flight Scope

| Option | Description | Selected |
|--------|-------------|----------|
| 4 tests from arch doc | stream-json, permissions, max-turns, resume | ✓ |
| Extended suite | Add API quota check, disk space, network connectivity | |
| Minimal | Just verify claude CLI is installed and responds | |

**User's choice:** [auto] 4 tests from architecture doc (recommended)
**Notes:** Matches VCO-ARCHITECTURE.md pre-flight section exactly.

---

## Circuit Breaker Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Alert + stop + manual | Alert #alerts, stop relaunch, require !relaunch to reset | ✓ |
| Alert + degrade | Alert but auto-reset after cooldown period | |
| Hard stop all | Kill all agents when any one trips circuit breaker | |

**User's choice:** [auto] Alert + stop + manual reset (recommended)
**Notes:** Prevents resource drain while keeping other agents running.

---

## Claude's Discretion

- Crash log format and rotation
- Pre-flight test timeout values
- tmux session naming convention
- --dry-run support for dispatch

## Deferred Ideas

None
