# Phase 29: Transport Channel Protocol - Research

**Researched:** 2026-03-31
**Domain:** Bidirectional message protocol (Pydantic models, NDJSON serialization, transport-agnostic framing)
**Confidence:** HIGH

## Summary

Phase 29 defines the typed message protocol that head and worker use to communicate. This is a pure data-modeling phase -- no networking, no transport wiring, no runtime integration. The deliverables are: (1) Pydantic v2 models for every head-to-worker and worker-to-head message type, (2) a framing/serialization layer that produces bytes any transport can carry, and (3) a test suite proving round-trip fidelity.

The project already has an excellent precedent: `daemon/protocol.py` uses Pydantic BaseModel with NDJSON serialization (`model_dump_json().encode() + b"\n"` / `model_validate_json(line.strip())`). The channel protocol should follow this exact pattern but use Pydantic discriminated unions (verified working with installed Pydantic 2.12.5) to dispatch on a `type` field rather than JSON-RPC method strings.

**Primary recommendation:** Define all message types as Pydantic models with a `Literal` type discriminator field, group them into `HeadMessage` and `WorkerMessage` discriminated unions, serialize as NDJSON (one JSON object per line), and provide `encode()`/`decode()` functions that handle the bytes boundary. Keep the protocol module dependency-free (only pydantic + stdlib) so it can be imported by both vco-head and vco-worker.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked -- all implementation choices at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion. Key constraints from project context:
- Containers run INSIDE transports, not as daemon-side Python objects (v4.0 architecture decision)
- Transport channel is the ONLY communication between head and worker
- Protocol must be transport-agnostic (stdin/stdout, socket, TCP, WebSocket)
- Use Pydantic v2 models (project standard)
- vco-worker must be installable standalone -- no discord.py, no bot code, no orchestration dependencies

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CHAN-01 | Bidirectional message protocol defined (head->worker: start/task/message/stop/health-check; worker->head: signal/report/ask/send-file/health-report) | Pydantic discriminated unions for typed dispatch, NDJSON framing matching daemon/protocol.py pattern, round-trip serialization tests |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Use Pydantic v2 (>=2.11) for all data contracts
- No GitPython -- subprocess for git operations (not relevant here)
- httpx for HTTP (not relevant here)
- Filesystem YAML/Markdown for state (not relevant here)
- Protocol module must be importable by future vco-worker package without pulling in discord.py, anthropic, libtmux, or any heavy dependencies

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.5 (installed) | Message model definitions, validation, JSON serialization | Project standard. Already used for daemon protocol, config models, message contexts. Discriminated unions provide type-safe message dispatch. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| typing (stdlib) | N/A | Literal, Union, Annotated for discriminator pattern | Every message model definition |
| enum (stdlib) | N/A | StrEnum for message type constants | Message type enumeration |
| datetime (stdlib) | N/A | Timestamps in messages | Health reports, event timestamps |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pydantic discriminated unions | JSON-RPC method field (like daemon/protocol.py) | JSON-RPC adds request/response coupling. Channel messages are fire-and-forget or async -- discriminated union on `type` field is simpler and more appropriate for a bidirectional stream protocol. |
| NDJSON framing | Length-prefixed binary | NDJSON is human-debuggable, already proven in daemon protocol, and sufficient for message sizes involved. Length-prefixed is better for binary payloads but adds complexity. |
| StrEnum for types | Plain string literals | StrEnum gives IDE autocomplete and prevents typos while still serializing as plain strings in JSON. |

**No installation needed.** All dependencies already present via existing pydantic requirement in pyproject.toml.

## Architecture Patterns

### Recommended Module Structure
```
src/vcompany/transport/
    channel/
        __init__.py         # Public API: encode, decode, HeadMessage, WorkerMessage
        messages.py         # All Pydantic message models + discriminated unions
        framing.py          # NDJSON encode/decode (bytes <-> model)
    protocol.py             # Existing AgentTransport protocol (unchanged)
    local.py                # Existing LocalTransport (unchanged)
    docker.py               # Existing DockerTransport (unchanged)
    __init__.py             # Existing exports (add channel re-exports)
```

