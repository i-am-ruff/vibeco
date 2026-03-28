"""Delegation protocol — policy, request, result, and tracker models.

Enables ContinuousAgents to request task spawns through their supervisor
with policy enforcement (concurrent caps and hourly rate limits).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from pydantic import BaseModel


class DelegationPolicy(BaseModel):
    """Policy governing delegation limits for a supervisor.

    Args:
        max_concurrent_delegations: Max active delegated agents per requester.
        max_delegations_per_hour: Rate limit per requester (sliding window).
        allowed_agent_types: Agent types that can be delegated.
    """

    max_concurrent_delegations: int = 3
    max_delegations_per_hour: int = 10
    allowed_agent_types: list[str] = ["gsd"]


@dataclass
class DelegationRequest:
    """A request from an agent to delegate a task.

    Args:
        requester_id: ID of the agent requesting delegation.
        task_description: Human-readable description of the task.
        agent_type: Type of agent to spawn (must be in policy allowed_types).
        context_overrides: Optional overrides for the spawned agent's context.
    """

    requester_id: str
    task_description: str
    agent_type: str = "gsd"
    context_overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class DelegationResult:
    """Result of a delegation request.

    Args:
        approved: Whether the delegation was approved.
        agent_id: ID of the spawned agent (None if rejected).
        reason: Rejection reason (empty string if approved).
    """

    approved: bool
    agent_id: str | None = None
    reason: str = ""


class DelegationTracker:
    """Tracks active delegations and enforces policy limits.

    Uses a sliding window for rate limiting and per-requester concurrent caps.

    Args:
        policy: The delegation policy to enforce.
    """

    def __init__(self, policy: DelegationPolicy) -> None:
        self._policy = policy
        self._active: dict[str, set[str]] = {}
        self._history: list[float] = []
        self._clock = time.monotonic

    def can_delegate(self, requester_id: str, agent_type: str) -> tuple[bool, str]:
        """Check whether a delegation request is allowed.

        Args:
            requester_id: The requesting agent's ID.
            agent_type: The type of agent to spawn.

        Returns:
            Tuple of (allowed, reason). reason is empty string if allowed.
        """
        # Check agent type
        if agent_type not in self._policy.allowed_agent_types:
            return False, f"Agent type '{agent_type}' not in allowed types: {self._policy.allowed_agent_types}"

        # Check concurrent cap for this requester
        active_set = self._active.get(requester_id, set())
        if len(active_set) >= self._policy.max_concurrent_delegations:
            return False, (
                f"Concurrent delegation limit reached ({self._policy.max_concurrent_delegations}) "
                f"for requester {requester_id}"
            )

        # Check rate limit (sliding 1-hour window)
        now = self._clock()
        cutoff = now - 3600.0
        recent = [t for t in self._history if t > cutoff]
        if len(recent) >= self._policy.max_delegations_per_hour:
            return False, (
                f"Hourly rate limit reached ({self._policy.max_delegations_per_hour}/hour)"
            )

        return True, ""

    def record_delegation(self, requester_id: str, agent_id: str) -> None:
        """Record a new active delegation.

        Args:
            requester_id: The requesting agent's ID.
            agent_id: The spawned delegated agent's ID.
        """
        if requester_id not in self._active:
            self._active[requester_id] = set()
        self._active[requester_id].add(agent_id)
        self._history.append(self._clock())

    def record_completion(self, requester_id: str, agent_id: str) -> None:
        """Record that a delegated agent has completed (or crashed).

        Removes from active set, releasing concurrent capacity.
        No error if agent_id is not found.

        Args:
            requester_id: The requesting agent's ID.
            agent_id: The completed delegated agent's ID.
        """
        active_set = self._active.get(requester_id)
        if active_set is not None:
            active_set.discard(agent_id)
