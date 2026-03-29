"""HTTP signal endpoint for push-based agent readiness/idle signaling.

Replaces polling-based sentinel temp files with push-based HTTP signals.
Claude Code hooks POST to the daemon instead of writing to /tmp.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from aiohttp import web

logger = logging.getLogger("vcompany.daemon.signal_handler")


class SignalRouter:
    """Routes incoming agent signals to registered container callbacks."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[str], Awaitable[None]]] = {}

    def register(self, agent_id: str, handler: Callable[[str], Awaitable[None]]) -> None:
        """Register a signal handler for an agent. Handler receives signal type ('ready'|'idle')."""
        self._handlers[agent_id] = handler
        logger.debug("Signal handler registered for %s", agent_id)

    def unregister(self, agent_id: str) -> None:
        """Remove signal handler for an agent."""
        self._handlers.pop(agent_id, None)
        logger.debug("Signal handler unregistered for %s", agent_id)

    async def deliver(self, agent_id: str, signal_type: str) -> bool:
        """Deliver a signal to the registered handler. Returns False if no handler found."""
        handler = self._handlers.get(agent_id)
        if handler is None:
            logger.warning("No signal handler for agent %s (signal: %s)", agent_id, signal_type)
            return False
        await handler(signal_type)
        logger.info("Signal delivered: agent=%s type=%s", agent_id, signal_type)
        return True


def create_signal_app(router: SignalRouter) -> web.Application:
    """Create aiohttp app for the signal HTTP endpoint."""
    app = web.Application()

    async def handle_signal(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        agent_id = data.get("agent_id")
        signal_type = data.get("signal")  # "ready" or "idle"

        if not agent_id or not signal_type:
            return web.json_response(
                {"error": "missing agent_id or signal"}, status=400
            )

        if signal_type not in ("ready", "idle"):
            return web.json_response(
                {"error": f"invalid signal type: {signal_type}"}, status=400
            )

        delivered = await router.deliver(agent_id, signal_type)
        if not delivered:
            return web.json_response(
                {"error": f"no handler for agent {agent_id}"}, status=404
            )

        return web.json_response({"status": "ok"})

    app.router.add_post("/signal", handle_signal)
    return app
