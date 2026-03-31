"""Tests for the transport channel protocol: message models and NDJSON framing."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vcompany.transport.channel import (
    AskMessage,
    GiveTaskMessage,
    HealthCheckMessage,
    HealthReportMessage,
    InboundMessage,
    ReportMessage,
    SendFileMessage,
    SignalMessage,
    StartMessage,
    StopMessage,
    decode_head,
    decode_worker,
    encode,
)

# --- Fixture instances for parametrized tests ---

ALL_HEAD_MESSAGES = [
    StartMessage(agent_id="a1", config={"handler": "session"}),
    GiveTaskMessage(task_id="t-1", description="Build the feature"),
    InboundMessage(sender="human", channel="dev", content="hi"),
    StopMessage(reason="done", graceful=True),
    HealthCheckMessage(),
]

ALL_WORKER_MESSAGES = [
    SignalMessage(signal="ready"),
    ReportMessage(channel="dev", content="Done"),
    AskMessage(channel="strat", question="Which approach?"),
    SendFileMessage(channel="dev", filename="out.txt", content_b64="aGVsbG8="),
    HealthReportMessage(status="healthy", uptime_seconds=120.5),
]


@pytest.mark.parametrize("msg", ALL_HEAD_MESSAGES, ids=lambda m: m.type)
def test_head_message_roundtrip(msg):
    """Encode a head message, decode it back, and verify identity."""
    data = encode(msg)
    assert data.endswith(b"\n"), "Encoded bytes must end with newline (NDJSON)"
    decoded = decode_head(data)
    assert type(decoded) is type(msg), f"Expected {type(msg).__name__}, got {type(decoded).__name__}"
    assert decoded == msg


@pytest.mark.parametrize("msg", ALL_WORKER_MESSAGES, ids=lambda m: m.type)
def test_worker_message_roundtrip(msg):
    """Encode a worker message, decode it back, and verify identity."""
    data = encode(msg)
    assert data.endswith(b"\n"), "Encoded bytes must end with newline (NDJSON)"
    decoded = decode_worker(data)
    assert type(decoded) is type(msg), f"Expected {type(msg).__name__}, got {type(decoded).__name__}"
    assert decoded == msg


def test_decode_head_rejects_worker_message():
    """decode_head must reject a valid worker message (wrong direction)."""
    worker_msg = SignalMessage(signal="ready")
    data = encode(worker_msg)
    with pytest.raises(ValidationError):
        decode_head(data)


def test_decode_worker_rejects_head_message():
    """decode_worker must reject a valid head message (wrong direction)."""
    head_msg = StartMessage(agent_id="a1")
    data = encode(head_msg)
    with pytest.raises(ValidationError):
        decode_worker(data)


def test_decode_head_rejects_malformed_json():
    """decode_head must raise ValidationError on malformed JSON."""
    with pytest.raises(ValidationError):
        decode_head(b"not json\n")


def test_decode_worker_rejects_malformed_json():
    """decode_worker must raise ValidationError on malformed JSON."""
    with pytest.raises(ValidationError):
        decode_worker(b"{invalid\n")
