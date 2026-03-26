"""Tests for MonitorLoop — async cycle orchestration composing checks,
status generation, heartbeat, and callbacks.

Uses pytest-asyncio for async test support. All external dependencies
are mocked (checks, status_generator, heartbeat, agents.json loading).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from vcompany.models.config import AgentConfig, ProjectConfig
from vcompany.models.monitor_state import CheckResult


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project directory structure."""
    (tmp_path / "state").mkdir()
    (tmp_path / "clones" / "frontend").mkdir(parents=True)
    (tmp_path / "clones" / "backend").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def config() -> ProjectConfig:
    """Two-agent config for testing."""
    return ProjectConfig(
        project="test-proj",
        repo="https://github.com/test/repo",
        agents=[
            AgentConfig(
                id="frontend",
                role="Frontend developer",
                owns=["src/frontend/"],
                consumes="INTERFACES.md",
                gsd_mode="full",
                system_prompt="Build the frontend",
            ),
            AgentConfig(
                id="backend",
                role="Backend developer",
                owns=["src/backend/"],
                consumes="INTERFACES.md",
                gsd_mode="full",
                system_prompt="Build the backend",
            ),
        ],
    )


@pytest.fixture
def tmux() -> MagicMock:
    return MagicMock()


def _ok_liveness(agent_id: str) -> CheckResult:
    return CheckResult(check_type="liveness", agent_id=agent_id, passed=True, detail="alive")


def _ok_stuck(agent_id: str) -> CheckResult:
    return CheckResult(check_type="stuck", agent_id=agent_id, passed=True, detail="recent")


def _ok_plan_gate(agent_id: str) -> tuple[CheckResult, dict[str, float]]:
    return (
        CheckResult(check_type="plan_gate", agent_id=agent_id, passed=True, detail="no new"),
        {},
    )


def _make_registry_json(agents: dict) -> str:
    """Build a minimal agents.json string."""
    import json

    entries = {}
    for aid, vals in agents.items():
        entries[aid] = {
            "agent_id": aid,
            "pane_id": vals.get("pane_id", f"%{aid}"),
            "pid": vals.get("pid", 12345),
            "session_name": "vco-test",
            "status": "running",
            "launched_at": "2026-01-01T00:00:00Z",
        }
    return json.dumps({"project": "test-proj", "agents": entries})