The `channel/` subpackage keeps the new protocol isolated from the existing transport layer. This is the module that both vco-head and vco-worker will import.

### Pattern 1: Discriminated Union with Type Field
**What:** Each message has a `type: Literal["specific-type"]` field. Head and worker message unions use `Field(discriminator="type")` for O(1) dispatch.
**When to use:** Always -- this is the core pattern for the entire protocol.
**Example:**
```python
from __future__ import annotations
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field
from enum import StrEnum

class HeadMessageType(StrEnum):
    START = "start"
    GIVE_TASK = "give-task"
    MESSAGE = "message"
    STOP = "stop"
    HEALTH_CHECK = "health-check"

class StartMessage(BaseModel):
    """Head tells worker to initialize with config."""
    type: Literal[HeadMessageType.START] = HeadMessageType.START
    agent_id: str
    config: dict  # handler type, capabilities, gsd_command, persona, env vars

class GiveTaskMessage(BaseModel):
    """Head assigns a task to the worker."""
    type: Literal[HeadMessageType.GIVE_TASK] = HeadMessageType.GIVE_TASK
    task_id: str
    description: str
    context: dict = Field(default_factory=dict)

# ... other head messages ...

HeadMessage = Annotated[
    Union[StartMessage, GiveTaskMessage, ...],
    Field(discriminator="type"),
]
```

### Pattern 2: NDJSON Framing (Matching Daemon Protocol)
**What:** Each message serialized as one JSON line terminated by `\n`. Matches the `to_line()` / `from_line()` pattern in `daemon/protocol.py`.
**When to use:** All serialization/deserialization at the transport boundary.
**Example:**
```python
from pydantic import TypeAdapter

_head_adapter = TypeAdapter(HeadMessage)
_worker_adapter = TypeAdapter(WorkerMessage)

def encode(msg: BaseModel) -> bytes:
    """Serialize a message to NDJSON bytes (one line)."""
    return msg.model_dump_json().encode("utf-8") + b"\n"

def decode_head(line: bytes) -> HeadMessage:
    """Deserialize bytes to a head->worker message."""
    return _head_adapter.validate_json(line.strip())

def decode_worker(line: bytes) -> WorkerMessage:
    """Deserialize bytes to a worker->head message."""
    return _worker_adapter.validate_json(line.strip())
```

### Pattern 3: Envelope with Metadata
**What:** Optional envelope fields (timestamp, sequence number) on a base class for debugging and ordering.
**When to use:** Consider for all messages to aid debugging, especially across transport boundaries.
**Example:**
```python
from datetime import datetime

class ChannelMessage(BaseModel):
    """Base for all channel protocol messages."""
    seq: int | None = None        # Optional sequence number for ordering
    ts: datetime | None = None    # Optional timestamp for debugging
```

### Anti-Patterns to Avoid
- **Generic `params: dict[str, Any]` payload:** The daemon protocol uses this (JSON-RPC style) -- it defeats type safety. Each message type should have explicitly typed fields.
- **Inheritance hierarchy for messages:** Pydantic discriminated unions work best with flat, independent model classes. Deep inheritance creates confusing validation behavior.
- **Binary payloads in JSON:** For `send-file`, include file path and base64-encoded content OR a content hash with separate binary transfer. Do not embed raw bytes in JSON.
- **Bidirectional type union:** Do NOT create a single `ChannelMessage = HeadMessage | WorkerMessage` union. Keep head and worker message types separate -- the decoder always knows which direction it's parsing based on which side it's on.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON serialization | Custom dict-to-json encoder | `model_dump_json()` / `model_validate_json()` | Pydantic handles datetime, enums, nested models, validation errors |
| Type dispatch | if/elif chain on string field | `Field(discriminator="type")` + TypeAdapter | O(1) dispatch, exhaustive validation, clear error messages |
| Message versioning | Custom version negotiation | `protocol_version: int` field + TypeAdapter per version | Start with version 1, add adapters when protocol evolves |
| NDJSON line splitting | Custom buffer management | `asyncio.StreamReader.readline()` | stdlib handles partial reads, buffering, EOF correctly |

