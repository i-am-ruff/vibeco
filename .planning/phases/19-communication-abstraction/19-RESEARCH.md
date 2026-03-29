# Phase 19: Communication Abstraction - Research

**Researched:** 2026-03-29
**Domain:** Python Protocol-based abstraction layer for platform communication
**Confidence:** HIGH

## Summary

Phase 19 defines a `CommunicationPort` protocol in the daemon layer that abstracts all outbound platform communication (send messages, send embeds, create threads, subscribe to channels). A `DiscordCommunicationPort` adapter in the bot layer implements this protocol and is registered with the daemon at startup via dependency injection. The daemon module tree must have zero `discord.py` imports after this phase.

The project already has a v2.1 `CommunicationPort` protocol in `src/vcompany/container/communication.py` with `send_message` and `receive_message` methods. Phase 19 replaces this with a richer protocol in the daemon layer that covers the four required operations: `send_message`, `send_embed`, `create_thread`, and `subscribe_to_channel`. The existing protocol is container-to-container focused; the new one is daemon-to-platform focused.

**Primary recommendation:** Define the new `CommunicationPort` as a `typing.Protocol` (not ABC) in `src/vcompany/daemon/comm.py` with Pydantic models for all message payloads. The `DiscordCommunicationPort` adapter lives in `src/vcompany/bot/comm_adapter.py` and translates protocol calls into discord.py API calls. Registration happens in `VcoBot.on_ready()` by calling a setter on the Daemon instance.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked -- all implementation choices at Claude's discretion per CONTEXT.md.

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Key architectural principles:
- CommunicationPort is a Python Protocol (typing.Protocol) -- not an ABC -- for structural subtyping
- Daemon module tree must have zero discord.py imports -- enforced at import level
- DiscordCommunicationPort lives in bot layer (not daemon) -- keeps the dependency boundary clean
- Adapter is registered with daemon on startup -- injection pattern, not import
- Methods must be typed (Pydantic models for message payloads preferred over raw dicts)

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase with clear scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COMM-01 | CommunicationPort protocol formalized with methods for send_message, send_embed, create_thread, subscribe_to_channel | Protocol definition pattern with typing.Protocol + Pydantic payload models; existing v2.1 CommunicationPort shows the pattern already used in the project |
| COMM-02 | Daemon never imports discord.py -- all platform communication goes through CommunicationPort | Daemon module currently has zero discord.py imports (verified). Bot is typed as `object` in Daemon constructor. New comm.py module must maintain this invariant. |
| COMM-03 | DiscordCommunicationPort adapter implements CommunicationPort protocol in the bot layer | Adapter lives in bot layer, uses discord.py channel/thread APIs, registered via setter on Daemon |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| typing.Protocol | stdlib | CommunicationPort protocol definition | Structural subtyping -- no inheritance required. Already the pattern used in `container/communication.py` |
| pydantic | 2.11.x | Payload models for messages, embeds, threads | Already used throughout project for data validation. Pydantic models preferred over raw dicts per CONTEXT.md |
| discord.py | 2.7.x | DiscordCommunicationPort adapter internals | Only imported in bot layer. Adapter translates protocol calls to discord.py API |

No new dependencies needed. This phase uses only existing project stack.

## Architecture Patterns

### Recommended Project Structure
```
src/vcompany/
  daemon/
    comm.py          # CommunicationPort protocol + Pydantic payload models
    daemon.py         # Daemon class gains _comm_port: CommunicationPort | None
    ...
  bot/
    comm_adapter.py   # DiscordCommunicationPort implements CommunicationPort
    client.py         # on_ready registers adapter with daemon
    ...
```

### Pattern 1: typing.Protocol for Structural Subtyping
**What:** Define CommunicationPort as a `typing.Protocol` with `@runtime_checkable` so that any class with matching method signatures satisfies it without inheriting.
**When to use:** Always for cross-layer abstractions where you want to avoid import coupling.
**Example:**
```python
# src/vcompany/daemon/comm.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from pydantic import BaseModel

class SendMessagePayload(BaseModel):
    channel_id: str
    content: str

class SendEmbedPayload(BaseModel):
    channel_id: str
    title: str
    description: str
    color: int | None = None
    fields: list[EmbedField] = []

class EmbedField(BaseModel):
    name: str
    value: str
    inline: bool = False

class CreateThreadPayload(BaseModel):
    channel_id: str
    name: str
    message: str | None = None

class ThreadResult(BaseModel):
    thread_id: str
    name: str

class SubscribePayload(BaseModel):
    channel_id: str
    event_types: list[str] = []  # e.g. ["message", "reaction"]

@runtime_checkable
class CommunicationPort(Protocol):
    async def send_message(self, payload: SendMessagePayload) -> bool: ...
    async def send_embed(self, payload: SendEmbedPayload) -> bool: ...
    async def create_thread(self, payload: CreateThreadPayload) -> ThreadResult | None: ...
    async def subscribe_to_channel(self, payload: SubscribePayload) -> bool: ...
```

