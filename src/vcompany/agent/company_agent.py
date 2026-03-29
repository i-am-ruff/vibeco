"""CompanyAgent -- Discord-message-driven container for Strategist role (TYPE-05).

Company-scoped (no project_id), survives project restarts, holds cross-project
state in memory_store. Receives Discord messages via receive_discord_message()
and forwards to StrategistConversation for processing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from statemachine.orderedset import OrderedSet

from vcompany.agent.event_driven_lifecycle import EventDrivenLifecycle
from vcompany.container.container import AgentContainer
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport
from vcompany.models.messages import MessageContext
from vcompany.strategist.conversation import StrategistConversation

if TYPE_CHECKING:
    from vcompany.container.communication import CommunicationPort, SendMessagePayload

logger = logging.getLogger("vcompany.agent.company_agent")


class CompanyAgent(AgentContainer):
    """Discord-message-driven agent for Strategist role (TYPE-05).

    Company-scoped (context.project_id should be None), survives project
    restarts, holds cross-project state in memory_store. Receives Discord
    messages and forwards to StrategistConversation.

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

    # --- Properties (override parent for compound state handling) ---

    @property
    def state(self) -> str:
        """Current outer lifecycle state as a plain string."""
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            return str(list(val)[0])
        return str(val)

    @property
    def inner_state(self) -> str | None:
        """Sub-state when in running compound state (listening/processing)."""
        val = self._fsm_state
        if isinstance(val, OrderedSet):
            items = list(val)
            if len(items) >= 2:
                return str(items[1])
        return None

    # --- Conversation ---

    def initialize_conversation(self, persona_path: Path | None = None) -> None:
        """Create the StrategistConversation owned by this container.

        Args:
            persona_path: Path to STRATEGIST-PERSONA.md, or None for default.
        """
        self._conversation = StrategistConversation(persona_path=persona_path)
        logger.info("StrategistConversation initialized (persona=%s)", persona_path)

    # --- Discord Message Handling ---

    async def receive_discord_message(self, context: MessageContext) -> None:
        """Process an inbound Discord message routed to the Strategist.

        Forwards the message content to the StrategistConversation and posts
        the response back to Discord via _send_discord().

        Args:
            context: Message context with sender, channel, content.
        """
        self._lifecycle.start_processing()
        try:
            if self._conversation is None:
                logger.warning(
                    "Strategist received message but conversation not initialized"
                )
                return

            response = await self._conversation.send(context.content)
            await self._send_discord(context.channel, response)
            logger.info(
                "Strategist responded to message from %s (len=%d)",
                context.sender, len(response),
            )
        finally:
            self._lifecycle.done_processing()

    # --- Discord Output ---

    async def _send_discord(self, channel_name: str, content: str) -> None:
        """Send a message to a Discord channel via the CommunicationPort.

        Uses self.comm_port (from parent AgentContainer) if available.
        Channel name is used as a logical identifier; the CommunicationPort
        adapter handles name-to-id resolution.

        Args:
            channel_name: Logical channel name (e.g. "strategist").
            content: Message text to send.
        """
        if self.comm_port is None:
            logger.warning("Cannot send Discord message -- no comm_port wired")
            return
        from vcompany.container.communication import SendMessagePayload

        payload = SendMessagePayload(channel_id=channel_name, content=content)
        await self.comm_port.send_message(payload)

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

    # --- Lifecycle Overrides ---

    async def start(self) -> None:
        """Transition to running and open memory."""
        await super().start()

    async def stop(self) -> None:
        """Delegate to parent stop."""
        await super().stop()

    async def sleep(self) -> None:
        """Transition to sleeping."""
        await super().sleep()

    async def error(self) -> None:
        """Transition to errored."""
        await super().error()
