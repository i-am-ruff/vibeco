"""Main monitor loop: composes check functions, status generation, and heartbeat
into the core 60-second async supervision cycle.

Implements D-01 through D-09. Each cycle:
1. Writes heartbeat (Pitfall 6: at START of cycle)
2. Loads agents.json for pane info
3. Checks all agents in parallel via asyncio.gather
4. Generates and distributes PROJECT-STATUS.md
5. Fires callbacks for dead/stuck/new-plan events

One agent's check failure never affects another (independent try/except per D-01).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path

from vcompany.models.agent_state import AgentsRegistry
from vcompany.models.config import ProjectConfig
from vcompany.models.monitor_state import AgentMonitorState
from vcompany.monitor.checks import check_liveness, check_plan_gate, check_stuck
from vcompany.monitor.heartbeat import write_heartbeat
from vcompany.monitor.status_generator import (
    distribute_project_status,
    generate_project_status,
)
from vcompany.tmux.session import TmuxManager

logger = logging.getLogger("vcompany.monitor.loop")


class MonitorLoop:
    """Main monitor loop. Checks all agents every 60s cycle."""

    CYCLE_INTERVAL = 60  # seconds, per D-01

    def __init__(
        self,
        project_dir: Path,
        config: ProjectConfig,
        tmux: TmuxManager,
        *,
        on_agent_dead: Callable[[str], None] | None = None,
        on_agent_stuck: Callable[[str], None] | None = None,
        on_plan_detected: Callable[[str, Path], None] | None = None,
        on_status_digest: Callable[[str], None] | None = None,
        digest_interval: int = 1800,
        cycle_interval: int | None = None,
    ) -> None:
        self._project_dir = Path(project_dir)
        self._config = config
        self._tmux = tmux
        self._on_agent_dead = on_agent_dead
        self._on_agent_stuck = on_agent_stuck
        self._on_plan_detected = on_plan_detected
        self._on_status_digest = on_status_digest
        self._digest_interval = digest_interval
        self._last_digest_time: float = 0.0
        self._last_status_content: str = ""
        self._cycle_interval = cycle_interval if cycle_interval is not None else self.CYCLE_INTERVAL
        self._running = False

        # Per-agent state persists between cycles
        self._agent_states: dict[str, AgentMonitorState] = {}
        for agent in config.agents:
            self._agent_states[agent.id] = AgentMonitorState(agent_id=agent.id)

    async def run(self) -> None:
        """Main loop. Runs _run_cycle + sleep until stopped."""
        self._running = True
        while self._running:
            await self._run_cycle()
            if not self._running:
                break
            if self._cycle_interval > 0:
                await asyncio.sleep(self._cycle_interval)

    def stop(self) -> None:
        """Graceful shutdown: stops after current cycle completes."""
        self._running = False

    async def _run_cycle(self) -> None:
        """Execute one monitoring cycle per D-01.

        1. Write heartbeat FIRST (Pitfall 6)
        2. Load agents.json registry for pane info
        3. Check all agents in parallel (asyncio.gather with return_exceptions=True)
        4. Log any exceptions but never propagate
        5. Generate and distribute PROJECT-STATUS.md
        """
        # Step 1: Heartbeat at cycle START (Pitfall 6)
        try:
            write_heartbeat(self._project_dir)
        except Exception:
            logger.exception("Failed to write heartbeat")

        # Step 2: Load agents.json for pane info
        registry = self._load_registry()

        # Step 3: Check all agents in parallel
        tasks = [self._check_agent(agent.id, registry) for agent in self._config.agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Step 4: Log any exceptions from gather
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agent_id = self._config.agents[i].id
                logger.error("Agent check raised for %s: %s", agent_id, result)

        # Step 5: Generate and distribute status
        try:
            status_content = generate_project_status(self._project_dir, self._config)
            distribute_project_status(self._project_dir, self._config, status_content)

            # Phase 6: Periodic status digest to Strategist per D-13
            now = time.monotonic()
            if self._on_status_digest and (now - self._last_digest_time >= self._digest_interval):
                # Only send if status changed per D-13
                if status_content != self._last_status_content:
                    try:
                        self._on_status_digest(status_content)
                    except Exception:
                        logger.exception("Failed to send status digest")
                    self._last_status_content = status_content
                self._last_digest_time = now
        except Exception:
            logger.exception("Failed to generate/distribute project status")

    async def _check_agent(self, agent_id: str, registry: AgentsRegistry) -> None:
        """Run all checks for a single agent. Wraps in try/except per D-01.

        Uses asyncio.to_thread for blocking git operations (Pitfall 2).
        """
        try:
            # Get pane and PID info from registry
            entry = registry.agents.get(agent_id)
            pane = entry.pane_id if entry else None
            agent_pid = entry.pid if entry else None
            clone_dir = self._project_dir / "clones" / agent_id

            # Liveness check — pass agent_pid for full PID validation per MON-02/D-02
            liveness = await asyncio.to_thread(
                check_liveness, agent_id, self._tmux, pane, agent_pid=agent_pid
            )
            if not liveness.passed and self._on_agent_dead:
                self._on_agent_dead(agent_id)

            # Stuck check
            stuck = await asyncio.to_thread(check_stuck, agent_id, clone_dir)
            if not stuck.passed and self._on_agent_stuck:
                self._on_agent_stuck(agent_id)

            # Plan gate check with persisted mtimes
            state = self._agent_states.get(agent_id)
            last_mtimes = state.last_plan_mtimes if state else {}
            plan_result, updated_mtimes = await asyncio.to_thread(
                check_plan_gate, agent_id, clone_dir, last_mtimes
            )

            # Update stored mtimes
            if state:
                state.last_plan_mtimes = updated_mtimes

            # Fire callback for each new plan
            if plan_result.new_plans and self._on_plan_detected:
                for plan_path in plan_result.new_plans:
                    self._on_plan_detected(agent_id, Path(plan_path))

        except Exception:
            logger.exception("Error checking agent %s", agent_id)

    def _load_registry(self) -> AgentsRegistry:
        """Load agents.json from project state directory."""
        agents_json_path = self._project_dir / "state" / "agents.json"
        if agents_json_path.exists():
            try:
                return AgentsRegistry.model_validate_json(agents_json_path.read_text())
            except Exception:
                logger.warning("Failed to load agents.json, using empty registry")
        return AgentsRegistry(project=self._config.project)
