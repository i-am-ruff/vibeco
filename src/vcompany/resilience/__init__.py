"""Resilience utilities for vCompany.

Exports the priority message queue used for all outbound Discord messaging.
"""

from vcompany.resilience.message_queue import (
    MessagePriority,
    MessageQueue,
    QueuedMessage,
    RateLimited,
)

__all__ = [
    "MessagePriority",
    "MessageQueue",
    "QueuedMessage",
    "RateLimited",
]
