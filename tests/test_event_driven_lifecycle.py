"""Tests for EventDrivenLifecycle FSM — compound running state with listening/processing."""

from __future__ import annotations

import pytest
from statemachine.exceptions import TransitionNotAllowed
from statemachine.orderedset import OrderedSet


class TestInitialState:
    """Test 1: Starts in creating."""

    def test_initial_state_is_creating(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        assert sm.current_state_value == "creating"


class TestStartTransition:
    """Test 1 continued: start transitions to running.listening."""

    def test_start_transitions_to_running_listening(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        assert sm.configuration_values == OrderedSet({"running", "listening"})


class TestStartProcessing:
    """Test 2: start_processing transitions from listening to processing."""

    def test_start_processing(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.start_processing()
        assert sm.configuration_values == OrderedSet({"running", "processing"})


class TestDoneProcessing:
    """Test 3: done_processing transitions from processing back to listening."""

    def test_done_processing_returns_to_listening(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.start_processing()
        sm.done_processing()
        assert sm.configuration_values == OrderedSet({"running", "listening"})


class TestSleepFromRunning:
    """Test 4: sleep from running goes to sleeping."""

    def test_sleep_from_listening(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.sleep()
        assert sm.current_state_value == "sleeping"

    def test_sleep_from_processing(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.start_processing()
        sm.sleep()
        assert sm.current_state_value == "sleeping"


class TestWakeHistoryState:
    """Test 5: wake from sleeping goes to running via HistoryState."""

    def test_wake_preserves_listening(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        # Was in listening
        sm.sleep()
        sm.wake()
        assert sm.configuration_values == OrderedSet({"running", "listening"})

    def test_wake_preserves_processing(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.start_processing()
        # Was in processing
        sm.sleep()
        sm.wake()
        assert sm.configuration_values == OrderedSet({"running", "processing"})


class TestErrorAndRecover:
    """Test 6: error from running goes to errored; recover via HistoryState."""

    def test_error_from_running(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.error()
        assert sm.current_state_value == "errored"

    def test_recover_preserves_listening(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.error()
        sm.recover()
        assert sm.configuration_values == OrderedSet({"running", "listening"})

    def test_recover_preserves_processing(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.start_processing()
        sm.error()
        sm.recover()
        assert sm.configuration_values == OrderedSet({"running", "processing"})

    def test_error_from_creating(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.error()
        assert sm.current_state_value == "errored"

    def test_error_from_sleeping(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.sleep()
        sm.error()
        assert sm.current_state_value == "errored"


class TestStopAndDestroy:
    """Test 7: stop and destroy transitions work (two-phase: begin_stop/finish_stop)."""

    def test_stop_from_running(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.begin_stop()
        sm.finish_stop()
        assert sm.current_state_value == "stopped"

    def test_stop_from_sleeping(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.sleep()
        sm.begin_stop()
        sm.finish_stop()
        assert sm.current_state_value == "stopped"

    def test_stop_from_errored(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.error()
        sm.begin_stop()
        sm.finish_stop()
        assert sm.current_state_value == "stopped"

    def test_destroy_from_stopped(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.start()
        sm.begin_stop()
        sm.finish_stop()
        sm.destroy()
        assert sm.current_state_value == "destroyed"

    def test_destroy_from_errored(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        sm.error()
        sm.destroy()
        assert sm.current_state_value == "destroyed"


class TestAfterTransitionCallback:
    """Test 8: after_transition calls model._on_state_change."""

    def test_after_transition_calls_model(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        class FakeModel:
            def __init__(self) -> None:
                self.changes: list[str] = []
                self._fsm_state: object = None

            def _on_state_change(self) -> None:
                self.changes.append("changed")

        model = FakeModel()
        sm = EventDrivenLifecycle(model=model, state_field="_fsm_state")
        sm.start()
        assert len(model.changes) >= 1

        sm.start_processing()
        assert len(model.changes) >= 2

        sm.done_processing()
        assert len(model.changes) >= 3

    def test_no_callback_without_model(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        # Should not raise even without a model
        sm = EventDrivenLifecycle()
        sm.start()
        sm.start_processing()
        sm.done_processing()


class TestInvalidTransitions:
    """Additional: invalid transitions raise TransitionNotAllowed."""

    def test_cannot_process_from_creating(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        with pytest.raises(TransitionNotAllowed):
            sm.start_processing()

    def test_cannot_sleep_from_creating(self) -> None:
        from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle

        sm = EventDrivenLifecycle()
        with pytest.raises(TransitionNotAllowed):
            sm.sleep()
