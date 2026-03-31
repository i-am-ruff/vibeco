# Phase 31: Head Refactor - Research

**Researched:** 2026-03-31
**Domain:** Daemon-side architecture refactor -- replace container objects with transport handles + metadata
**Confidence:** HIGH

## Summary

Phase 31 transforms the daemon (head) from directly instantiating and managing Python container objects (GsdAgent, CompanyAgent, FulltimeAgent, etc.) into a thin orchestration layer that holds only transport handles and agent metadata. The worker (Phase 30) already contains a full container runtime -- this phase makes the head use it by sending config blobs through the transport channel instead of creating containers locally.

The core change is replacing `AgentContainer` instances in `CompanyRoot._company_agents` and `Supervisor._children` with a lightweight `AgentHandle` (Pydantic model) that stores only: id, type, capabilities, channel_id, handler type, config, and a transport reference. The hire flow changes from "create container + launch in tmux" to "create Discord channel + register routing + send StartMessage through transport." Health reporting changes from calling `container.health_report()` on daemon-side objects to receiving `HealthReportMessage` through the channel protocol.

**Primary recommendation:** Introduce an `AgentHandle` Pydantic model as the daemon-side representation of an agent, refactor RuntimeAPI/CompanyRoot/Supervisor to operate on handles instead of containers, and wire health reporting through the existing channel protocol messages defined in Phase 29.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all implementation choices are at Claude's discretion (infrastructure phase).

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key constraints from project context:
- Containers run INSIDE transports, not as daemon-side Python objects
- Daemon only talks to transport -- container is self-managed behind the abstraction boundary
- Transport channel is the ONLY communication between head and worker
- Agent metadata stored daemon-side: id, type, capabilities, channel_id, handler type, config
- Health tree receives HealthReportMessages through transport channel
- Discord channel/category lifecycle (create on hire, cleanup on dismiss) stays in head
- Use Pydantic v2 models (project standard)
- Phase 29 channel protocol and Phase 30 worker runtime are the building blocks

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HEAD-01 | Daemon holds transport handle + agent metadata per agent (id, type, capabilities, channel_id, handler type, config) -- enough to route messages, report health, and identify agents without knowing internals | AgentHandle model replaces AgentContainer in CompanyRoot._company_agents and Supervisor._children |
| HEAD-02 | Hire flow creates Discord channel, registers routing, sends config blob through transport -- worker bootstraps from config | RuntimeAPI.hire() refactored to build WorkerConfig, send StartMessage through transport channel instead of calling create_container + container.start() |
| HEAD-03 | Health tree populated from worker health reports received through transport, not daemon-side container objects | CompanyRoot.health_tree() reads cached HealthReportMessage data from AgentHandle instead of calling container.health_report() |
| HEAD-05 | Discord channel/category lifecycle managed by head -- create on hire, cleanup on dismiss, routing persists across daemon restarts | Channel creation already in RuntimeAPI.hire() via CommunicationPort; add cleanup on dismiss; add persistence for routing state |
</phase_requirements>

## Architecture Patterns

### Current Architecture (What Exists)

```
Daemon
  CompanyRoot
    _company_agents: dict[str, AgentContainer]  # Full Python objects
    _projects: dict[str, ProjectSupervisor]
      _children: dict[str, AgentContainer]      # Full Python objects
  RuntimeAPI
    hire() -> creates AgentContainer via factory
    give_task() -> calls container.give_task()
    health_tree() -> calls container.health_report()
    dismiss() -> calls container.stop()
```

Key coupling points in the current code:
1. `RuntimeAPI.hire()` calls `self._root.hire()` which calls `create_container()` from factory
2. `RuntimeAPI.give_task()` calls `container.give_task()` directly on a Python object
3. `RuntimeAPI.health_tree()` calls `self._root.health_tree()` which calls `agent.health_report()` on each container
4. `RuntimeAPI.dispatch()`, `kill()`, `relaunch()` call `container.start()/stop()/restart()` directly
5. `MentionRouterCog.register_agent()` stores an `AgentContainer` reference and calls `container.receive_discord_message()`
6. `CompanyRoot.health_tree()` iterates `self._company_agents.values()` calling `.health_report()` on each

