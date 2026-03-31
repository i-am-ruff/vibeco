# Phase 30: Worker Runtime - Research

**Researched:** 2026-03-31
**Domain:** Python package extraction, agent container runtime, transport channel communication
**Confidence:** HIGH

## Summary

Phase 30 extracts the agent container runtime from the daemon-side monolith into a standalone `vco-worker` Python package. The existing codebase already has well-separated components: `container/` (lifecycle FSM, memory store, health), `handler/` (session, conversation, transient protocols), `agent/` (GSD, continuous, fulltime, company, task subclasses), and `transport/channel/` (Phase 29 protocol messages). The worker package must compose these into a self-contained runtime that accepts a config blob over the channel, starts the right agent process, and communicates exclusively via channel messages.

The primary technical challenge is dependency isolation: the existing container/handler/agent code imports from `vcompany.*` and references daemon-side types (CommunicationPort, MessageContext, AgentTransport). The worker package must contain copies/adaptations of these modules that depend only on pydantic, python-statemachine, aiosqlite, and the channel protocol -- not discord.py, anthropic, libtmux, or daemon orchestration.

**Primary recommendation:** Use uv workspaces to create `packages/vco-worker/` as a workspace member alongside the existing `src/vcompany/` root package. Extract and adapt container, handler, agent, and memory_store code into the worker package. Replace CommunicationPort/MessageContext with channel protocol messages. Worker's main loop: read HeadMessages from stdin/transport, dispatch to container, emit WorkerMessages back.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked -- all implementation choices at Claude's discretion per CONTEXT.md.

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key constraints from project context:
- Containers run INSIDE transports, not as daemon-side Python objects
- Transport channel is the ONLY communication between head and worker
- vco-worker must be installable standalone -- no discord.py, no bot code, no orchestration dependencies
- Worker accepts a config blob at startup (handler type, capabilities, gsd_command, persona, env vars)
- Worker manages full agent lifecycle: start, health reporting, graceful stop
- Must contain handler logic (session/conversation/transient), lifecycle FSM, task queue, idle tracking, memory store, checkpoint/restore
- Use Pydantic v2 models (project standard)
- Phase 29's channel protocol (src/vcompany/transport/channel/) is the communication layer

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WORK-01 | vco-worker is a separate installable package with report/ask/send-file/signal commands that communicate through the transport channel | uv workspace member pattern; CLI entry points via pyproject.toml `[project.scripts]`; channel protocol messages (ReportMessage, AskMessage, SendFileMessage, SignalMessage) already defined in Phase 29 |
| WORK-02 | vco-worker accepts config blob at startup (handler type, capabilities, gsd_command, persona, env vars) and self-configures the right agent process | WorkerConfig Pydantic model; handler registry pattern from existing factory.py; StartMessage.config dict from channel protocol |
| WORK-03 | vco-worker manages agent lifecycle inside the execution environment (start, health reporting, graceful stop) | ContainerLifecycle/GsdLifecycle FSMs from python-statemachine; HealthReportMessage from channel protocol; StopMessage handling |
| WORK-04 | vco-worker communicates exclusively through the transport channel (no socket mounts, no shared filesystem, no direct Discord access) | All outbound communication via WorkerMessage types (encode/NDJSON); all inbound via HeadMessage types (decode_head); no CommunicationPort, no discord.py imports |
| WORK-05 | Worker contains full agent container runtime -- handler logic, lifecycle FSM, task queue, idle tracking, memory store, checkpoint/restore | Existing code in container/, handler/, agent/ modules provides the implementation; needs extraction and adaptation to remove daemon-side dependencies |
</phase_requirements>

## Standard Stack

### Core (Worker Package Dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.x | Config models, message validation | Already project standard; WorkerConfig, HealthReport models |
| python-statemachine | 3.0.0 | ContainerLifecycle, GsdLifecycle FSMs | Already used for all container FSMs; compound state support essential |
| aiosqlite | 0.22.1 | MemoryStore (per-agent SQLite persistence) | Already used for checkpoint/restore, KV store |
| PyYAML | 6.0.x | Agent type config parsing | Already project standard |

