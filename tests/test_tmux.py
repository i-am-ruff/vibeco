"""Tests for the tmux session wrapper.

These tests run against a real tmux server. Sessions are created with a
'test-vco-' prefix and cleaned up in teardown.
"""

import time

import pytest

from vcompany.tmux.session import TmuxManager


@pytest.fixture
def tmux_manager():
    """Create a TmuxManager and clean up all test sessions after."""
    manager = TmuxManager()
    created_sessions: list[str] = []
    yield manager, created_sessions
    # Teardown: kill all test sessions
    for name in created_sessions:
        manager.kill_session(name)


class TestCreateSession:
    def test_create_session(self, tmux_manager):
        manager, created = tmux_manager
        name = "test-vco-create"
        created.append(name)
        session = manager.create_session(name)
        assert session is not None
        assert name in manager.list_sessions()

    def test_create_session_replaces_existing(self, tmux_manager):
        manager, created = tmux_manager
        name = "test-vco-replace"
        created.append(name)
        session1 = manager.create_session(name)
        session2 = manager.create_session(name)
        # Should still have exactly one session with that name
        matches = [s for s in manager.list_sessions() if s == name]
        assert len(matches) == 1


class TestKillSession:
    def test_kill_session(self, tmux_manager):
        manager, created = tmux_manager
        name = "test-vco-kill"
        manager.create_session(name)
        result = manager.kill_session(name)
        assert result is True
        assert name not in manager.list_sessions()

    def test_kill_nonexistent_session(self, tmux_manager):
        manager, created = tmux_manager
        result = manager.kill_session("test-vco-nonexistent-xyz")
        assert result is False


class TestCreatePane:
    def test_create_pane_with_window(self, tmux_manager):
        manager, created = tmux_manager
        name = "test-vco-pane"
        created.append(name)
        session = manager.create_session(name)
        pane = manager.create_pane(session, window_name="worker")
        assert pane is not None


class TestSendCommand:
    def test_send_command(self, tmux_manager):
        manager, created = tmux_manager
        name = "test-vco-cmd"
        created.append(name)
        session = manager.create_session(name)
        pane = session.active_window.active_pane
        manager.send_command(pane, "echo hello-vco-test")
        # Give tmux a moment to process
        time.sleep(0.5)
        output = manager.get_output(pane)
        assert any("hello-vco-test" in line for line in output)


class TestIsAlive:
    def test_is_alive(self, tmux_manager):
        manager, created = tmux_manager
        name = "test-vco-alive"
        created.append(name)
        session = manager.create_session(name)
        pane = session.active_window.active_pane
        assert manager.is_alive(pane) is True


class TestListSessions:
    def test_list_sessions(self, tmux_manager):
        manager, created = tmux_manager
        name1 = "test-vco-list1"
        name2 = "test-vco-list2"
        created.extend([name1, name2])
        manager.create_session(name1)
        manager.create_session(name2)
        sessions = manager.list_sessions()
        assert name1 in sessions
        assert name2 in sessions