### Target Architecture (Phase 31)

```
Daemon
  CompanyRoot
    _company_agents: dict[str, AgentHandle]  # Lightweight metadata + transport ref
    _projects: dict[str, ProjectSupervisor]
      _children: dict[str, AgentHandle]      # Lightweight metadata + transport ref
  RuntimeAPI
    hire() -> creates AgentHandle, sends StartMessage through transport
    give_task() -> sends GiveTaskMessage through transport
    health_tree() -> reads cached HealthReportMessages from handles
    dismiss() -> sends StopMessage through transport, cleans up Discord channel
```

### Pattern 1: AgentHandle -- Daemon-Side Agent Representation

**What:** A Pydantic model that stores everything the head needs to know about an agent without instantiating the agent's Python container.

**When to use:** Every place the daemon currently holds an `AgentContainer` reference.

```python
from pydantic import BaseModel, Field

class AgentHandle(BaseModel):
    """Daemon-side lightweight agent representation.

    Holds enough metadata to route messages, report health,
    and identify agents -- without any container runtime.
    """
    agent_id: str
    agent_type: str
    capabilities: list[str] = Field(default_factory=list)
    channel_id: str | None = None  # Discord channel for this agent
    handler_type: str = "session"  # session/conversation/transient
    config: dict = Field(default_factory=dict)  # Full WorkerConfig as dict

    # Transport reference (not serialized -- runtime only)
    # This is the AgentTransport instance that connects to the worker
    _transport: Any = None  # Set at runtime, not part of model

    # Cached health from last HealthReportMessage
    _last_health: HealthReportMessage | None = None
    _last_health_time: datetime | None = None
```

### Pattern 2: Message-Based Lifecycle Management

**What:** All lifecycle operations (start, give_task, stop, health_check) happen by sending typed messages through the transport channel instead of calling Python methods.

**When to use:** Any RuntimeAPI method that currently accesses container objects.

```python
# Current: container.give_task(task)
# New: send GiveTaskMessage through transport
from vcompany.transport.channel.messages import GiveTaskMessage

async def give_task(self, agent_id: str, task: str) -> None:
    handle = await self._root._find_handle(agent_id)
    if handle is None:
        raise KeyError(f"Agent {agent_id!r} not found")
    msg = GiveTaskMessage(task_id=task_id, description=task)
    await handle.send(msg)  # Sends through transport channel
```

### Pattern 3: Transport Channel Reader Loop

**What:** A background asyncio task per agent that reads WorkerMessages from the transport channel and dispatches them (health reports, signals, ask requests, file sends, reports).

**When to use:** Needed for each active agent to process worker-to-head messages.

```python
async def _channel_reader(self, handle: AgentHandle) -> None:
    """Read worker messages from transport channel, dispatch to handlers."""
    async for msg in handle.transport.read_messages():
        if isinstance(msg, HealthReportMessage):
            handle.update_health(msg)
        elif isinstance(msg, SignalMessage):
            await self._handle_signal(handle, msg)
        elif isinstance(msg, ReportMessage):
            await self._route_report(handle, msg)
        elif isinstance(msg, AskMessage):
            await self._handle_ask(handle, msg)
        elif isinstance(msg, SendFileMessage):
            await self._handle_send_file(handle, msg)
```

### Pattern 4: Routing State Persistence

**What:** Channel-to-agent routing must survive daemon restarts. When the daemon comes back up, it needs to know which Discord channels belong to which agents.

**When to use:** HEAD-05 requires routing persistence.

```python
# Persist routing state as YAML/JSON file alongside other state
# Location: state/supervision/routing.json
{
    "agents": {
        "agent-1": {
            "channel_id": "123456789",
            "category_id": "987654321",
            "agent_type": "gsd",
            "handler_type": "session"
        }
    }
}
```

