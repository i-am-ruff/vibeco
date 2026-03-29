"""Transport abstraction layer for agent execution environments."""

from vcompany.transport.docker import DockerTransport
from vcompany.transport.local import LocalTransport
from vcompany.transport.protocol import AgentTransport, NoopTransport

__all__ = ["AgentTransport", "DockerTransport", "LocalTransport", "NoopTransport"]