### NOT in Worker Package (isolation boundary)
| Library | Why Excluded | What Replaces It |
|---------|-------------|------------------|
| discord.py | Worker has no Discord access | Channel protocol messages (ReportMessage, AskMessage) |
| anthropic | Strategist conversation runs inside Claude Code, not worker Python | Worker just manages the process; conversation handler sends channel messages |
| libtmux | Worker manages tmux locally via subprocess, not libtmux | `subprocess.run(["tmux", ...])` or the agent process is already in the environment |
| docker | Worker runs INSIDE Docker, doesn't manage Docker | N/A -- head-side concern |

### Build/Development
| Tool | Version | Purpose |
|------|---------|---------|
| uv | 0.11.x | Workspace management, package building |
| hatchling | latest | Build backend (matches root package) |

**Installation (from workspace root):**
```bash
uv sync --package vco-worker
```

**Standalone installation:**
```bash
pip install vco-worker
```

## Architecture Patterns

### Recommended Project Structure
```
packages/
  vco-worker/
    pyproject.toml           # Standalone package definition
    src/
      vco_worker/
        __init__.py
        main.py              # Entry point: read channel, dispatch, respond
        config.py            # WorkerConfig Pydantic model (from StartMessage.config)
        container/
          __init__.py
          container.py        # WorkerContainer (adapted AgentContainer)
          state_machine.py    # ContainerLifecycle (copied, no changes needed)
          context.py          # ContainerContext (copied, no changes needed)
          health.py           # HealthReport (copied, no changes needed)
          memory_store.py     # MemoryStore (copied, no changes needed)
        handler/
          __init__.py
          protocol.py         # Handler protocols (adapted -- no AgentContainer import)
          session.py          # GsdSessionHandler (adapted)
          conversation.py     # ConversationHandler (adapted)
          transient.py        # TransientHandler (adapted)
          registry.py         # Handler name -> class mapping
        agent/
          __init__.py
          gsd_lifecycle.py    # GsdLifecycle FSM (copied)
          gsd_phases.py       # GsdPhase enum, CheckpointData (copied)
          event_driven_lifecycle.py  # EventDrivenLifecycle (copied)
        channel/
          __init__.py         # Re-export from shared protocol
          messages.py         # Shared channel protocol (or dependency)
          framing.py          # NDJSON encode/decode
        cli.py               # CLI entry points: vco-worker-report, vco-worker-ask, etc.
        process.py            # Agent process management (tmux session, claude -p, Python)
```

### Pattern 1: Channel Message Loop (Worker Main)
**What:** Worker's main loop reads HeadMessages from a transport stream, dispatches to the container, and writes WorkerMessages back.
**When to use:** Always -- this is the core worker pattern.
**Example:**
```python
# Source: Adapted from Phase 29 channel protocol
import asyncio
import sys
from vco_worker.channel.framing import decode_head, encode
from vco_worker.channel.messages import (
    HealthCheckMessage, GiveTaskMessage, InboundMessage,
    StartMessage, StopMessage, HealthReportMessage, SignalMessage,
)

async def run_worker(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Main worker loop: read head messages, dispatch, respond."""
    container = None
    async for line in reader:
        msg = decode_head(line)
        if isinstance(msg, StartMessage):
            container = await bootstrap_container(msg.agent_id, msg.config)
            writer.write(encode(SignalMessage(signal="ready")))
        elif isinstance(msg, GiveTaskMessage):
            await container.give_task(msg.description)
        elif isinstance(msg, InboundMessage):
            await container.handle_inbound(msg)
        elif isinstance(msg, HealthCheckMessage):
            report = container.health_report()
            writer.write(encode(HealthReportMessage(
                status=report.state,
                agent_state=report.inner_state or "",
                uptime_seconds=report.uptime,
            )))
        elif isinstance(msg, StopMessage):
            await container.stop()
            writer.write(encode(SignalMessage(signal="stopped")))
            break
        await writer.drain()
```

### Pattern 2: Config-Driven Bootstrap
**What:** Worker receives a config blob and self-configures handler type, lifecycle FSM, and agent process.
**When to use:** On StartMessage receipt -- worker is inert until configured.
**Example:**
```python
# Source: Adapted from existing factory.py registry pattern
from vco_worker.config import WorkerConfig
from vco_worker.container.container import WorkerContainer
from vco_worker.handler.registry import get_handler

async def bootstrap_container(agent_id: str, config_dict: dict) -> WorkerContainer:
    """Create and start a fully configured worker container from config blob."""
    config = WorkerConfig.model_validate(config_dict)
    container = WorkerContainer(
        agent_id=agent_id,
        handler_type=config.handler_type,
        capabilities=config.capabilities,
        gsd_command=config.gsd_command,
        persona=config.persona,
        env_vars=config.env_vars,
    )
    handler = get_handler(config.handler_type)
    container.set_handler(handler)
    await container.start()
    return container
```

