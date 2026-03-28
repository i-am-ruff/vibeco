"""Tests for BLOCKED FSM state across all three lifecycle state machines (ARCH-03)."""

import pytest
from statemachine.exceptions import TransitionNotAllowed
from statemachine.orderedset import OrderedSet

from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle
from vcompany.agent.gsd_lifecycle import GsdLifecycle
from vcompany.container.health import HealthReport
from vcompany.container.state_machine import ContainerLifecycle


class TestContainerLifecycleBlocked:
    def test_block_transitions_running_to_blocked(self):
        fsm = ContainerLifecycle()
        fsm.start()
        fsm.block()
        assert fsm.current_state_value == "blocked"

    def test_unblock_restores_running(self):
        fsm = ContainerLifecycle()
        fsm.start()
        fsm.block()
        fsm.unblock()
        assert fsm.current_state_value == "running"

    def test_error_from_blocked(self):
        fsm = ContainerLifecycle()
        fsm.start()
        fsm.block()
        fsm.error()
        assert fsm.current_state_value == "errored"

    def test_begin_stop_from_blocked(self):
        fsm = ContainerLifecycle()
        fsm.start()
        fsm.block()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_cannot_block_from_creating(self):
        fsm = ContainerLifecycle()
        with pytest.raises(TransitionNotAllowed):
            fsm.block()

    def test_cannot_block_from_sleeping(self):
        fsm = ContainerLifecycle()
        fsm.start()
        fsm.sleep()
        with pytest.raises(TransitionNotAllowed):
            fsm.block()


class TestGsdLifecycleBlocked:
    def test_block_transitions_running_to_blocked(self):
        fsm = GsdLifecycle()
        fsm.start()
        fsm.block()
        assert fsm.current_state_value == "blocked"

    def test_unblock_restores_running_history(self):
        """unblock() on GsdLifecycle restores the inner phase via HistoryState."""
        fsm = GsdLifecycle()
        fsm.start()
        fsm.start_discuss()
        assert fsm.configuration_values == OrderedSet({"running", "discuss"})
        fsm.block()
        assert fsm.current_state_value == "blocked"
        fsm.unblock()
        # HistoryState should restore 'discuss' inner state
        assert fsm.configuration_values == OrderedSet({"running", "discuss"})

    def test_error_from_blocked(self):
        fsm = GsdLifecycle()
        fsm.start()
        fsm.block()
        fsm.error()
        assert fsm.current_state_value == "errored"

    def test_begin_stop_from_blocked(self):
        fsm = GsdLifecycle()
        fsm.start()
        fsm.block()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"


class TestEventDrivenLifecycleBlocked:
    def test_block_transitions_running_to_blocked(self):
        fsm = EventDrivenLifecycle()
        fsm.start()
        fsm.block()
        assert fsm.current_state_value == "blocked"

    def test_unblock_restores_inner_sub_state(self):
        """unblock() restores listening/processing inner sub-state via HistoryState."""
        fsm = EventDrivenLifecycle()
        fsm.start()
        fsm.start_processing()
        assert fsm.configuration_values == OrderedSet({"running", "processing"})
        fsm.block()
        assert fsm.current_state_value == "blocked"
        fsm.unblock()
        # HistoryState should restore 'processing' inner state
        assert fsm.configuration_values == OrderedSet({"running", "processing"})

    def test_error_from_blocked(self):
        fsm = EventDrivenLifecycle()
        fsm.start()
        fsm.block()
        fsm.error()
        assert fsm.current_state_value == "errored"

    def test_begin_stop_from_blocked(self):
        fsm = EventDrivenLifecycle()
        fsm.start()
        fsm.block()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"


class TestHealthReportBlockedReason:
    def test_blocked_reason_defaults_to_none(self):
        from datetime import datetime, timezone
        report = HealthReport(
            agent_id="agent-1",
            state="running",
            uptime=10.0,
            last_heartbeat=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
        )
        assert report.blocked_reason is None

    def test_blocked_reason_set_when_blocked(self):
        from datetime import datetime, timezone
        report = HealthReport(
            agent_id="agent-1",
            state="blocked",
            uptime=10.0,
            last_heartbeat=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
            blocked_reason="Waiting for plan approval",
        )
        assert report.blocked_reason == "Waiting for plan approval"