@pytest.mark.asyncio
async def test_run_cycle_checks_all_agents(project_dir, config, tmux):
    """MonitorLoop._run_cycle calls checks for every agent in config."""
    from vcompany.monitor.loop import MonitorLoop

    # Write agents.json
    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    checked_agents: list[str] = []

    with (
        patch("vcompany.monitor.loop.check_liveness") as mock_live,
        patch("vcompany.monitor.loop.check_stuck") as mock_stuck,
        patch("vcompany.monitor.loop.check_plan_gate") as mock_gate,
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        def live_side(agent_id, tmux_mgr, pane, agent_pid=None):
            checked_agents.append(agent_id)
            return _ok_liveness(agent_id)

        mock_live.side_effect = live_side
        mock_stuck.side_effect = lambda aid, cd, **kw: _ok_stuck(aid)
        mock_gate.side_effect = lambda aid, cd, mtimes: _ok_plan_gate(aid)

        loop = MonitorLoop(project_dir, config, tmux)
        await loop._run_cycle()

    assert sorted(checked_agents) == ["backend", "frontend"]


@pytest.mark.asyncio
async def test_run_cycle_parallel(project_dir, config, tmux):
    """Checks run via asyncio.gather (not sequentially)."""
    from vcompany.monitor.loop import MonitorLoop

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    call_order: list[str] = []

    with (
        patch("vcompany.monitor.loop.check_liveness") as mock_live,
        patch("vcompany.monitor.loop.check_stuck") as mock_stuck,
        patch("vcompany.monitor.loop.check_plan_gate") as mock_gate,
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        mock_live.side_effect = lambda aid, t, p, agent_pid=None: (
            call_order.append(f"live-{aid}") or _ok_liveness(aid)
        )
        mock_stuck.side_effect = lambda aid, cd, **kw: (
            call_order.append(f"stuck-{aid}") or _ok_stuck(aid)
        )
        mock_gate.side_effect = lambda aid, cd, mtimes: (
            call_order.append(f"gate-{aid}") or _ok_plan_gate(aid)
        )

        loop = MonitorLoop(project_dir, config, tmux)
        await loop._run_cycle()

    # Both agents should have been checked (gather ensures both run)
    assert "live-frontend" in call_order
    assert "live-backend" in call_order


@pytest.mark.asyncio
async def test_run_cycle_agent_error_isolated(project_dir, config, tmux):
    """If one agent's check raises, others still complete (per D-01)."""
    from vcompany.monitor.loop import MonitorLoop

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    backend_checked = False

    with (
        patch("vcompany.monitor.loop.check_liveness") as mock_live,
        patch("vcompany.monitor.loop.check_stuck") as mock_stuck,
        patch("vcompany.monitor.loop.check_plan_gate") as mock_gate,
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        def live_effect(aid, t, p, agent_pid=None):
            if aid == "frontend":
                raise RuntimeError("Simulated crash in frontend check")
            nonlocal backend_checked
            backend_checked = True
            return _ok_liveness(aid)

        mock_live.side_effect = live_effect
        mock_stuck.side_effect = lambda aid, cd, **kw: _ok_stuck(aid)
        mock_gate.side_effect = lambda aid, cd, mtimes: _ok_plan_gate(aid)

        loop = MonitorLoop(project_dir, config, tmux)
        await loop._run_cycle()

    assert backend_checked, "Backend should still be checked even if frontend raises"


@pytest.mark.asyncio
async def test_run_cycle_generates_status(project_dir, config, tmux):
    """Each cycle calls generate_project_status + distribute_project_status."""
    from vcompany.monitor.loop import MonitorLoop

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    with (
        patch("vcompany.monitor.loop.check_liveness", side_effect=lambda aid, t, p, agent_pid=None: _ok_liveness(aid)),
        patch("vcompany.monitor.loop.check_stuck", side_effect=lambda aid, cd, **kw: _ok_stuck(aid)),
        patch("vcompany.monitor.loop.check_plan_gate", side_effect=lambda aid, cd, mtimes: _ok_plan_gate(aid)),
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status") as mock_gen,
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2) as mock_dist,
    ):
        loop = MonitorLoop(project_dir, config, tmux)
        await loop._run_cycle()

    mock_gen.assert_called_once_with(project_dir, config)
    mock_dist.assert_called_once_with(project_dir, config, "# status")


@pytest.mark.asyncio
async def test_run_cycle_writes_heartbeat_first(project_dir, config, tmux):
    """Heartbeat written at START of cycle (per Pitfall 6), before checks."""
    from vcompany.monitor.loop import MonitorLoop

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    call_order: list[str] = []

    with (
        patch("vcompany.monitor.loop.check_liveness", side_effect=lambda aid, t, p, agent_pid=None: (
            call_order.append("check") or _ok_liveness(aid)
        )),
        patch("vcompany.monitor.loop.check_stuck", side_effect=lambda aid, cd, **kw: _ok_stuck(aid)),
        patch("vcompany.monitor.loop.check_plan_gate", side_effect=lambda aid, cd, mtimes: _ok_plan_gate(aid)),
        patch("vcompany.monitor.loop.write_heartbeat", side_effect=lambda pd, **kw: call_order.append("heartbeat")),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        loop = MonitorLoop(project_dir, config, tmux)
        await loop._run_cycle()

    assert call_order[0] == "heartbeat", f"Heartbeat must be first, got: {call_order}"


@pytest.mark.asyncio
async def test_callback_on_dead_agent(project_dir, config, tmux):
    """on_agent_dead callback fires when liveness check fails."""
    from vcompany.monitor.loop import MonitorLoop

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    dead_agents: list[str] = []

    with (
        patch("vcompany.monitor.loop.check_liveness") as mock_live,
        patch("vcompany.monitor.loop.check_stuck", side_effect=lambda aid, cd, **kw: _ok_stuck(aid)),
        patch("vcompany.monitor.loop.check_plan_gate", side_effect=lambda aid, cd, mtimes: _ok_plan_gate(aid)),
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        def live_effect(aid, t, p, agent_pid=None):
            if aid == "frontend":
                return CheckResult(check_type="liveness", agent_id=aid, passed=False, detail="dead")
            return _ok_liveness(aid)

        mock_live.side_effect = live_effect

        loop = MonitorLoop(
            project_dir, config, tmux,
            on_agent_dead=lambda aid: dead_agents.append(aid),
        )
        await loop._run_cycle()

    assert dead_agents == ["frontend"]


@pytest.mark.asyncio
async def test_callback_on_stuck_agent(project_dir, config, tmux):
    """on_agent_stuck callback fires when stuck check triggers."""
    from vcompany.monitor.loop import MonitorLoop

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    stuck_agents: list[str] = []

    with (
        patch("vcompany.monitor.loop.check_liveness", side_effect=lambda aid, t, p, agent_pid=None: _ok_liveness(aid)),
        patch("vcompany.monitor.loop.check_stuck") as mock_stuck,
        patch("vcompany.monitor.loop.check_plan_gate", side_effect=lambda aid, cd, mtimes: _ok_plan_gate(aid)),
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        def stuck_effect(aid, cd, **kw):
            if aid == "backend":
                return CheckResult(check_type="stuck", agent_id=aid, passed=False, detail="stuck")
            return _ok_stuck(aid)

        mock_stuck.side_effect = stuck_effect

        loop = MonitorLoop(
            project_dir, config, tmux,
            on_agent_stuck=lambda aid: stuck_agents.append(aid),
        )
        await loop._run_cycle()

    assert stuck_agents == ["backend"]


@pytest.mark.asyncio
async def test_callback_on_plan_detected(project_dir, config, tmux):
    """on_plan_detected callback fires with agent_id and plan path."""
    from vcompany.monitor.loop import MonitorLoop

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    detected: list[tuple[str, Path]] = []

    with (
        patch("vcompany.monitor.loop.check_liveness", side_effect=lambda aid, t, p, agent_pid=None: _ok_liveness(aid)),
        patch("vcompany.monitor.loop.check_stuck", side_effect=lambda aid, cd, **kw: _ok_stuck(aid)),
        patch("vcompany.monitor.loop.check_plan_gate") as mock_gate,
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        def gate_effect(aid, cd, mtimes):
            if aid == "frontend":
                return (
                    CheckResult(
                        check_type="plan_gate", agent_id=aid, passed=True,
                        detail="1 new", new_plans=["/some/01-01-PLAN.md"],
                    ),
                    {"/some/01-01-PLAN.md": 100.0},
                )
            return _ok_plan_gate(aid)

        mock_gate.side_effect = gate_effect

        loop = MonitorLoop(
            project_dir, config, tmux,
            on_plan_detected=lambda aid, p: detected.append((aid, p)),
        )
        await loop._run_cycle()

    assert len(detected) == 1
    assert detected[0][0] == "frontend"
    assert str(detected[0][1]) == "/some/01-01-PLAN.md"


@pytest.mark.asyncio
async def test_stop_gracefully(project_dir, config, tmux):
    """Setting _running = False stops the loop after current cycle."""
    from vcompany.monitor.loop import MonitorLoop

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    cycle_count = 0

    with (
        patch("vcompany.monitor.loop.check_liveness", side_effect=lambda aid, t, p, agent_pid=None: _ok_liveness(aid)),
        patch("vcompany.monitor.loop.check_stuck", side_effect=lambda aid, cd, **kw: _ok_stuck(aid)),
        patch("vcompany.monitor.loop.check_plan_gate", side_effect=lambda aid, cd, mtimes: _ok_plan_gate(aid)),
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        loop = MonitorLoop(project_dir, config, tmux, cycle_interval=0)

        original_run_cycle = loop._run_cycle

        async def counting_cycle():
            nonlocal cycle_count
            await original_run_cycle()
            cycle_count += 1
            if cycle_count >= 2:
                loop.stop()

        loop._run_cycle = counting_cycle
        await loop.run()

    assert cycle_count == 2


@pytest.mark.asyncio
async def test_plan_mtimes_persist_between_cycles(project_dir, config, tmux):
    """Plan gate mtime state carries across cycles."""
    from vcompany.monitor.loop import MonitorLoop

    # Single agent config for simplicity
    single_config = ProjectConfig(
        project="test-proj",
        repo="https://github.com/test/repo",
        agents=[
            AgentConfig(
                id="frontend",
                role="Frontend developer",
                owns=["src/frontend/"],
                consumes="INTERFACES.md",
                gsd_mode="full",
                system_prompt="Build the frontend",
            ),
        ],
    )

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}})
    )

    gate_calls: list[dict[str, float]] = []

    with (
        patch("vcompany.monitor.loop.check_liveness", side_effect=lambda aid, t, p, agent_pid=None: _ok_liveness(aid)),
        patch("vcompany.monitor.loop.check_stuck", side_effect=lambda aid, cd, **kw: _ok_stuck(aid)),
        patch("vcompany.monitor.loop.check_plan_gate") as mock_gate,
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        def gate_effect(aid, cd, mtimes):
            gate_calls.append(dict(mtimes))
            # Return updated mtimes each time
            new_mtimes = dict(mtimes)
            new_mtimes["plan1.md"] = len(gate_calls) * 100.0
            return (
                CheckResult(check_type="plan_gate", agent_id=aid, passed=True, detail="ok"),
                new_mtimes,
            )

        mock_gate.side_effect = gate_effect

        loop = MonitorLoop(project_dir, single_config, tmux, cycle_interval=0)

        # Run two cycles manually
        await loop._run_cycle()
        await loop._run_cycle()

    # First call should get empty mtimes (initial state)
    assert gate_calls[0] == {}
    # Second call should get mtimes from first call's return
    assert gate_calls[1] == {"plan1.md": 100.0}


@pytest.mark.asyncio
async def test_advisory_callback_on_dead_agent(project_dir, config, tmux):
    """on_advisory callback fires with message when liveness check fails."""
    from vcompany.monitor.loop import MonitorLoop

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    on_advisory = AsyncMock()

    with (
        patch("vcompany.monitor.loop.check_liveness") as mock_live,
        patch("vcompany.monitor.loop.check_stuck", side_effect=lambda aid, cd, **kw: _ok_stuck(aid)),
        patch("vcompany.monitor.loop.check_plan_gate", side_effect=lambda aid, cd, mtimes: _ok_plan_gate(aid)),
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        def live_effect(aid, t, p, agent_pid=None):
            if aid == "frontend":
                return CheckResult(check_type="liveness", agent_id=aid, passed=False, detail="pane gone")
            return _ok_liveness(aid)

        mock_live.side_effect = live_effect

        loop = MonitorLoop(
            project_dir, config, tmux,
            on_advisory=on_advisory,
        )
        await loop._run_cycle()

    on_advisory.assert_called_once()
    args = on_advisory.call_args[0]
    assert args[0] == "frontend"
    assert "appears dead" in args[1]
    assert "pane gone" in args[1]


@pytest.mark.asyncio
async def test_advisory_callback_on_stuck_agent(project_dir, config, tmux):
    """on_advisory callback fires with message when stuck check fails."""
    from vcompany.monitor.loop import MonitorLoop

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    on_advisory = AsyncMock()

    with (
        patch("vcompany.monitor.loop.check_liveness", side_effect=lambda aid, t, p, agent_pid=None: _ok_liveness(aid)),
        patch("vcompany.monitor.loop.check_stuck") as mock_stuck,
        patch("vcompany.monitor.loop.check_plan_gate", side_effect=lambda aid, cd, mtimes: _ok_plan_gate(aid)),
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        def stuck_effect(aid, cd, **kw):
            if aid == "backend":
                return CheckResult(check_type="stuck", agent_id=aid, passed=False, detail="no commits 30min")
            return _ok_stuck(aid)

        mock_stuck.side_effect = stuck_effect

        loop = MonitorLoop(
            project_dir, config, tmux,
            on_advisory=on_advisory,
        )
        await loop._run_cycle()

    on_advisory.assert_called_once()
    args = on_advisory.call_args[0]
    assert args[0] == "backend"
    assert "appears stuck" in args[1]
    assert "no commits 30min" in args[1]


@pytest.mark.asyncio
async def test_advisory_none_no_error_on_dead(project_dir, config, tmux):
    """When on_advisory is None, dead agent detection doesn't error."""
    from vcompany.monitor.loop import MonitorLoop

    (project_dir / "state" / "agents.json").write_text(
        _make_registry_json({"frontend": {}, "backend": {}})
    )

    with (
        patch("vcompany.monitor.loop.check_liveness") as mock_live,
        patch("vcompany.monitor.loop.check_stuck", side_effect=lambda aid, cd, **kw: _ok_stuck(aid)),
        patch("vcompany.monitor.loop.check_plan_gate", side_effect=lambda aid, cd, mtimes: _ok_plan_gate(aid)),
        patch("vcompany.monitor.loop.write_heartbeat"),
        patch("vcompany.monitor.loop.generate_project_status", return_value="# status"),
        patch("vcompany.monitor.loop.distribute_project_status", return_value=2),
    ):
        mock_live.side_effect = lambda aid, t, p, agent_pid=None: CheckResult(
            check_type="liveness", agent_id=aid, passed=False, detail="dead"
        )

        # No on_advisory, no on_agent_dead -- should not crash
        loop = MonitorLoop(project_dir, config, tmux)
        await loop._run_cycle()  # Should complete without error