**Key insight:** Pydantic v2's TypeAdapter with discriminated unions does exactly what a message protocol needs -- validate, dispatch, and (de)serialize typed messages from raw bytes. The daemon protocol already proves this pattern works in this codebase.

## Common Pitfalls

### Pitfall 1: Forward References Break TypeAdapter
**What goes wrong:** Using `from __future__ import annotations` (which the codebase uses everywhere) turns type hints into strings. `TypeAdapter` needs resolved types.
**Why it happens:** PEP 563 defers annotation evaluation. TypeAdapter must evaluate them.
**How to avoid:** Create TypeAdapter instances at module level AFTER all model classes are defined, or use `model_rebuild()` if needed. Alternatively, define the Union type explicitly rather than relying on forward references.
**Warning signs:** `PydanticUserError` about unresolvable forward references at import time.

### Pitfall 2: Discriminator Field Not in JSON
**What goes wrong:** If a message model has `type` with a default but the serialized JSON omits it (e.g., using `exclude_defaults=True`), the discriminator fails.
**Why it happens:** `model_dump_json(exclude_defaults=True)` strips the type field.
**How to avoid:** Never use `exclude_defaults=True` or `exclude_unset=True` for channel messages. Always serialize with defaults included. The `encode()` function should use bare `model_dump_json()`.
**Warning signs:** Pydantic validation error "Unable to extract tag" during deserialization.

### Pitfall 3: send-file Binary Content in JSON
**What goes wrong:** Encoding large binary files as base64 in JSON messages creates huge strings, memory pressure, and slow serialization.
**Why it happens:** JSON cannot represent binary natively.
**How to avoid:** For `send-file`, include file metadata (path, size, hash) in the JSON message. Use base64 only for small files (< 64KB). For larger files, define a two-phase protocol: metadata message followed by raw binary frame, or defer binary transfer to a transport-specific mechanism. For Phase 29, define the message model with `content_b64: str | None` for small files and document the large-file extension point.
**Warning signs:** Messages exceeding 1MB, JSON parse timeouts.

### Pitfall 4: Forgetting to Test All Message Types
**What goes wrong:** A message type gets defined but its round-trip is never tested. Later, a field name typo or wrong type causes runtime failures.
**Why it happens:** Combinatorial explosion -- easy to miss one type in manual test writing.
**How to avoid:** Use pytest parametrize over ALL message types. Collect all concrete message classes programmatically.
**Warning signs:** Message type works in model creation but fails in `TypeAdapter.validate_json()`.

### Pitfall 5: Mutable Default Factory
**What goes wrong:** Using `config: dict = {}` instead of `config: dict = Field(default_factory=dict)` causes shared mutable state between instances.
**Why it happens:** Classic Python mutable default argument trap.
**How to avoid:** Always use `Field(default_factory=dict)` or `Field(default_factory=list)` for mutable defaults. Pydantic v2 warns about this but does not always catch it.
**Warning signs:** One message's config dict mysteriously contains another message's data.

## Code Examples

