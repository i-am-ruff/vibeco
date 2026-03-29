"""NDJSON protocol models for the vco daemon Unix socket API.

Follows JSON-RPC 2.0 structure: request/response with id, notifications without.
Each message is a single JSON line terminated by newline (NDJSON).
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

PROTOCOL_VERSION: int = 1


class ErrorCode(IntEnum):
    """Standard JSON-RPC 2.0 error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INTERNAL_ERROR = -32603


class Request(BaseModel):
    """Client-to-daemon request."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

    def to_line(self) -> bytes:
        return self.model_dump_json().encode() + b"\n"

    @classmethod
    def from_line(cls, line: bytes) -> Request:
        return cls.model_validate_json(line.strip())


class ErrorData(BaseModel):
    """Error payload inside an ErrorResponse."""

    code: int
    message: str


class Response(BaseModel):
    """Daemon-to-client success response."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: str
    result: dict[str, Any]

    def to_line(self) -> bytes:
        return self.model_dump_json().encode() + b"\n"


class ErrorResponse(BaseModel):
    """Daemon-to-client error response."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: str | None
    error: ErrorData

    def to_line(self) -> bytes:
        return self.model_dump_json().encode() + b"\n"


class Event(BaseModel):
    """Server-pushed notification (no id, not a response to a request)."""

    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

    def to_line(self) -> bytes:
        return self.model_dump_json().encode() + b"\n"


class HelloParams(BaseModel):
    """Parameters for the hello handshake request."""

    version: int


class HelloResult(BaseModel):
    """Result of the hello handshake response."""

    version: int
    daemon_version: str
