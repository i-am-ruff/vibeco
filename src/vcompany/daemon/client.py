"""Synchronous NDJSON client for CLI -> daemon communication.

Uses blocking Unix socket I/O so CLI commands can be simple synchronous code.
The daemon's async SocketServer handles the other end.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

from vcompany.daemon.protocol import PROTOCOL_VERSION, Request


class DaemonClient:
    """Synchronous NDJSON client for CLI -> daemon communication."""

    def __init__(self, socket_path: Path, timeout: float = 30.0) -> None:
        self._socket_path = socket_path
        self._timeout = timeout
        self._sock: socket.socket | None = None
        self._request_counter = 0

    def connect(self) -> None:
        """Connect and perform hello handshake."""
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(self._timeout)
        self._sock.connect(str(self._socket_path))
        # Hello handshake
        hello = Request(id="hello", method="hello", params={"version": PROTOCOL_VERSION})
        self._send_raw(hello.to_line())
        resp = self._recv_line()
        parsed = json.loads(resp)
        if "error" in parsed:
            raise RuntimeError(f"Handshake failed: {parsed['error']['message']}")

    def call(self, method: str, params: dict | None = None) -> dict:
        """Send request, return result dict. Raises on error response."""
        self._request_counter += 1
        req = Request(id=f"req-{self._request_counter}", method=method, params=params or {})
        self._send_raw(req.to_line())
        resp_line = self._recv_line()
        parsed = json.loads(resp_line)
        if "error" in parsed:
            raise RuntimeError(f"RPC error: {parsed['error']['message']}")
        return parsed.get("result", {})

    def close(self) -> None:
        """Close the socket connection."""
        if self._sock:
            self._sock.close()
            self._sock = None

    def _send_raw(self, data: bytes) -> None:
        assert self._sock is not None
        self._sock.sendall(data)

    def _recv_line(self) -> bytes:
        assert self._sock is not None
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("Server closed connection")
            buf += chunk
        return buf

    def __enter__(self) -> DaemonClient:
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