### Complete Message Type Definition Pattern
```python
# Source: Verified against Pydantic 2.12.5 installed in project
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# --- Head -> Worker messages ---

class HeadMessageType(StrEnum):
    START = "start"
    GIVE_TASK = "give-task"
    MESSAGE = "message"
    STOP = "stop"
    HEALTH_CHECK = "health-check"


class StartMessage(BaseModel):
    type: Literal[HeadMessageType.START] = HeadMessageType.START
    agent_id: str
    config: dict = Field(default_factory=dict)


class GiveTaskMessage(BaseModel):
    type: Literal[HeadMessageType.GIVE_TASK] = HeadMessageType.GIVE_TASK
    task_id: str
    description: str
    context: dict = Field(default_factory=dict)


class InboundMessage(BaseModel):
    type: Literal[HeadMessageType.MESSAGE] = HeadMessageType.MESSAGE
    sender: str
    channel: str
    content: str
    message_id: str | None = None


class StopMessage(BaseModel):
    type: Literal[HeadMessageType.STOP] = HeadMessageType.STOP
    reason: str = ""
    graceful: bool = True


class HealthCheckMessage(BaseModel):
    type: Literal[HeadMessageType.HEALTH_CHECK] = HeadMessageType.HEALTH_CHECK


HeadMessage = Annotated[
    Union[StartMessage, GiveTaskMessage, InboundMessage, StopMessage, HealthCheckMessage],
    Field(discriminator="type"),
]


# --- Worker -> Head messages ---

class WorkerMessageType(StrEnum):
    SIGNAL = "signal"
    REPORT = "report"
    ASK = "ask"
    SEND_FILE = "send-file"
    HEALTH_REPORT = "health-report"


class SignalMessage(BaseModel):
    type: Literal[WorkerMessageType.SIGNAL] = WorkerMessageType.SIGNAL
    signal: str  # e.g., "ready", "busy", "idle", "error"
    detail: str = ""


class ReportMessage(BaseModel):
    type: Literal[WorkerMessageType.REPORT] = WorkerMessageType.REPORT
    channel: str
    content: str
    task_id: str | None = None


class AskMessage(BaseModel):
    type: Literal[WorkerMessageType.ASK] = WorkerMessageType.ASK
    channel: str
    question: str
    context: dict = Field(default_factory=dict)


class SendFileMessage(BaseModel):
    type: Literal[WorkerMessageType.SEND_FILE] = WorkerMessageType.SEND_FILE
    channel: str
    filename: str
    content_b64: str  # base64-encoded file content
    description: str = ""


class HealthReportMessage(BaseModel):
    type: Literal[WorkerMessageType.HEALTH_REPORT] = WorkerMessageType.HEALTH_REPORT
    status: str  # "healthy", "degraded", "unhealthy"
    agent_state: str = ""  # FSM state if applicable
    uptime_seconds: float = 0.0
    detail: dict = Field(default_factory=dict)


WorkerMessage = Annotated[
    Union[SignalMessage, ReportMessage, AskMessage, SendFileMessage, HealthReportMessage],
    Field(discriminator="type"),
]
```

### NDJSON Encode/Decode Functions
```python
# Source: Pattern from daemon/protocol.py to_line()/from_line(), adapted for TypeAdapter
from pydantic import TypeAdapter

_head_adapter: TypeAdapter[HeadMessage] = TypeAdapter(HeadMessage)
_worker_adapter: TypeAdapter[WorkerMessage] = TypeAdapter(WorkerMessage)

PROTOCOL_VERSION: int = 1


def encode(msg: BaseModel) -> bytes:
    """Serialize any channel message to NDJSON bytes."""
    return msg.model_dump_json().encode("utf-8") + b"\n"


def decode_head(data: bytes) -> HeadMessage:
    """Parse bytes into a head->worker message."""
    return _head_adapter.validate_json(data.strip())


def decode_worker(data: bytes) -> WorkerMessage:
    """Parse bytes into a worker->head message."""
    return _worker_adapter.validate_json(data.strip())
```

