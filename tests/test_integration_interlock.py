"""Tests for integration interlock, checkin auto-trigger, and all_agents_idle().

Verifies:
- AgentMonitorState has integration_pending and checkin_sent fields
- MonitorLoop._run_cycle checks integration_pending after agent checks
- When all agents idle and integration_pending, _on_integration_ready fires
- When not all agents idle, callback does NOT fire
- set_integration_pending sets the flag
- After phase completion and checkin_sent=False, monitor triggers _on_checkin
- checkin_sent=True prevents duplicate triggers
- all_agents_idle() returns correct bool
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vcompany.models.monitor_state import AgentMonitorState


# ── AgentMonitorState field tests ─────────────────────────────────────


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


# ── MonitorLoop integration interlock tests ───────────────────────────


def _make_config(agent_ids: list[str]) -> MagicMock:
    """Create a mock ProjectConfig with the given agent IDs."""
    config = MagicMock()
    agents = []
    for aid in agent_ids:
        agent = MagicMock()
        agent.id = aid
        agents.append(agent)
    config.agents = agents
    return config


def _make_monitor(
    agent_ids: list[str],
    on_integration_ready: AsyncMock | None = None,
    on_checkin: AsyncMock | None = None,
) -> "MonitorLoop":
    from vcompany.monitor.loop import MonitorLoop

    config = _make_config(agent_ids)
    tmux = MagicMock()
    monitor = MonitorLoop(
        project_dir=Path("/tmp/test-project"),
        config=config,
        tmux=tmux,
        on_integration_ready=on_integration_ready,
        on_checkin=on_checkin,
        cycle_interval=0,  # no sleep
    )
    return monitor


class TestSetIntegrationPending:
    """Test set_integration_pending method."""

    def test_set_pending_true(self) -> None:
        monitor = _make_monitor(["agent-a"])
        monitor.set_integration_pending(True)
        assert monitor._integration_pending is True

    def test_set_pending_false(self) -> None:
        monitor = _make_monitor(["agent-a"])
        monitor.set_integration_pending(True)
        monitor.set_integration_pending(False)
        assert monitor._integration_pending is False


class TestAllAgentsIdle:
    """Test all_agents_idle() public method."""

    def test_empty_states_returns_false(self) -> None:
        from vcompany.monitor.loop import MonitorLoop

        config = _make_config([])
        tmux = MagicMock()
        monitor = MonitorLoop(
            project_dir=Path("/tmp/test-project"),
            config=config,
            tmux=tmux,
            cycle_interval=0,
        )
        assert monitor.all_agents_idle() is False

    def test_all_completed_and_idle(self) -> None:
        monitor = _make_monitor(["agent-a", "agent-b"])
        for state in monitor._agent_states.values():
            state.phase_status = "completed"
            state.plan_gate_status = "idle"
        assert monitor.all_agents_idle() is True

    def test_one_not_completed(self) -> None:
        monitor = _make_monitor(["agent-a", "agent-b"])
        monitor._agent_states["agent-a"].phase_status = "completed"
        monitor._agent_states["agent-a"].plan_gate_status = "idle"
        monitor._agent_states["agent-b"].phase_status = "in_progress"
        monitor._agent_states["agent-b"].plan_gate_status = "idle"
        assert monitor.all_agents_idle() is False

    def test_one_awaiting_review(self) -> None:
        monitor = _make_monitor(["agent-a", "agent-b"])
        for state in monitor._agent_states.values():
            state.phase_status = "completed"
        monitor._agent_states["agent-a"].plan_gate_status = "idle"
        monitor._agent_states["agent-b"].plan_gate_status = "awaiting_review"
        assert monitor.all_agents_idle() is False


class TestIntegrationInterlock:
    """Test that _on_integration_ready fires at the right time."""

    @pytest.mark.asyncio
    async def test_fires_when_all_idle_and_pending(self) -> None:
        callback = AsyncMock()
        monitor = _make_monitor(["agent-a", "agent-b"], on_integration_ready=callback)
        monitor.set_integration_pending(True)

        # Set all agents to idle
        for state in monitor._agent_states.values():
            state.phase_status = "completed"
            state.plan_gate_status = "idle"

        # Patch out the actual check logic and status generation
        with patch.object(monitor, "_check_agent", new_callable=AsyncMock), \
             patch("vcompany.monitor.loop.write_heartbeat"), \
             patch.object(monitor, "_load_registry", return_value=MagicMock()), \
             patch("vcompany.monitor.loop.generate_project_status", return_value=""), \
             patch("vcompany.monitor.loop.distribute_project_status"):
            await monitor._run_cycle()

        callback.assert_awaited_once()
        assert monitor._integration_pending is False

    @pytest.mark.asyncio
    async def test_does_not_fire_when_not_all_idle(self) -> None:
        callback = AsyncMock()
        monitor = _make_monitor(["agent-a", "agent-b"], on_integration_ready=callback)
        monitor.set_integration_pending(True)

        # Only one agent idle
        monitor._agent_states["agent-a"].phase_status = "completed"
        monitor._agent_states["agent-a"].plan_gate_status = "idle"
        monitor._agent_states["agent-b"].phase_status = "in_progress"

        with patch.object(monitor, "_check_agent", new_callable=AsyncMock), \
             patch("vcompany.monitor.loop.write_heartbeat"), \
             patch.object(monitor, "_load_registry", return_value=MagicMock()), \
             patch("vcompany.monitor.loop.generate_project_status", return_value=""), \
             patch("vcompany.monitor.loop.distribute_project_status"):
            await monitor._run_cycle()

        callback.assert_not_awaited()
        assert monitor._integration_pending is True

    @pytest.mark.asyncio
    async def test_does_not_fire_when_not_pending(self) -> None:
        callback = AsyncMock()
        monitor = _make_monitor(["agent-a"], on_integration_ready=callback)
        # NOT setting pending

        monitor._agent_states["agent-a"].phase_status = "completed"
        monitor._agent_states["agent-a"].plan_gate_status = "idle"

        with patch.object(monitor, "_check_agent", new_callable=AsyncMock), \
             patch("vcompany.monitor.loop.write_heartbeat"), \
             patch.object(monitor, "_load_registry", return_value=MagicMock()), \
             patch("vcompany.monitor.loop.generate_project_status", return_value=""), \
             patch("vcompany.monitor.loop.distribute_project_status"):
            await monitor._run_cycle()

        callback.assert_not_awaited()


class TestCheckinAutoTrigger:
    """Test that _on_checkin fires on phase completion."""

    @pytest.mark.asyncio
    async def test_checkin_fires_on_phase_completion(self) -> None:
        checkin_cb = AsyncMock()
        monitor = _make_monitor(["agent-a"], on_checkin=checkin_cb)

        # Simulate _check_agent detecting phase completion
        state = monitor._agent_states["agent-a"]
        state.checkin_sent = False

        # We need to test _check_agent's checkin logic
        # Patch the check functions to simulate phase completion
        with patch("vcompany.monitor.loop.check_liveness") as mock_live, \
             patch("vcompany.monitor.loop.check_stuck") as mock_stuck, \
             patch("vcompany.monitor.loop.check_plan_gate") as mock_gate, \
             patch("vcompany.monitor.loop.check_phase_completion") as mock_phase:
            mock_live.return_value = MagicMock(passed=True)
            mock_stuck.return_value = MagicMock(passed=True)
            mock_gate.return_value = (MagicMock(passed=True, new_plans=[]), {})
            mock_phase.return_value = ("phase-1", "completed")

            registry = MagicMock()
            entry = MagicMock()
            entry.pane_id = "test-pane"
            entry.pid = 1234
            agents_dict = MagicMock()
            agents_dict.get = MagicMock(return_value=entry)
            registry.agents = agents_dict

            await monitor._check_agent("agent-a", registry)

        checkin_cb.assert_awaited_once_with("agent-a")
        assert state.checkin_sent is True

    @pytest.mark.asyncio
    async def test_checkin_does_not_fire_twice(self) -> None:
        checkin_cb = AsyncMock()
        monitor = _make_monitor(["agent-a"], on_checkin=checkin_cb)

        state = monitor._agent_states["agent-a"]
        state.checkin_sent = True  # Already sent

        with patch("vcompany.monitor.loop.check_liveness") as mock_live, \
             patch("vcompany.monitor.loop.check_stuck") as mock_stuck, \
             patch("vcompany.monitor.loop.check_plan_gate") as mock_gate, \
             patch("vcompany.monitor.loop.check_phase_completion") as mock_phase:
            mock_live.return_value = MagicMock(passed=True)
            mock_stuck.return_value = MagicMock(passed=True)
            mock_gate.return_value = (MagicMock(passed=True, new_plans=[]), {})
            mock_phase.return_value = ("phase-1", "completed")

            registry = MagicMock()
            entry = MagicMock()
            entry.pane_id = "test-pane"
            entry.pid = 1234
            agents_dict = MagicMock()
            agents_dict.get = MagicMock(return_value=entry)
            registry.agents = agents_dict

            await monitor._check_agent("agent-a", registry)

        checkin_cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_checkin_does_not_fire_when_not_completed(self) -> None:
        checkin_cb = AsyncMock()
        monitor = _make_monitor(["agent-a"], on_checkin=checkin_cb)

        state = monitor._agent_states["agent-a"]
        state.checkin_sent = False

        with patch("vcompany.monitor.loop.check_liveness") as mock_live, \
             patch("vcompany.monitor.loop.check_stuck") as mock_stuck, \
             patch("vcompany.monitor.loop.check_plan_gate") as mock_gate, \
             patch("vcompany.monitor.loop.check_phase_completion") as mock_phase:
            mock_live.return_value = MagicMock(passed=True)
            mock_stuck.return_value = MagicMock(passed=True)
            mock_gate.return_value = (MagicMock(passed=True, new_plans=[]), {})
            mock_phase.return_value = ("phase-1", "in_progress")

            registry = MagicMock()
            entry = MagicMock()
            entry.pane_id = "test-pane"
            entry.pid = 1234
            agents_dict = MagicMock()
            agents_dict.get = MagicMock(return_value=entry)
            registry.agents = agents_dict

            await monitor._check_agent("agent-a", registry)

        checkin_cb.assert_not_awaited()
