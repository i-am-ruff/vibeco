"""Tests for StrategistConversation and Knowledge Transfer."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock helpers for Anthropic SDK
# ---------------------------------------------------------------------------

class MockStreamResponse:
    """Mock for client.messages.stream() async context manager."""

    def __init__(self, text_chunks: list[str]):
        self._chunks = text_chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    @property
    def text_stream(self):
        return self._aiter_chunks()

    async def _aiter_chunks(self):
        for chunk in self._chunks:
            yield chunk


class MockTokenCountResult:
    """Mock for count_tokens() return value."""

    def __init__(self, input_tokens: int):
        self.input_tokens = input_tokens


def make_mock_client(
    text_chunks: list[str] | None = None,
    token_count: int = 100,
):
    """Create a mock AsyncAnthropic client."""
    if text_chunks is None:
        text_chunks = ["Hello", " world"]

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(
        return_value=MockStreamResponse(text_chunks)
    )
    client.messages.count_tokens = AsyncMock(
        return_value=MockTokenCountResult(token_count)
    )
    return client


# ---------------------------------------------------------------------------
# Tests for StrategistConversation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_appends_user_and_assistant_messages():
    """send() appends user message and assistant response to messages list."""
    from vcompany.strategist.conversation import StrategistConversation

    client = make_mock_client(text_chunks=["Hi", " there"])
    conv = StrategistConversation(client=client)

    chunks = []
    async for chunk in conv.send("Hello"):
        chunks.append(chunk)

    messages = conv.messages
    assert len(messages) == 2
    assert messages[0] == {"role": "user", "content": "Hello"}
    assert messages[1] == {"role": "assistant", "content": "Hi there"}


@pytest.mark.asyncio
async def test_send_yields_text_chunks():
    """send() yields text chunks from streaming response."""
    from vcompany.strategist.conversation import StrategistConversation

    client = make_mock_client(text_chunks=["chunk1", "chunk2", "chunk3"])
    conv = StrategistConversation(client=client)

    chunks = []
    async for chunk in conv.send("test"):
        chunks.append(chunk)

    assert chunks == ["chunk1", "chunk2", "chunk3"]


@pytest.mark.asyncio
async def test_messages_list_grows_persistently():
    """Messages list grows with each send() call (persistent conversation)."""
    from vcompany.strategist.conversation import StrategistConversation

    client = make_mock_client(text_chunks=["reply"])
    conv = StrategistConversation(client=client)

    # First send
    async for _ in conv.send("first"):
        pass

    # Reset the stream mock for second call
    client.messages.stream = MagicMock(
        return_value=MockStreamResponse(["second reply"])
    )

    async for _ in conv.send("second"):
        pass

    messages = conv.messages
    assert len(messages) == 4  # user1, assistant1, user2, assistant2
    assert messages[0]["content"] == "first"
    assert messages[1]["content"] == "reply"
    assert messages[2]["content"] == "second"
    assert messages[3]["content"] == "second reply"


@pytest.mark.asyncio
async def test_token_check_triggers_kt_on_limit():
    """Token check triggers KT when estimate exceeds TOKEN_LIMIT (800_000)."""
    from vcompany.strategist.conversation import StrategistConversation

    # Set up client that returns token count above limit
    client = make_mock_client(text_chunks=["ok"], token_count=850_000)
    conv = StrategistConversation(client=client)

    # Seed some messages to make rough estimate high enough to trigger count_tokens
    # Each char ~ 1/4 token, so we need ~2.8M chars to reach 700K rough estimate
    big_content = "x" * 2_900_000
    conv._messages = [{"role": "user", "content": big_content}]

    async for _ in conv.send("trigger KT"):
        pass

    # After KT, messages should be reset with KT document as first message
    messages = conv.messages
    assert len(messages) == 2  # KT user message + assistant reply to "trigger KT" after KT
    assert "[KNOWLEDGE TRANSFER]" in messages[0]["content"]


@pytest.mark.asyncio
async def test_after_kt_messages_reset_with_kt_doc():
    """After KT, messages list is reset with KT document as first user message."""
    from vcompany.strategist.conversation import StrategistConversation

    client = make_mock_client(text_chunks=["acknowledged"], token_count=850_000)
    conv = StrategistConversation(client=client)

    # Seed messages to trigger KT
    big_content = "x" * 3_000_000
    conv._messages = [
        {"role": "user", "content": big_content},
        {"role": "assistant", "content": "some decision made"},
    ]

    async for _ in conv.send("new question"):
        pass

    messages = conv.messages
    # First message should be KT document
    assert messages[0]["role"] == "user"
    assert "Knowledge Transfer" in messages[0]["content"]
    # Token count should be reset
    assert conv.token_count == 0


@pytest.mark.asyncio
async def test_asyncio_lock_prevents_concurrent_sends():
    """asyncio.Lock prevents concurrent send() calls (second call waits)."""
    from vcompany.strategist.conversation import StrategistConversation

    execution_order = []

    class SlowStreamResponse:
        def __init__(self, label):
            self._label = label

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        @property
        def text_stream(self):
            return self._aiter()

        async def _aiter(self):
            execution_order.append(f"start-{self._label}")
            await asyncio.sleep(0.05)
            yield f"response-{self._label}"
            execution_order.append(f"end-{self._label}")

    call_count = 0

    def make_stream(**kwargs):
        nonlocal call_count
        call_count += 1
        return SlowStreamResponse(str(call_count))

    client = make_mock_client()
    client.messages.stream = make_stream
    conv = StrategistConversation(client=client)

    async def send_msg(content):
        async for _ in conv.send(content):
            pass

    # Launch two concurrent sends
    await asyncio.gather(send_msg("first"), send_msg("second"))

    # With lock, first should complete before second starts
    assert execution_order[0] == "start-1"
    assert execution_order[1] == "end-1"
    assert execution_order[2] == "start-2"
    assert execution_order[3] == "end-2"


@pytest.mark.asyncio
async def test_missing_persona_uses_default(tmp_path: Path):
    """Missing STRATEGIST-PERSONA.md uses default persona gracefully per Pitfall 7."""
    from vcompany.strategist.conversation import (
        DEFAULT_PERSONA,
        StrategistConversation,
    )

    nonexistent = tmp_path / "STRATEGIST-PERSONA.md"
    client = make_mock_client()
    conv = StrategistConversation(client=client, persona_path=nonexistent)

    assert conv._system_prompt == DEFAULT_PERSONA


@pytest.mark.asyncio
async def test_persona_loaded_from_file(tmp_path: Path):
    """Persona loaded from file when it exists."""
    from vcompany.strategist.conversation import StrategistConversation

    persona_file = tmp_path / "STRATEGIST-PERSONA.md"
    persona_file.write_text("You are a genius CEO.")
    client = make_mock_client()
    conv = StrategistConversation(client=client, persona_path=persona_file)

    assert conv._system_prompt == "You are a genius CEO."


# ---------------------------------------------------------------------------
# Tests for generate_knowledge_transfer
# ---------------------------------------------------------------------------


def test_generate_knowledge_transfer_has_required_sections():
    """generate_knowledge_transfer produces markdown with required sections."""
    from vcompany.strategist.knowledge_transfer import generate_knowledge_transfer

    messages = [
        {"role": "user", "content": "What should we build?"},
        {"role": "assistant", "content": "I decided we should build X. Decision: go with React."},
        {"role": "user", "content": "Good idea."},
        {"role": "assistant", "content": "Thanks, let me elaborate on the architecture."},
    ]
    system_prompt = "You are a strategic advisor."
    token_count = 500_000

    result = generate_knowledge_transfer(messages, system_prompt, token_count)

    assert "# Knowledge Transfer" in result
    assert "## Token Count at Transfer" in result
    assert "500000" in result or "500,000" in result
    assert "## Conversation Summary" in result
    assert "## Key Decisions Made" in result
    assert "## Personality and Tone" in result
    assert "## Open Threads" in result
    assert "## Original System Prompt" in result
    assert "You are a strategic advisor." in result


def test_generate_knowledge_transfer_extracts_decisions():
    """KT extracts lines containing decision keywords from assistant messages."""
    from vcompany.strategist.knowledge_transfer import generate_knowledge_transfer

    messages = [
        {"role": "user", "content": "Should we use React?"},
        {"role": "assistant", "content": "I have decided that React is the best choice.\nAlso the sky is blue."},
        {"role": "user", "content": "What about the database?"},
        {"role": "assistant", "content": "Approved: use PostgreSQL. Rejected: MongoDB for this use case."},
    ]

    result = generate_knowledge_transfer(messages, "system", 100_000)

    # Should contain the decision-related lines
    assert "decided" in result.lower() or "decision" in result.lower()
    assert "approved" in result.lower()
    assert "rejected" in result.lower()


def test_generate_knowledge_transfer_personality_from_first_assistant():
    """KT extracts first assistant message as personality calibration reference."""
    from vcompany.strategist.knowledge_transfer import generate_knowledge_transfer

    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hey! Great to be working with you. Let's crush this project."},
        {"role": "user", "content": "What next?"},
        {"role": "assistant", "content": "Let's plan it out."},
    ]

    result = generate_knowledge_transfer(messages, "system", 50_000)

    assert "Hey! Great to be working with you" in result


# ---------------------------------------------------------------------------
# Tests for rough token estimate behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rough_estimate_skips_api_when_low():
    """Rough token estimate (len(text)/4) used between real API counts per Pitfall 2."""
    from vcompany.strategist.conversation import StrategistConversation

    client = make_mock_client(text_chunks=["ok"], token_count=100)
    conv = StrategistConversation(client=client)

    # Small message - rough estimate way below threshold
    async for _ in conv.send("short message"):
        pass

    # count_tokens should NOT have been called (rough estimate far below 700K)
    client.messages.count_tokens.assert_not_called()


@pytest.mark.asyncio
async def test_count_tokens_called_when_rough_estimate_high():
    """count_tokens called only when rough estimate exceeds 700K threshold."""
    from vcompany.strategist.conversation import StrategistConversation

    client = make_mock_client(text_chunks=["ok"], token_count=750_000)
    conv = StrategistConversation(client=client)

    # Seed messages to make rough estimate exceed 700K
    # 700K tokens * 4 chars/token = 2.8M chars
    big_content = "x" * 2_900_000
    conv._messages = [{"role": "user", "content": big_content}]

    async for _ in conv.send("check tokens"):
        pass

    # count_tokens should have been called
    client.messages.count_tokens.assert_called()
