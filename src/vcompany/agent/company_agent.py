"""CompanyAgent -- Discord-message-driven container for Strategist role (TYPE-05).

Company-scoped (no project_id), survives project restarts, holds cross-project
state in memory_store. Message handling delegated to StrategistConversationHandler
via base container.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport
from vcompany.strategist.conversation import StrategistConversation

if TYPE_CHECKING:
    from vcompany.container.communication import CommunicationPort

logger = logging.getLogger("vcompany.agent.company_agent")


class CompanyAgent(AgentContainer):
    """Thin wrapper: EventDrivenLifecycle + Strategist conversation management.

    Message handling is delegated to StrategistConversationHandler via base container.
    state/inner_state inherited from base container (OrderedSet handling).
    _send_discord inherited from base container (D-04).

    Args:
        context: Immutable agent metadata (project_id should be None).
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
        # Strategist conversation (wired via initialize_conversation())
        self._conversation: StrategistConversation | None = None

    # --- Conversation ---

    def initialize_conversation(self, persona_path: Path | None = None) -> None:
        """Create the StrategistConversation owned by this container.

        Passes the container's transport for subprocess abstraction.

        Args:
            persona_path: Path to STRATEGIST-PERSONA.md, or None for default.
        """
        self._conversation = StrategistConversation(
            persona_path=persona_path,
            transport=self._transport,
        )
        logger.info("StrategistConversation initialized (persona=%s)", persona_path)

    # --- Cross-Project State ---

    async def get_cross_project_state(self, key: str) -> str | None:
        """Read a cross-project state value from memory_store.

        Cross-project keys are prefixed with ``xp:`` to distinguish from
        standard per-agent keys.
        """
        return await self.memory.get(f"xp:{key}")

    async def set_cross_project_state(self, key: str, value: str) -> None:
        """Write a cross-project state value to memory_store.

        Cross-project keys are prefixed with ``xp:`` to distinguish from
        standard per-agent keys.
        """
        await self.memory.set(f"xp:{key}", value)
