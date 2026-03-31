"""Tests for vco-worker: WorkerConfig validation and channel protocol round-trip."""

import pytest
from pydantic import ValidationError

from vco_worker.config import WorkerConfig
from vco_worker.channel import encode, decode_worker, SignalMessage


class TestWorkerConfigMinimal:
    """WorkerConfig validates with only handler_type."""

    def test_minimal_config(self):
        config = WorkerConfig(handler_type="session")
        assert config.handler_type == "session"

    def test_defaults(self):
        config = WorkerConfig(handler_type="session")
        assert config.agent_type == "gsd"
        assert config.data_dir == "/tmp/vco-worker/data"
        assert config.capabilities == []
        assert config.gsd_command is None
        assert config.persona is None
        assert config.env_vars == {}
        assert config.uses_tmux is False


class TestWorkerConfigFull:
    """WorkerConfig validates with all fields populated."""

    def test_full_config(self):
        config = WorkerConfig(
            handler_type="conversation",
            agent_type="event_driven",
            capabilities=["code", "research"],
            gsd_command="/usr/bin/gsd",
            persona="Senior Engineer",
            env_vars={"GITHUB_TOKEN": "xxx"},
            data_dir="/data/agent-1",
            project_id="proj-123",
            project_dir="/home/dev/project",
            project_session_name="proj-session",
            uses_tmux=True,
        )
        assert config.handler_type == "conversation"
        assert config.agent_type == "event_driven"
        assert config.capabilities == ["code", "research"]
        assert config.gsd_command == "/usr/bin/gsd"
        assert config.persona == "Senior Engineer"
        assert config.env_vars == {"GITHUB_TOKEN": "xxx"}
        assert config.data_dir == "/data/agent-1"
        assert config.project_id == "proj-123"
        assert config.uses_tmux is True


class TestWorkerConfigValidation:
    """WorkerConfig rejects invalid input."""

    def test_missing_handler_type_raises(self):
        with pytest.raises(ValidationError):
            WorkerConfig()  # type: ignore[call-arg]


class TestChannelProtocolRoundTrip:
    """Channel protocol encode/decode round-trip inside worker package."""

    def test_signal_message_round_trip(self):
        original = SignalMessage(signal="ready", detail="all systems go")
        encoded = encode(original)
        decoded = decode_worker(encoded)
        assert decoded.signal == "ready"
        assert decoded.detail == "all systems go"
        assert decoded.type == "signal"

    def test_encode_produces_ndjson(self):
        msg = SignalMessage(signal="test")
        encoded = encode(msg)
        assert encoded.endswith(b"\n")
        # Single line of JSON
        lines = encoded.strip().split(b"\n")
        assert len(lines) == 1
