"""CommunicationPort protocol and Message dataclass (CONT-06).

Defines the interface for container-to-container communication.
No file IPC, no in-memory callbacks -- Discord implements this in later phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class Message:
    """A message passed between containers via a CommunicationPort."""

    source: str
    target: str
    content: str
    timestamp: datetime


@runtime_checkable
class CommunicationPort(Protocol):
    """Abstract communication interface for containers.

    Implementations are provided in later phases (Discord-backed).
    Containers hold a reference to a CommunicationPort and never
    import discord.py or know about file paths directly.
    """

    async def send_message(self, target: str, content: str) -> bool:
        """Send a message to a target container. Returns True on success."""
        ...

    async def receive_message(self) -> Message | None:
        """Receive the next pending message, or None if queue is empty."""
        ...
