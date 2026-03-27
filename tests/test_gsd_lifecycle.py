"""Tests for GsdLifecycle FSM and supporting data models."""

from __future__ import annotations

from enum import Enum

import pytest


# --- Task 1: GsdPhase enum and CheckpointData model ---


class TestGsdPhaseEnum:
    """GsdPhase enum value tests."""

    def test_gsd_phase_enum(self) -> None:
        from vcompany.agent.gsd_phases import GsdPhase

        assert issubclass(GsdPhase, str)
        assert issubclass(GsdPhase, Enum)

        expected = {
            "IDLE": "idle",
            "DISCUSS": "discuss",
            "PLAN": "plan",
            "EXECUTE": "execute",
            "UAT": "uat",
            "SHIP": "ship",
        }
        for name, value in expected.items():
            member = GsdPhase[name]
            assert member.value == value
            # str(Enum) behavior: value is accessible via .value
            assert member == value  # str comparison works for str, Enum

        # Exactly 6 members
        assert len(GsdPhase) == 6


class TestCheckpointData:
    """CheckpointData serialization tests."""

    def test_checkpoint_data_serialization(self) -> None:
        from vcompany.agent.gsd_phases import CheckpointData

        data = CheckpointData(
            configuration=["running", "plan"],
            phase="plan",
            timestamp="2026-03-27T12:00:00Z",
        )

        # Round-trip through JSON
        json_str = data.model_dump_json()
        restored = CheckpointData.model_validate_json(json_str)

        assert restored.configuration == ["running", "plan"]
        assert restored.phase == "plan"
        assert restored.timestamp == "2026-03-27T12:00:00Z"

    def test_checkpoint_data_fields(self) -> None:
        from vcompany.agent.gsd_phases import CheckpointData

        data = CheckpointData(
            configuration=["sleeping"],
            phase="execute",
            timestamp="2026-03-27T12:00:00Z",
        )
        assert data.configuration == ["sleeping"]
        assert data.phase == "execute"


# --- Task 2: GsdLifecycle compound state machine ---


class TestGsdLifecycleInitial:
    """Initial state tests."""

    def test_initial_state_is_creating(self) -> None:
        from vcompany.agent.gsd_lifecycle import GsdLifecycle

        sm = GsdLifecycle()
        assert sm.current_state_value == "creating"

    def test_start_transitions_to_running_idle(self) -> None:
        from statemachine.orderedset import OrderedSet

        from vcompany.agent.gsd_lifecycle import GsdLifecycle

        sm = GsdLifecycle()
        sm.start()
        assert sm.configuration_values == OrderedSet({"running", "idle"})


class TestGsdLifecyclePhases:
    """Phase transition tests."""

    def test_phase_transitions_full_sequence(self) -> None:
        from statemachine.orderedset import OrderedSet

        from vcompany.agent.gsd_lifecycle import GsdLifecycle

        sm = GsdLifecycle()
        sm.start()

        sm.start_discuss()
        assert sm.configuration_values == OrderedSet({"running", "discuss"})

        sm.start_plan()
        assert sm.configuration_values == OrderedSet({"running", "plan"})

        sm.start_execute()
        assert sm.configuration_values == OrderedSet({"running", "execute"})

        sm.start_uat()
        assert sm.configuration_values == OrderedSet({"running", "uat"})

        sm.start_ship()
        assert sm.configuration_values == OrderedSet({"running", "ship"})

    def test_phases_only_in_running(self) -> None:
        from statemachine.exceptions import TransitionNotAllowed

        from vcompany.agent.gsd_lifecycle import GsdLifecycle

        sm = GsdLifecycle()
        # In creating state, start_discuss should fail
        with pytest.raises(TransitionNotAllowed):
            sm.start_discuss()


class TestGsdLifecycleHistory:
    """HistoryState tests for sleep/wake and error/recover."""

    def test_history_state_sleep_wake(self) -> None:
        from statemachine.orderedset import OrderedSet

        from vcompany.agent.gsd_lifecycle import GsdLifecycle

        sm = GsdLifecycle()
        sm.start()
        sm.start_discuss()
        sm.start_plan()

        # Sleep from running.plan
        sm.sleep()
        assert sm.current_state_value == "sleeping"

        # Wake should restore running.plan
        sm.wake()
        assert sm.configuration_values == OrderedSet({"running", "plan"})

    def test_history_state_error_recover(self) -> None:
        from statemachine.orderedset import OrderedSet

        from vcompany.agent.gsd_lifecycle import GsdLifecycle

        sm = GsdLifecycle()
        sm.start()
        sm.start_discuss()
        sm.start_plan()
        sm.start_execute()

        # Error from running.execute
        sm.error()
        assert sm.current_state_value == "errored"

        # Recover should restore running.execute
        sm.recover()
        assert sm.configuration_values == OrderedSet({"running", "execute"})


class TestGsdLifecycleSerialization:
    """State serialization round-trip tests."""

    def test_state_serialization_roundtrip(self) -> None:
        from statemachine.orderedset import OrderedSet

        from vcompany.agent.gsd_lifecycle import GsdLifecycle

        sm = GsdLifecycle()
        sm.start()
        sm.start_discuss()
        sm.start_plan()

        # Serialize
        saved = list(sm.configuration_values)
        assert saved == ["running", "plan"]

        # Restore on new instance
        sm2 = GsdLifecycle()
        sm2.current_state_value = OrderedSet(saved)
        assert sm2.configuration_values == OrderedSet({"running", "plan"})

        # Can continue transitions from restored state
        sm2.start_execute()
        assert sm2.configuration_values == OrderedSet({"running", "execute"})


class TestGsdLifecycleModel:
    """Model binding and callback tests."""

    def test_after_transition_calls_model(self) -> None:
        from vcompany.agent.gsd_lifecycle import GsdLifecycle

        class FakeModel:
            def __init__(self) -> None:
                self.changes: list[str] = []
                self._fsm_state: object = None

            def _on_state_change(self) -> None:
                self.changes.append("changed")

        model = FakeModel()
        sm = GsdLifecycle(model=model, state_field="_fsm_state")
        sm.start()
        assert len(model.changes) >= 1

        sm.start_discuss()
        assert len(model.changes) >= 2
