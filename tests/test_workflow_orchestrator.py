"""Tests for WorkflowOrchestrator state machine, signal detection, and verify gate."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vcompany.orchestrator.workflow_orchestrator import (
    AgentWorkflowState,
    WorkflowOrchestrator,
    WorkflowStage,
    detect_stage_signal,
)


@pytest.fixture
def mock_agent_manager():
    mgr = MagicMock()
    mgr.send_work_command.return_value = True
    return mgr


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    agent1 = MagicMock()
    agent1.id = "frontend"
    agent2 = MagicMock()
    agent2.id = "backend"
    cfg.agents = [agent1, agent2]
    return cfg


@pytest.fixture
def orchestrator(tmp_path, mock_config, mock_agent_manager):
    return WorkflowOrchestrator(
        project_dir=tmp_path,
        config=mock_config,
        agent_manager=mock_agent_manager,
    )


class TestWorkflowOrchestratorSeparation:
    """D-01: WorkflowOrchestrator is a separate class from MonitorLoop."""

    def test_is_separate_class(self):
        assert WorkflowOrchestrator is not None
        assert WorkflowStage is not None
        assert AgentWorkflowState is not None


class TestPerAgentIndependentState:
    """D-02: Each agent has independent state."""

    def test_independent_agent_states(self, orchestrator, mock_agent_manager):
        orchestrator.start_agent("frontend", 1)
        orchestrator.start_agent("backend", 1)

        # Change frontend stage, backend should be unaffected
        orchestrator.on_stage_complete("frontend", "discuss")

        fe_state = orchestrator.get_agent_state("frontend")
        be_state = orchestrator.get_agent_state("backend")

        assert fe_state.stage == WorkflowStage.DISCUSSION_GATE
        assert be_state.stage == WorkflowStage.DISCUSS


class TestStartAgent:
    """D-04: start_agent sends /gsd:discuss-phase without --auto."""

    def test_start_agent_sends_discuss_command(self, orchestrator, mock_agent_manager):
        result = orchestrator.start_agent("frontend", 3)

        assert result is True
        mock_agent_manager.send_work_command.assert_called_once_with(
            "frontend", "/gsd:discuss-phase 3", wait_for_ready=True
        )

        state = orchestrator.get_agent_state("frontend")
        assert state.stage == WorkflowStage.DISCUSS
        assert state.current_phase == 3


class TestDetectStageSignal:
    """Signal detection from vco report messages."""

    def test_detect_discuss_complete(self):
        result = detect_stage_signal(
            "2026-03-27T02:19:08Z frontend: discuss-phase complete"
        )
        assert result == ("frontend", "discuss")

    def test_detect_plan_complete(self):
        result = detect_stage_signal(
            "2026-03-27T02:19:08Z backend: @PM plan-phase complete - ready for review"
        )
        assert result == ("backend", "plan")

    def test_detect_execute_complete(self):
        result = detect_stage_signal(
            "2026-03-27T02:19:08Z backend: @PM execute-phase complete - verify"
        )
        assert result == ("backend", "execute")

    def test_detect_random_message_returns_none(self):
        result = detect_stage_signal("random message")
        assert result is None


class TestOnStageComplete:
    """Stage transition logic."""

    def test_discuss_to_discussion_gate(self, orchestrator):
        orchestrator.start_agent("frontend", 1)
        new_stage = orchestrator.on_stage_complete("frontend", "discuss")
        assert new_stage == WorkflowStage.DISCUSSION_GATE

    def test_plan_to_pm_plan_review_gate(self, orchestrator):
        orchestrator.start_agent("frontend", 1)
        orchestrator.on_stage_complete("frontend", "discuss")
        orchestrator.advance_from_gate("frontend", approved=True)
        new_stage = orchestrator.on_stage_complete("frontend", "plan")
        assert new_stage == WorkflowStage.PM_PLAN_REVIEW_GATE

    def test_execute_to_verify_not_phase_complete(self, orchestrator):
        """D-07: Execute transitions to VERIFY, NOT PHASE_COMPLETE."""
        orchestrator.start_agent("frontend", 1)
        # Advance through discuss -> plan -> execute
        orchestrator.on_stage_complete("frontend", "discuss")
        orchestrator.advance_from_gate("frontend", approved=True)
        orchestrator.on_stage_complete("frontend", "plan")
        orchestrator.advance_from_gate("frontend", approved=True)
        new_stage = orchestrator.on_stage_complete("frontend", "execute")
        assert new_stage == WorkflowStage.VERIFY


class TestAdvanceFromGate:
    """Gate advancement logic."""

    def test_discussion_gate_approved_sends_plan(self, orchestrator, mock_agent_manager):
        orchestrator.start_agent("frontend", 2)
        orchestrator.on_stage_complete("frontend", "discuss")
        mock_agent_manager.send_work_command.reset_mock()

        result = orchestrator.advance_from_gate("frontend", approved=True)

        assert result is True
        mock_agent_manager.send_work_command.assert_called_once_with(
            "frontend", "/gsd:plan-phase 2", wait_for_ready=True
        )
        assert orchestrator.get_agent_state("frontend").stage == WorkflowStage.PLAN

    def test_discussion_gate_rejected_resends_discuss(self, orchestrator, mock_agent_manager):
        orchestrator.start_agent("frontend", 2)
        orchestrator.on_stage_complete("frontend", "discuss")
        mock_agent_manager.send_work_command.reset_mock()

        result = orchestrator.advance_from_gate("frontend", approved=False)

        assert result is True
        mock_agent_manager.send_work_command.assert_called_once_with(
            "frontend", "/gsd:discuss-phase 2", wait_for_ready=True
        )
        assert orchestrator.get_agent_state("frontend").stage == WorkflowStage.DISCUSS

    def test_pm_plan_review_gate_approved_sends_execute(self, orchestrator, mock_agent_manager):
        orchestrator.start_agent("frontend", 1)
        orchestrator.on_stage_complete("frontend", "discuss")
        orchestrator.advance_from_gate("frontend", approved=True)
        orchestrator.on_stage_complete("frontend", "plan")
        mock_agent_manager.send_work_command.reset_mock()

        result = orchestrator.advance_from_gate("frontend", approved=True)

        assert result is True
        mock_agent_manager.send_work_command.assert_called_once_with(
            "frontend", "/gsd:execute-phase 1", wait_for_ready=True
        )
        assert orchestrator.get_agent_state("frontend").stage == WorkflowStage.EXECUTE

    def test_verify_gate_approved_to_phase_complete(self, orchestrator, mock_agent_manager):
        """D-07: VERIFY_GATE approved transitions to PHASE_COMPLETE."""
        orchestrator.start_agent("frontend", 1)
        orchestrator.on_stage_complete("frontend", "discuss")
        orchestrator.advance_from_gate("frontend", approved=True)
        orchestrator.on_stage_complete("frontend", "plan")
        orchestrator.advance_from_gate("frontend", approved=True)
        orchestrator.on_stage_complete("frontend", "execute")
        # Now at VERIFY, simulate verify completing
        # VERIFY -> VERIFY_GATE would happen via on_stage_complete or direct state manipulation
        # The orchestrator should go from VERIFY_GATE -> PHASE_COMPLETE on approval
        state = orchestrator.get_agent_state("frontend")
        state.stage = WorkflowStage.VERIFY_GATE
        mock_agent_manager.send_work_command.reset_mock()

        result = orchestrator.advance_from_gate("frontend", approved=True)

        assert result is True
        assert orchestrator.get_agent_state("frontend").stage == WorkflowStage.PHASE_COMPLETE
        # No command should be sent for VERIFY_GATE approval
        mock_agent_manager.send_work_command.assert_not_called()

    def test_verify_gate_rejected_resends_execute(self, orchestrator, mock_agent_manager):
        """D-07: VERIFY_GATE rejected transitions back to EXECUTE."""
        orchestrator.start_agent("frontend", 1)
        orchestrator.on_stage_complete("frontend", "discuss")
        orchestrator.advance_from_gate("frontend", approved=True)
        orchestrator.on_stage_complete("frontend", "plan")
        orchestrator.advance_from_gate("frontend", approved=True)
        orchestrator.on_stage_complete("frontend", "execute")
        state = orchestrator.get_agent_state("frontend")
        state.stage = WorkflowStage.VERIFY_GATE
        mock_agent_manager.send_work_command.reset_mock()

        result = orchestrator.advance_from_gate("frontend", approved=False)

        assert result is True
        mock_agent_manager.send_work_command.assert_called_once_with(
            "frontend", "/gsd:execute-phase 1", wait_for_ready=True
        )
        assert orchestrator.get_agent_state("frontend").stage == WorkflowStage.EXECUTE


class TestGetAgentState:
    """get_agent_state returns current state."""

    def test_returns_state(self, orchestrator):
        orchestrator.start_agent("frontend", 1)
        state = orchestrator.get_agent_state("frontend")
        assert isinstance(state, AgentWorkflowState)
        assert state.agent_id == "frontend"

    def test_returns_none_for_unknown(self, orchestrator):
        state = orchestrator.get_agent_state("nonexistent")
        assert state is None


class TestRecoverFromState:
    """D-08: Crash recovery reads STATE.md."""

    def test_recover_from_context_gathered(self, orchestrator, tmp_path):
        clone_dir = tmp_path / "clones" / "frontend"
        planning_dir = clone_dir / ".planning"
        planning_dir.mkdir(parents=True)
        (planning_dir / "STATE.md").write_text(
            "---\nstatus: Ready to plan\n---\n\n# State\n\nStopped at: Phase 1 context gathered\n"
        )
        orchestrator.start_agent("frontend", 1)

        stage = orchestrator.recover_from_state("frontend", clone_dir)

        assert stage == WorkflowStage.DISCUSSION_GATE

    def test_recover_from_planned(self, orchestrator, tmp_path):
        clone_dir = tmp_path / "clones" / "backend"
        planning_dir = clone_dir / ".planning"
        planning_dir.mkdir(parents=True)
        (planning_dir / "STATE.md").write_text(
            "---\nstatus: Planning\n---\n\n# State\n\nStopped at: Phase 2 planned\n"
        )
        orchestrator.start_agent("backend", 2)

        stage = orchestrator.recover_from_state("backend", clone_dir)

        assert stage == WorkflowStage.PM_PLAN_REVIEW_GATE

    def test_recover_from_executing(self, orchestrator, tmp_path):
        clone_dir = tmp_path / "clones" / "backend"
        planning_dir = clone_dir / ".planning"
        planning_dir.mkdir(parents=True)
        (planning_dir / "STATE.md").write_text(
            "---\nstatus: Executing\n---\n\n# State\n\nStopped at: Phase 3 executing\n"
        )
        orchestrator.start_agent("backend", 3)

        stage = orchestrator.recover_from_state("backend", clone_dir)

        assert stage == WorkflowStage.EXECUTE

    def test_recover_from_verified(self, orchestrator, tmp_path):
        clone_dir = tmp_path / "clones" / "backend"
        planning_dir = clone_dir / ".planning"
        planning_dir.mkdir(parents=True)
        (planning_dir / "STATE.md").write_text(
            "---\nstatus: Verified\n---\n\n# State\n\nStopped at: Phase 3 verified\n"
        )
        orchestrator.start_agent("backend", 3)

        stage = orchestrator.recover_from_state("backend", clone_dir)

        assert stage == WorkflowStage.VERIFY_GATE


class TestHandleUnknownPrompt:
    """D-15: Unknown prompts block and alert."""

    def test_sets_blocked_state(self, orchestrator):
        orchestrator.start_agent("frontend", 1)
        msg = orchestrator.handle_unknown_prompt("frontend", "Do you want to continue?")

        state = orchestrator.get_agent_state("frontend")
        assert state.blocked_since is not None
        assert "Do you want to continue?" in state.blocked_reason
        assert "blocked" in msg.lower()


class TestCheckBlockedAgents:
    """D-16: Check for agents blocked >600s."""

    def test_returns_agents_blocked_over_timeout(self, orchestrator):
        orchestrator.start_agent("frontend", 1)
        state = orchestrator.get_agent_state("frontend")

        # Simulate being blocked for 700 seconds
        with patch("time.monotonic", return_value=1000.0):
            orchestrator.handle_unknown_prompt("frontend", "some prompt")

        with patch("time.monotonic", return_value=1700.0):
            blocked = orchestrator.check_blocked_agents(timeout=600.0)

        assert len(blocked) == 1
        assert blocked[0].agent_id == "frontend"

    def test_no_agents_blocked_under_timeout(self, orchestrator):
        orchestrator.start_agent("frontend", 1)

        with patch("time.monotonic", return_value=1000.0):
            orchestrator.handle_unknown_prompt("frontend", "some prompt")

        with patch("time.monotonic", return_value=1100.0):
            blocked = orchestrator.check_blocked_agents(timeout=600.0)

        assert len(blocked) == 0


class TestGetAllStates:
    """get_all_states returns complete state dict."""

    def test_returns_all(self, orchestrator):
        orchestrator.start_agent("frontend", 1)
        orchestrator.start_agent("backend", 2)

        states = orchestrator.get_all_states()
        assert "frontend" in states
        assert "backend" in states
        assert len(states) == 2
