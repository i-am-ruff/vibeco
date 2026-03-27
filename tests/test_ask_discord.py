"""Tests for ask_discord.py PreToolUse hook -- Discord REST API version."""

from __future__ import annotations

import ast
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Add tools/ to path so we can import ask_discord
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import ask_discord


# ---------------------------------------------------------------------------
# Fixtures / Test Data
# ---------------------------------------------------------------------------

VALID_STDIN = json.dumps(
    {
        "session_id": "sess-123",
        "hook_event_name": "PreToolUse",
        "tool_name": "AskUserQuestion",
        "tool_input": {
            "questions": [
                {
                    "question": "Which database should we use?",
                    "header": "Database",
                    "multiSelect": False,
                    "options": [
                        {"label": "PostgreSQL", "description": "Relational database"},
                        {"label": "MongoDB", "description": "Document store"},
                    ],
                }
            ]
        },
    }
)

NON_ASK_STDIN = json.dumps(
    {
        "session_id": "sess-456",
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/some/file"},
    }
)

GUILD_CHANNELS = [
    {"id": "cat-1", "name": "vco-myproject", "type": 4, "parent_id": None},
    {"id": "chan-100", "name": "agent-frontend", "type": 0, "parent_id": "cat-1"},
    {"id": "chan-200", "name": "agent-backend", "type": 0, "parent_id": "cat-1"},
    {"id": "chan-300", "name": "general", "type": 0, "parent_id": None},
]

QUESTION_MSG_RESPONSE = {"id": "msg-999", "type": 0}

REPLY_MESSAGES = [
    {
        "id": "msg-1001",
        "content": "Use PostgreSQL",
        "message_reference": {"message_id": "msg-999"},
    },
]

ESCALATION_MESSAGES = [
    {
        "id": "msg-1002",
        "content": "This has been escalated to the owner",
        "message_reference": None,
    },
]


def _mock_urlopen_factory(responses):
    """Create a mock urlopen that returns different responses per call."""
    call_count = [0]

    def mock_urlopen(req, timeout=10):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        resp = responses[idx]
        if isinstance(resp, Exception):
            raise resp
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(resp).encode("utf-8")
        mock_resp.status = 200
        mock_resp.getheader.return_value = None
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    return mock_urlopen


# ---------------------------------------------------------------------------
# test_parse_stdin_valid
# ---------------------------------------------------------------------------

def test_parse_stdin_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given valid AskUserQuestion JSON on stdin, parse returns dict with questions."""
    monkeypatch.setattr("sys.stdin", io.StringIO(VALID_STDIN))
    result = ask_discord.parse_stdin()
    assert result["tool_name"] == "AskUserQuestion"
    questions = result["tool_input"]["questions"]
    assert len(questions) == 1
    assert questions[0]["question"] == "Which database should we use?"


# ---------------------------------------------------------------------------
# test_parse_stdin_non_ask_outputs_allow
# ---------------------------------------------------------------------------

def test_parse_stdin_non_ask_outputs_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given non-AskUserQuestion tool_name, hook outputs allow JSON and exits."""
    monkeypatch.setattr("sys.stdin", io.StringIO(NON_ASK_STDIN))
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("DISCORD_GUILD_ID", "guild-1")
    monkeypatch.setenv("VCO_AGENT_ID", "test-agent")

    stdout_capture = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout_capture)

    with pytest.raises(SystemExit) as exc_info:
        ask_discord.main()

    assert exc_info.value.code == 0
    output = json.loads(stdout_capture.getvalue())
    assert output["hookSpecificOutput"]["permissionDecision"] == "allow"


# ---------------------------------------------------------------------------
# test_resolve_channel_finds_channel_by_name
# ---------------------------------------------------------------------------

def test_resolve_channel_finds_channel_by_name() -> None:
    """resolve_channel finds channel by name scoped to project category."""
    mock_urlopen = _mock_urlopen_factory([GUILD_CHANNELS])
    with patch("ask_discord.urllib.request.urlopen", mock_urlopen):
        result = ask_discord.resolve_channel(
            "fake-token", "guild-1", "frontend", "myproject"
        )
    assert result == "chan-100"


# ---------------------------------------------------------------------------
# test_resolve_channel_returns_none_when_not_found
# ---------------------------------------------------------------------------

def test_resolve_channel_returns_none_when_not_found() -> None:
    """resolve_channel returns None when channel not found."""
    mock_urlopen = _mock_urlopen_factory([GUILD_CHANNELS])
    with patch("ask_discord.urllib.request.urlopen", mock_urlopen):
        result = ask_discord.resolve_channel(
            "fake-token", "guild-1", "nonexistent", "myproject"
        )
    assert result is None


