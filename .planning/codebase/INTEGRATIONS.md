# External Integrations

**Analysis Date:** 2026-04-05

## Claude Code / LLM Integration

**Claude CLI subprocess path**
- `src/vcompany/strategist/pm.py` calls `claude -p` with `--output-format json` for PM-tier answers.
- `packages/vco-worker/src/vco_worker/handler/conversation.py` is documented as a subprocess-based Claude conversation path rather than an Anthropic SDK path.
- `docker/Dockerfile` installs `@anthropic-ai/claude-code` globally so worker containers can invoke Claude tooling directly.

**Prompt and workflow assets**
- Codex-side prompts live in `.codex/prompts/`.
- Upstream GSD workflow assets live in `.claude/get-shit-done/workflows/`.
- GSD role contracts live in `.claude/agents/gsd-*.md`.
- Codex role config layers live in `.codex/agents/gsd-*.toml`.

## Discord Integration

**Bot client**
- Core client: `src/vcompany/bot/client.py`
- Config: `src/vcompany/bot/config.py`
- Communication port adapter: `src/vcompany/bot/comm_adapter.py`

**Discord responsibilities**
- Slash commands and message routing live in `src/vcompany/bot/cogs/`.
- Channel/category setup is handled in `src/vcompany/bot/channel_setup.py`.
- Permission gating lives in `src/vcompany/bot/permissions.py`.
- Embed/view helpers live in `src/vcompany/bot/embeds.py` and `src/vcompany/bot/views/`.

**Environment-backed settings**
- `BotConfig` loads `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, `PROJECT_DIR`, optional `ANTHROPIC_API_KEY`, `STRATEGIST_PERSONA_PATH`, and `STATUS_DIGEST_INTERVAL`.
- The config model points at `.env` via `pydantic-settings`, but the repo should treat that file as secret-bearing local state.

## Daemon and Socket Integration

**Unix socket signaling**
- `src/vcompany/cli/signal_cmd.py` sends readiness/idle events over a Unix socket using `httpx.HTTPTransport(uds=...)`.
- The command targets the signal socket derived from `vcompany.shared.paths.VCO_SOCKET_PATH`.

**Runtime API boundary**
- `src/vcompany/daemon/runtime_api.py` is the typed gateway used by bot cogs and CLI surfaces.
- The daemon owns runtime/business logic; Discord cogs are intended to stay as thin I/O adapters.

**Communication protocol**
- `src/vcompany/daemon/comm.py` defines `CommunicationPort` and its payload models.
- Adapters can implement Discord or noop backends without importing Discord into the daemon layer.

## Worker / Head Protocol Integration

**Worker bootstrap**
- `packages/vco-worker/src/vco_worker/main.py` reads NDJSON head messages from stdin or a socket transport.
- It handles `StartMessage`, `GiveTaskMessage`, `InboundMessage`, `HealthCheckMessage`, `ReconnectMessage`, and `StopMessage`.

**Worker configuration blob**
- `packages/vco-worker/src/vco_worker/config.py` validates the config sent by the head process.
- Config includes handler type, agent type, capabilities, GSD command, persona, env vars, project metadata, and tmux usage.

**Socket server mode**
- Worker socket mode is implemented in `packages/vco-worker/src/vco_worker/channel/socket_server.py`.
- `VCO_WORKER_SOCKET` is set so child processes can post worker messages to the outbox socket.

## Docker Integration

**Image build**
- `docker/Dockerfile` packages the runtime used for worker containers.
- The image contains Python, Node, Claude Code, `vcompany`, `vco-worker`, and default Claude settings.

**Claude settings baked into image**
- `docker/settings.json` is copied to `/root/.claude/settings.json`.
- That file is the repo-controlled place for hook behavior and default permissions in the agent image.

## tmux Integration

- Session abstraction: `src/vcompany/tmux/session.py`
- tmux-backed agents are implied by agent capabilities in `agent-types.yaml`.
- Worker config includes `uses_tmux` and session metadata to coordinate pane/session-backed execution.

## Git Integration

- Git operations are centralized in `src/vcompany/git/ops.py`.
- Monitoring code uses git history for recent activity in status generation.
- CLI/project lifecycle flows reference `agents.yaml`, clone directories, and worktrees managed under project structure conventions.

## Project Context Integration

- Strategist/PM context files are read from `context/` via `src/vcompany/strategist/context_builder.py`.
- Important context files include `PROJECT-BLUEPRINT.md`, `INTERFACES.md`, `MILESTONE-SCOPE.md`, and `PROJECT-STATUS.md`.
- Agent prompts in `src/vcompany/templates/*.j2` treat `PROJECT-STATUS.md` as read-only orchestrator-generated state.

## Supporting Scripts and Utilities

- `tools/ask_discord.py` routes question flow to Discord-related infrastructure.
- `tools/discord_send.py` and `tools/discord_clean.py` support operational message and cleanup flows.
- `tools/patch_gsd_workflows.py` exists specifically to maintain GSD workflow integration.
- Research support scripts live under `tools/research_scripts/`.

## Practical Integration Guidance

- Any change to socket or channel payloads must be reflected on both daemon/head and worker sides.
- Discord-facing logic should route through `RuntimeAPI` or `CommunicationPort` rather than importing daemon internals into cogs.
- Claude/LLM subprocess assumptions affect both the root package and the worker image; update Docker/runtime and PM/worker callsites together.
