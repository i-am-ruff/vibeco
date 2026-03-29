"""Unix socket server for the vco daemon.

Handles client connections over Unix socket using NDJSON protocol.
Provides built-in methods: hello (handshake), ping, subscribe, and
supports registration of custom method handlers.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Callable

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

logger = logging.getLogger("vcompany.daemon.server")


class SocketServer:
    """NDJSON-over-Unix-socket server with client management and event broadcast."""

    def __init__(self, socket_path: Path) -> None:
        self._socket_path = socket_path
        self._server: asyncio.Server | None = None
        self._clients: dict[int, asyncio.StreamWriter] = {}
        self._subscriptions: dict[int, set[str]] = {}
        self._methods: dict[str, Callable] = {}
        self._handshake_done: set[int] = set()

    async def start(self) -> None:
        """Start listening on Unix socket. Set permissions to 0o600."""
        self._register_builtins()
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self._socket_path)
        )
        os.chmod(str(self._socket_path), 0o600)
        logger.info("Socket server listening on %s", self._socket_path)

    async def stop(self) -> None:
        """Close server and all client connections."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for writer in list(self._clients.values()):
            writer.close()
        self._clients.clear()
        self._subscriptions.clear()
        self._handshake_done.clear()

    def register_method(self, name: str, handler: Callable) -> None:
        """Register a method handler. Handler signature: async (params: dict) -> dict"""
        self._methods[name] = handler

    async def broadcast_event(self, event_type: str, params: dict) -> None:
        """Send event to all clients subscribed to event_type."""
        event = Event(method=f"event.{event_type}", params=params)
        line = event.to_line()
        dead_clients: list[int] = []
        for client_id, subscribed in self._subscriptions.items():
            if event_type in subscribed:
                writer = self._clients.get(client_id)
                if writer:
                    try:
                        writer.write(line)
                        await writer.drain()
                    except (ConnectionResetError, BrokenPipeError):
                        dead_clients.append(client_id)
        for cid in dead_clients:
            self._remove_client(cid)

    def _register_builtins(self) -> None:
        """Register hello, ping, subscribe built-in methods."""
        self._methods["hello"] = self._handle_hello
        self._methods["ping"] = self._handle_ping
        self._methods["subscribe"] = self._handle_subscribe

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Per-connection handler. Reads NDJSON lines, dispatches, responds."""
        client_id = id(writer)
        self._clients[client_id] = writer
        try:
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=300.0)
                if not line:
                    break
                try:
                    request = Request.from_line(line)
                except Exception:
                    err = ErrorResponse(
                        id=None,
                        error=ErrorData(
                            code=ErrorCode.PARSE_ERROR, message="Parse error"
                        ),
                    )
                    writer.write(err.to_line())
                    await writer.drain()
                    continue

                # Enforce hello-first handshake
                if (
                    client_id not in self._handshake_done
                    and request.method != "hello"
                ):
                    err = ErrorResponse(
                        id=request.id,
                        error=ErrorData(
                            code=ErrorCode.INVALID_REQUEST,
                            message="Must send hello first",
                        ),
                    )
                    writer.write(err.to_line())
                    await writer.drain()
                    continue

                response = await self._dispatch(client_id, request)
                if response is not None:
                    writer.write(response.to_line())
                    await writer.drain()
        except asyncio.TimeoutError:
            pass
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self._remove_client(client_id)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch(
        self, client_id: int, request: Request
    ) -> Response | ErrorResponse | None:
        """Route request to method handler, return response."""
        handler = self._methods.get(request.method)
        if not handler:
            return ErrorResponse(
                id=request.id,
                error=ErrorData(
                    code=ErrorCode.METHOD_NOT_FOUND,
                    message=f"Method not found: {request.method}",
                ),
            )
        try:
            if request.method in ("hello", "subscribe"):
                result = await handler(client_id, request.params)
            else:
                result = await handler(request.params)
            return Response(id=request.id, result=result)
        except Exception as exc:
            return ErrorResponse(
                id=request.id,
                error=ErrorData(
                    code=ErrorCode.INTERNAL_ERROR, message=str(exc)
                ),
            )

    async def _handle_hello(self, client_id: int, params: dict) -> dict:
        """Validate protocol version and mark client as handshake-complete."""
        hello = HelloParams.model_validate(params)
        if hello.version != PROTOCOL_VERSION:
            raise ValueError(
                f"Unsupported protocol version {hello.version}. "
                f"Supported: [{PROTOCOL_VERSION}]"
            )
        self._handshake_done.add(client_id)
        result = HelloResult(version=PROTOCOL_VERSION, daemon_version="0.1.0")
        return result.model_dump()

    async def _handle_ping(self, params: dict) -> dict:
        """Return pong."""
        return {"pong": True}

    async def _handle_subscribe(self, client_id: int, params: dict) -> dict:
        """Subscribe client to event types."""
        events = params.get("events", [])
        self._subscriptions.setdefault(client_id, set()).update(events)
        return {"subscribed": sorted(self._subscriptions[client_id])}

    def _remove_client(self, client_id: int) -> None:
        """Clean up client tracking state."""
        self._clients.pop(client_id, None)
        self._subscriptions.pop(client_id, None)
        self._handshake_done.discard(client_id)
