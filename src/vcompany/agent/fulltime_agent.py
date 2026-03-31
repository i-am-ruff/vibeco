"""FulltimeAgent -- Discord-message-driven container for PM role (TYPE-04).

Reacts to inbound Discord messages via handler (PMTransientHandler). Scoped to
a project (has project_id). Persists state via memory_store for crash recovery.

Extended with backlog operations: routes task lifecycle events through Discord
messages to ProjectStateManager for PM-owned project state coordination.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle
from vcompany.autonomy.backlog import BacklogItem, BacklogQueue
from vcompany.autonomy.project_state import ProjectStateManager
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport

if TYPE_CHECKING:
    from vcompany.container.communication import CommunicationPort

logger = logging.getLogger("vcompany.agent.fulltime_agent")


class FulltimeAgent(AgentContainer):
    """Thin wrapper: EventDrivenLifecycle + PM domain methods.

    Message handling delegated to PMTransientHandler via base container.
    state/inner_state inherited from base container (OrderedSet handling).
    _send_discord inherited from base container (D-04).
    Stuck detector lifecycle managed by handler on_start/on_stop.

    Args:
        context: Immutable agent metadata (must have project_id set).
        data_dir: Root directory for persistent data.
        comm_port: Optional communication channel.
        on_state_change: Optional callback invoked with HealthReport after
            every lifecycle transition.
    """

    def __init__(
        self,
        context: ContainerContext,
        data_dir: Path,
        comm_port: CommunicationPort | None = None,
        on_state_change: Callable[[HealthReport], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(context, data_dir, comm_port, on_state_change, **kwargs)
        # Override parent's ContainerLifecycle with EventDrivenLifecycle
        self._lifecycle = EventDrivenLifecycle(model=self, state_field="_fsm_state")
        # Backlog and project state (wired after construction, not in __init__ args)
        self.backlog: BacklogQueue | None = None
        self._project_state: ProjectStateManager | None = None

        # Stuck detector state (PMAC-05) -- accessed by PMTransientHandler
        self._agent_state_timestamps: dict[str, tuple[str, float]] = {}
        self._stuck_threshold_seconds: float = 1800.0  # 30 min default
        self._stuck_check_interval: float = 60.0  # poll every 60s
        self._stuck_detected_agents: set[str] = set()
        self._stuck_detector_task: asyncio.Task[None] | None = None

    # --- PM Action Methods ---

    async def trigger_integration_review(self) -> None:
        """Trigger integration review via Discord message (PMAC-01)."""
        logger.info("PM triggering integration review")
        await self._send_discord(
            "integration",
            "[Integration Review] PM requests integration review",
        )

    async def inject_backlog_item(self, item: BacklogItem, urgent: bool = False) -> None:
        """Inject an item into the backlog (PMAC-02)."""
        if self.backlog is None:
            logger.warning("Cannot inject backlog item -- backlog not wired")
            return
        if urgent:
            await self.backlog.insert_urgent(item)
            logger.info("Injected urgent backlog item: %s", item.item_id)
        else:
            await self.backlog.append(item)
            logger.info("Appended backlog item: %s", item.item_id)

    async def escalate_to_strategist(
        self, agent_id: str, question: str, confidence: float = 0.0
    ) -> None:
        """Escalate a decision to the Strategist via Discord (PMAC-04)."""
        logger.info("PM escalating to Strategist for %s: %s", agent_id, question[:80])
        await self._send_discord(
            "strategist",
            f"[PM Escalation] Agent {agent_id} asks: {question}\n"
            f"PM confidence: {confidence:.0%}. Please provide your assessment.",
        )
