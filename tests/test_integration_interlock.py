"""Tests for AgentMonitorState fields used by integration interlock.

Verifies:
- AgentMonitorState has integration_pending and checkin_sent fields

Note: MonitorLoop-based interlock, checkin, and all_agents_idle tests removed
during MIGR-03 (v1 MonitorLoop deleted). Supervision tree health system now
handles these concerns.
"""

from __future__ import annotations

import pytest

from vcompany.models.monitor_state import AgentMonitorState


# -- AgentMonitorState field tests --


class TestAgentMonitorStateFields:
    """Test that integration_pending and checkin_sent fields exist with defaults."""

    def test_integration_pending_default_false(self) -> None:
        state = AgentMonitorState(agent_id="agent-a")
        assert state.integration_pending is False

    def test_checkin_sent_default_false(self) -> None:
        state = AgentMonitorState(agent_id="agent-a")
        assert state.checkin_sent is False

    def test_integration_pending_settable(self) -> None:
        state = AgentMonitorState(agent_id="agent-a")
        state.integration_pending = True
        assert state.integration_pending is True

    def test_checkin_sent_settable(self) -> None:
        state = AgentMonitorState(agent_id="agent-a")
        state.checkin_sent = True
        assert state.checkin_sent is True
