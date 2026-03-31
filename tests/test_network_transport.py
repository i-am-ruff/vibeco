"""Tests for NetworkTransport -- TCP-based ChannelTransport implementation.

Tests use asyncio.start_server on localhost with OS-assigned ports (port 0)
for isolation. Each test starts its own server and cleans up after.
"""

from __future__ import annotations

import asyncio

import pytest

from vcompany.transport.channel_transport import ChannelTransport
from vcompany.transport.network import NetworkTransport


@pytest.fixture
async def tcp_server():
    """Start a local TCP server on an OS-assigned port. Yields (host, port, received_data).

    received_data is a list that accumulates bytes received from clients.
    """
    received: list[bytes] = []

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            received.append(data)
            # Echo back for round-trip tests
            writer.write(data)
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    host, port = addr[0], addr[1]

    yield host, port, received

    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_network_transport_satisfies_protocol():
    """NetworkTransport must be a runtime instance of ChannelTransport protocol."""
    transport = NetworkTransport()
    assert isinstance(transport, ChannelTransport)


@pytest.mark.asyncio
async def test_spawn_connects_and_returns_streams(tcp_server):
    """spawn() should connect to a TCP server and return (StreamReader, StreamWriter)."""
    host, port, _ = tcp_server
    transport = NetworkTransport(host=host, port=port)
    reader, writer = await transport.spawn("agent-1", config={})
    assert isinstance(reader, asyncio.StreamReader)
    assert isinstance(writer, asyncio.StreamWriter)
    writer.close()
    await writer.wait_closed()


@pytest.mark.asyncio
async def test_connect_returns_streams(tcp_server):
    """connect() should connect to a TCP server and return (StreamReader, StreamWriter)."""
    host, port, _ = tcp_server
    transport = NetworkTransport(host=host, port=port)
    reader, writer = await transport.connect("agent-2")
    assert isinstance(reader, asyncio.StreamReader)
    assert isinstance(writer, asyncio.StreamWriter)
    writer.close()
    await writer.wait_closed()


@pytest.mark.asyncio
async def test_terminate_closes_connection(tcp_server):
    """terminate() should close the connection and remove from internal tracking."""
    host, port, _ = tcp_server
    transport = NetworkTransport(host=host, port=port)
    await transport.spawn("agent-3", config={})
    assert "agent-3" in transport._connections
    await transport.terminate("agent-3")
    assert "agent-3" not in transport._connections


@pytest.mark.asyncio
async def test_transport_type_returns_network():
    """transport_type property should return 'network'."""
    transport = NetworkTransport()
    assert transport.transport_type == "network"


@pytest.mark.asyncio
async def test_round_trip_data(tcp_server):
    """Data sent through writer should be received by the server and echoed back."""
    host, port, received = tcp_server
    transport = NetworkTransport(host=host, port=port)
    reader, writer = await transport.spawn("agent-4", config={})

    test_data = b'{"type":"report","content":"hello"}\n'
    writer.write(test_data)
    await writer.drain()

    # Read the echo back
    echoed = await asyncio.wait_for(reader.read(4096), timeout=2.0)
    assert echoed == test_data

    # Server also received it
    assert len(received) >= 1
    assert test_data in b"".join(received)

    writer.close()
    await writer.wait_closed()


@pytest.mark.asyncio
async def test_connection_refused_on_bad_port():
    """Connecting to a non-existent server should raise ConnectionRefusedError."""
    transport = NetworkTransport(host="127.0.0.1", port=1)  # Port 1 is unlikely to be open
    with pytest.raises((ConnectionRefusedError, OSError)):
        await transport.spawn("agent-bad", config={})