# ---------------------------------------------------------------------------
# test_post_question_sends_embed_returns_msg_id
# ---------------------------------------------------------------------------

def test_post_question_sends_embed_returns_msg_id() -> None:
    """post_question sends POST with embed and returns message_id."""
    questions = [
        {
            "question": "Pick a color",
            "options": [
                {"label": "Red", "description": "Warm color"},
                {"label": "Blue", "description": "Cool color"},
            ],
        }
    ]

    mock_urlopen = _mock_urlopen_factory([QUESTION_MSG_RESPONSE])
    with patch("ask_discord.urllib.request.urlopen", mock_urlopen):
        result = ask_discord.post_question(
            "fake-token", "chan-100", "agent-1", "req-123", questions
        )

    assert result == "msg-999"


# ---------------------------------------------------------------------------
# test_post_question_embed_format
# ---------------------------------------------------------------------------

def test_post_question_embed_format() -> None:
    """post_question embed has correct title, footer, fields, entity prefix in content."""
    questions = [
        {
            "question": "Pick a color",
            "options": [
                {"label": "Red", "description": "Warm color"},
            ],
        }
    ]

    with patch("ask_discord.urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"id": "msg-1"}).encode("utf-8")
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ask_discord.post_question(
            "fake-token", "chan-100", "agent-1", "req-123", questions
        )

    call_args = mock_urlopen.call_args
    request_obj = call_args[0][0]
    payload = json.loads(request_obj.data.decode("utf-8"))

    # Entity prefix in content
    assert "[agent-1]" in payload["content"]

    embed = payload["embeds"][0]
    assert embed["title"] == "Question from agent-1"
    assert embed["footer"]["text"] == "Request: req-123"
    assert "Red" in embed["description"]
    assert "Warm color" in embed["description"]
    assert embed["color"] == 0x3498DB


# ---------------------------------------------------------------------------
# test_poll_for_reply_finds_reply_by_message_reference
# ---------------------------------------------------------------------------

def test_poll_for_reply_finds_reply_by_message_reference() -> None:
    """poll_for_reply finds reply by message_reference.message_id match."""
    mock_urlopen = _mock_urlopen_factory([REPLY_MESSAGES])
    with patch("ask_discord.urllib.request.urlopen", mock_urlopen):
        result = ask_discord.poll_for_reply(
            "fake-token", "chan-100", "msg-999",
            poll_interval=0, max_polls=1
        )
    assert result == "Use PostgreSQL"


# ---------------------------------------------------------------------------
# test_poll_for_reply_returns_none_on_timeout
# ---------------------------------------------------------------------------

def test_poll_for_reply_returns_none_on_timeout() -> None:
    """poll_for_reply returns None on timeout (max_polls exhausted)."""
    mock_urlopen = _mock_urlopen_factory([[]])  # empty messages each time
    with patch("ask_discord.urllib.request.urlopen", mock_urlopen):
        result = ask_discord.poll_for_reply(
            "fake-token", "chan-100", "msg-999",
            poll_interval=0, max_polls=2
        )
    assert result is None


# ---------------------------------------------------------------------------
# test_poll_for_reply_detects_escalation
# ---------------------------------------------------------------------------

def test_poll_for_reply_detects_escalation() -> None:
    """poll_for_reply detects escalation marker and extends polling."""
    # First poll returns escalation message (no reply), second returns actual reply
    escalation_msg = [
        {
            "id": "msg-1002",
            "content": "This has been escalated to owner",
            "message_reference": None,
        }
    ]
    reply_msg = [
        {
            "id": "msg-1003",
            "content": "Owner says: use PostgreSQL",
            "message_reference": {"message_id": "msg-999"},
        }
    ]

    responses = [escalation_msg, reply_msg]
    mock_urlopen = _mock_urlopen_factory(responses)
    with patch("ask_discord.urllib.request.urlopen", mock_urlopen):
        result = ask_discord.poll_for_reply(
            "fake-token", "chan-100", "msg-999",
            poll_interval=0, max_polls=1  # Would timeout without escalation extension
        )
    assert result == "Owner says: use PostgreSQL"


# ---------------------------------------------------------------------------
# test_main_flow_end_to_end
# ---------------------------------------------------------------------------

def test_main_flow_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: post question, poll, get answer, output deny with answer."""
    monkeypatch.setattr("sys.stdin", io.StringIO(VALID_STDIN))
    monkeypatch.setenv("VCO_AGENT_ID", "frontend")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("DISCORD_GUILD_ID", "guild-1")
    monkeypatch.setenv("PROJECT_NAME", "myproject")

    stdout_capture = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout_capture)

    # Mock resolve_channel, post_question, poll_for_reply
    with patch.object(ask_discord, "resolve_channel", return_value="chan-100"), \
         patch.object(ask_discord, "post_question", return_value="msg-999"), \
         patch.object(ask_discord, "poll_for_reply", return_value="Use PostgreSQL"):
        with pytest.raises(SystemExit) as exc_info:
            ask_discord.main()

    assert exc_info.value.code == 0
    output = json.loads(stdout_capture.getvalue())
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "PostgreSQL" in output["hookSpecificOutput"]["permissionDecisionReason"]


# ---------------------------------------------------------------------------
# test_main_flow_timeout_fallback
# ---------------------------------------------------------------------------

def test_main_flow_timeout_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout: post question, poll exhausted, fallback answer, alert posted."""
    monkeypatch.setattr("sys.stdin", io.StringIO(VALID_STDIN))
    monkeypatch.setenv("VCO_AGENT_ID", "frontend")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("DISCORD_GUILD_ID", "guild-1")
    monkeypatch.setenv("PROJECT_NAME", "myproject")
    monkeypatch.setenv("VCO_TIMEOUT_MODE", "continue")

    stdout_capture = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout_capture)

    with patch.object(ask_discord, "resolve_channel", return_value="chan-100"), \
         patch.object(ask_discord, "post_question", return_value="msg-999"), \
         patch.object(ask_discord, "poll_for_reply", return_value=None), \
         patch.object(ask_discord, "alert_timeout") as mock_alert:
        with pytest.raises(SystemExit) as exc_info:
            ask_discord.main()

    assert exc_info.value.code == 0
    output = json.loads(stdout_capture.getvalue())
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "auto" in reason.lower() or "timeout" in reason.lower()
    mock_alert.assert_called_once()


