"""Tests for ContinuousLifecycle FSM and supporting data models."""

from __future__ import annotations

from enum import Enum

import pytest


# --- CyclePhase enum and CycleCheckpointData model ---


class TestCyclePhaseEnum:
    """CyclePhase enum value tests."""

    def test_cycle_phase_enum(self) -> None:
        from vcompany.agent.continuous_phases import CyclePhase

        assert issubclass(CyclePhase, str)
        assert issubclass(CyclePhase, Enum)

        expected = {
            "WAKE": "wake",
            "GATHER": "gather",
            "ANALYZE": "analyze",
            "ACT": "act",
            "REPORT": "report",
            "SLEEP_PREP": "sleep_prep",
        }
        for name, value in expected.items():
            member = CyclePhase[name]
            assert member.value == value
            assert member == value

        assert len(CyclePhase) == 6


class TestCycleCheckpointData:
    """CycleCheckpointData serialization tests."""

    def test_checkpoint_data_serialization(self) -> None:
        from vcompany.agent.continuous_phases import CycleCheckpointData

        data = CycleCheckpointData(
            configuration=["running", "gather"],
            cycle_phase="gather",
            cycle_count=3,
            timestamp="2026-03-27T12:00:00Z",
        )

        json_str = data.model_dump_json()
        restored = CycleCheckpointData.model_validate_json(json_str)

        assert restored.configuration == ["running", "gather"]
        assert restored.cycle_phase == "gather"
        assert restored.cycle_count == 3
        assert restored.timestamp == "2026-03-27T12:00:00Z"

    def test_checkpoint_data_fields(self) -> None:
        from vcompany.agent.continuous_phases import CycleCheckpointData

        data = CycleCheckpointData(
            configuration=["sleeping"],
            cycle_phase="act",
            cycle_count=0,
            timestamp="2026-03-27T12:00:00Z",
        )
        assert data.configuration == ["sleeping"]
        assert data.cycle_phase == "act"
        assert data.cycle_count == 0


# --- ContinuousLifecycle compound state machine ---


class TestContinuousLifecycleInitial:
    """Initial state tests."""

    def test_initial_state_is_creating(self) -> None:
        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        assert sm.current_state_value == "creating"

    def test_start_transitions_to_running_wake(self) -> None:
        from statemachine.orderedset import OrderedSet

        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        sm.start()
        assert sm.configuration_values == OrderedSet({"running", "wake"})


class TestContinuousLifecycleCyclePhases:
    """Cycle phase transition tests."""

    def test_full_cycle_transitions(self) -> None:
        from statemachine.orderedset import OrderedSet

        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        sm.start()

        sm.start_gather()
        assert sm.configuration_values == OrderedSet({"running", "gather"})

        sm.start_analyze()
        assert sm.configuration_values == OrderedSet({"running", "analyze"})

        sm.start_act()
        assert sm.configuration_values == OrderedSet({"running", "act"})

        sm.start_report()
        assert sm.configuration_values == OrderedSet({"running", "report"})

        sm.start_sleep_prep()
        assert sm.configuration_values == OrderedSet({"running", "sleep_prep"})

    def test_phases_only_in_running(self) -> None:
        from statemachine.exceptions import TransitionNotAllowed

        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        with pytest.raises(TransitionNotAllowed):
            sm.start_gather()


class TestContinuousLifecycleSleepWake:
    """Sleep/wake transitions -- wake starts fresh, NOT HistoryState."""

    def test_sleep_from_running(self) -> None:
        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        sm.start()
        sm.start_gather()
        sm.sleep()
        assert sm.current_state_value == "sleeping"

    def test_wake_starts_fresh_at_wake_phase(self) -> None:
        """CRITICAL: wake goes to running.wake, NOT running.h (not HistoryState)."""
        from statemachine.orderedset import OrderedSet

        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        sm.start()
        sm.start_gather()
        sm.start_analyze()

        sm.sleep()
        assert sm.current_state_value == "sleeping"

        # Wake should go to running.wake (fresh), NOT running.analyze (history)
        sm.wake()
        assert sm.configuration_values == OrderedSet({"running", "wake"})


class TestContinuousLifecycleErrorRecover:
    """Error/recover transitions -- recover uses HistoryState."""

    def test_error_from_running(self) -> None:
        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        sm.start()
        sm.start_gather()
        sm.start_analyze()
        sm.error()
        assert sm.current_state_value == "errored"

    def test_recover_resumes_via_history_state(self) -> None:
        """CRITICAL: recover goes to running.h (HistoryState) to resume mid-cycle."""
        from statemachine.orderedset import OrderedSet

        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        sm.start()
        sm.start_gather()
        sm.start_analyze()

        sm.error()
        assert sm.current_state_value == "errored"

        sm.recover()
        assert sm.configuration_values == OrderedSet({"running", "analyze"})


class TestContinuousLifecycleStopDestroy:
    """Stop and destroy transitions."""

    def test_stop_from_running(self) -> None:
        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        sm.start()
        sm.stop()
        assert sm.current_state_value == "stopped"

    def test_destroy_from_stopped(self) -> None:
        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        sm.start()
        sm.stop()
        sm.destroy()
        assert sm.current_state_value == "destroyed"

    def test_stop_from_errored(self) -> None:
        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        sm.start()
        sm.error()
        sm.stop()
        assert sm.current_state_value == "stopped"


class TestContinuousLifecycleModel:
    """Model binding and callback tests."""

    def test_after_transition_calls_model(self) -> None:
        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        class FakeModel:
            def __init__(self) -> None:
                self.changes: list[str] = []
                self._fsm_state: object = None

            def _on_state_change(self) -> None:
                self.changes.append("changed")

        model = FakeModel()
        sm = ContinuousLifecycle(model=model, state_field="_fsm_state")
        sm.start()
        assert len(model.changes) >= 1

        sm.start_gather()
        assert len(model.changes) >= 2


class TestContinuousLifecycleSerialization:
    """State serialization round-trip tests."""

    def test_state_serialization_roundtrip(self) -> None:
        from statemachine.orderedset import OrderedSet

        from vcompany.agent.continuous_lifecycle import ContinuousLifecycle

        sm = ContinuousLifecycle()
        sm.start()
        sm.start_gather()
        sm.start_analyze()

        saved = list(sm.configuration_values)
        assert saved == ["running", "analyze"]

        sm2 = ContinuousLifecycle()
        sm2.current_state_value = OrderedSet(saved)
        assert sm2.configuration_values == OrderedSet({"running", "analyze"})

        sm2.start_act()
        assert sm2.configuration_values == OrderedSet({"running", "act"})
