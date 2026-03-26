"""Tests for StrategistConversation using Claude CLI."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock helpers for subprocess (Claude CLI)
# ---------------------------------------------------------------------------


def make_mock_process(result_text: str = "Hello world", returncode: int = 0):
    """Create a mock asyncio subprocess process returning plain text result."""
    proc = AsyncMock()
    proc.returncode = returncode

    # Mock stdin
    proc.stdin = AsyncMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()

    # Mock communicate to return plain text output
    proc.communicate = AsyncMock(
        return_value=(result_text.encode(), b"")
    )

    return proc


# ---------------------------------------------------------------------------
# Tests for StrategistConversation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_yields_text_from_cli():
    """send() returns text from Claude CLI response."""
    from vcompany.strategist.conversation import StrategistConversation

    proc = make_mock_process(result_text="Hi there")

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        conv = StrategistConversation()
        result = await conv.send("Hello")

    assert result == "Hi there"


@pytest.mark.asyncio
async def test_send_yields_text_chunks():
    """send() returns text from CLI response."""
    from vcompany.strategist.conversation import StrategistConversation

    proc = make_mock_process(result_text="chunk1 chunk2 chunk3")

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        conv = StrategistConversation()
        result = await conv.send("test")

    assert result == "chunk1 chunk2 chunk3"


@pytest.mark.asyncio
async def test_session_id_reused_across_sends():
    """Session ID is reused across multiple send() calls (conversation persistence)."""
    from vcompany.strategist.conversation import StrategistConversation

    conv = StrategistConversation()
    session_id = conv.session_id

    call_count = 0
    call_args_list = []

    async def mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        call_args_list.append(args)
        # First call is resume attempt (fails), second is create, third is resume with user msg
        if call_count == 1:
            return make_mock_process(result_text="", returncode=1)
        return make_mock_process(result_text="reply")

    with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
        await conv.send("first")
        await conv.send("second")

    # All calls should reference the same session_id
    for args in call_args_list:
        found_id = None
        for flag in ("--session-id", "--resume"):
            if flag in args:
                idx = args.index(flag)
                found_id = args[idx + 1]
        assert found_id == session_id, f"Wrong session ID in {args}"


@pytest.mark.asyncio
async def test_first_send_loads_persona_as_message():
    """First send() sends persona as first message, not --system-prompt."""
    from vcompany.strategist.conversation import StrategistConversation

    call_count = 0
    stdin_contents = []

    async def mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        proc = make_mock_process(result_text="ok")
        original_communicate = proc.communicate

        async def capture_communicate(input=None):
            if input:
                stdin_contents.append(input.decode())
            return await original_communicate(input=input)

        proc.communicate = capture_communicate
        # First call: resume fails (no existing session)
        if call_count == 1:
            return make_mock_process(result_text="", returncode=1)
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
        conv = StrategistConversation()
        await conv.send("hello")

    # No --system-prompt flag in any call
    # (persona is sent as stdin content, not as a CLI flag)
    # call_count should be 3: resume(fail), create(persona), resume(hello)
    assert call_count == 3


@pytest.mark.asyncio
async def test_asyncio_lock_prevents_concurrent_sends():
    """asyncio.Lock prevents concurrent send() calls (second call waits)."""
    from vcompany.strategist.conversation import StrategistConversation

    execution_order = []

    async def slow_exec(*args, **kwargs):
        proc = AsyncMock()
        proc.returncode = 0
        proc.stdin = AsyncMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdin.close = MagicMock()

        label = "1" if len(execution_order) == 0 else "2"
        execution_order.append(f"start-{label}")

        async def slow_communicate(input=None):
            await asyncio.sleep(0.05)
            execution_order.append(f"end-{label}")
            return (f"response-{label}".encode(), b"")

        proc.communicate = slow_communicate
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=slow_exec):
        conv = StrategistConversation()

        async def send_msg(content):
            await conv.send(content)

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
    conv = StrategistConversation(persona_path=nonexistent)

    assert conv._system_prompt == DEFAULT_PERSONA


@pytest.mark.asyncio
async def test_persona_loaded_from_file(tmp_path: Path):
    """Persona loaded from file when it exists."""
    from vcompany.strategist.conversation import StrategistConversation

    persona_file = tmp_path / "STRATEGIST-PERSONA.md"
    persona_file.write_text("You are a genius CEO.")
    conv = StrategistConversation(persona_path=persona_file)

    assert conv._system_prompt == "You are a genius CEO."


@pytest.mark.asyncio
async def test_cli_error_yields_error_message():
    """CLI error (non-zero exit) returns an error message."""
    from vcompany.strategist.conversation import StrategistConversation

    proc = make_mock_process(returncode=1)
    proc.communicate = AsyncMock(return_value=(b"", b"error"))

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        conv = StrategistConversation()
        result = await conv.send("test")

    assert "error" in result.lower() or "snag" in result.lower()


# ---------------------------------------------------------------------------
# Tests for generate_knowledge_transfer (unchanged, no Anthropic dependency)
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
