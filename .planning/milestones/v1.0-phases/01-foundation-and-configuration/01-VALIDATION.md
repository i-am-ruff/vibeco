---
phase: 1
slug: foundation-and-configuration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (latest, installed via uv) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` section (Wave 0) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | FOUND-07 | smoke | `uv run python -c "import vcompany"` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | FOUND-01 | unit | `uv run pytest tests/test_config.py -x` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | FOUND-04 | unit | `uv run pytest tests/test_git_ops.py -x` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | FOUND-05 | unit | `uv run pytest tests/test_tmux.py -x` | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 1 | FOUND-06 | unit | `uv run pytest tests/test_file_ops.py -x` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | FOUND-02 | integration | `uv run pytest tests/test_init_cmd.py -x` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | FOUND-03 | integration | `uv run pytest tests/test_clone_cmd.py -x` | ❌ W0 | ⬜ pending |
| 01-03-03 | 03 | 2 | COORD-04 | unit | `uv run pytest tests/test_config.py::test_agent_prompt_generation -x` | ❌ W0 | ⬜ pending |
| 01-03-04 | 03 | 2 | COORD-05 | unit | `uv run pytest tests/test_clone_cmd.py::test_claude_md_content -x` | ❌ W0 | ⬜ pending |
| 01-03-05 | 03 | 2 | COORD-06 | integration | `uv run pytest tests/test_clone_cmd.py::test_command_files_deployed -x` | ❌ W0 | ⬜ pending |
| 01-03-06 | 03 | 2 | COORD-07 | integration | `uv run pytest tests/test_clone_cmd.py::test_settings_json_deployed -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` with `[tool.pytest.ini_options]` section
- [ ] `tests/conftest.py` — shared fixtures (tmp directories, sample agents.yaml, mock git repos)
- [ ] `tests/test_config.py` — FOUND-01 validation tests
- [ ] `tests/test_git_ops.py` — FOUND-04 wrapper tests
- [ ] `tests/test_tmux.py` — FOUND-05 wrapper tests
- [ ] `tests/test_file_ops.py` — FOUND-06 atomic write tests
- [ ] `tests/test_init_cmd.py` — FOUND-02 integration tests
- [ ] `tests/test_clone_cmd.py` — FOUND-03, COORD-05, COORD-06, COORD-07 tests
- [ ] Framework install: `uv add --dev pytest`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| tmux pane visually shows running session | FOUND-05 | Requires visual tmux inspection | Start tmux session via wrapper, verify pane exists with `tmux list-panes` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
