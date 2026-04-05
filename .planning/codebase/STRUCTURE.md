# Structure

**Analysis Date:** 2026-04-05

## Root Layout

- `.claude/` — upstream GSD workflows, templates, references, and agent contracts.
- `.codex/` — Codex-side prompt, agent, and skill assets.
- `.planning/` — generated planning artifacts and, now, the codebase map.
- `commands/` — operator/workflow Markdown command references.
- `context/` — shared project context documents used by PM/strategist flows.
- `docker/` — Docker image definition and Claude settings.
- `packages/` — workspace subpackages; currently includes `vco-worker`.
- `src/` — main Python application package (`vcompany`).
- `tests/` — unit/integration/regression tests.
- `tools/` — supporting operational and research scripts.
- `VCO-ARCHITECTURE.md`, `CLAUDE.md`, `STRATEGIST-PERSONA.md` — primary design/reference docs.
- `agent-types.yaml` — agent template catalog.
- `pyproject.toml` — root package, dependencies, test config, and tooling.
- `uv.lock` — lockfile for the workspace.

## Main Application Package: `src/vcompany/`

**CLI**
- `src/vcompany/cli/` contains one file per command, usually named `*_cmd.py`.
- `src/vcompany/cli/main.py` registers all CLI entrypoints.

**Bot / Discord**
- `src/vcompany/bot/client.py` is the bot client.
- `src/vcompany/bot/cogs/` contains Discord cogs split by responsibility.
- `src/vcompany/bot/views/` holds interactive Discord views.
- `src/vcompany/bot/channel_setup.py`, `permissions.py`, `embeds.py`, and `comm_adapter.py` support the bot surface.

**Daemon / runtime**
- `src/vcompany/daemon/` contains the daemon, runtime API, protocol abstractions, and agent-handle layer.

**Supervisor**
- `src/vcompany/supervisor/` holds company/project supervision, scheduling, health, and restart logic.

**Transport**
- `src/vcompany/transport/` contains channel and runtime transport helpers.
- Channel message schema lives in `src/vcompany/transport/channel/`.

**Monitoring**
- `src/vcompany/monitor/` contains status, safety, and heartbeat logic.

**Strategy / PM**
- `src/vcompany/strategist/` contains confidence scoring, PM answering, context assembly, and review helpers.

**Coordination / communication**
- `src/vcompany/coordination/` and `src/vcompany/communication/` support standups, check-ins, and shared coordination logic.

**Shared / support**
- `src/vcompany/shared/` contains cross-cutting helpers such as file ops, memory store, templates, paths, and workflow types.
- `src/vcompany/git/`, `src/vcompany/docker/`, `src/vcompany/tmux/`, `src/vcompany/integration/`, `src/vcompany/autonomy/`, and `src/vcompany/resilience/` are focused subsystems with domain-specific helpers.

## Worker Package: `packages/vco-worker/`

- `packages/vco-worker/src/vco_worker/main.py` — worker entrypoint and protocol loop.
- `packages/vco-worker/src/vco_worker/config.py` — worker config model from head bootstrap.
- `packages/vco-worker/src/vco_worker/channel/` — worker-side message framing and socket handling.
- `packages/vco-worker/src/vco_worker/container/` — worker container lifecycle and state.
- `packages/vco-worker/src/vco_worker/handler/` — handler registry and execution modes.
- `packages/vco-worker/src/vco_worker/agent/` — agent lifecycle/state-machine code.
- `packages/vco-worker/src/vco_worker/conversation.py` — Claude conversation session handling.

## Tests

- Tests are flat under `tests/` and named `test_*.py`.
- The suite covers CLI commands, daemon behavior, bot config, routing, worker behavior, PM logic, monitoring, supervision, and protocol flows.
- Representative files:
  - `tests/test_cli_commands.py`
  - `tests/test_daemon.py`
  - `tests/test_pm_tier.py`
  - `tests/test_worker_main.py`
  - `tests/test_integration_pipeline.py`

## Tools and Operational Scripts

- `tools/ask_discord.py` — question/Discord bridge support.
- `tools/discord_send.py`, `tools/discord_clean.py` — Discord utilities.
- `tools/patch_gsd_workflows.py` — GSD workflow patching/maintenance.
- `tools/research_scripts/` — report/citation/research helpers.
- `tools/research_reference/` — methodology and quality-gate references.

## Templates and Generated Assets

- Main app templates live in `src/vcompany/templates/*.j2`.
- GSD templates live under `.claude/get-shit-done/templates/`.
- Planning artifacts generated during workflows live in `.planning/`.
- Context documents read by PM/strategist live in `context/`.

## Placement Guidance

- Add new CLI commands to `src/vcompany/cli/`.
- Add new Discord command/event logic to `src/vcompany/bot/cogs/`.
- Add new worker-protocol behavior to both `src/vcompany/transport/channel/` and `packages/vco-worker/src/vco_worker/channel/` where appropriate.
- Add new supervision/runtime behavior to `src/vcompany/daemon/` or `src/vcompany/supervisor/`, depending on whether the concern is interface/gateway logic or tree/lifecycle logic.
- Add new agent execution/runtime features to `packages/vco-worker/src/vco_worker/`.