### Pattern 3: Channel-Based Communication (Replacing CommunicationPort)
**What:** Worker uses channel messages instead of CommunicationPort for all outbound communication.
**When to use:** Everywhere the existing code calls `_send_discord()`.
**Example:**
```python
# Instead of:
#   await self.comm_port.send_message(payload)
# Worker does:
from vco_worker.channel.messages import ReportMessage
from vco_worker.channel.framing import encode

class WorkerContainer:
    async def send_report(self, channel: str, content: str):
        """Send a report via channel protocol (replaces _send_discord)."""
        msg = ReportMessage(channel=channel, content=content)
        self._writer.write(encode(msg))
        await self._writer.drain()
```

### Pattern 4: CLI Commands as Channel Message Senders
**What:** `vco-worker-report`, `vco-worker-ask`, `vco-worker-signal` are thin CLI wrappers that write a single WorkerMessage to stdout/transport.
**When to use:** Called by agent processes (Claude Code hooks, GSD scripts) to communicate with head.
**Example:**
```python
# cli.py entry point for 'vco-worker-report'
import click
import json
import sys
from vco_worker.channel.messages import ReportMessage
from vco_worker.channel.framing import encode

@click.command()
@click.argument("channel")
@click.argument("content")
def report(channel: str, content: str):
    """Send a report message through the transport channel."""
    msg = ReportMessage(channel=channel, content=content)
    sys.stdout.buffer.write(encode(msg))
    sys.stdout.buffer.flush()
```

### Anti-Patterns to Avoid
- **Importing from vcompany.***: Worker package must NOT import from the main vcompany package at runtime. The channel protocol messages can be duplicated or extracted to a shared micro-package.
- **Direct Discord access**: No httpx webhook calls, no discord.py imports. All communication through channel messages.
- **Daemon-side state assumptions**: Worker must not assume CompanyRoot, Supervisor, or ChildSpecRegistry exist. It bootstraps from the config blob alone.
- **Shared filesystem state**: Worker's MemoryStore is local to its execution environment. Head cannot read worker's SQLite files directly.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Lifecycle FSM | Custom state tracking with booleans/strings | python-statemachine 3.0 (ContainerLifecycle, GsdLifecycle) | Already battle-tested in codebase; compound states, history states, transition validation |
| Persistent KV + checkpoints | File-based JSON persistence | aiosqlite MemoryStore (existing implementation) | WAL mode, atomic writes, checkpoint history, already proven |
| Message serialization | Custom JSON parsing | Pydantic v2 discriminated unions + NDJSON framing | Type-safe, validated, human-readable; already defined in Phase 29 |
| Config validation | Manual dict parsing | Pydantic BaseModel (WorkerConfig) | Fail-fast on invalid config, auto-documentation, IDE support |

**Key insight:** Almost all the runtime logic already exists in the codebase. The work is extraction and adaptation, not greenfield development. The container/handler/agent modules are well-factored with clear boundaries.

## Common Pitfalls

### Pitfall 1: Circular Import with Main Package
**What goes wrong:** Worker package tries to import from `vcompany.transport.channel` at runtime, creating a hard dependency on the main package.
**Why it happens:** The channel protocol lives in `src/vcompany/transport/channel/`. Worker needs these exact types.
**How to avoid:** Either (a) duplicate the channel protocol into the worker package (simple, ~150 lines), or (b) extract it to a shared `vco-protocol` micro-package that both depend on. Option (a) is recommended for v4 -- the protocol is small and stable.
**Warning signs:** `ImportError: No module named 'vcompany'` when running worker standalone.

