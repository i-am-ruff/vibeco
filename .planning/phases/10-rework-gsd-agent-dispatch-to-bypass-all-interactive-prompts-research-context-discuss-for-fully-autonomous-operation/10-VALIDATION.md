---
phase: 10
slug: rework-gsd-agent-dispatch-to-bypass-all-interactive-prompts-research-context-discuss-for-fully-autonomous-operation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q --tb=short` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --tb=short`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| *To be filled by planner* | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WorkflowOrchestrator drives agent through full discuss→plan→execute cycle | D-02 | Requires live Discord + running agents | Dispatch agent, verify orchestrator sends correct GSD commands and gates transitions |
| Discussion flows through Discord hook naturally | D-09, D-10 | Requires live PM/Strategist answering questions | Run discuss-phase, verify AskUserQuestion goes through Discord, PM answers |
| GSD patches eliminate interactive prompts | D-13 | Requires running patched GSD in agent clone | Run plan-phase without --auto, verify no prompts block |
| Unknown prompt blocks agent and alerts | D-15 | Requires triggering unexpected prompt scenario | Simulate unknown prompt, verify agent blocks and Discord alert fires |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