### Pattern 2: Dependency Injection via Setter
**What:** Daemon exposes a `set_comm_port(port: CommunicationPort)` method. Bot calls this in `on_ready()` after constructing the adapter.
**When to use:** When the dependency cannot be provided at construction time (bot needs to be running to create channels).
**Example:**
```python
# In Daemon class
class Daemon:
    def __init__(self, ...):
        self._comm_port: CommunicationPort | None = None

    def set_comm_port(self, port: CommunicationPort) -> None:
        self._comm_port = port

    @property
    def comm_port(self) -> CommunicationPort:
        if self._comm_port is None:
            raise RuntimeError("CommunicationPort not registered")
        return self._comm_port
```

```python
# In VcoBot on_ready or startup
adapter = DiscordCommunicationPort(bot=self)
self.daemon.set_comm_port(adapter)  # daemon reference set on bot
```

### Pattern 3: Channel ID Abstraction
**What:** The protocol uses string channel IDs, not discord.py Channel objects. The adapter resolves string IDs to discord.py channels internally.
**When to use:** Always -- this is what makes the protocol platform-agnostic.
**Why:** The daemon should never handle discord.py types. String IDs (or semantic names like "alerts", "strategist") are platform-neutral. The adapter maps them to actual Discord channel objects.

### Anti-Patterns to Avoid
- **Passing discord.Embed objects through the protocol:** Use Pydantic models for embed data. The adapter constructs discord.Embed from the model.
- **Importing discord.py in daemon for type hints:** Even `TYPE_CHECKING` imports of discord in the daemon violate COMM-02. Use string channel IDs and Pydantic models everywhere.
- **Making CommunicationPort an ABC:** CONTEXT.md explicitly says `typing.Protocol` for structural subtyping. ABCs require inheritance which creates import coupling.
- **Registering at construction time:** The bot isn't connected when Daemon.__init__ runs. Registration must happen after bot connects (on_ready).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Message payload validation | Manual dict checking | Pydantic BaseModel for each payload type | Type safety, serialization, already used everywhere in project |
| Protocol enforcement | Manual duck typing checks | `@runtime_checkable` + `isinstance()` | stdlib support, tests can verify compliance |
| Embed construction | Custom embed dict format | Pydantic model -> discord.Embed conversion in adapter | discord.py Embed API handles all edge cases (field limits, color, footer) |

## Common Pitfalls

### Pitfall 1: Circular Import Between Daemon and Bot
**What goes wrong:** Bot imports from daemon (for Daemon class). If daemon imports from bot for the adapter, circular import.
**Why it happens:** Temptation to type-hint the adapter in daemon.
**How to avoid:** Daemon only knows about `CommunicationPort` (the Protocol). Never imports anything from bot layer. Bot imports from daemon (one-way dependency).
**Warning signs:** `ImportError` at module load time.

### Pitfall 2: Registering Adapter Before Bot is Ready
**What goes wrong:** `on_ready` can fire multiple times (reconnects). Channel resolution may fail if guilds aren't cached yet.
**Why it happens:** discord.py fires `on_ready` after each reconnect, not just initial connect.
**How to avoid:** Guard registration with a flag (`_comm_registered`). On reconnect, update adapter's internal channel cache but don't re-register.
**Warning signs:** `AttributeError` on None channels, duplicate registration logs.

### Pitfall 3: Blocking the Event Loop in Adapter
**What goes wrong:** discord.py channel.send() is async. If adapter methods aren't properly awaited, messages drop silently.
**Why it happens:** Protocol methods are async but callers might forget to await.
**How to avoid:** All CommunicationPort methods are `async def`. Type checkers catch missing awaits.
**Warning signs:** RuntimeWarning about coroutines never being awaited.

