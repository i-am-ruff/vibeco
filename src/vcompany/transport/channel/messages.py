"""Typed Pydantic v2 message models for the head-worker transport channel protocol.

Defines 10 message types: 5 head-to-worker, 5 worker-to-head.
Each direction has its own StrEnum and discriminated union type.
Protocol module depends only on pydantic + stdlib.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# --- Direction enums ---


class HeadMessageType(StrEnum):
    """Message types sent from head to worker."""

    START = "start"
    GIVE_TASK = "give-task"
    MESSAGE = "message"
    STOP = "stop"
    HEALTH_CHECK = "health-check"


class WorkerMessageType(StrEnum):
    """Message types sent from worker to head."""

    SIGNAL = "signal"
    REPORT = "report"
    ASK = "ask"
    SEND_FILE = "send-file"
    HEALTH_REPORT = "health-report"


# --- Head-to-worker messages ---


class StartMessage(BaseModel):
    """Head tells worker to initialize with given config."""

    type: Literal[HeadMessageType.START] = HeadMessageType.START
    agent_id: str
    config: dict = Field(default_factory=dict)


class GiveTaskMessage(BaseModel):
    """Head assigns a task to the worker."""

    type: Literal[HeadMessageType.GIVE_TASK] = HeadMessageType.GIVE_TASK
    task_id: str
    description: str
    context: dict = Field(default_factory=dict)


class InboundMessage(BaseModel):
    """Head forwards an inbound message (from Discord etc.) to the worker."""

    type: Literal[HeadMessageType.MESSAGE] = HeadMessageType.MESSAGE
    sender: str
    channel: str
    content: str
    message_id: str | None = None


class StopMessage(BaseModel):
    """Head tells worker to shut down."""

    type: Literal[HeadMessageType.STOP] = HeadMessageType.STOP
    reason: str = ""
    graceful: bool = True


class HealthCheckMessage(BaseModel):
    """Head requests a health report from the worker."""

    type: Literal[HeadMessageType.HEALTH_CHECK] = HeadMessageType.HEALTH_CHECK


# --- Worker-to-head messages ---


class SignalMessage(BaseModel):
    """Worker signals a state change or event to head."""

    type: Literal[WorkerMessageType.SIGNAL] = WorkerMessageType.SIGNAL
    signal: str
    detail: str = ""


class ReportMessage(BaseModel):
    """Worker sends a report/output to a channel via head."""

    type: Literal[WorkerMessageType.REPORT] = WorkerMessageType.REPORT
    channel: str
    content: str
    task_id: str | None = None


class AskMessage(BaseModel):
    """Worker asks a question to a channel via head."""

    type: Literal[WorkerMessageType.ASK] = WorkerMessageType.ASK
    channel: str
    question: str
    context: dict = Field(default_factory=dict)


class SendFileMessage(BaseModel):
    """Worker sends a file to a channel via head."""

    type: Literal[WorkerMessageType.SEND_FILE] = WorkerMessageType.SEND_FILE
    channel: str
    filename: str
    content_b64: str
    description: str = ""


class HealthReportMessage(BaseModel):
    """Worker responds to a health check with its status."""

    type: Literal[WorkerMessageType.HEALTH_REPORT] = WorkerMessageType.HEALTH_REPORT
    status: str
    agent_state: str = ""
    uptime_seconds: float = 0.0
    detail: dict = Field(default_factory=dict)


# --- Discriminated unions ---

HeadMessage = Annotated[
    Union[StartMessage, GiveTaskMessage, InboundMessage, StopMessage, HealthCheckMessage],
    Field(discriminator="type"),
]

WorkerMessage = Annotated[
    Union[SignalMessage, ReportMessage, AskMessage, SendFileMessage, HealthReportMessage],
    Field(discriminator="type"),
]
