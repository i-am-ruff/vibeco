"""TaskAgent — lightweight company-scoped agent for Strategist-dispatched tasks.

Runs Claude Code interactively in tmux (like GSD agents) but without GSD
workflow, phases, or plan gates.  The Strategist dispatches it with a task
prompt, communicates via Discord (messages relayed to/from the tmux pane),
and dismisses it when done.

Lifecycle:
  1. Dispatched by Strategist → scratch dir created, Claude launched in tmux
  2. Agent works autonomously, posts results via /vco:send
  3. Strategist replies → relayed to agent's tmux pane
  4. Agent finishes → runs /vco:finish (writes marker, exits)
  5. Container detects clean finish (marker) vs crash (no marker)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport

if TYPE_CHECKING:
    from vcompany.container.communication import CommunicationPort

logger = logging.getLogger("vcompany.agent.task_agent")

# Scratch directory root for task agents
TASKS_DIR = Path.home() / "vco-tasks"


class TaskAgent(AgentContainer):
    """Company-scoped task agent running Claude Code in tmux.

    Unlike GSD agents, TaskAgents:
    - Have no phase FSM or plan gates
    - Work in a scratch directory, not a project clone
    - Communicate with the Strategist via Discord + tmux relay
    - Use TEMPORARY restart policy (no auto-restart on crash)
    - Track lightweight inner state via a ``.phase`` marker file

    Path layout: the ``project_dir`` IS the working directory — no
    ``clones/`` subdirectory. System prompt is handled by CLAUDE.md
    auto-discovery, not ``--append-system-prompt-file``.
    """

    # --- Path Properties (override base class GSD-centric defaults) ---

    @property
    def working_dir(self) -> Path:
        """The scratch directory this agent works in (= project_dir)."""
        if self._project_dir is not None:
            return self._project_dir
        return TASKS_DIR / self.context.agent_id

    @property
    def system_prompt_path(self) -> Path | None:
        """None — task agents use CLAUDE.md auto-discovery, not --append-system-prompt-file."""
        return None

    # --- Finish & Phase Tracking ---

    @property
    def _finished_marker_path(self) -> Path:
        """Path to the clean-finish marker file."""
        return self.working_dir / ".finished"

    @property
    def _phase_path(self) -> Path:
        """Path to the lightweight phase marker file."""
        return self.working_dir / ".phase"

    @property
    def is_finished(self) -> bool:
        """True if the agent completed cleanly (marker file exists)."""
        return self._finished_marker_path.exists()

    @property
    def inner_state(self) -> str | None:
        """Lightweight phase tracking via ``.phase`` marker file.

        The agent (or its scripts) writes the current phase to ``.phase``.
        Returns None if no phase file exists (agent hasn't started tracking).
        """
        try:
            return self._phase_path.read_text().strip() or None
        except FileNotFoundError:
            return None

    # --- Health ---

    def health_report(self) -> HealthReport:
        """Health report with clean-finish awareness.

        If the pane is dead but ``.finished`` marker exists, report as
        ``stopped`` (clean completion) instead of ``errored`` (crash).
        """
        report = super().health_report()
        if report.state == "errored" and self.is_finished:
            report = report.model_copy(update={"state": "stopped"})
        return report

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start the task agent in tmux."""
        self._lifecycle.start()
        await self.memory.open()
        if self._tmux is not None and self._needs_tmux_session:
            await self._launch_tmux_session()

    async def stop(self) -> None:
        """Stop the task agent and clean up signal files."""
        await super().stop()
        # Don't delete working_dir — Strategist may want to read REPORT.md