### Pitfall 4: Conflicting with Existing v2.1 CommunicationPort
**What goes wrong:** `container/communication.py` already defines a `CommunicationPort` protocol. Name collision causes confusion.
**Why it happens:** v2.1 protocol is container-to-container; v3.0 protocol is daemon-to-platform. Different purposes.
**How to avoid:** The new protocol goes in `daemon/comm.py` with a distinct import path. The old one in `container/communication.py` can coexist for now and be deprecated/removed in a later phase (Phase 20+ when containers route through daemon). Document this clearly.
**Warning signs:** Tests importing wrong CommunicationPort.

### Pitfall 5: discord.py Leaking Into Daemon Via Strategist/DecisionLog
**What goes wrong:** `strategist/decision_log.py` directly imports discord (line 18). If daemon later hosts strategist logic (Phase 20), this creates a COMM-02 violation.
**Why it happens:** Existing code was written before the abstraction boundary existed.
**How to avoid:** Phase 19 scope is daemon module tree only. `strategist/` is not in daemon yet. But document this as a known issue for Phase 20.
**Warning signs:** Grep for `import discord` outside bot layer.

## Code Examples

### CommunicationPort Protocol Definition
```python
# src/vcompany/daemon/comm.py
from __future__ import annotations

from typing import Protocol, runtime_checkable
from pydantic import BaseModel


class EmbedField(BaseModel):
    name: str
    value: str
    inline: bool = False


class SendMessagePayload(BaseModel):
    channel_id: str
    content: str


class SendEmbedPayload(BaseModel):
    channel_id: str
    title: str
    description: str = ""
    color: int | None = None
    fields: list[EmbedField] = []


class CreateThreadPayload(BaseModel):
    channel_id: str
    name: str
    initial_message: str | None = None


class ThreadResult(BaseModel):
    thread_id: str
    name: str


class SubscribePayload(BaseModel):
    channel_id: str


@runtime_checkable
class CommunicationPort(Protocol):
    """Platform-agnostic communication interface for the daemon."""

    async def send_message(self, payload: SendMessagePayload) -> bool: ...
    async def send_embed(self, payload: SendEmbedPayload) -> bool: ...
    async def create_thread(self, payload: CreateThreadPayload) -> ThreadResult | None: ...
    async def subscribe_to_channel(self, payload: SubscribePayload) -> bool: ...
```

### DiscordCommunicationPort Adapter Skeleton
```python
# src/vcompany/bot/comm_adapter.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from vcompany.daemon.comm import (
    CommunicationPort,
    CreateThreadPayload,
    SendEmbedPayload,
    SendMessagePayload,
    SubscribePayload,
    ThreadResult,
)

if TYPE_CHECKING:
    from vcompany.bot.client import VcoBot

logger = logging.getLogger(__name__)


class DiscordCommunicationPort:
    """Discord adapter implementing CommunicationPort protocol."""

    def __init__(self, bot: VcoBot) -> None:
        self._bot = bot

    def _resolve_channel(self, channel_id: str) -> discord.TextChannel | None:
        """Resolve string channel ID to discord.py channel object."""
        try:
            ch = self._bot.get_channel(int(channel_id))
            if isinstance(ch, discord.TextChannel):
                return ch
        except ValueError:
            pass
        return None

    async def send_message(self, payload: SendMessagePayload) -> bool:
        channel = self._resolve_channel(payload.channel_id)
        if not channel:
            logger.warning("Channel %s not found", payload.channel_id)
            return False
        await channel.send(payload.content)
        return True

    async def send_embed(self, payload: SendEmbedPayload) -> bool:
        channel = self._resolve_channel(payload.channel_id)
        if not channel:
            return False
        embed = discord.Embed(
            title=payload.title,
            description=payload.description,
            color=discord.Colour(payload.color) if payload.color else None,
        )
        for field in payload.fields:
            embed.add_field(name=field.name, value=field.value, inline=field.inline)
        await channel.send(embed=embed)
        return True

    async def create_thread(self, payload: CreateThreadPayload) -> ThreadResult | None:
        channel = self._resolve_channel(payload.channel_id)
        if not channel:
            return None
        thread = await channel.create_thread(
            name=payload.name,
            type=discord.ChannelType.public_thread,
        )
        if payload.initial_message:
            await thread.send(payload.initial_message)
        return ThreadResult(thread_id=str(thread.id), name=thread.name)

    async def subscribe_to_channel(self, payload: SubscribePayload) -> bool:
        # For Discord, "subscribing" means the bot is listening to a channel.
        # This is inherently true for all channels the bot can see.
        channel = self._resolve_channel(payload.channel_id)
        return channel is not None
```