### Pattern 5: MentionRouter Adaptation

**What:** `MentionRouterCog` currently stores `AgentContainer` references and calls `container.receive_discord_message()`. It needs to work with `AgentHandle` instead, forwarding messages through the transport channel.

**When to use:** All message routing from Discord to agents.

```python
# Current: container.receive_discord_message(context)
# New: handle sends InboundMessage through transport
async def _deliver_to_agent(self, handle: str, message: discord.Message) -> None:
    agent_handle = self._agent_handles.get(handle)
    if agent_handle is None:
        return
    content = await self._build_content_with_attachments(message)
    inbound = InboundMessage(
        sender=message.author.display_name,
        channel=getattr(message.channel, "name", "unknown"),
        content=content,
    )
    await agent_handle.send(inbound)
```

### Anti-Patterns to Avoid
- **Importing agent subclasses in daemon code:** After this phase, the daemon should never import GsdAgent, CompanyAgent, etc. Those live exclusively in the worker.
- **Calling methods on container objects:** All interaction must go through typed channel messages. No `container.give_task()`, `container.stop()`, etc.
- **Building launch commands daemon-side:** The `_build_launch_command()` method on AgentContainer is a worker concern. The head sends config; the worker decides how to launch.
- **Polling health from container objects:** Health comes from HealthReportMessage received through the channel, not from calling `container.health_report()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Message serialization | Custom JSON encoding | Existing `encode()`/`decode_head()`/`decode_worker()` from channel protocol (Phase 29) | Already handles discriminated unions, NDJSON framing |
| Health report caching | Custom cache with expiry | Simple field on AgentHandle + timestamp | Health reports arrive via channel; just cache the latest one |
| Discord channel creation | Direct discord.py calls | Existing CommunicationPort.create_channel() | Already abstracted; RuntimeAPI.hire() already uses it |
| Config blob format | New schema | Existing WorkerConfig model from Phase 30 | Worker already validates and uses this exact schema |

## Common Pitfalls

### Pitfall 1: Breaking the Strategist Agent

**What goes wrong:** The Strategist is a special company agent that uses `StrategistConversationHandler` and has unique routing. Refactoring it to use AgentHandle breaks conversation history.
**Why it happens:** Strategist's conversation state lives in daemon-side `StrategistConversation` object.
**How to avoid:** The Strategist must also be bootstrapped through the transport channel. Its conversation handler already exists in the worker package. Ensure the config blob includes persona path and conversation settings.
**Warning signs:** Strategist stops responding to Discord messages after refactor.

### Pitfall 2: Transport Channel Not Yet Bidirectional for Local Transport

**What goes wrong:** The current `LocalTransport` uses tmux panes for interactive agents and subprocess for piped agents. Neither currently implements the NDJSON channel protocol for bidirectional communication.
**Why it happens:** Phase 29 defined the protocol and Phase 30 built the worker that reads/writes it, but the head-side transport doesn't yet have a channel reader/writer layer.
**How to avoid:** This phase must add a channel communication layer to the transport. For local transport, the natural approach is to spawn `vco-worker` as a subprocess with stdin/stdout as the channel, even for agents that currently use tmux. The transport channel wraps the process, and the worker handles the tmux/Claude Code launch internally.
**Warning signs:** Head sends StartMessage but worker never receives it.

### Pitfall 3: Race Between Channel Creation and Worker Bootstrap

**What goes wrong:** Discord channel creation is async. If the worker sends a `ReportMessage` before the channel ID is registered, the report gets lost.
**How to avoid:** Create the Discord channel and register routing BEFORE sending StartMessage to the worker. This is already the order in current `RuntimeAPI.hire()` -- preserve it.
**Warning signs:** Early worker messages (like "ready" signal) silently dropped.

### Pitfall 4: Health Report Staleness

**What goes wrong:** If the worker crashes or network is lost, cached health reports show stale "healthy" status.
**Why it happens:** Without a heartbeat timeout, the last received health report persists indefinitely.
**How to avoid:** Track `_last_health_time` on AgentHandle. If health data is older than a threshold (e.g., 60s), report status as "unknown" or "unreachable" in the health tree.
**Warning signs:** `vco health` shows agents as "running" after they've crashed.

### Pitfall 5: MentionRouterCog Container Type Coupling

**What goes wrong:** `MentionRouterCog` currently stores `AgentContainer` references and has `TYPE_CHECKING` import. After refactor, it needs `AgentHandle` or a send callback instead.
**Why it happens:** Tight coupling between routing cog and container type.
**How to avoid:** Change MentionRouterCog to store either AgentHandle objects or a simple callback `async def deliver(msg: InboundMessage)`. The callback approach is cleanest -- the router doesn't need to know about handles at all.
**Warning signs:** Type errors at runtime because MentionRouterCog expects `.receive_discord_message()` method.

### Pitfall 6: Supervisor._children Type Change Ripple

**What goes wrong:** `Supervisor._children` is `dict[str, AgentContainer]`. Changing to `dict[str, AgentHandle]` breaks all supervisor methods: health_tree(), _start_child(), _handle_child_failure(), etc.
**Why it happens:** Supervisor deeply assumes children are AgentContainer instances.
**How to avoid:** Either (a) make AgentHandle duck-type compatible with the AgentContainer interface used by Supervisor (implement health_report(), start(), stop() as transport-forwarding methods) or (b) refactor Supervisor to work with handles. Option (a) is less invasive and preserves the supervisor restart semantics.
**Warning signs:** Supervisor restart logic breaks because it tries to call methods that don't exist on AgentHandle.

## Key Implementation Decisions

### Transport Channel Integration

The critical architectural question is: how does the head-side transport gain channel protocol communication with the worker?

**Current state:** LocalTransport creates tmux panes and sends commands via `tmux send-keys`. DockerTransport creates Docker containers and execs commands in them. Neither speaks the channel protocol.

**Required state:** The head must be able to send HeadMessages to and receive WorkerMessages from each agent.

**Recommended approach:** For each agent, the head spawns `vco-worker` as a subprocess (stdin/stdout = channel). The worker internally handles its own execution environment (tmux, Docker, etc.). This is the natural architecture from Phase 30's design -- the worker is already built to read HeadMessages from stdin and write WorkerMessages to stdout.

This means:
1. Head spawns `vco-worker` subprocess per agent
2. Head writes HeadMessages to subprocess stdin (NDJSON)
3. Head reads WorkerMessages from subprocess stdout (NDJSON)
4. Worker manages its own tmux/Docker/process internally

The existing `AgentTransport` protocol is NOT the right abstraction for this -- it's about execution environments (setup tmux pane, exec command). The new abstraction is about channel communication (send message, receive message). A new `ChannelTransport` or modification of the hire flow is needed.

### What Changes in Each File

| File | Current Role | Changes |
|------|-------------|---------|
| `runtime_api.py` | Wraps CompanyRoot, calls container methods | Replace container method calls with channel message sends |
| `company_root.py` | Manages AgentContainer dicts | Replace AgentContainer with AgentHandle, change health_tree to use cached reports |
| `supervisor.py` | Creates containers, monitors health | Replace container creation with handle creation + worker spawn |
| `daemon.py` | Imports container factory, wires everything | Remove container factory imports, wire channel readers |
| `factory.py` | Creates AgentContainer instances with transports | Not used by daemon anymore (HEAD-04 will remove, but Phase 31 just bypasses it) |
| `mention_router.py` | Stores AgentContainer refs, calls receive_discord_message | Store AgentHandle refs, send InboundMessage through channel |
| `container/health.py` | HealthReport model used daemon-side | Keep model but populate from HealthReportMessage data instead of container state |

### Routing State Persistence (HEAD-05)

**What needs persisting:** agent_id -> {channel_id, category_id, agent_type, handler_type, config}

**Where:** `state/supervision/routing.json` (alongside existing supervision state)

**When to save:** After every hire/dismiss. Load on daemon startup.

**On restart:** Daemon loads routing state, reconnects to existing transport channels (workers may still be running if daemon crashed), re-registers MentionRouterCog handles.

### Scope Boundary: What Phase 31 Does NOT Do

- **Does NOT remove dead code** -- that's HEAD-04 in Phase 34. Old container classes, agent subclasses, factory remain in the codebase but are no longer called by daemon code paths.
- **Does NOT implement Docker transport channel** -- that's CHAN-02 in Phase 32. Phase 31 uses subprocess-based channel (LocalTransport spawning vco-worker).
- **Does NOT implement container autonomy** -- that's AUTO-01/02/03 in Phase 33. Workers don't yet survive daemon restart in Phase 31 (routing persistence enables the head side of reconnection, but full AUTO-03 is Phase 33).

## Code Examples

### AgentHandle Model (new file)

```python
# src/vcompany/daemon/agent_handle.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from vcompany.transport.channel.messages import (
    HealthReportMessage, HeadMessage, WorkerMessage,
)


