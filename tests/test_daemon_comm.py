"""Tests for CommunicationPort protocol, payload models, and NoopCommunicationPort."""

from __future__ import annotations

import asyncio
import pathlib
from typing import runtime_checkable

import pytest


# --- Protocol definition tests ---


def test_communication_port_is_runtime_checkable():
    from vcompany.daemon.comm import CommunicationPort

    assert hasattr(CommunicationPort, "__protocol_attrs__") or hasattr(
        CommunicationPort, "__abstractmethods__"
    ) or getattr(CommunicationPort, "_is_runtime_protocol", False)


def test_communication_port_has_four_async_methods():
    from vcompany.daemon.comm import CommunicationPort

    expected = {"send_message", "send_embed", "create_thread", "subscribe_to_channel"}
    # Protocol members are callable
    for method_name in expected:
        assert hasattr(CommunicationPort, method_name), f"Missing method: {method_name}"


# --- Payload model tests ---


def test_send_message_payload():
    from vcompany.daemon.comm import SendMessagePayload

    p = SendMessagePayload(channel_id="123", content="hello")
    assert p.channel_id == "123"
    assert p.content == "hello"


def test_send_embed_payload_defaults():
    from vcompany.daemon.comm import SendEmbedPayload

    p = SendEmbedPayload(channel_id="123", title="Test")
    assert p.description == ""
    assert p.color is None
    assert p.fields == []


def test_send_embed_payload_with_fields():
    from vcompany.daemon.comm import EmbedField, SendEmbedPayload

    f = EmbedField(name="key", value="val")
    assert f.inline is False

    p = SendEmbedPayload(
        channel_id="c1",
        title="T",
        description="D",
        color=0xFF0000,
        fields=[f],
    )
    assert len(p.fields) == 1
    assert p.fields[0].name == "key"


def test_embed_field():
    from vcompany.daemon.comm import EmbedField

    f = EmbedField(name="n", value="v", inline=True)
    assert f.inline is True


def test_create_thread_payload():
    from vcompany.daemon.comm import CreateThreadPayload

    p = CreateThreadPayload(channel_id="c1", name="thread1")
    assert p.initial_message is None

    p2 = CreateThreadPayload(channel_id="c1", name="thread1", initial_message="hi")
    assert p2.initial_message == "hi"


def test_thread_result():
    from vcompany.daemon.comm import ThreadResult

    r = ThreadResult(thread_id="t1", name="thread1")
    assert r.thread_id == "t1"
    assert r.name == "thread1"


def test_subscribe_payload():
    from vcompany.daemon.comm import SubscribePayload

    p = SubscribePayload(channel_id="c1")
    assert p.channel_id == "c1"


# --- NoopCommunicationPort tests ---


def test_noop_satisfies_protocol():
    from vcompany.daemon.comm import CommunicationPort, NoopCommunicationPort

    noop = NoopCommunicationPort()
    assert isinstance(noop, CommunicationPort)


def test_noop_send_message_returns_true():
    from vcompany.daemon.comm import NoopCommunicationPort, SendMessagePayload

    noop = NoopCommunicationPort()
    result = asyncio.get_event_loop().run_until_complete(
        noop.send_message(SendMessagePayload(channel_id="c", content="x"))
    )
    assert result is True


def test_noop_create_thread_returns_thread_result():
    from vcompany.daemon.comm import (
        CreateThreadPayload,
        NoopCommunicationPort,
        ThreadResult,
    )

    noop = NoopCommunicationPort()
    result = asyncio.get_event_loop().run_until_complete(
        noop.create_thread(CreateThreadPayload(channel_id="c", name="t1"))
    )
    assert isinstance(result, ThreadResult)
    assert result.name == "t1"


# --- Daemon integration tests ---


def test_daemon_set_comm_port_accepts_noop():
    from vcompany.daemon.comm import NoopCommunicationPort
    from vcompany.daemon.daemon import Daemon

    daemon = Daemon(
        bot=object(),
        bot_token="test-token",
        socket_path=pathlib.Path("/tmp/test-comm.sock"),
        pid_path=pathlib.Path("/tmp/test-comm.pid"),
    )
    noop = NoopCommunicationPort()
    daemon.set_comm_port(noop)  # Should not raise


def test_daemon_comm_port_returns_registered():
    from vcompany.daemon.comm import NoopCommunicationPort
    from vcompany.daemon.daemon import Daemon

    daemon = Daemon(
        bot=object(),
        bot_token="test-token",
        socket_path=pathlib.Path("/tmp/test-comm.sock"),
        pid_path=pathlib.Path("/tmp/test-comm.pid"),
    )
    noop = NoopCommunicationPort()
    daemon.set_comm_port(noop)
    assert daemon.comm_port is noop


def test_daemon_comm_port_raises_when_not_registered():
    from vcompany.daemon.daemon import Daemon

    daemon = Daemon(
        bot=object(),
        bot_token="test-token",
        socket_path=pathlib.Path("/tmp/test-comm.sock"),
        pid_path=pathlib.Path("/tmp/test-comm.pid"),
    )
    with pytest.raises(RuntimeError, match="CommunicationPort not registered"):
        _ = daemon.comm_port


def test_daemon_set_comm_port_rejects_invalid():
    from vcompany.daemon.daemon import Daemon

    daemon = Daemon(
        bot=object(),
        bot_token="test-token",
        socket_path=pathlib.Path("/tmp/test-comm.sock"),
        pid_path=pathlib.Path("/tmp/test-comm.pid"),
    )
    with pytest.raises(TypeError, match="does not satisfy CommunicationPort"):
        daemon.set_comm_port(object())  # type: ignore[arg-type]


# --- COMM-02: No discord imports in daemon module ---


def test_no_discord_imports_in_daemon():
    """Scan all .py files in src/vcompany/daemon/ for discord imports."""
    daemon_dir = pathlib.Path("src/vcompany/daemon")
    violations = []
    for py_file in sorted(daemon_dir.glob("**/*.py")):
        content = py_file.read_text()
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if "import discord" in line or "from discord" in line:
                violations.append(f"{py_file}:{i}: {line.strip()}")
    assert violations == [], f"Discord imports found in daemon module:\n" + "\n".join(
        violations
    )