### Daemon Registration
```python
# In Daemon class (daemon.py)
from vcompany.daemon.comm import CommunicationPort

class Daemon:
    def __init__(self, ...):
        self._comm_port: CommunicationPort | None = None

    def set_comm_port(self, port: CommunicationPort) -> None:
        if not isinstance(port, CommunicationPort):
            raise TypeError(f"{type(port)} does not satisfy CommunicationPort protocol")
        self._comm_port = port

    @property
    def comm_port(self) -> CommunicationPort:
        if self._comm_port is None:
            raise RuntimeError("CommunicationPort not registered -- is the bot connected?")
        return self._comm_port
```

### Noop Adapter for Testing
```python
# src/vcompany/daemon/comm.py (or separate test helper)
class NoopCommunicationPort:
    """Test/fallback adapter. Logs calls, returns success."""

    async def send_message(self, payload: SendMessagePayload) -> bool:
        return True

    async def send_embed(self, payload: SendEmbedPayload) -> bool:
        return True

    async def create_thread(self, payload: CreateThreadPayload) -> ThreadResult | None:
        return ThreadResult(thread_id="noop-thread", name=payload.name)

    async def subscribe_to_channel(self, payload: SubscribePayload) -> bool:
        return True
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 0.24+ |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_daemon_comm.py -x` |
| Full suite command | `uv run pytest tests/ -x --ignore=tests/test_container_tmux_bridge.py -m "not integration"` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COMM-01 | CommunicationPort protocol has send_message, send_embed, create_thread, subscribe_to_channel | unit | `uv run pytest tests/test_daemon_comm.py::test_protocol_methods -x` | Wave 0 |
| COMM-01 | Pydantic payload models validate correctly | unit | `uv run pytest tests/test_daemon_comm.py::test_payload_models -x` | Wave 0 |
| COMM-02 | Daemon module tree has zero discord.py imports | unit | `uv run pytest tests/test_daemon_comm.py::test_no_discord_imports -x` | Wave 0 |
| COMM-03 | DiscordCommunicationPort satisfies CommunicationPort protocol | unit | `uv run pytest tests/test_discord_comm_adapter.py::test_adapter_satisfies_protocol -x` | Wave 0 |
| COMM-03 | DiscordCommunicationPort registered with daemon on startup | unit | `uv run pytest tests/test_discord_comm_adapter.py::test_adapter_registration -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_daemon_comm.py tests/test_discord_comm_adapter.py -x`
- **Per wave merge:** `uv run pytest tests/ -x --ignore=tests/test_container_tmux_bridge.py -m "not integration"`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_daemon_comm.py` -- covers COMM-01, COMM-02
- [ ] `tests/test_discord_comm_adapter.py` -- covers COMM-03

## Open Questions

1. **Channel ID format: numeric Discord IDs vs semantic names?**
   - What we know: Discord channel IDs are numeric strings (snowflakes). The project also uses semantic names like "alerts", "strategist" in bot code.
   - What's unclear: Should the protocol accept semantic names (resolved by adapter) or require numeric IDs (resolved by caller)?
   - Recommendation: Use numeric string IDs in the protocol for universality. The daemon can maintain a name-to-ID mapping populated by the adapter at registration time. This keeps the protocol simple and platform-agnostic.

2. **Relationship to existing v2.1 CommunicationPort in container/communication.py**
   - What we know: Existing protocol has `send_message(target, content)` and `receive_message()`. Different purpose (container-to-container).
   - What's unclear: Should the old protocol be replaced, deprecated, or kept alongside?
   - Recommendation: Keep both for now. Phase 19 creates the new daemon-layer protocol. Phase 20+ can deprecate the old one when containers route through daemon. Document the distinction clearly.

## Sources

### Primary (HIGH confidence)
- Project codebase: `src/vcompany/daemon/` -- Phase 18 daemon foundation (verified direct read)
- Project codebase: `src/vcompany/container/communication.py` -- existing v2.1 CommunicationPort (verified direct read)
- Project codebase: `src/vcompany/bot/client.py` -- current Discord communication patterns (verified direct read)
- Python docs: `typing.Protocol` -- structural subtyping, `@runtime_checkable` (stdlib, stable since 3.8)

### Secondary (MEDIUM confidence)
- Project STATE.md: Decision that bot typed as `object` in Daemon to avoid discord.py coupling (Phase 18 decision)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib + existing project dependencies, no new packages
- Architecture: HIGH -- Protocol pattern well-established in Python, existing v2.1 precedent in codebase
- Pitfalls: HIGH -- based on direct codebase analysis of import patterns and discord.py behavior

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (stable -- stdlib patterns, no moving targets)