# ---------------------------------------------------------------------------
# test_top_level_exception_handler
# ---------------------------------------------------------------------------

def test_top_level_exception_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    """Top-level exception handler produces valid JSON (never hangs)."""
    monkeypatch.setattr("sys.stdin", io.StringIO("not valid json{{{"))

    stdout_capture = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout_capture)

    # Simulate __main__ top-level handler
    with pytest.raises(SystemExit) as exc_info:
        try:
            ask_discord.main()
        except SystemExit:
            raise
        except Exception as exc:
            ask_discord.output_deny(
                f"Hook error (auto-fallback): {exc}. "
                "Proceeding with first available option."
            )

    assert exc_info.value.code == 0
    output = json.loads(stdout_capture.getvalue())
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# test_no_file_based_ipc_references
# ---------------------------------------------------------------------------

def test_no_file_based_ipc_references() -> None:
    """No references to /tmp/vco-answers or ANSWER_DIR remain in the hook."""
    script_path = Path(__file__).resolve().parent.parent / "tools" / "ask_discord.py"
    content = script_path.read_text()
    assert "vco-answers" not in content, "Found /tmp/vco-answers reference"
    assert "ANSWER_DIR" not in content, "Found ANSWER_DIR reference"
    assert "webhook_url" not in content, "Found webhook_url reference"
    assert "DISCORD_AGENT_WEBHOOK_URL" not in content, "Found DISCORD_AGENT_WEBHOOK_URL reference"


# ---------------------------------------------------------------------------
# test_no_external_imports
# ---------------------------------------------------------------------------

def test_no_external_imports() -> None:
    """ast.parse of ask_discord.py shows no imports outside stdlib."""
    script_path = Path(__file__).resolve().parent.parent / "tools" / "ask_discord.py"
    tree = ast.parse(script_path.read_text())

    stdlib_modules = {
        "sys", "json", "os", "time", "uuid", "urllib", "urllib.request",
        "urllib.error", "pathlib", "__future__",
    }

    external = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in stdlib_modules:
                    external.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module not in stdlib_modules:
                external.append(node.module)

    assert external == [], f"Found non-stdlib imports: {external}"


# ---------------------------------------------------------------------------
# test_deny_response_format
# ---------------------------------------------------------------------------

def test_deny_response_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """output_deny produces correct JSON structure."""
    stdout_capture = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout_capture)

    with pytest.raises(SystemExit) as exc_info:
        ask_discord.output_deny("Test reason")

    assert exc_info.value.code == 0
    output = json.loads(stdout_capture.getvalue())
    assert output["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert output["hookSpecificOutput"]["permissionDecisionReason"] == "Test reason"
