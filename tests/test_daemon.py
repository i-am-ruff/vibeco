"""Tests for the Daemon class lifecycle, PID management, and signal handling.

Uses tmp_path for PID and socket paths. Mocks VcoBot to avoid discord.py import.
"""

from __future__ import annotations

import asyncio
import os
import signal

import pytest

from vcompany.daemon.daemon import Daemon


class MockBot:
    """Mock bot with async start() and close() for testing."""

    def __init__(self):
        self._stop_event = asyncio.Event()
        self.start_called_with: str | None = None
        self.close_called = False
        self._close_order: list[str] | None = None
        self._daemon: Daemon | None = None  # Set by test to signal bot readiness

    async def start(self, token: str) -> None:
        self.start_called_with = token
        # Simulate on_ready by signalling bot readiness to the daemon
        if self._daemon is not None:
            self._daemon._bot_ready_event.set()
        await self._stop_event.wait()

    async def close(self) -> None:
        self.close_called = True
        if self._close_order is not None:
            self._close_order.append("bot.close")
        self._stop_event.set()


def test_pid_lifecycle(tmp_path):
    """Daemon writes PID file on start and removes it after shutdown."""

    async def _test():
        pid_path = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"
        bot = MockBot()
        daemon = Daemon(bot, "test-token", socket_path=sock_path, pid_path=pid_path)
        bot._daemon = daemon

        # Start daemon in background, trigger shutdown after PID is written
        async def _trigger_shutdown():
            # Wait until PID file exists
            for _ in range(100):
                if pid_path.exists():
                    break
                await asyncio.sleep(0.01)
            assert pid_path.exists(), "PID file should exist while running"
            pid_text = pid_path.read_text().strip()
            assert pid_text == str(os.getpid()), "PID should match current process"
            daemon._shutdown_event.set()

        task = asyncio.create_task(daemon._run())
        trigger = asyncio.create_task(_trigger_shutdown())
        await asyncio.gather(task, trigger)

        assert not pid_path.exists(), "PID file should be removed after shutdown"

    asyncio.run(_test())


def test_already_running_refuses(tmp_path):
    """Daemon refuses to start if another instance is running (current PID)."""
    pid_path = tmp_path / "test.pid"
    sock_path = tmp_path / "test.sock"

    # Write current process PID -- it IS running
    pid_path.write_text(str(os.getpid()))

    bot = MockBot()
    daemon = Daemon(bot, "test-token", socket_path=sock_path, pid_path=pid_path)

    with pytest.raises(SystemExit, match="already running"):
        daemon._check_already_running()


def test_stale_pid_cleanup(tmp_path):
    """Stale PID file (non-existent process) is cleaned up without raising."""
    pid_path = tmp_path / "test.pid"
    sock_path = tmp_path / "test.sock"

    # Write a PID that definitely doesn't exist
    pid_path.write_text("99999999")
    sock_path.write_text("fake-socket")

    bot = MockBot()
    daemon = Daemon(bot, "test-token", socket_path=sock_path, pid_path=pid_path)

    # Should not raise -- just clean up
    daemon._check_already_running()

    assert not pid_path.exists(), "Stale PID file should be removed"
    assert not sock_path.exists(), "Stale socket file should be removed"


def test_signal_shutdown(tmp_path):
    """SIGTERM causes daemon to shut down cleanly."""

    async def _test():
        pid_path = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"
        bot = MockBot()
        daemon = Daemon(bot, "test-token", socket_path=sock_path, pid_path=pid_path)
        bot._daemon = daemon

        async def _send_sigterm():
            # Wait for daemon to be running
            for _ in range(100):
                if pid_path.exists():
                    break
                await asyncio.sleep(0.01)
            # Send SIGTERM to self
            os.kill(os.getpid(), signal.SIGTERM)

        task = asyncio.create_task(daemon._run())
        trigger = asyncio.create_task(_send_sigterm())
        await asyncio.gather(task, trigger)

        assert daemon._shutdown_event.is_set(), "Shutdown event should be set"
        assert not pid_path.exists(), "PID file should be cleaned up"

    asyncio.run(_test())


def test_bot_costart(tmp_path):
    """Bot.start(token) is called with the provided token."""

    async def _test():
        pid_path = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"
        bot = MockBot()
        daemon = Daemon(bot, "my-secret-token", socket_path=sock_path, pid_path=pid_path)
        bot._daemon = daemon

        async def _trigger_shutdown():
            for _ in range(100):
                if bot.start_called_with is not None:
                    break
                await asyncio.sleep(0.01)
            daemon._shutdown_event.set()

        task = asyncio.create_task(daemon._run())
        trigger = asyncio.create_task(_trigger_shutdown())
        await asyncio.gather(task, trigger)

        assert bot.start_called_with == "my-secret-token"

    asyncio.run(_test())


def test_shutdown_order(tmp_path):
    """Server.stop() is called before bot.close() during shutdown."""

    async def _test():
        pid_path = tmp_path / "test.pid"
        sock_path = tmp_path / "test.sock"
        order: list[str] = []
        bot = MockBot()
        bot._close_order = order
        daemon = Daemon(bot, "test-token", socket_path=sock_path, pid_path=pid_path)
        bot._daemon = daemon

        async def _trigger_shutdown():
            for _ in range(100):
                if pid_path.exists():
                    break
                await asyncio.sleep(0.01)
            # Patch server.stop to record order
            original_stop = daemon._server.stop

            async def _patched_stop():
                order.append("server.stop")
                await original_stop()

            daemon._server.stop = _patched_stop
            daemon._shutdown_event.set()

        task = asyncio.create_task(daemon._run())
        trigger = asyncio.create_task(_trigger_shutdown())
        await asyncio.gather(task, trigger)

        assert order == ["server.stop", "bot.close"], f"Expected server before bot, got {order}"

    asyncio.run(_test())
