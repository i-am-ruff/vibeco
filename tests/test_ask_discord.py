"""Tests for ask_discord.py PreToolUse hook."""

from __future__ import annotations

import ast
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add tools/ to path so we can import ask_discord
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import ask_discord


# ---------------------------------------------------------------------------
# Fixtures
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
# test_parse_stdin_non_ask
# ---------------------------------------------------------------------------

def test_parse_stdin_non_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given non-AskUserQuestion tool_name, hook outputs allow JSON and exits."""
    monkeypatch.setattr("sys.stdin", io.StringIO(NON_ASK_STDIN))
    monkeypatch.setenv("DISCORD_AGENT_WEBHOOK_URL", "")
    monkeypatch.setenv("VCO_AGENT_ID", "test-agent")

    stdout_capture = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout_capture)

    with pytest.raises(SystemExit) as exc_info:
        ask_discord.main()

    assert exc_info.value.code == 0
    output = json.loads(stdout_capture.getvalue())
    assert output["hookSpecificOutput"]["permissionDecision"] == "allow"


# ---------------------------------------------------------------------------
# test_parse_stdin_malformed
# ---------------------------------------------------------------------------

def test_parse_stdin_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given malformed JSON on stdin, hook outputs deny with error fallback."""
    monkeypatch.setattr("sys.stdin", io.StringIO("not valid json{{{"))

    stdout_capture = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout_capture)

    # parse_stdin should raise, and the top-level handler produces deny
    with pytest.raises(SystemExit) as exc_info:
        ask_discord.main()

    assert exc_info.value.code == 0
    output = json.loads(stdout_capture.getvalue())
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "error" in output["hookSpecificOutput"]["permissionDecisionReason"].lower() or \
           "fallback" in output["hookSpecificOutput"]["permissionDecisionReason"].lower()


# ---------------------------------------------------------------------------
# test_post_webhook_success
# ---------------------------------------------------------------------------

def test_post_webhook_success() -> None:
    """Given valid webhook URL, POST sends JSON with embed containing agent info."""
    questions = [
        {
            "question": "Pick a color",
            "options": [
                {"label": "Red", "description": "Warm color"},
                {"label": "Blue", "description": "Cool color"},
            ],
        }
    ]

    with patch("ask_discord.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        ask_discord.post_question(
            "https://discord.com/api/webhooks/test",
            "agent-1",
            "req-123",
            questions,
        )

    mock_urlopen.assert_called_once()
    call_args = mock_urlopen.call_args
    request_obj = call_args[0][0]
    payload = json.loads(request_obj.data.decode("utf-8"))
    embed = payload["embeds"][0]
    assert "agent-1" in embed["title"]
    assert embed["description"] == "Pick a color"
    assert len(embed["fields"]) == 2
    assert embed["footer"]["text"] == "Request: req-123"
    assert embed["color"] == 0x3498DB


# ---------------------------------------------------------------------------
# test_post_webhook_failure
# ---------------------------------------------------------------------------

def test_post_webhook_failure() -> None:
    """Given unreachable webhook URL, post_question raises."""
    import urllib.error

    questions = [{"question": "Test?", "options": []}]

    with patch("ask_discord.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        with pytest.raises(urllib.error.URLError):
            ask_discord.post_question(
                "https://bad-url.example.com/webhook",
                "agent-1",
                "req-456",
                questions,
            )


# ---------------------------------------------------------------------------
# test_poll_answer_found
# ---------------------------------------------------------------------------

def test_poll_answer_found(tmp_path: Path) -> None:
    """Given answer file exists, poll returns answer text and deletes file."""
    request_id = "test-req-found"
    answer_dir = tmp_path / "vco-answers"
    answer_dir.mkdir()
    answer_file = answer_dir / f"{request_id}.json"
    answer_file.write_text(json.dumps({"answer": "PostgreSQL"}))

    with patch.object(ask_discord, "ANSWER_DIR", answer_dir):
        result = ask_discord.poll_answer(request_id, poll_interval=0, max_polls=1)

    assert result == "PostgreSQL"
    assert not answer_file.exists(), "Answer file should be deleted after reading"


# ---------------------------------------------------------------------------
# test_poll_answer_timeout_continue
# ---------------------------------------------------------------------------

def test_poll_answer_timeout_continue() -> None:
    """Given no answer after polling, continue mode returns first option with note."""
    questions = [
        {
            "question": "Pick one",
            "options": [
                {"label": "Option A", "description": "First option"},
                {"label": "Option B", "description": "Second option"},
            ],
        }
    ]
    result = ask_discord.get_fallback_answer(questions, "continue")
    assert "Option A" in result
    assert "auto" in result.lower() or "timeout" in result.lower()


# ---------------------------------------------------------------------------
# test_poll_answer_timeout_block
# ---------------------------------------------------------------------------

def test_poll_answer_timeout_block() -> None:
    """Given no answer after polling, block mode returns block message."""
    questions = [
        {
            "question": "Pick one",
            "options": [{"label": "X", "description": "Y"}],
        }
    ]
    result = ask_discord.get_fallback_answer(questions, "block")
    assert "BLOCKED" in result or "block" in result.lower()
    assert "wait" in result.lower()


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


# ---------------------------------------------------------------------------
# test_error_fallback
# ---------------------------------------------------------------------------

def test_error_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any exception in main() caught by top-level handler, produces valid deny JSON."""
    # Make parse_stdin raise an unexpected error
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    stdout_capture = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout_capture)

    # Simulate what happens at __main__ level
    try:
        ask_discord.main()
    except SystemExit:
        pass

    output = json.loads(stdout_capture.getvalue())
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


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
# test_cleanup_answer_file
# ---------------------------------------------------------------------------

def test_cleanup_answer_file(tmp_path: Path) -> None:
    """After reading answer file, hook deletes it."""
    request_id = "test-req-cleanup"
    answer_dir = tmp_path / "vco-answers"
    answer_dir.mkdir()
    answer_file = answer_dir / f"{request_id}.json"
    answer_file.write_text(json.dumps({"answer": "Cleaned up"}))

    with patch.object(ask_discord, "ANSWER_DIR", answer_dir):
        result = ask_discord.poll_answer(request_id, poll_interval=0, max_polls=1)

    assert result == "Cleaned up"
    assert not answer_file.exists()