class AgentHandle(BaseModel):
    """Daemon-side agent representation -- metadata + transport, no container."""

    model_config = {"arbitrary_types_allowed": True}

    agent_id: str
    agent_type: str
    capabilities: list[str] = Field(default_factory=list)
    channel_id: str | None = None
    handler_type: str = "session"
    config: dict = Field(default_factory=dict)

    # Runtime state (excluded from serialization)
    _process: asyncio.subprocess.Process | None = None
    _reader_task: asyncio.Task | None = None
    _last_health: HealthReportMessage | None = None
    _last_health_time: datetime | None = None

    async def send(self, msg: HeadMessage) -> None:
        """Send a HeadMessage to the worker through the channel."""
        if self._process is None or self._process.stdin is None:
            raise RuntimeError(f"No transport for agent {self.agent_id}")
        from vcompany.transport.channel.framing import encode
        self._process.stdin.write(encode(msg))
        await self._process.stdin.drain()

    def update_health(self, report: HealthReportMessage) -> None:
        """Cache a received health report."""
        self._last_health = report
        self._last_health_time = datetime.now(timezone.utc)

    @property
    def state(self) -> str:
        """Current agent state from last health report."""
        if self._last_health is None:
            return "unknown"
        return self._last_health.status

    def health_report(self) -> dict:
        """Build a HealthReport-compatible dict from cached data."""
        now = datetime.now(timezone.utc)
        if self._last_health is not None:
            return {
                "agent_id": self.agent_id,
                "state": self._last_health.status,
                "inner_state": self._last_health.agent_state or None,
                "uptime": self._last_health.uptime_seconds,
                "last_heartbeat": self._last_health_time or now,
                "error_count": 0,
                "last_activity": self._last_health_time or now,
            }
        return {
            "agent_id": self.agent_id,
            "state": "unknown",
            "inner_state": None,
            "uptime": 0.0,
            "last_heartbeat": now,
            "error_count": 0,
            "last_activity": now,
        }
