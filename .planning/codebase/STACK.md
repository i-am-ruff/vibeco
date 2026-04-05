# Technology Stack

**Analysis Date:** 2026-04-05

## Languages

**Primary**
- Python 3.12 drives the main application and the worker runtime. The root package lives in `src/vcompany`, and the worker package lives in `packages/vco-worker/src/vco_worker`.

**Secondary**
- JavaScript/Node.js is part of the agent runtime environment rather than the product code. `docker/Dockerfile` starts from `node:22-slim` and installs Claude Code globally.
- Markdown and Jinja templates are first-class repo assets. Operational prompts and design docs live in `VCO-ARCHITECTURE.md`, `CLAUDE.md`, `commands/vco/*.md`, `.claude/get-shit-done/`, and `src/vcompany/templates/*.j2`.

## Runtime Environments

**Main application**
- The root package is `vcompany` from `pyproject.toml`.
- CLI entry point: `vco = "vcompany.cli.main:cli"`.
- Core runtime code lives under `src/vcompany`.

**Worker runtime**
- Separate package: `packages/vco-worker/pyproject.toml`.
- Entrypoints: `vco-worker`, `vco-worker-report`, `vco-worker-ask`, `vco-worker-signal`, `vco-worker-send-file`.
- Channel protocol and worker lifecycle live in `packages/vco-worker/src/vco_worker`.

**Container/runtime image**
- `docker/Dockerfile` builds the universal agent image.
- The image installs Python 3.12, `uv`, Claude Code, the root `vcompany` package, and the `vco-worker` package.
- Default container command: `python -m vco_worker`.

## Packaging and Dependency Management

**Package manager**
- `uv` is the primary package/dependency tool for local and container installs.
- Lockfile: `uv.lock`.
- Workspace members are declared in `pyproject.toml` under `[tool.uv.workspace]` and currently include `packages/*`.

**Build backend**
- Both root and worker packages use `hatchling`.

**Python package layout**
- Root wheel package: `src/vcompany`.
- Worker wheel package: `packages/vco-worker/src/vco_worker`.

## Root Runtime Dependencies

**CLI / application shell**
- `click` for command definitions in `src/vcompany/cli`.
- `rich` for formatted terminal output.

**Configuration / models**
- `pydantic` and `pydantic-settings` for typed config and protocol/state models.
- `pyyaml` for `agents.yaml` and agent-type config parsing.

**Orchestration / runtime**
- `docker` for container lifecycle support.
- `libtmux` for tmux-backed agent sessions in `src/vcompany/tmux/session.py`.
- `python-statemachine` for lifecycle/state handling.
- `aiosqlite` for async persistence and memory/state storage.

**Bot / external interface**
- `discord-py` for the Discord bot surface in `src/vcompany/bot`.
- `anthropic` is declared as a dependency, but PM/strategist answering in `src/vcompany/strategist/pm.py` is implemented via the `claude` CLI subprocess path rather than the Anthropic SDK.

## Worker Runtime Dependencies

- `pydantic`
- `python-statemachine`
- `aiosqlite`
- `pyyaml`
- `click`

The worker package intentionally carries a smaller dependency surface than the root package.

## Development Tooling

- `pytest` and `pytest-asyncio` drive the test suite in `tests/`.
- `ruff` defines formatting/lint expectations in `pyproject.toml`.
- Pytest path configuration and marker configuration live in `pyproject.toml`.

## Major Framework and Subsystem Choices

**Discord runtime**
- Bot client: `src/vcompany/bot/client.py`
- Communication adapter: `src/vcompany/bot/comm_adapter.py`
- Slash command and event cogs: `src/vcompany/bot/cogs/*.py`

**Daemon / orchestration**
- Runtime gateway: `src/vcompany/daemon/runtime_api.py`
- Daemon lifecycle: `src/vcompany/daemon/daemon.py`
- Platform-agnostic communication protocol: `src/vcompany/daemon/comm.py`

**Supervisor / company model**
- Company root: `src/vcompany/supervisor/company_root.py`
- Supervisor loop and scheduling: `src/vcompany/supervisor/*.py`

**Transport / channel messaging**
- Root transport messages: `src/vcompany/transport/channel/messages.py`
- Worker-side channel messages: `packages/vco-worker/src/vco_worker/channel/messages.py`
- Worker bootstrap and dispatch: `packages/vco-worker/src/vco_worker/main.py`

**Strategist / PM**
- PM tier: `src/vcompany/strategist/pm.py`
- Confidence scoring: `src/vcompany/strategist/confidence.py`
- Context assembly: `src/vcompany/strategist/context_builder.py`

**Monitoring**
- Project status generation: `src/vcompany/monitor/status_generator.py`
- Health/safety checks: `src/vcompany/monitor/checks.py`, `src/vcompany/monitor/safety_validator.py`

## Configuration Surfaces

- Root package and toolchain: `pyproject.toml`
- Worker package metadata: `packages/vco-worker/pyproject.toml`
- Agent type catalog: `agent-types.yaml`
- Dockerized Claude Code settings: `docker/settings.json`
- Local Python version hint: `.python-version`
- Codex/GSD bridge: `.codex/` and `.claude/get-shit-done/`
- Environment-backed bot configuration: `src/vcompany/bot/config.py`

## Practical Notes For Future Work

- New CLI behavior belongs under `src/vcompany/cli/*_cmd.py`.
- New bot commands/events belong under `src/vcompany/bot/cogs/`.
- Worker protocol changes must be reflected in both `src/vcompany/transport/channel/messages.py` and `packages/vco-worker/src/vco_worker/channel/messages.py`.
- When adding runtime dependencies used by CLI or daemon code, update `pyproject.toml` explicitly instead of relying on transitive installs.
