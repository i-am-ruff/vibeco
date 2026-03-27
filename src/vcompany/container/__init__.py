"""Agent container foundation -- lifecycle, context, health, communication."""

from vcompany.container.communication import CommunicationPort, Message
from vcompany.container.context import ContainerContext
from vcompany.container.health import HealthReport
from vcompany.container.state_machine import ContainerLifecycle

__all__ = [
    "ContainerLifecycle",
    "ContainerContext",
    "HealthReport",
    "CommunicationPort",
    "Message",
]