### Pitfall 2: Handler State Leaking to Daemon Types
**What goes wrong:** Existing handlers reference `AgentContainer` from `vcompany.container.container`, `MessageContext` from `vcompany.models.messages`, and other daemon types.
**Why it happens:** Handlers were written for daemon-side use and use TYPE_CHECKING imports from the main package.
**How to avoid:** Worker's container class (`WorkerContainer`) must satisfy the same interface handlers expect. Create a worker-local `MessageContext` equivalent or adapt InboundMessage from the channel protocol to serve as the context object.
**Warning signs:** Handlers failing to import their type stubs at runtime.

### Pitfall 3: asyncio Event Loop Not Running for CLI Commands
**What goes wrong:** CLI commands (`vco-worker-report`, `vco-worker-ask`) are invoked by shell scripts/hooks that are synchronous.
**Why it happens:** Channel protocol encode is sync, but if CLI tries to use async channel transport, it fails.
**How to avoid:** CLI commands should be purely synchronous -- encode a message, write to stdout/pipe, exit. No asyncio needed for one-shot CLI commands. Only the main worker loop is async.
**Warning signs:** `RuntimeError: no current event loop` from CLI commands.

### Pitfall 4: MemoryStore Path Not Isolated
**What goes wrong:** Worker creates SQLite files outside its execution environment, or multiple workers share the same DB path.
**Why it happens:** MemoryStore takes a `data_dir` path that was previously managed by the daemon.
**How to avoid:** Worker config blob should include a `data_dir` path or default to a well-known location inside the execution environment (e.g., `/tmp/vco-worker/{agent_id}/`). Each worker gets its own directory.
**Warning signs:** `sqlite3.OperationalError: database is locked` from concurrent workers.

### Pitfall 5: python-statemachine Model Binding
**What goes wrong:** FSM's `model=self` and `state_field="_fsm_state"` pattern breaks if WorkerContainer doesn't have the expected attribute.
**Why it happens:** python-statemachine 3.0 writes state to the model object via the `state_field` parameter.
**How to avoid:** WorkerContainer must have `_fsm_state: str | None = None` attribute and `_on_state_change` method, same as current AgentContainer.
**Warning signs:** `AttributeError: 'WorkerContainer' object has no attribute '_fsm_state'`.

### Pitfall 6: Conversation Handler Needs StrategistConversation
**What goes wrong:** StrategistConversationHandler delegates to `container._conversation` which is a `StrategistConversation` object that depends on `anthropic` SDK.
**Why it happens:** CompanyAgent initializes StrategistConversation with transport for subprocess calls to `claude -p`.
**How to avoid:** In the worker, the conversation handler should use subprocess directly (same as current StrategistConversation but without the anthropic SDK import). The `claude -p` call is just a subprocess -- the anthropic SDK is not needed for piped mode. Alternatively, the conversation handler in the worker can be simplified to just relay messages via channel protocol and let the agent process (Claude Code) handle the conversation.
**Warning signs:** `ModuleNotFoundError: No module named 'anthropic'`.

## Code Examples

### WorkerConfig Pydantic Model
```python
# Source: Adapted from existing ContainerContext + agent-types.yaml schema
from pydantic import BaseModel, Field

class WorkerConfig(BaseModel):
    """Config blob sent by head in StartMessage.config."""
    handler_type: str  # "session", "conversation", "transient"
    capabilities: list[str] = Field(default_factory=list)
    gsd_command: str | None = None
    persona: str | None = None
    env_vars: dict[str, str] = Field(default_factory=dict)
    agent_type: str = "gsd"  # For lifecycle FSM selection
    data_dir: str = "/tmp/vco-worker/data"
    project_id: str | None = None
    project_dir: str | None = None
    project_session_name: str | None = None
```

### pyproject.toml for vco-worker
```toml
# Source: uv workspace pattern from official docs
[project]
name = "vco-worker"
version = "0.1.0"
description = "vCompany worker runtime -- runs inside agent execution environments"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.11,<3",
    "python-statemachine>=3.0.0",
    "aiosqlite>=0.22.1",
    "pyyaml>=6.0",
    "click>=8.1.6",
]

[project.scripts]
vco-worker = "vco_worker.main:main"
vco-worker-report = "vco_worker.cli:report"
vco-worker-ask = "vco_worker.cli:ask"
vco-worker-signal = "vco_worker.cli:signal"
vco-worker-send-file = "vco_worker.cli:send_file"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/vco_worker"]
```

### Root pyproject.toml Workspace Addition
```toml
# Add to existing /home/developer/vcompany/pyproject.toml
[tool.uv.workspace]
members = ["packages/*"]
```

