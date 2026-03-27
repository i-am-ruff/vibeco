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
