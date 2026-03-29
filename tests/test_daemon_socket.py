"""Tests for the Unix socket server (SocketServer).

Uses tmp_path for socket path, asyncio.open_unix_connection for client.
Wraps async tests with asyncio.run() for compatibility with older pytest-asyncio.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest

from vcompany.daemon.protocol import PROTOCOL_VERSION, Request
from vcompany.daemon.server import SocketServer


def _make_request(method: str, params: dict | None = None) -> bytes:
    """Build a Request and return its NDJSON line bytes."""
    req = Request(id=str(uuid.uuid4()), method=method, params=params or {})
    return req.to_line()


def _hello_line() -> bytes:
    """Build a hello request line."""
    return _make_request("hello", {"version": PROTOCOL_VERSION})


async def _connect(socket_path):
    """Open a unix connection and return (reader, writer)."""
    return await asyncio.open_unix_connection(str(socket_path))


async def _send_recv(writer, reader, line: bytes) -> dict:
    """Send a line and read+parse the response."""
    writer.write(line)
    await writer.drain()
    resp_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
    return json.loads(resp_line)


async def _handshake(writer, reader) -> dict:
    """Perform hello handshake, return response dict."""
    return await _send_recv(writer, reader, _hello_line())


def test_socket_accepts(tmp_path):
    """Server accepts a client connection."""

    async def _test():
        sock = tmp_path / "test.sock"
        server = SocketServer(sock)
        await server.start()
        try:
            reader, writer = await _connect(sock)
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()

    asyncio.run(_test())


def test_hello_handshake(tmp_path):
    """Hello with correct version returns success with version and daemon_version."""

    async def _test():
        sock = tmp_path / "test.sock"
        server = SocketServer(sock)
        await server.start()
        try:
            reader, writer = await _connect(sock)
            resp = await _handshake(writer, reader)
            assert resp["jsonrpc"] == "2.0"
            assert "result" in resp
            assert resp["result"]["version"] == PROTOCOL_VERSION
            assert resp["result"]["daemon_version"] == "0.1.0"
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()

    asyncio.run(_test())


def test_hello_wrong_version(tmp_path):
    """Hello with wrong version returns error."""

    async def _test():
        sock = tmp_path / "test.sock"
        server = SocketServer(sock)
        await server.start()
        try:
            reader, writer = await _connect(sock)
            line = _make_request("hello", {"version": 99})
            resp = await _send_recv(writer, reader, line)
            assert "error" in resp
            assert "Unsupported protocol version" in resp["error"]["message"]
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()

    asyncio.run(_test())


def test_must_hello_first(tmp_path):
    """Sending ping before hello returns 'Must send hello first' error."""

    async def _test():
        sock = tmp_path / "test.sock"
        server = SocketServer(sock)
        await server.start()
        try:
            reader, writer = await _connect(sock)
            line = _make_request("ping")
            resp = await _send_recv(writer, reader, line)
            assert "error" in resp
            assert "Must send hello first" in resp["error"]["message"]
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()

    asyncio.run(_test())


def test_ndjson_roundtrip(tmp_path):
    """Hello then ping returns pong result."""

    async def _test():
        sock = tmp_path / "test.sock"
        server = SocketServer(sock)
        await server.start()
        try:
            reader, writer = await _connect(sock)
            await _handshake(writer, reader)
            ping_line = _make_request("ping")
            resp = await _send_recv(writer, reader, ping_line)
            assert resp["result"] == {"pong": True}
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()

    asyncio.run(_test())


def test_method_not_found(tmp_path):
    """Unknown method after hello returns METHOD_NOT_FOUND error."""

    async def _test():
        sock = tmp_path / "test.sock"
        server = SocketServer(sock)
        await server.start()
        try:
            reader, writer = await _connect(sock)
            await _handshake(writer, reader)
            line = _make_request("nonexistent_method")
            resp = await _send_recv(writer, reader, line)
            assert "error" in resp
            assert resp["error"]["code"] == -32601
            assert "Method not found" in resp["error"]["message"]
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()

    asyncio.run(_test())


def test_parse_error(tmp_path):
    """Malformed JSON line returns PARSE_ERROR."""

    async def _test():
        sock = tmp_path / "test.sock"
        server = SocketServer(sock)
        await server.start()
        try:
            reader, writer = await _connect(sock)
            writer.write(b"this is not json\n")
            await writer.drain()
            resp_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            resp = json.loads(resp_line)
            assert "error" in resp
            assert resp["error"]["code"] == -32700
            assert resp["id"] is None
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()

    asyncio.run(_test())


def test_event_subscription(tmp_path):
    """Subscribed client receives events; unsubscribed client does not."""

    async def _test():
        sock = tmp_path / "test.sock"
        server = SocketServer(sock)
        await server.start()
        try:
            # Client A: subscribe to health_change
            reader_a, writer_a = await _connect(sock)
            await _handshake(writer_a, reader_a)
            sub_line = _make_request("subscribe", {"events": ["health_change"]})
            sub_resp = await _send_recv(writer_a, reader_a, sub_line)
            assert "health_change" in sub_resp["result"]["subscribed"]

            # Client B: connect and handshake but do NOT subscribe
            reader_b, writer_b = await _connect(sock)
            await _handshake(writer_b, reader_b)

            # Broadcast health_change event
            await server.broadcast_event("health_change", {"status": "degraded"})

            # Client A should receive the event
            event_line = await asyncio.wait_for(reader_a.readline(), timeout=5.0)
            event = json.loads(event_line)
            assert event["method"] == "event.health_change"
            assert event["params"]["status"] == "degraded"

            # Client B should NOT receive anything (use short timeout)
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(reader_b.readline(), timeout=0.2)

            writer_a.close()
            await writer_a.wait_closed()
            writer_b.close()
            await writer_b.wait_closed()
        finally:
            await server.stop()

    asyncio.run(_test())


def test_socket_permissions(tmp_path):
    """Socket file has 0o600 permissions after server starts."""

    async def _test():
        sock = tmp_path / "test.sock"
        server = SocketServer(sock)
        await server.start()
        try:
            mode = os.stat(str(sock)).st_mode & 0o777
            assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"
        finally:
            await server.stop()

    asyncio.run(_test())
