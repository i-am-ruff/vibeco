"""NDJSON framing for the transport channel protocol.

Provides encode/decode functions for head-to-worker and worker-to-head messages.
Each message is serialized as a single JSON line terminated by newline.
"""

from __future__ import annotations

from pydantic import BaseModel, TypeAdapter

from .messages import HeadMessage, WorkerMessage

PROTOCOL_VERSION: int = 1

_head_adapter: TypeAdapter[HeadMessage] = TypeAdapter(HeadMessage)
_worker_adapter: TypeAdapter[WorkerMessage] = TypeAdapter(WorkerMessage)


def encode(msg: BaseModel) -> bytes:
    """Serialize a message to NDJSON bytes (JSON + newline)."""
    return msg.model_dump_json().encode("utf-8") + b"\n"


def decode_head(data: bytes) -> HeadMessage:
    """Deserialize NDJSON bytes to a head-to-worker message.

    Raises pydantic.ValidationError if the data is not valid JSON
    or does not match any head message type.
    """
    return _head_adapter.validate_json(data.strip())


def decode_worker(data: bytes) -> WorkerMessage:
    """Deserialize NDJSON bytes to a worker-to-head message.

    Raises pydantic.ValidationError if the data is not valid JSON
    or does not match any worker message type.
    """
    return _worker_adapter.validate_json(data.strip())
