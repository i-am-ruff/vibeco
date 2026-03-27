"""Tests for CommunicationPort and Message — CONT-06."""

from datetime import datetime, timezone

from vcompany.container.communication import CommunicationPort, Message


class TestMessage:
    """Message dataclass has required fields."""

    def test_message_fields(self):
        now = datetime.now(timezone.utc)
        msg = Message(source="agent-1", target="agent-2", content="hello", timestamp=now)
        assert msg.source == "agent-1"
        assert msg.target == "agent-2"
        assert msg.content == "hello"
        assert msg.timestamp == now


class TestCommunicationPort:
    """CONT-06: CommunicationPort is a Protocol."""

    def test_protocol_is_runtime_checkable(self):
        assert hasattr(CommunicationPort, "__protocol_attrs__") or hasattr(
            CommunicationPort, "__abstractmethods__"
        ) or isinstance(CommunicationPort, type)
        # Runtime checkable means we can use isinstance()
        assert callable(getattr(CommunicationPort, "__instancecheck__", None))

    def test_class_implementing_protocol_satisfies_it(self):

        class GoodPort:
            async def send_message(self, target: str, content: str) -> bool:
                return True

            async def receive_message(self) -> Message | None:
                return None

        assert isinstance(GoodPort(), CommunicationPort)

    def test_class_missing_send_message_does_not_satisfy(self):

        class BadPort:
            async def receive_message(self) -> Message | None:
                return None

        assert not isinstance(BadPort(), CommunicationPort)
