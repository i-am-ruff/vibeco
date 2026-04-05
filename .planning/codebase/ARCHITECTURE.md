# Architecture

**Analysis Date:** 2026-04-05

## Top-Level Shape

The repo implements an orchestrated multi-agent development system with a Python control plane, a Discord operator surface, a daemon/runtime gateway, a worker runtime, and a GSD/Codex workflow layer.

The clearest architecture references are:
- `VCO-ARCHITECTURE.md`
- `src/vcompany/daemon/runtime_api.py`
- `src/vcompany/supervisor/company_root.py`
- `packages/vco-worker/src/vco_worker/main.py`

## Layer 1: Operator and Bot Surface

**Discord bot as I/O adapter**
- `src/vcompany/bot/client.py` loads cogs, creates/initializes Discord channels, and registers a `DiscordCommunicationPort` with the daemon.
- `src/vcompany/bot/cogs/commands.py` holds operator slash commands and routes business actions through `RuntimeAPI`.
- `src/vcompany/bot/cogs/workflow_orchestrator_cog.py` listens for agent stage signals and advances gate reviews.
- `src/vcompany/bot/cogs/question_handler.py`, `workflow_master.py`, `task_relay.py`, `strategist.py`, and `health.py` split Discord concerns by channel/task type.

**Architectural rule**
- Bot cogs are intended to be thin adapters.
- Runtime/business logic is supposed to stay in daemon/runtime/supervisor layers, not in Discord handlers.

## Layer 2: CLI and Runtime Gateway

**CLI boundary**
- `src/vcompany/cli/main.py` registers the public CLI commands.
- Individual command modules under `src/vcompany/cli/` wrap daemon/socket/runtime operations rather than embedding orchestration state directly.

**Gateway pattern**
- `src/vcompany/daemon/runtime_api.py` is the typed gateway into company/project operations.
- This file is the main bridge between user-facing surfaces and orchestration internals.
- Bot cogs and daemon socket handlers both rely on it.

## Layer 3: Daemon and Company Supervision

**Daemon**
- `src/vcompany/daemon/daemon.py` owns bot lifecycle, socket server lifecycle, signal handling, runtime API registration, and startup/shutdown ordering.
- `src/vcompany/daemon/comm.py` defines platform-agnostic outbound communication payloads and protocol expectations.
- `src/vcompany/daemon/agent_handle.py` is part of the bridge from runtime API calls into running agents.

**Supervision model**
- `src/vcompany/supervisor/company_root.py` is the central company/project tree owner.
- Supporting supervision modules (`supervisor.py`, `scheduler.py`, `strategies.py`, `project_supervisor.py`, `health.py`, `restart_tracker.py`) suggest a tree of company-level and project-level supervision with health tracking and restart logic.

**Architectural pattern**
- Runtime surfaces talk to `RuntimeAPI`.
- `RuntimeAPI` delegates to `CompanyRoot` and related supervision primitives.
- The daemon also mediates communication-port access and socket-facing endpoints.

## Layer 4: Worker and Channel Protocol

**Head/worker split**
- The orchestrator controls workers over a structured message protocol.
- Root-side message models live in `src/vcompany/transport/channel/messages.py`.
- Worker-side message models live in `packages/vco-worker/src/vco_worker/channel/messages.py`.

**Worker lifecycle**
- `packages/vco-worker/src/vco_worker/main.py` bootstraps a `WorkerContainer` from a validated config blob.
- Handlers are selected from `packages/vco-worker/src/vco_worker/handler/registry.py`.
- Container state and lifecycle live under `packages/vco-worker/src/vco_worker/container/`.

**Protocol shape**
- Start/config bootstrap
- Task delivery
- Inbound message relay
- Health reporting
- Reconnect handling
- Stop/shutdown

This is a clean boundary: the head process does not need direct access to the worker’s internal state machine, only its messages and health reports.

## Layer 5: Strategy, PM, and Context

**PM tier**
- `src/vcompany/strategist/pm.py` performs confidence-scored PM answering.
- It loads context files fresh for each question, scores confidence, then either answers via `claude -p` or escalates.

**Supporting strategy modules**
- `src/vcompany/strategist/confidence.py`
- `src/vcompany/strategist/context_builder.py`
- `src/vcompany/strategist/plan_reviewer.py`
- `src/vcompany/strategist/decision_log.py`
- `src/vcompany/strategist/persona.py`

**Architectural role**
- This layer does not own transport or Discord mechanics.
- It owns decision framing, context assembly, and answer/review policy.

## Layer 6: Monitoring, Health, and Coordination

**Monitoring**
- `src/vcompany/monitor/status_generator.py` assembles `PROJECT-STATUS.md` from roadmap and git activity.
- `src/vcompany/monitor/checks.py`, `heartbeat.py`, `safety_validator.py`, and `status_generator.py` show a monitoring subsystem concerned with liveness, safety, and progress reporting.

**Coordination**
- `src/vcompany/coordination/` and `src/vcompany/communication/` contain interaction, standup, and check-in support.
- `src/vcompany/shared/workflow_types.py` is used by the workflow orchestrator cog for stage signal handling.

## Architectural Data Flow

**Typical command path**
1. User issues a CLI command or Discord slash command.
2. Command/cog routes to `RuntimeAPI`.
3. `RuntimeAPI` delegates into daemon/company supervision.
4. The head process talks to workers through the transport/channel protocol.
5. Workers run handlers and emit signals/health/events back.
6. Discord/system channels receive updates through the communication port.

**Typical workflow path**
1. Agent reports a stage completion signal in its channel.
2. `WorkflowOrchestratorCog` detects the signal.
3. The cog verifies the agent/container via `RuntimeAPI`.
4. The cog runs the next gate review or stage transition.
5. PM and project context are consulted when needed.

## Important Architectural Seams

- `RuntimeAPI` is the main seam between external interfaces and orchestration logic.
- `CommunicationPort` is the seam between daemon logic and platform-specific messaging.
- Root/channel message models are the seam between the head process and worker runtime.
- `agent-types.yaml` is the seam between static configuration and runtime agent construction.

## Where To Extend Architecture Safely

- Add CLI behavior under `src/vcompany/cli/` and route it through `RuntimeAPI`.
- Add Discord behavior under `src/vcompany/bot/cogs/` without bypassing `RuntimeAPI`.
- Add protocol features by updating both root and worker message layers.
- Add worker execution behavior under `packages/vco-worker/src/vco_worker/`.
- Add planning/PM policy under `src/vcompany/strategist/` rather than inside cogs or transport code.