```

### Refactored Hire Flow

```python
# In RuntimeAPI.hire() -- sends config through transport instead of creating container
async def hire(self, agent_id: str, template: str = "generic",
               agent_type: str | None = None) -> str:
    # 1. Create Discord channel (existing logic)
    result = await self._get_comm().create_channel(
        CreateChannelPayload(category_name="vco-tasks", channel_name=f"task-{agent_id}")
    )
    channel_id = result.channel_id if result else None
    if channel_id:
        self._channel_ids[f"task-{agent_id}"] = channel_id

    # 2. Build config blob for worker
    effective_type = agent_type or "task"
    config = WorkerConfig(
        handler_type="session",  # from agent-types.yaml
        agent_type=effective_type,
        capabilities=[],
        gsd_command=None,
    )

    # 3. Create AgentHandle (metadata only)
    handle = AgentHandle(
        agent_id=agent_id,
        agent_type=effective_type,
        channel_id=channel_id,
        handler_type=config.handler_type,
        config=config.model_dump(),
    )

    # 4. Spawn worker subprocess + send StartMessage
    process = await asyncio.create_subprocess_exec(
        "vco-worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    handle._process = process

    # 5. Send StartMessage
    await handle.send(StartMessage(agent_id=agent_id, config=config.model_dump()))

    # 6. Start channel reader task
    handle._reader_task = asyncio.create_task(
        self._channel_reader(handle)
    )

    # 7. Register in CompanyRoot
    self._root._company_agents[agent_id] = handle
    return agent_id
```

### Health Tree from Cached Reports

```python
# In CompanyRoot.health_tree() -- reads cached health instead of calling containers
def health_tree(self) -> CompanyHealthTree:
    company_nodes = []
    for handle in self._company_agents.values():
        report_data = handle.health_report()
        company_nodes.append(HealthNode(
            report=HealthReport(**report_data)
        ))
    # ... same pattern for project trees
    return CompanyHealthTree(
        supervisor_id=self.supervisor_id,
        state=self._state,
        company_agents=company_nodes,
        projects=project_trees,
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Daemon creates full container objects | Daemon holds handles, worker manages containers | Phase 31 (this phase) | Containers become opaque to daemon |
| Health from direct method calls | Health from channel messages | Phase 31 | Enables remote workers |
| Container factory in daemon | Worker bootstraps from config blob | Phase 30 built worker, Phase 31 stops using factory | Factory becomes dead code (cleaned in Phase 34) |

## Open Questions

1. **Strategist conversation in worker process**
   - What we know: Strategist uses StrategistConversationHandler which depends on anthropic SDK. The worker package deliberately excludes anthropic as a dependency.
   - What's unclear: Should the Strategist be the one exception that runs differently, or should vco-worker gain an optional anthropic dependency?
   - Recommendation: Use WorkerConversationHandler's relay mode (Phase 30 decision). In relay mode, the worker receives InboundMessages and sends them back as ReportMessages -- the head handles the actual Anthropic API call. This is already designed for this exact case.

2. **Worker subprocess management**
   - What we know: Each agent needs a vco-worker subprocess with stdin/stdout channel.
   - What's unclear: Should vco-worker be installed globally or invoked via `python -m vco_worker` from the packages directory?
   - Recommendation: Use `python -m vco_worker` for development; `vco-worker` console_script for production. Check if vco-worker is installed in the same venv.

3. **Graceful transition during development**
   - What we know: Phase 34 removes dead code. Phase 31 should leave old code in place but not use it.
   - What's unclear: Do we need a feature flag to toggle between old (container) and new (handle) code paths?
   - Recommendation: No feature flag. Phase 31 directly replaces the code paths. Old container code stays importable but isn't called. This is cleaner than maintaining two code paths.

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/vcompany/daemon/daemon.py`, `runtime_api.py`, `company_root.py` -- current architecture
- Codebase inspection: `src/vcompany/transport/channel/messages.py` -- Phase 29 protocol messages
- Codebase inspection: `packages/vco-worker/src/vco_worker/` -- Phase 30 worker runtime
- Codebase inspection: `src/vcompany/container/container.py` -- current container implementation
- CONTEXT.md: Phase 31 decisions and constraints
- REQUIREMENTS.md: HEAD-01 through HEAD-05 specifications
- STATE.md: Accumulated architecture decisions from v3.0-v4.0

### Secondary (MEDIUM confidence)
- Phase 30 decisions about WorkerConfig, relay mode, StdioWriter -- from STATE.md accumulated context

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new libraries needed; all components exist from Phases 29-30
- Architecture: HIGH - Clear transformation from container-based to handle-based; all building blocks exist
- Pitfalls: HIGH - Based on direct codebase analysis of coupling points

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable -- internal architecture refactor, no external dependency changes)