### Handler Registry (Worker-Side)
```python
# Source: Adapted from existing factory.py _HANDLER_REGISTRY
from vco_worker.handler.session import GsdSessionHandler
from vco_worker.handler.conversation import WorkerConversationHandler
from vco_worker.handler.transient import PMTransientHandler

_HANDLER_REGISTRY: dict[str, type] = {
    "session": GsdSessionHandler,
    "conversation": WorkerConversationHandler,
    "transient": PMTransientHandler,
}

def get_handler(handler_type: str):
    """Get handler instance by type name."""
    cls = _HANDLER_REGISTRY.get(handler_type)
    if cls is None:
        raise ValueError(f"Unknown handler type: {handler_type}")
    return cls()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Daemon-side AgentContainer objects | Worker-side self-managed containers | v4.0 (this phase) | Containers are fully autonomous; daemon only holds metadata + transport handle |
| CommunicationPort for Discord | Channel protocol messages | v4.0 (Phase 29-30) | Worker has zero Discord dependency |
| Factory + registry on daemon | Config blob + local bootstrap | v4.0 (this phase) | Worker can run anywhere that has Python + the config blob |
| pip install vcompany (monolith) | pip install vco-worker (isolated) | v4.0 (this phase) | Light dependency footprint; no discord.py/anthropic/libtmux |

## Open Questions

1. **Channel protocol sharing strategy**
   - What we know: The channel protocol (messages.py, framing.py) is ~150 lines and defined in `src/vcompany/transport/channel/`.
   - What's unclear: Whether to duplicate into worker package or extract to shared `vco-protocol` package.
   - Recommendation: Duplicate for now. The protocol is small, stable (defined in Phase 29), and extracting a third package adds complexity. If it drifts, Phase 34 cleanup can extract it.

2. **CLI command transport mechanism**
   - What we know: CLI commands (vco-worker-report, etc.) need to send messages through the channel.
   - What's unclear: Whether CLI commands write to stdout (piped to worker main loop) or to a local socket/file that the worker reads.
   - Recommendation: Use environment variable `VCO_WORKER_PIPE` pointing to a named pipe or Unix socket. CLI commands connect, write one message, disconnect. Worker main loop reads from this alongside the transport channel. Simpler alternative: CLI writes to a well-known file path that the worker watches.

3. **StrategistConversation in worker context**
   - What we know: CompanyAgent uses StrategistConversation which calls `claude -p --resume` via subprocess.
   - What's unclear: Whether the worker conversation handler should replicate this subprocess pattern or simplify to channel-based relay.
   - Recommendation: For v4, the conversation handler in the worker simply runs `claude -p` via subprocess (same as now, minus the anthropic SDK dependency). The subprocess call only needs `asyncio.create_subprocess_exec` (stdlib). No anthropic import needed.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Worker runtime | Yes | 3.12.3 | -- |
| uv | Package management, workspace | Yes | 0.11.1 | pip (but loses workspace support) |
| tmux | Session handler agent process | Yes | 3.4 | -- |
| Node.js | Claude Code (GSD runtime) | Yes | 22.x | -- |
| aiosqlite | MemoryStore | Yes | 0.22.1 | -- |
| python-statemachine | Lifecycle FSMs | Yes | 3.0.0 | -- |
| pydantic | Config/message models | Yes | 2.12.5 | -- |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `src/vcompany/container/`, `src/vcompany/handler/`, `src/vcompany/agent/`, `src/vcompany/transport/channel/` -- direct code inspection
- [uv workspace docs](https://docs.astral.sh/uv/concepts/projects/workspaces/) -- workspace member configuration, `--package` flag
- python-statemachine 3.0.0 -- installed and verified, compound state support confirmed

### Secondary (MEDIUM confidence)
- [uv monorepo patterns](https://pydevtools.com/handbook/how-to/how-to-set-up-a-python-monorepo-with-uv-workspaces/) -- workspace setup patterns verified against official docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all dependencies already in use and installed; versions verified against pip/uv
- Architecture: HIGH -- extraction from existing well-factored code; patterns directly observable in codebase
- Pitfalls: HIGH -- based on direct code inspection of import chains and dependency graphs

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable -- all components are mature/pinned)
