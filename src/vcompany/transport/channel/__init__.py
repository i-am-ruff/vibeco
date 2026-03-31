"""Transport channel protocol: typed messages and NDJSON framing for head-worker communication."""

from vcompany.transport.channel.framing import (
    PROTOCOL_VERSION,
    decode_head,
    decode_worker,
    encode,
)
from vcompany.transport.channel.messages import (
    AskMessage,
    GiveTaskMessage,
    HeadMessage,
    HeadMessageType,
    HealthCheckMessage,
    HealthReportMessage,
    InboundMessage,
    ReportMessage,
    SendFileMessage,
    SignalMessage,
    StartMessage,
    StopMessage,
    WorkerMessage,
    WorkerMessageType,
)

__all__ = [
    # Enums
    "HeadMessageType",
    "WorkerMessageType",
    # Head-to-worker messages
    "StartMessage",
    "GiveTaskMessage",
    "InboundMessage",
    "StopMessage",
    "HealthCheckMessage",
    # Worker-to-head messages
    "SignalMessage",
    "ReportMessage",
    "AskMessage",
    "SendFileMessage",
    "HealthReportMessage",
    # Discriminated unions
    "HeadMessage",
    "WorkerMessage",
    # Framing
    "PROTOCOL_VERSION",
    "encode",
    "decode_head",
    "decode_worker",
]
