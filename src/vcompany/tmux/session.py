"""tmux session wrapper abstracting libtmux.

This is the ONLY module in the codebase that imports libtmux.
All tmux operations go through TmuxManager. If libtmux's pre-1.0 API
changes, only this file needs updating.
"""

import logging
import os

import libtmux

logger = logging.getLogger("vcompany.tmux")


class TmuxManager:
    """Wrapper around libtmux. Only module that imports libtmux."""

    def __init__(self) -> None:
        self._server = libtmux.Server()

    def get_session(self, name: str) -> libtmux.Session | None:
        """Get an existing tmux session by name, or None if not found."""
        try:
            return self._server.sessions.get(session_name=name)
        except Exception:
            return None

    def get_or_create_session(self, name: str) -> libtmux.Session:
        """Get existing session or create a new one (does not kill existing)."""
        existing = self.get_session(name)
        if existing:
            logger.info("Found existing tmux session: %s", name)
            return existing
        session = self._server.new_session(session_name=name, detach=True)
        logger.info("Created tmux session: %s", name)
        return session

    def create_session(self, name: str) -> libtmux.Session:
        """Create a new detached tmux session. Kills existing session with same name first."""
        self.kill_session(name)
        session = self._server.new_session(session_name=name, detach=True)
        logger.info("Created tmux session: %s", name)
        return session

    def kill_session(self, name: str) -> bool:
        """Kill a tmux session by name. Returns True if killed, False if not found."""
        try:
            session = self._server.sessions.get(session_name=name)
            if session:
                session.kill()
                logger.info("Killed tmux session: %s", name)
                return True
        except Exception:
            pass
        return False

    def create_pane(
        self, session: libtmux.Session, window_name: str | None = None
    ) -> libtmux.Pane:
        """Create a new pane. If window_name given, creates new window first."""
        if window_name:
            window = session.new_window(window_name=window_name)
        else:
            window = session.active_window
        return window.active_pane

    def send_command(self, pane: libtmux.Pane, command: str) -> None:
        """Send a command string to a tmux pane."""
        pane.send_keys(command)

    def is_alive(self, pane: libtmux.Pane) -> bool:
        """Check if the pane's shell process is still running via PID check."""
        try:
            pane_pid = pane.pane_pid
            if pane_pid:
                os.kill(int(pane_pid), 0)
                return True
        except (ProcessLookupError, OSError, TypeError, ValueError):
            pass
        return False

    def get_output(self, pane: libtmux.Pane, lines: int = 50) -> list[str]:
        """Capture recent output lines from a pane."""
        return pane.capture_pane()

    def kill_pane(self, pane: libtmux.Pane) -> None:
        """Kill a specific pane."""
        pane.kill()

    def list_sessions(self) -> list[str]:
        """List all tmux session names."""
        return [s.session_name for s in self._server.sessions]
