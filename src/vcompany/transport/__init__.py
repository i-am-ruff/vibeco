"""Transport abstraction layer for agent execution environments."""

from vcompany.transport.channel_transport import ChannelTransport
try:
    from vcompany.transport.docker import DockerTransport
except ImportError:
    DockerTransport = None  # docker SDK not installed
from vcompany.transport.docker_channel import DockerChannelTransport
from vcompany.transport.local import LocalTransport
from vcompany.transport.native import NativeTransport
from vcompany.transport.protocol import AgentTransport, NoopTransport

__all__ = [
    "AgentTransport",
    "ChannelTransport",
    "DockerTransport",
    "DockerChannelTransport",
    "LocalTransport",
    "NativeTransport",
    "NoopTransport",
]
