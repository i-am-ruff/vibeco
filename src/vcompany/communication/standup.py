"""Standup ritual: per-agent blocking interlock with thread-based communication.

Agents are blocked (via asyncio.Future) until owner explicitly releases them.
No timeout -- owner decides when each agent resumes per D-11.

Owner messages in standup threads are routed to agent tmux panes via /gsd:quick
per COMM-05. Agent responds by updating ROADMAP.md or STATE.md per COMM-06/D-13.

References: COMM-03 (standup threads), COMM-04 (thread messages), COMM-05 (routing),
COMM-06 (agent updates), D-11 (blocking interlock), D-12 (owner reprioritize).
"""

from __future__ import annotations

import asyncio
from typing import Any

from vcompany.shared.logging import get_logger

logger = get_logger("standup")


class StandupSession:
    """Tracks active standup state with per-agent blocking per D-11.

    Agents are blocked (via asyncio.Future) until owner explicitly releases them.
    No timeout -- owner decides when each agent resumes.
    """

    def __init__(self, tmux: Any | None = None) -> None:
        self._pending: dict[str, asyncio.Future[None]] = {}  # agent_id -> release future
        self._threads: dict[str, int] = {}  # agent_id -> thread_id
        self._tmux = tmux

    @property
    def is_active(self) -> bool:
        """True when any agents are blocked in standup."""
        return len(self._pending) > 0

    async def block_agent(self, agent_id: str) -> None:
        """Block until owner releases this agent."""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[agent_id] = future
        await future  # Blocks until release_agent() called

    def release_agent(self, agent_id: str) -> None:
        """Unblock a specific agent per D-11."""
        if agent_id in self._pending and not self._pending[agent_id].done():
            self._pending[agent_id].set_result(None)
        self._pending.pop(agent_id, None)

    def release_all(self) -> None:
        """Release all blocked agents."""
        for agent_id in list(self._pending.keys()):
            self.release_agent(agent_id)

    def register_thread(self, agent_id: str, thread_id: int) -> None:
        """Map agent to its standup thread."""
        self._threads[agent_id] = thread_id

    def get_agent_for_thread(self, thread_id: int) -> str | None:
        """Look up which agent owns a thread."""
        for agent_id, tid in self._threads.items():
            if tid == thread_id:
                return agent_id
        return None

    async def route_message_to_agent(
        self, agent_id: str, message: str, pane_id: str
    ) -> bool:
        """Route an owner message from a standup thread to the agent's tmux pane.

        Sends as /gsd:quick per COMM-05 so the agent processes it as a task.
        Per D-12: owner can reprioritize, ask questions, change scope.
        Per D-13/COMM-06: agent updates ROADMAP.md or STATE.md based on feedback.
        """
        if self._tmux is None:
            return False
        prompt = (
            f"/gsd:quick Owner standup message: {message}. "
            "Update ROADMAP.md or STATE.md if this changes your priorities or scope."
        )
        sent = self._tmux.send_command(pane_id, prompt)
        if sent:
            logger.info("Routed standup message to %s (pane %s)", agent_id, pane_id)
        else:
            logger.error("Failed to route standup message to %s (pane %s)", agent_id, pane_id)
        return sent
