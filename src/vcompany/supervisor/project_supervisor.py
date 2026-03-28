"""ProjectSupervisor -- mid-level supervisor managing agent containers for a project.

Thin subclass of Supervisor with sensible defaults for managing per-project
agent containers. Defaults to ONE_FOR_ONE strategy (independent agents).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from vcompany.container.child_spec import ChildSpec
from vcompany.supervisor.strategies import RestartStrategy
from vcompany.supervisor.supervisor import Supervisor


class ProjectSupervisor(Supervisor):
    """Manages agent containers for a single project.

    Args:
        project_id: Unique identifier for the project.
        child_specs: Ordered list of child specifications.
        strategy: Restart strategy (defaults to ONE_FOR_ONE).
        max_restarts: Maximum restarts within window.
        window_seconds: Sliding window size in seconds.
        parent: Parent supervisor for escalation.
        data_dir: Root directory for child container data.
    """

    def __init__(
        self,
        project_id: str,
        child_specs: list[ChildSpec],
        strategy: RestartStrategy = RestartStrategy.ONE_FOR_ONE,
        max_restarts: int = 3,
        window_seconds: int = 600,
        parent: Any | None = None,
        on_escalation: Callable[[str], Awaitable[None]] | None = None,
        data_dir: Path | None = None,
        tmux_manager: object | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self._project_id = project_id
        super().__init__(
            supervisor_id=f"project-{project_id}",
            strategy=strategy,
            child_specs=child_specs,
            max_restarts=max_restarts,
            window_seconds=window_seconds,
            parent=parent,
            on_escalation=on_escalation,
            data_dir=data_dir,
            tmux_manager=tmux_manager,
            project_dir=project_dir,
            session_name=f"vco-{project_id}",
        )

    @property
    def project_id(self) -> str:
        """The project identifier this supervisor manages."""
        return self._project_id
