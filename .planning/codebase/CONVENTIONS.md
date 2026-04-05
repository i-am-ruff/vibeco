# Coding Conventions

**Analysis Date:** 2026-04-05

## Module and File Naming

- CLI command modules use the `*_cmd.py` suffix under `src/vcompany/cli/`.
- Tests use `tests/test_*.py`.
- Packages are responsibility-oriented: `daemon`, `bot`, `monitor`, `strategist`, `supervisor`, `transport`, `shared`, `autonomy`, `resilience`.

## Docstrings and Module Headers

- Modules generally start with a descriptive top-level docstring explaining role and constraints.
- Many files document the architectural rule they enforce, for example:
  - `src/vcompany/bot/client.py`
  - `src/vcompany/bot/cogs/commands.py`
  - `src/vcompany/daemon/runtime_api.py`
  - `packages/vco-worker/src/vco_worker/main.py`

**Use this style**
- Start new modules with a short purpose docstring.
- Document cross-layer restrictions directly in the file when a module must stay pure (for example, “no discord.py imports allowed here”).

## Typing Style

- The codebase uses Python type hints heavily on public functions, async methods, return values, and internal state.
- Pydantic models are preferred for structured payloads and config:
  - `src/vcompany/models/config.py`
  - `src/vcompany/daemon/comm.py`
  - `packages/vco-worker/src/vco_worker/config.py`

**Use this style**
- Type new interfaces and payloads explicitly.
- Prefer small typed models to loosely structured dictionaries at transport boundaries.

## Async Boundaries

- Async I/O is common in bot, daemon, worker, and PM layers.
- `asyncio` is the standard coordination mechanism.
- Long-lived services expose async methods rather than hiding event-loop work behind sync wrappers.

**Use this style**
- Keep async boundaries explicit.
- If code crosses process/socket/container boundaries, prefer clear async message handling rather than implicit shared state.

## Layering Rules

- Discord cogs are intended to be thin I/O adapters that call `RuntimeAPI`.
- Daemon/runtime logic belongs in `src/vcompany/daemon/` and `src/vcompany/supervisor/`.
- PM and strategy rules belong in `src/vcompany/strategist/`.
- Worker/container runtime behavior belongs in `packages/vco-worker/src/vco_worker/`.

**Use this style**
- Do not put business/supervision logic directly into Discord cogs.
- Do not import Discord types into daemon/core layers that are meant to be platform-agnostic.

## Logging and Error Handling

- Named loggers are standard: `logging.getLogger("vcompany....")` or `logging.getLogger("vco_worker")`.
- Many modules log and degrade gracefully rather than crashing the outer workflow.
- Examples:
  - `src/vcompany/bot/client.py` logs channel/setup failures and continues.
  - `src/vcompany/cli/signal_cmd.py` fails silently if the daemon is down so Claude hooks do not block.
  - `src/vcompany/monitor/status_generator.py` returns “status unknown” on parse/read failures.

**Use this style**
- Log operational failures with enough context to debug.
- Preserve the outer agent or bot workflow when failure should be non-fatal.

## Configuration Conventions

- Environment-backed config uses `BaseSettings` via `pydantic-settings`.
- `BotConfig` is the clearest example in `src/vcompany/bot/config.py`.
- Tooling/runtime configuration is centralized in `pyproject.toml`, `agent-types.yaml`, `docker/settings.json`, and GSD/Codex directories.

**Use this style**
- Add new config as typed fields on config models instead of ad hoc `os.environ` lookups spread across files.
- Keep environment loading logic near the boundary that owns the config.

## CLI Command Conventions

- Commands are declared with Click decorators and registered centrally in `src/vcompany/cli/main.py`.
- Command files typically do one of three things:
  - validate input
  - call daemon/runtime helpers
  - render user-facing output

**Use this style**
- Add new commands as isolated modules under `src/vcompany/cli/`.
- Keep command functions thin; delegate core behavior to runtime/core modules.

## Template and Context Conventions

- Prompt/template files live in `src/vcompany/templates/` and `.claude/get-shit-done/templates/`.
- Context files like `PROJECT-STATUS.md` are treated as read-only generated artifacts in prompt templates.

**Use this style**
- Keep generated/read-only files clearly marked in prompts and templates.
- Put reusable prompt fragments or output templates in template directories, not inline in code.
