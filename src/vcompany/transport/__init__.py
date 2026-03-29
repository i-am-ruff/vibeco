"""Transport abstraction layer for agent execution environments."""

from vcompany.transport.protocol import AgentTransport, NoopTransport

__all__ = ["AgentTransport", "NoopTransport"]
