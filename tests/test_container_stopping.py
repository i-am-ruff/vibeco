"""Tests for STOPPING FSM state across all three lifecycle state machines (LIFE-01)."""

import pytest
from statemachine.exceptions import TransitionNotAllowed

from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle
from vcompany.agent.gsd_lifecycle import GsdLifecycle
from vcompany.container.health import CompanyHealthTree, HealthNode, HealthReport
from vcompany.container.state_machine import ContainerLifecycle


def _make_health_node(agent_id: str = "agent-1") -> HealthNode:
    from datetime import datetime, timezone
    return HealthNode(report=HealthReport(
        agent_id=agent_id,
        state="running",
        uptime=1.0,
        last_heartbeat=datetime.now(timezone.utc),
        last_activity=datetime.now(timezone.utc),
    ))


class TestContainerLifecycleStopping:
    def test_begin_stop_from_running(self):
        fsm = ContainerLifecycle()
        fsm.start()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_begin_stop_from_sleeping(self):
        fsm = ContainerLifecycle()
        fsm.start()
        fsm.sleep()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_begin_stop_from_errored(self):
        fsm = ContainerLifecycle()
        fsm.start()
        fsm.error()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_begin_stop_from_blocked(self):
        fsm = ContainerLifecycle()
        fsm.start()
        fsm.block()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_finish_stop_transitions_to_stopped(self):
        fsm = ContainerLifecycle()
        fsm.start()
        fsm.begin_stop()
        fsm.finish_stop()
        assert fsm.current_state_value == "stopped"

    def test_cannot_transition_from_stopping_except_finish_stop(self):
        """Stopping is a gate -- only finish_stop is valid from stopping."""
        fsm = ContainerLifecycle()
        fsm.start()
        fsm.begin_stop()
        with pytest.raises(TransitionNotAllowed):
            fsm.error()
        with pytest.raises(TransitionNotAllowed):
            fsm.begin_stop()  # double begin_stop not allowed

    def test_no_bare_stop_transition(self):
        """Old stop() transition should no longer exist on ContainerLifecycle."""
        fsm = ContainerLifecycle()
        fsm.start()
        with pytest.raises((TransitionNotAllowed, AttributeError)):
            fsm.stop()


class TestGsdLifecycleStopping:
    def test_begin_stop_from_running(self):
        fsm = GsdLifecycle()
        fsm.start()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_begin_stop_from_sleeping(self):
        fsm = GsdLifecycle()
        fsm.start()
        fsm.sleep()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_begin_stop_from_errored(self):
        fsm = GsdLifecycle()
        fsm.start()
        fsm.error()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_begin_stop_from_blocked(self):
        fsm = GsdLifecycle()
        fsm.start()
        fsm.block()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_finish_stop_transitions_to_stopped(self):
        fsm = GsdLifecycle()
        fsm.start()
        fsm.begin_stop()
        fsm.finish_stop()
        assert fsm.current_state_value == "stopped"

    def test_no_bare_stop_transition(self):
        """Old stop() transition should no longer exist on GsdLifecycle."""
        fsm = GsdLifecycle()
        fsm.start()
        with pytest.raises((TransitionNotAllowed, AttributeError)):
            fsm.stop()


class TestEventDrivenLifecycleStopping:
    def test_begin_stop_from_running(self):
        fsm = EventDrivenLifecycle()
        fsm.start()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_begin_stop_from_sleeping(self):
        fsm = EventDrivenLifecycle()
        fsm.start()
        fsm.sleep()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_begin_stop_from_errored(self):
        fsm = EventDrivenLifecycle()
        fsm.start()
        fsm.error()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_begin_stop_from_blocked(self):
        fsm = EventDrivenLifecycle()
        fsm.start()
        fsm.block()
        fsm.begin_stop()
        assert fsm.current_state_value == "stopping"

    def test_finish_stop_transitions_to_stopped(self):
        fsm = EventDrivenLifecycle()
        fsm.start()
        fsm.begin_stop()
        fsm.finish_stop()
        assert fsm.current_state_value == "stopped"

    def test_no_bare_stop_transition(self):
        """Old stop() transition should no longer exist on EventDrivenLifecycle."""
        fsm = EventDrivenLifecycle()
        fsm.start()
        with pytest.raises((TransitionNotAllowed, AttributeError)):
            fsm.stop()


class TestCompanyHealthTreeCompanyAgents:
    def test_company_agents_defaults_to_empty_list(self):
        tree = CompanyHealthTree(supervisor_id="company", state="running")
        assert tree.company_agents == []

    def test_company_agents_accepts_health_nodes(self):
        node = _make_health_node("strategist-1")
        tree = CompanyHealthTree(
            supervisor_id="company",
            state="running",
            company_agents=[node],
        )
        assert len(tree.company_agents) == 1
        assert tree.company_agents[0].report.agent_id == "strategist-1"
