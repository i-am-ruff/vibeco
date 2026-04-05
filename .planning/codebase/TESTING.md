# Testing Patterns

**Analysis Date:** 2026-04-05

## Test Framework and Configuration

- Primary framework: `pytest`
- Async support: `pytest-asyncio`
- Lint/style tool: `ruff`

Pytest configuration lives in `pyproject.toml`:
- `testpaths = ["tests"]`
- `pythonpath = ["src", "packages/vco-worker/src"]`
- `asyncio_mode = "auto"`
- marker: `integration`

## Test File Organization

- Tests are flat under `tests/`.
- File names follow `test_*.py`.
- Coverage is organized by subsystem rather than mirrored directories. Examples:
  - CLI: `tests/test_cli_commands.py`
  - daemon/runtime: `tests/test_daemon.py`, `tests/test_daemon_protocol.py`
  - PM/strategist: `tests/test_pm_tier.py`, `tests/test_pm_integration.py`
  - worker/container: `tests/test_worker_main.py`, `tests/test_worker_container.py`
  - monitor/supervision: `tests/test_monitor_checks.py`, `tests/test_supervision_tree.py`

## Common Testing Styles

**CLI tests**
- Use `click.testing.CliRunner`.
- Patch daemon helpers or runtime entrypoints.
- Assert exit code, output, and exact downstream call parameters.
- Example: `tests/test_cli_commands.py`.

**Async service tests**
- Use `pytest.mark.asyncio` for coroutine tests.
- Use `AsyncMock` for subprocesses, bot lifecycle methods, or async collaborators.
- Example: `tests/test_pm_tier.py`, `tests/test_daemon.py`.

**Environment/config tests**
- Use `monkeypatch` to set or remove env vars.
- Avoid relying on a real `.env` during tests.
- Example: `tests/test_bot_config.py`.

**Protocol/runtime tests**
- Use fake streams, patched subprocesses, or mock clients to simulate channels and workers.
- Focus on message flow and lifecycle transitions rather than end-to-end external systems.

## Representative Patterns

**Subprocess mocking**
- `tests/test_pm_tier.py` mocks `asyncio.create_subprocess_exec` to test PM behavior without a real Claude call.

**Daemon lifecycle testing**
- `tests/test_daemon.py` uses a `MockBot` and tmp-path PID/socket files to test startup, shutdown, signal handling, and cleanup order.

**RPC/daemon-client patching**
- CLI tests patch `daemon_client` or helper constructors so commands can be verified without a running daemon.

**Validation testing**
- Config/model tests use `pytest.raises(...)` around invalid env/config input and then assert exact fallback/default behavior.

## What Future Tests Should Match

- Keep tests narrow and behavior-focused.
- Assert exact public behavior at the module boundary being tested.
- Prefer patching interfaces at the seam the code already uses rather than rewriting architecture for tests.
- For CLI commands, verify both human-visible output and the exact daemon/runtime call payload.
- For async services, assert state transitions and emitted messages/signals, not just “no exception”.

## Practical Commands

- Full suite: `python -m pytest`
- Run a subset: `python -m pytest -k <pattern>`
- Run integration-only flows when appropriate: `python -m pytest -m integration`
- Lint/style check: `ruff check .`

## Current Testing Gaps To Watch

- The repo has broad subsystem coverage, but large orchestration modules still concentrate a lot of behavior in a few files. When changing `src/vcompany/daemon/runtime_api.py`, `src/vcompany/daemon/daemon.py`, `src/vcompany/bot/cogs/workflow_orchestrator_cog.py`, or `src/vcompany/supervisor/company_root.py`, extend tests near the touched seam rather than relying on existing broad coverage alone.
