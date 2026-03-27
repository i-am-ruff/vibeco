"""DegradedModeManager -- monitors Claude API health and manages degraded state.

When Claude servers are unreachable for consecutive checks, the system enters
degraded mode: existing containers stay alive, new dispatches are blocked,
and the owner is notified. The system auto-recovers when service returns.

Supports both active probing (background health check loop) and passive
operational detection (callers report success/failure of API calls).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


class DegradedModeManager:
    """Manages degraded mode transitions based on health check results.

    Args:
        health_check: Async callable returning True if healthy, False if not.
        check_interval: Seconds between health checks in the background loop.
        failure_threshold: Consecutive failures before entering degraded mode.
        recovery_threshold: Consecutive successes before recovering from degraded.
        on_degraded: Async callback invoked when entering degraded mode.
        on_recovered: Async callback invoked when recovering from degraded mode.
    """

    def __init__(
        self,
        health_check: Callable[[], Awaitable[bool]],
        check_interval: float = 60.0,
        failure_threshold: int = 3,
        recovery_threshold: int = 2,
        on_degraded: Callable[[], Awaitable[None]] | None = None,
        on_recovered: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._health_check = health_check
        self._check_interval = check_interval
        self._failure_threshold = failure_threshold
        self._recovery_threshold = recovery_threshold
        self._on_degraded = on_degraded
        self._on_recovered = on_recovered

        self._state: str = "normal"
        self._consecutive_failures: int = 0
        self._consecutive_successes: int = 0
        self._task: asyncio.Task | None = None

    @property
    def is_degraded(self) -> bool:
        """True when the system is in degraded mode."""
        return self._state == "degraded"

    @property
    def state(self) -> str:
        """Current state: 'normal' or 'degraded'."""
        return self._state

    async def start(self) -> None:
        """Start the background health check loop."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._check_loop())
        logger.info("DegradedModeManager started (interval=%.1fs)", self._check_interval)

    async def stop(self) -> None:
        """Stop the background health check loop."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("DegradedModeManager stopped")

    async def _check_loop(self) -> None:
        """Background loop that periodically probes health."""
        while True:
            try:
                healthy = await self._health_check()
            except Exception:
                healthy = False
            await self._record_result(healthy)
            await asyncio.sleep(self._check_interval)

    async def _record_result(self, healthy: bool) -> None:
        """Record a health check result and transition state if needed.

        Args:
            healthy: True if the check succeeded, False otherwise.
        """
        if healthy:
            self._consecutive_successes += 1
            self._consecutive_failures = 0
            if (
                self._state == "degraded"
                and self._consecutive_successes >= self._recovery_threshold
            ):
                self._state = "normal"
                self._consecutive_successes = 0
                logger.info("System recovered from degraded mode")
                if self._on_recovered is not None:
                    await self._on_recovered()
        else:
            self._consecutive_failures += 1
            self._consecutive_successes = 0
            if (
                self._state == "normal"
                and self._consecutive_failures >= self._failure_threshold
            ):
                self._state = "degraded"
                self._consecutive_failures = 0
                logger.warning("System entered degraded mode")
                if self._on_degraded is not None:
                    await self._on_degraded()

    async def record_operational_failure(self) -> None:
        """Record an operational API failure (passive detection).

        Called by external code when a Claude API call fails during normal
        operation. Contributes to the failure counter alongside active probing.
        """
        await self._record_result(False)

    async def record_operational_success(self) -> None:
        """Record an operational API success (passive detection).

        Called by external code when a Claude API call succeeds. Contributes
        to the success counter for recovery detection.
        """
        await self._record_result(True)