### Round-Trip Test Pattern
```python
# Source: pytest pattern for exhaustive message testing
import pytest
from pydantic import TypeAdapter

ALL_HEAD_MESSAGES = [
    StartMessage(agent_id="test-01", config={"handler": "session"}),
    GiveTaskMessage(task_id="t-1", description="Build feature"),
    InboundMessage(sender="human", channel="dev", content="hello"),
    StopMessage(reason="shutdown"),
    HealthCheckMessage(),
]

ALL_WORKER_MESSAGES = [
    SignalMessage(signal="ready"),
    ReportMessage(channel="dev", content="Done"),
    AskMessage(channel="strategist", question="Which approach?"),
    SendFileMessage(channel="dev", filename="out.txt", content_b64="aGVsbG8="),
    HealthReportMessage(status="healthy", uptime_seconds=120.5),
]

@pytest.mark.parametrize("msg", ALL_HEAD_MESSAGES, ids=lambda m: m.type)
def test_head_message_roundtrip(msg):
    raw = encode(msg)
    assert raw.endswith(b"\n")
    decoded = decode_head(raw)
    assert decoded == msg
    assert type(decoded) is type(msg)

@pytest.mark.parametrize("msg", ALL_WORKER_MESSAGES, ids=lambda m: m.type)
def test_worker_message_roundtrip(msg):
    raw = encode(msg)
    assert raw.endswith(b"\n")
    decoded = decode_worker(raw)
    assert decoded == msg
    assert type(decoded) is type(msg)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| daemon/protocol.py JSON-RPC with `params: dict` | Discriminated union with typed fields | Phase 29 (new) | Type-safe dispatch, exhaustive field validation, IDE support |
| AgentTransport.exec() RPC-style | Channel message stream | Phase 29 (new) | Decouples head from worker internals, enables async bidirectional communication |

**Key evolution:** The existing daemon protocol (`daemon/protocol.py`) uses JSON-RPC 2.0 with generic `params: dict[str, Any]`. This works for a client-server API but is wrong for a bidirectional stream protocol where both sides send messages independently. The channel protocol uses discriminated unions -- each message is self-describing via its `type` field, and Pydantic dispatches to the correct model automatically.

## Open Questions

1. **Config blob schema for StartMessage**
   - What we know: Head sends config (handler type, capabilities, gsd_command, persona, env vars) to worker at startup
   - What's unclear: Exact fields -- these depend on Phase 30 (Worker Runtime) which defines what the worker needs
   - Recommendation: Use `config: dict` for now. Phase 30 will define a `WorkerConfig` Pydantic model that replaces the dict. This is fine -- the protocol is transport-agnostic, the config schema is an application concern.

2. **Large file transfer in send-file**
   - What we know: Small files work fine as base64 in JSON. Large files (>64KB) will be slow.
   - What's unclear: What file sizes agents actually produce. Current usage is PLAN.md files (<10KB) and code diffs.
   - Recommendation: Use base64 in Phase 29. Add a streaming/chunked extension in Phase 32 (transport wiring) if needed. YAGNI for now.

3. **Message ordering guarantees**
   - What we know: NDJSON over a stream transport (stdin/stdout, TCP) preserves ordering naturally.
   - What's unclear: Whether any transport will reorder messages (e.g., UDP, unreliable WebSocket).
   - Recommendation: Include optional `seq: int | None` field on a base mixin. Do not enforce ordering in Phase 29 -- that is a transport concern for Phase 32/34.

## Sources

### Primary (HIGH confidence)
- `src/vcompany/daemon/protocol.py` -- existing NDJSON protocol pattern (verified in codebase)
- `src/vcompany/transport/protocol.py` -- existing AgentTransport Protocol interface (verified in codebase)
- `src/vcompany/models/messages.py` -- existing MessageContext Pydantic model (verified in codebase)
- Pydantic 2.12.5 discriminated union pattern -- verified working on installed version via interactive Python test

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` CHAN-01 requirement text -- defines message types
- `29-CONTEXT.md` architecture decisions -- containers inside transports, transport-agnostic protocol

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - only pydantic + stdlib, both verified installed and working
- Architecture: HIGH - follows proven daemon/protocol.py pattern, discriminated unions verified on installed Pydantic version
- Pitfalls: HIGH - forward reference and discriminator pitfalls verified through hands-on testing

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable -- Pydantic v2 API is mature, no breaking changes expected)
