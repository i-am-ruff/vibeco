"""Tests for ContainerLifecycle FSM — CONT-01 and CONT-02."""

import pytest
from statemachine.exceptions import TransitionNotAllowed

from vcompany.container.state_machine import ContainerLifecycle


class TestValidTransitions:
    """CONT-01: All valid state transitions."""

    def test_initial_state_is_creating(self):
        sm = ContainerLifecycle()
        assert sm.current_state_value == "creating"

    def test_creating_to_running_via_start(self):
        sm = ContainerLifecycle()
        sm.start()
        assert sm.current_state_value == "running"

    def test_running_to_sleeping_via_sleep(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.sleep()
        assert sm.current_state_value == "sleeping"

    def test_sleeping_to_running_via_wake(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.sleep()
        sm.wake()
        assert sm.current_state_value == "running"

    def test_running_to_errored_via_error(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.error()
        assert sm.current_state_value == "errored"

    def test_creating_to_errored_via_error(self):
        sm = ContainerLifecycle()
        sm.error()
        assert sm.current_state_value == "errored"

    def test_sleeping_to_errored_via_error(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.sleep()
        sm.error()
        assert sm.current_state_value == "errored"

    def test_errored_to_running_via_recover(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.error()
        sm.recover()
        assert sm.current_state_value == "running"

    def test_running_to_stopped_via_begin_finish_stop(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.begin_stop()
        assert sm.current_state_value == "stopping"
        sm.finish_stop()
        assert sm.current_state_value == "stopped"

    def test_sleeping_to_stopped_via_begin_finish_stop(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.sleep()
        sm.begin_stop()
        sm.finish_stop()
        assert sm.current_state_value == "stopped"

    def test_errored_to_stopped_via_begin_finish_stop(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.error()
        sm.begin_stop()
        sm.finish_stop()
        assert sm.current_state_value == "stopped"

    def test_stopped_to_destroyed_via_destroy(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.begin_stop()
        sm.finish_stop()
        sm.destroy()
        assert sm.current_state_value == "destroyed"

    def test_errored_to_destroyed_via_destroy(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.error()
        sm.destroy()
        assert sm.current_state_value == "destroyed"


class TestInvalidTransitions:
    """CONT-02: Invalid transitions raise TransitionNotAllowed."""

    def test_stopped_to_running_raises(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.begin_stop()
        sm.finish_stop()
        with pytest.raises(TransitionNotAllowed):
            sm.start()

    def test_destroyed_to_any_raises(self):
        sm = ContainerLifecycle()
        sm.start()
        sm.begin_stop()
        sm.finish_stop()
        sm.destroy()
        with pytest.raises(TransitionNotAllowed):
            sm.start()

    def test_creating_to_sleeping_raises(self):
        sm = ContainerLifecycle()
        with pytest.raises(TransitionNotAllowed):
            sm.sleep()

    def test_creating_to_stopped_raises(self):
        sm = ContainerLifecycle()
        with pytest.raises(TransitionNotAllowed):
            sm.begin_stop()

    def test_running_to_creating_raises(self):
        sm = ContainerLifecycle()
        sm.start()
        # There is no "create" event, but verify no transition back to creating
        with pytest.raises(TransitionNotAllowed):
            sm.wake()  # wake is only valid from sleeping


class TestStringBasedDispatch:
    """String-based event dispatch for supervisor use."""

    def test_send_event_start_from_creating(self):
        sm = ContainerLifecycle()
        sm.send_event("start")
        assert sm.current_state_value == "running"


class TestAfterTransitionCallback:
    """Verify after_transition calls model._on_state_change if present."""

    def test_after_transition_calls_model_callback(self):

        class FakeContainer:
            called = False

            def _on_state_change(self):
                self.called = True

        container = FakeContainer()
        sm = ContainerLifecycle(model=container)
        sm.start()
        assert container.called
