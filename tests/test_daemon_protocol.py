"""Tests for daemon NDJSON protocol models."""

import json

import pytest
from pydantic import ValidationError

from vcompany.daemon.protocol import (
    PROTOCOL_VERSION,
    ErrorCode,
    ErrorData,
    ErrorResponse,
    Event,
    HelloParams,
    HelloResult,
    Request,
    Response,
)


class TestProtocolVersion:
    def test_protocol_version_is_one(self):
        assert PROTOCOL_VERSION == 1


class TestErrorCode:
    def test_parse_error(self):
        assert ErrorCode.PARSE_ERROR == -32700

    def test_invalid_request(self):
        assert ErrorCode.INVALID_REQUEST == -32600

    def test_method_not_found(self):
        assert ErrorCode.METHOD_NOT_FOUND == -32601

    def test_internal_error(self):
        assert ErrorCode.INTERNAL_ERROR == -32603


class TestRequest:
    def test_requires_id_and_method(self):
        req = Request(id="1", method="hello")
        assert req.jsonrpc == "2.0"
        assert req.id == "1"
        assert req.method == "hello"
        assert req.params == {}

    def test_params_default_empty(self):
        req = Request(id="1", method="test")
        assert req.params == {}

    def test_params_custom(self):
        req = Request(id="1", method="test", params={"key": "value"})
        assert req.params == {"key": "value"}

    def test_missing_method_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Request(id="1")  # type: ignore[call-arg]

    def test_missing_id_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Request(method="hello")  # type: ignore[call-arg]

    def test_to_line_returns_bytes_with_newline(self):
        req = Request(id="1", method="hello")
        line = req.to_line()
        assert isinstance(line, bytes)
        assert line.endswith(b"\n")
        parsed = json.loads(line)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == "1"
        assert parsed["method"] == "hello"

    def test_from_line_parses_bytes(self):
        req = Request(id="42", method="status", params={"verbose": True})
        line = req.to_line()
        restored = Request.from_line(line)
        assert restored.id == "42"
        assert restored.method == "status"
        assert restored.params == {"verbose": True}

    def test_from_line_strips_whitespace(self):
        raw = b'{"jsonrpc":"2.0","id":"1","method":"ping","params":{}}\n'
        req = Request.from_line(raw)
        assert req.method == "ping"


class TestResponse:
    def test_response_fields(self):
        resp = Response(id="1", result={"ok": True})
        assert resp.jsonrpc == "2.0"
        assert resp.id == "1"
        assert resp.result == {"ok": True}

    def test_to_line_produces_valid_ndjson(self):
        resp = Response(id="1", result={"data": 42})
        line = resp.to_line()
        assert isinstance(line, bytes)
        assert line.endswith(b"\n")
        parsed = json.loads(line)
        assert parsed["result"]["data"] == 42


class TestErrorResponse:
    def test_error_response_with_id(self):
        err = ErrorResponse(
            id="1",
            error=ErrorData(code=-32600, message="Invalid request"),
        )
        assert err.jsonrpc == "2.0"
        assert err.id == "1"
        assert err.error.code == -32600
        assert err.error.message == "Invalid request"

    def test_error_response_with_null_id(self):
        err = ErrorResponse(
            id=None,
            error=ErrorData(code=-32700, message="Parse error"),
        )
        assert err.id is None

    def test_to_line(self):
        err = ErrorResponse(
            id="5",
            error=ErrorData(code=-32603, message="Internal error"),
        )
        line = err.to_line()
        assert isinstance(line, bytes)
        assert line.endswith(b"\n")
        parsed = json.loads(line)
        assert parsed["error"]["code"] == -32603


class TestEvent:
    def test_event_has_method_and_params(self):
        evt = Event(method="agent.status", params={"agent": "pm"})
        assert evt.jsonrpc == "2.0"
        assert evt.method == "agent.status"
        assert evt.params == {"agent": "pm"}

    def test_event_to_line(self):
        evt = Event(method="heartbeat")
        line = evt.to_line()
        assert isinstance(line, bytes)
        parsed = json.loads(line)
        assert "id" not in parsed
        assert parsed["method"] == "heartbeat"


class TestHelloParams:
    def test_hello_params_has_version(self):
        hp = HelloParams(version=1)
        assert hp.version == 1


class TestHelloResult:
    def test_hello_result_has_version_and_daemon_version(self):
        hr = HelloResult(version=1, daemon_version="0.1.0")
        assert hr.version == 1
        assert hr.daemon_version == "0.1.0"
