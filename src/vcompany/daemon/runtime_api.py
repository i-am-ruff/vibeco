"""RuntimeAPI -- typed gateway to CompanyRoot operations.

All methods are async. No discord.py imports. Uses CommunicationPort
for any outbound messaging. The daemon layer accesses CompanyRoot
exclusively through this class.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from vcompany.daemon.comm import CommunicationPort, CreateChannelPayload

if TYPE_CHECKING:
    from vcompany.supervisor.company_root import CompanyRoot

logger = logging.getLogger("vcompany.daemon.runtime_api")


class RuntimeAPI:
    """Typed gateway to CompanyRoot operations.

    Provides async methods for all agent lifecycle and status operations.
    Uses CommunicationPort (via lazy getter) for outbound messaging --
    no discord.py imports allowed in this module.
    """

    def __init__(
        self,
        company_root: CompanyRoot,
        comm_port_getter: Callable[[], CommunicationPort],
    ) -> None:
        self._root = company_root
        self._get_comm = comm_port_getter
        self._channel_ids: dict[str, str] = {}

    async def hire(
        self, agent_id: str, template: str = "generic"
    ) -> str:
        """Hire a company-level agent with optional channel creation.

        Creates a task channel via CommunicationPort before hiring,
        then delegates to CompanyRoot.hire() (no guild param -- channel
        creation is handled through the communication port).

        Returns:
            The agent_id of the hired container.
        """
        # Create channel via comm port (platform-agnostic)
        result = await self._get_comm().create_channel(
            CreateChannelPayload(
                category_name="vco-tasks",
                channel_name=f"task-{agent_id}",
            )
        )
        if result is not None:
            self._channel_ids[f"task-{agent_id}"] = result.channel_id
            logger.info(
                "Created channel task-%s (id=%s)", agent_id, result.channel_id
            )

        container = await self._root.hire(agent_id, template=template)
        return container.context.agent_id

    async def give_task(self, agent_id: str, task: str) -> None:
        """Assign a task to an existing agent.

        Finds the container by agent_id across company agents and
        project supervisors, then calls give_task on it.

        Raises:
            KeyError: If agent_id is not found.
        """
        container = await self._root._find_container(agent_id)
        if container is None:
            raise KeyError(f"Agent {agent_id!r} not found")
        await container.give_task(task)

    async def dismiss(self, agent_id: str) -> None:
        """Dismiss (stop) a company-level agent.

        Delegates to CompanyRoot.dismiss().

        Raises:
            KeyError: If agent_id is not found in company agents.
        """
        await self._root.dismiss(agent_id)

    async def status(self) -> dict:
        """Return a status summary of projects and company agents.

        Returns:
            Dict with 'projects' (project_id -> agent count) and
            'company_agents' (list of agent IDs).
        """
        return {
            "projects": {
                pid: {"agents": len(ps.children)}
                for pid, ps in self._root.projects.items()
            },
            "company_agents": list(self._root._company_agents.keys()),
        }

    async def health_tree(self) -> dict:
        """Return the full company health tree as a dict.

        Calls CompanyRoot.health_tree() and serializes to dict via
        pydantic model_dump().
        """
        return self._root.health_tree().model_dump()

    def register_channels(self, channels: dict[str, str]) -> None:
        """Register channel name -> ID mappings.

        Used during bot startup to populate known channel IDs.

        Args:
            channels: Dict of channel_name -> channel_id.
        """
        self._channel_ids.update(channels)

    def get_channel_id(self, name: str) -> str | None:
        """Look up a channel ID by name.

        Returns:
            The channel ID string, or None if not registered.
        """
        return self._channel_ids.get(name)
